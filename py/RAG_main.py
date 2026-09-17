import subprocess
import sys
import time
import urllib.request
import urllib.error

from llm import LLM_query, LLM_query_stream
import prompts
from json_search import load_universities
from vector_search import search_all_universities
from universities import named_universities
from sources import (
    correct_citations,
    passage_source,
    passage_texts,
    requirements_source,
    source_number,
    sources_footer,
    strip_sources,
)
import models

OLLAMA_URL = models.OLLAMA_URL

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  
    pass

# How many earlier turns are shown to the condenser. Only the recent ones
MAX_HISTORY_TURNS = 6

# How many passages are retrieved for each university named in the question
N_RESULTS = 20

def start_ollama() -> None:
    """Starts the Ollama server in the background, on macOS, Windows or Linux."""
    if sys.platform == "darwin":
        # on macOS the app starts its own background server
        command, detach = ["open", "-a", "Ollama"], {}
    elif sys.platform == "win32":
        # its own process group, so Ctrl+C here does not stop Ollama too, and no console window
        command = ["ollama", "serve"]
        detach = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    else:
        command, detach = ["ollama", "serve"], {"start_new_session": True}

    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **detach)
    except FileNotFoundError:
        raise RuntimeError("Ollama is not installed, or the ollama command is not on PATH.") from None


def ensure_ollama_running(timeout: int = 30) -> None:
    """
    Makes sure the Ollama server is up before we start querying it.
    Starts it if it isn't already running.
    """
    try:
        urllib.request.urlopen(OLLAMA_URL, timeout=1)
        return # already running
    except (urllib.error.URLError, OSError):
        pass

    print("Ollama not running, starting it...")
    start_ollama()

    for _ in range(timeout):
        try:
            urllib.request.urlopen(OLLAMA_URL, timeout=1)
            print("Ollama is up.")
            return
        except (urllib.error.URLError, OSError):
            time.sleep(1)

    raise RuntimeError(f"Ollama did not start within {timeout} seconds.")

def answer_qualification_construct(user_query: str, qualifications_data: dict) -> tuple[str, list]:
    """
    Constructs the context for answering qualification-related questions.
    data + query and then pass to LLM.
    Args:
        user_query (str): The user's query.
        qualifications_data (dict): Qualification records for the relevant universities retrieved from JSON files.

    Returns:
        (user_content, sources). each record is numbered [n] in user_content so the
        answerer can cite it - one university's records share a number, as they come
        from one page - and sources[n - 1] is what [n] refers to.
    """
    SKIP_FIELDS = {"id", "university", "course", "headline_grade", "additional_conditions"}
    
    context = ""

    sources = []
    for uni, rows in qualifications_data.items():
        context += f"\n=== {uni} ===\n"
        for r in rows:
            context += f"[{source_number(sources, *requirements_source(uni))}]\n"
            for k, v in r.items():
                if k in SKIP_FIELDS or v is None: # strip nulls — most fields are null most of the time
                    continue
                context += f"  {k}: {v}\n"
            context += "\n"

    user_content = f"""STAFF QUESTION: {user_query}

    UNIVERSITY RECORDS:{context}"""
    return user_content, sources

def answer_vector_search_construct(user_query: str, vector_search_results: dict[str, list[dict]]) -> tuple[str, list]:
    """
    Constructs the context for answering general questions using vector search results.
    Args:
        user_query (str): The user's query.
        vector_search_results (dict): university name -> list of results with "distance", "source_type", "document" and "metadata".

    Returns:
        (user_content, sources). each passage is numbered [n] in user_content so the
        answerer can cite it; passages from the same page share a number, and
        sources[n - 1] is what [n] refers to.
    """
    str_for_llm = ""
    sources = []
    # header per university so the answerer can tell whose fact is whose and never merge them
    for university, results in vector_search_results.items():
        str_for_llm += f"\n=== {university} ===\n"

        if not results:
            str_for_llm += "We hold no information about this university." + "\n"
            continue

        for result in results:
            n = source_number(sources, *passage_source(result["metadata"]))
            str_for_llm += f"[{n}] {result['document']}\n\n"

    user_content = f"""STAFF QUESTION: {user_query}

    VECTOR SEARCH RESULTS:{str_for_llm}"""
    return user_content, sources

def route_and_build(user_query: str, history: str = "") -> tuple[str | None, str, list]:
    """
    Routes the query and builds the input for the answering LLM.

    Args:
        user_query (str): what the staff member just typed.
        history (str): the earlier turns, "role: text" one per line. Empty on the
            first question, which is why most queries never pay for the condenser.

    Returns:
        (system_prompt, query_with_context, sources). system_prompt is None when no
        question was entered - there is nothing to answer, so query_with_context is the
        message to show instead. sources[n - 1] is what the answer's [n] cites; it is
        empty when nothing was retrieved.
    """
    # check for empty query
    if not user_query or not user_query.strip():
        return None, "No question was entered.", []

    # if there is a history, condense it to a single query. the condensed query is what drives
    # routing, university detection and vector search from here on; user_query stays as typed.
    routing_query = user_query
    if history:
        routing_query = LLM_query(
            prompts.CONDENSER,
            f"CONVERSATION SO FAR:\n{history}\n\nLATEST MESSAGE: {user_query}",
            model=models.LOW_EFFORT,
            deterministic=True,
        ).message.content.strip()
        print(f"Condensed query: {routing_query}")

    category = LLM_query(prompts.ROUTER, routing_query, model=models.LOW_EFFORT, deterministic=True).message.content.strip() # route the query to either requirement or general
    if category not in {"requirement", "general", "unclear"}: #if category is not one of the three known categories default to unclear
        category = "unclear"

    # route to JSON data for accuracy
    if category == "requirement":
        universities = named_universities(routing_query) # regex to find the universities mentioned in the user query
        qualifications_data = load_universities(universities) # load the qualification records for the universities mentioned in the user query
        query_with_context, sources = answer_qualification_construct(routing_query, qualifications_data)
        return prompts.REQUIREMENT_ANSWERER, query_with_context, sources

    #route to vector database similarity search
    elif category == "general":

        # rewritten for the EMBEDDING only. the routing query still drives university detection.
        embedding_query = LLM_query(prompts.REWRITER_LONG, routing_query, model=models.LOW_EFFORT, deterministic=True).message.content.strip()
        print(f"Rewritten query: {embedding_query}") # for debugging

        # pass to the vector search with regex for module code, scholarship or society wording, year/semester/credits for more accurate results.
        vector_search_results = search_all_universities(routing_query, embedding_query, n_results=N_RESULTS) # university name -> list of results
        query_with_context, sources = answer_vector_search_construct(routing_query, vector_search_results) # include search results in the query
        return prompts.GENERAL_ANSWERER, query_with_context, sources

    else:
        return "You are a helpful assistant at the University of Liverpool.", routing_query, []

def main(user_query: str, history: str = "") -> str:
    """Answers the query and returns the whole answer at once, sources list included."""
    system_prompt, query_with_context, sources = route_and_build(user_query, history)
    if system_prompt is None:
        return query_with_context
    answer = LLM_query(system_prompt, query_with_context, model=models.HIGH_EFFORT).message.content
    texts = passage_texts(query_with_context)
    answer = "\n".join(correct_citations(line, texts) for line in answer.split("\n"))
    return answer + sources_footer(answer, sources)


def main_stream(user_query: str, history: str = ""):
    """
    Same as main(), but yields the answer in pieces as the model writes it.

    Routing and retrieval still run first, so nothing is yielded until the answer
    itself starts - that is the short pause before the text begins appearing.

    The sources list comes last, as one final piece: which sources the answer cites
    is only known once the whole answer has been written.

    Each line's citations are checked (correct_citations) before they are shown, so a
    line streams up to its first "[" and the rest follows once the line is finished.

    Yields:
        str: the next piece of the answer
    """
    system_prompt, query_with_context, sources = route_and_build(user_query, history)
    if system_prompt is None:
        yield query_with_context
        return

    texts = passage_texts(query_with_context)
    answer = ""
    line, shown = "", 0  # the line being written, and how much of it has been yielded
    for piece in LLM_query_stream(system_prompt, query_with_context, model=models.HIGH_EFFORT):
        line += piece
        while "\n" in line:
            finished, line = line.split("\n", 1)
            finished = correct_citations(finished, texts) + "\n"
            yield finished[shown:]  # the check only rewrites citations, so what was shown is unchanged
            answer += finished
            shown = 0
        hold = line.find("[", shown)
        cut = len(line) if hold == -1 else hold
        if cut > shown:
            yield line[shown:cut]
            shown = cut

    if line:
        line = correct_citations(line, texts)
        yield line[shown:]
        answer += line

    footer = sources_footer(answer, sources)
    if footer:
        yield footer


if __name__ == "__main__":
    ensure_ollama_running()
    turns = []   # "role: text" lines, the same shape the API builds

    while True:
        user_query = input("\nEnter your query: ").strip()
        if not user_query:   # a stray newline from pasting submits an empty line
            continue

        answer = ""
        for piece in main_stream(user_query, "\n".join(turns[-MAX_HISTORY_TURNS:])):
            print(piece, end="", flush=True)   # printed as it arrives instead of all at the end
            answer += piece
        print()

        turns += [f"user: {user_query}", f"assistant: {strip_sources(answer)}"]  # what was said, not the citations