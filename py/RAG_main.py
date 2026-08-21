import subprocess
import time
import urllib.request
import urllib.error

from llm import LLM_query, LLM_query_stream, LLM_tool_call
import prompts
from json_search import load_universities
from vector_search import search_all_universities, named_universities
import models
import tools

OLLAMA_URL = models.OLLAMA_URL

def ensure_ollama_running(timeout: int = 30) -> None:
    """
    Makes sure the Ollama server is up before we start querying it.
    Opens the Ollama app (which starts its background server) if it isn't already running.
    """
    try:
        urllib.request.urlopen(OLLAMA_URL, timeout=1)
        return # already running
    except (urllib.error.URLError, OSError):
        pass

    print("Ollama not running, starting it...")
    subprocess.Popen(["open", "-a", "Ollama"])

    for _ in range(timeout):
        try:
            urllib.request.urlopen(OLLAMA_URL, timeout=1)
            print("Ollama is up.")
            return
        except (urllib.error.URLError, OSError):
            time.sleep(1)

    raise RuntimeError(f"Ollama did not start within {timeout} seconds.")

KNOWN_UNIVERSITIES = ["University of Liverpool", "University of York", "University of Leeds",
    "University of Manchester", "Newcastle University",
    "University of Sheffield", "University of Nottingham",
    "University of Lancaster",]

def qualification_context(qualifications_data: dict) -> str:
    """
    Formats the qualification records as text.
    Args:
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

    return context

def vector_search_context(vector_search_results: dict[str, list[dict]]) -> str:
    """
    Formats the vector search results as text.
    Args:
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

    return str_for_llm

def answer_qualification_constuct(user_query: str, qualifications_data: dict) -> str:
    """
    Constructs the context for answering qualification-related questions.
    Args:
        user_query (str): The user's query.
        qualifications_data (dict): Qualification records for the relevant universities retrieved from JSON files.
    """
    context = qualification_context(qualifications_data)

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
    str_for_llm = vector_search_context(vector_search_results)

    user_content = f"""STAFF QUESTION: {user_query}

    VECTOR SEARCH RESULTS:{str_for_llm}"""
    return user_content

def answer_combined_construct(user_query: str, qualifications_data: dict, vector_search_results: dict) -> str:
    """
    Constructs the context when the model asked for BOTH tools - an entry question that
    also asks about something we hold in the knowledge base. The question is stated once
    and both bodies of evidence follow it, so the answerer can see it has to cover both.
    Args:
        user_query (str): The user's query.
        qualifications_data (dict): Qualification records, as returned by the entry-requirements tool.
        vector_search_results (dict): university name -> list of results.
    """
    records = qualification_context(qualifications_data)
    searched = vector_search_context(vector_search_results)

    user_content = f"""STAFF QUESTION: {user_query}

    UNIVERSITY RECORDS:{records}

    VECTOR SEARCH RESULTS:{searched}"""
    return user_content

def generate_query_or_respond(user_query: str) -> tuple[list, str]:
    """
    The agent node. Given the question, the model either answers it directly or asks
    for retrieval by calling a tool - and it writes the search query itself, so this
    one call does the work the ROUTER, REWRITER and SOURCE_TYPE_ROUTER used to do in
    three. Retrieval runs only when the model requests it.

    Returns:
        (calls, text). calls is a list of (tool_name, arguments); empty means the model
        answered without retrieving, and text is that answer.
    """
    return LLM_tool_call(tools.AGENT, user_query, tools.TOOLS, model=models.LOW_EFFORT)


def retrieve(calls: list, user_query: str) -> tuple[str, str]:
    """
    Runs every tool the model asked for and builds the input for the answering LLM.

    A question can be both things at once - what grades does she need AND what will she
    study in year 1 - so the model may ask for both tools, and both results go to the
    answerer together.

    Args:
        calls (list): (tool_name, arguments) pairs from the agent node.
        user_query (str): what the staff member typed.
    Returns:
        (system_prompt, user_content) for the answering LLM.
    """
    qualifications_data = None
    vector_search_results = None

    for name, arguments in calls:
        kind, payload = tools.run(name, arguments, user_query)
        if kind == "requirement":
            qualifications_data = payload
        else:
            vector_search_results = payload

    if qualifications_data is not None and vector_search_results is not None:
        prompting = answer_combined_construct(user_query, qualifications_data, vector_search_results)
        # the knowledge base is the harder half to answer from, so its rules apply
        return prompts.GENERAL_ANSWERER, prompting

    if qualifications_data is not None:
        return prompts.ANSWERER, answer_qualification_constuct(user_query, qualifications_data)

    return prompts.GENERAL_ANSWERER, answer_vector_search_construct(user_query, vector_search_results)


def classification_route(user_query: str) -> tuple[str | None, str]:
    """
    The routing we used before tool calling: three prompts that each classify or rewrite,
    one after another. Still the path for models.PROVIDER == "ollama", because a 9b local
    model picks a category word far more reliably than it fills in tool arguments.
    """
    original_query = user_query

    category = LLM_query(prompts.ROUTER, original_query, model=models.LOW_EFFORT, deterministic=True).message.content.strip() # route the query to either requirement or general
    if category not in {"requirement", "general", "unclear"}: #if category is not one of the three known categories default to unclear
        category = "unclear"

    # route to JSON data for accuracy
    if category == "requirement":
        universities = named_universities(original_query) # regex to find the universities mentioned in the user query
        qualifications_data = load_universities(universities) # load the qualification records for the universities mentioned in the user query
        prompting = answer_qualification_constuct(original_query, qualifications_data)
        return prompts.ANSWERER, prompting

    #route to vector database similarity search
    elif category == "general":

        # rewritten for the EMBEDDING only. the original query still drives university
        # detection, module codes, years and semesters, so nothing else is affected.
        user_query = LLM_query(prompts.REWRITER, original_query, model=models.LOW_EFFORT, deterministic=True).message.content.strip()
        print(f"Rewritten query: {user_query}")

        # do sub routing
        source_type = LLM_query(prompts.SOURCE_TYPE_ROUTER, original_query, model=models.LOW_EFFORT, deterministic=True).message.content.strip() # detect what type of source it is (module, course_info, guild, scholarship, fee, general)
        print(source_type)
        if source_type not in {"module", "course_info", "guild", "scholarship", "fee", "general"}:
            source_type = "general" # if source type is not one of the known types, default to general

        vector_search_results = search_all_universities(original_query, user_query, source_type, n_results=20) # university name -> list of results
        prompting = answer_vector_search_construct(original_query, vector_search_results) # include search results in the query
        return prompts.GENERAL_ANSWERER, prompting

    else:
        return "You are a helpful assistant at the University of Liverpool.", user_query


def route_and_build(user_query: str) -> tuple[str | None, str]:
    """
    Decides what the answering LLM is given, and builds it.

    Everything here needs a complete string to work with (the model reads the whole
    question, the retrieval filters on the text), so this all happens before any answer
    is written.

    Returns:
        (system_prompt, user_content). system_prompt is None when there is nothing to
        answer from, so user_content is the message to show instead.
    """
    # check for empty query and return a message if so
    if not user_query or not user_query.strip():
        return None, "No question was entered."

    if models.PROVIDER != "openai":
        return classification_route(user_query)

    calls, _direct_answer = generate_query_or_respond(user_query)

    # no tool call means there is nothing to retrieve - a fragment like "notts?" that
    # needs a question put back to the staff member rather than a search. the agent node
    # writes with no reasoning budget, and its clarifying questions came out noticeably
    # blunter than the answering model's, so the fragment is handed on to be answered
    # properly. rare enough that it costs nothing on a normal question.
    if not calls:
        return "You are a helpful assistant at the University of Liverpool.", user_query

    return retrieve(calls, user_query)


def main(user_query: str) -> str:
    """Answers the query and returns the whole answer at once."""
    # system_prompt = instruction for LLM, prompting = the user query with context (result from search) for LLM to answer
    system_prompt, prompting = route_and_build(user_query)
    if system_prompt is None:
        return prompting
    return LLM_query(system_prompt, prompting, model=models.HIGH_EFFORT).message.content


def main_stream(user_query: str):
    """
    Same as main(), but yields the answer in pieces as the model writes it.

    Routing and retrieval still run first, so nothing is yielded until the answer
    itself starts - that is the short pause before the text begins appearing.

    Yields:
        str: the next piece of the answer
    """
    system_prompt, prompting = route_and_build(user_query)
    if system_prompt is None:
        yield prompting
        return
    yield from LLM_query_stream(system_prompt, prompting, model=models.HIGH_EFFORT)


if __name__ == "__main__":
    ensure_ollama_running()
    user_query = input("Enter your query: ").strip()
    while not user_query:   # a stray newline from pasting submits an empty line
        user_query = input("Enter your query: ").strip()
    for piece in main_stream(user_query):   # printed as it arrives instead of all at the end
        print(piece, end="", flush=True)
    print()