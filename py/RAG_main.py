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

def answer_qualification_construct(user_query: str, qualifications_data: dict) -> str:
    """
    Constructs the context for answering qualification-related questions.
    data + query and then pass to LLM.
    Args:
        user_query (str): The user's query.
        qualifications_data (dict): Qualification records for the relevant universities retrieved from JSON files.
    """
    SKIP_FIELDS = {"id", "university", "course", "headline_grade", "additional_conditions"}
    
    context = ""

    for uni, rows in qualifications_data.items():
        context += f"\n=== {uni} ===\n"
        for r in rows:
            for k, v in r.items():
                if k in SKIP_FIELDS or v is None: # strip nulls — most fields are null most of the time
                    continue
                context += f"  {k}: {v}\n"
            context += "\n"

    user_content = f"""STAFF QUESTION: {user_query}

    UNIVERSITY RECORDS:{context}"""
    return user_content

def answer_vector_search_construct(user_query: str, vector_search_results: dict[str, list[dict]]) -> str:
    """
    Constructs the context for answering general questions using vector search results.
    Args:
        user_query (str): The user's query.
        vector_search_results (dict): university name -> list of results with "distance", "source_type", and "document".
    """
    str_for_llm = ""
    # header per university so the answerer can tell whose fact is whose and never merge them
    for university, results in vector_search_results.items():
        str_for_llm += f"\n=== {university} ===\n"

        if not results:
            str_for_llm += "We hold no information about this university." + "\n"
            continue

        for result in results:
            str_for_llm += result["document"] + "\n\n"

    user_content = f"""STAFF QUESTION: {user_query}

    VECTOR SEARCH RESULTS:{str_for_llm}"""
    return user_content

def route_and_build(user_query: str, history: str = "") -> tuple[str | None, str]:
    """
    Routes the query and builds the input for the answering LLM.

    Args:
        user_query (str): what the staff member just typed.
        history (str): the earlier turns, "role: text" one per line. Empty on the
            first question, which is why most queries never pay for the condenser.

    Returns:
        (system_prompt, query_with_context). system_prompt is None when the query is
        unclear - there is nothing to answer from, so query_with_context is the message
        to show instead.
    """
    # check for empty query
    if not user_query or not user_query.strip():
        return None, "No question was entered."

    # if there is a history, condense it to a single query for the rewriter. the original query is still used for routing and vector search.
    if history:
        user_query = LLM_query(
            prompts.CONDENSER,
            f"CONVERSATION SO FAR:\n{history}\n\nLATEST MESSAGE: {user_query}",
            model=models.LOW_EFFORT,
            deterministic=True,
        ).message.content.strip()
        print(f"Condensed query: {user_query}")

    original_query = user_query # user_query for rewriter

    category = LLM_query(prompts.ROUTER, original_query, model=models.LOW_EFFORT, deterministic=True).message.content.strip() # route the query to either requirement or general
    if category not in {"requirement", "general", "unclear"}: #if category is not one of the three known categories default to unclear
        category = "unclear"

    # route to JSON data for accuracy
    if category == "requirement":
        universities = named_universities(original_query) # regex to find the universities mentioned in the user query
        qualifications_data = load_universities(universities) # load the qualification records for the universities mentioned in the user query
        query_with_context = answer_qualification_construct(original_query, qualifications_data)
        return prompts.ANSWERER, query_with_context

    #route to vector database similarity search
    elif category == "general":

        # rewritten for the EMBEDDING only. the original query still drives university
        user_query = LLM_query(prompts.REWRITER_LONG, original_query, model=models.LOW_EFFORT, deterministic=True).message.content.strip()
        print(f"Rewritten query: {user_query}")

        # pass to the vector search with regex for module code, scholarship or society wording, year/semester/credits for more accurate results.
        vector_search_results = search_all_universities(original_query, user_query, n_results=N_RESULTS) # university name -> list of results
        query_with_context = answer_vector_search_construct(original_query, vector_search_results) # include search results in the query
        return prompts.GENERAL_ANSWERER, query_with_context

    else:
        return "You are a helpful assistant at the University of Liverpool.", user_query

def main(user_query: str, history: str = "") -> str:
    """Answers the query and returns the whole answer at once."""
    # system_prompt = instruction for LLM, query_with_context = the user query with context (result from search) for LLM to answer
    system_prompt, query_with_context = route_and_build(user_query, history)
    if system_prompt is None:
        return query_with_context
    return LLM_query(system_prompt, query_with_context, model=models.HIGH_EFFORT).message.content


def main_stream(user_query: str, history: str = ""):
    """
    Same as main(), but yields the answer in pieces as the model writes it.

    Routing and retrieval still run first, so nothing is yielded until the answer
    itself starts - that is the short pause before the text begins appearing.

    Yields:
        str: the next piece of the answer
    """
    system_prompt, query_with_context = route_and_build(user_query, history)
    if system_prompt is None:
        yield query_with_context
        return
    yield from LLM_query_stream(system_prompt, query_with_context, model=models.HIGH_EFFORT)


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

        turns += [f"user: {user_query}", f"assistant: {answer}"]