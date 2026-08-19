import subprocess
import time
import urllib.request
import urllib.error

from llm import LLM_query, LLM_query_stream
import prompts
from json_search import load_universities
from vector_search import vector_similarity_search
import models
import json

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

def query_to_json(prompt, query, model) -> dict:
    """
    Queries the LLM with the given prompt, and returns the parsed JSON response.

    This only for query that we expect to return a JSON such as extractor and router. For other queries, use LLM_query directly.
    """
    response = LLM_query(prompt, query, model=model).message.content
    try:
        response = json.loads(response)
    except json.JSONDecodeError:
        response = {}
    return response

def extract_metadata(user_query) -> dict:
    """
    Extracts metadata from the user query and adds the University of Liverpool if not present.
    """
    data = query_to_json(prompts.EXTRACTOR, user_query, model=models.LOW_EFFORT) # extracted qualification and university information mentioned from the user query
    unis = data.get("universities") or []

    #insert University of Liverpool because this is from University of Liverpool staff and we want to compare against it.
    if "University of Liverpool" not in unis:
        unis.insert(0, "University of Liverpool")

    return {
        "universities": unis,
        "student_grades": data.get("student_grades") or "",
        "qualification_type": data.get("qualification_type") or ""
    }

def answer_qualification_constuct(user_query: str, extracted_meta: dict, qualifications_data: dict) -> str:
    """
    Constructs the context for answering qualification-related questions.
    Args:
        user_query (str): The user's query.
        extracted_meta (dict): example -> {"universities": ["University of Liverpool", "University of York"], "student_grades": "2:1", "qualification_type": "BSc Computer Science"}
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

    STUDENT GRADES: {extracted_meta.get('student_grades') or "(not stated)"}

    UNIVERSITY RECORDS:{context}"""
    return user_content

def answer_vector_search_construct(user_query: str, vector_search_results: list[dict]) -> str:
    """
    Constructs the context for answering general questions using vector search results.
    Args:
        user_query (str): The user's query.
        vector_search_results (list[dict]): List of search results, each containing "distance", "source_type", and "document".
    """
    str_for_llm = ""
    for vector_search_result in vector_search_results:
        str_for_llm += vector_search_result["document"] + "\n\n"

    user_content = f"""STAFF QUESTION: {user_query}

    VECTOR SEARCH RESULTS:{str_for_llm}"""
    return user_content

def route_and_build(user_query: str) -> tuple[str | None, str]:
    """
    Routes the query and builds the input for the answering LLM.

    Everything here needs a complete string to work with (the routers classify, the
    retrieval filters on the text), so this all happens before any answer is written.

    Returns:
        (system_prompt, user_content). system_prompt is None when the query is
        unclear - there is nothing to answer from, so user_content is the message
        to show instead.
    """
    original_query = user_query

    # check for empty query and return a message if so
    if not user_query or not user_query.strip():
        return None, "No question was entered."

    category = LLM_query(prompts.ROUTER, original_query, model=models.LOW_EFFORT).message.content.strip() # route the query to either requirement or general
    if category not in {"requirement", "general", "unclear"}: #if category is not one of the three known categories default to unclear
        category = "unclear"

    # route to JSON data for accuracy
    if category == "requirement":
        metadata = extract_metadata(original_query) # handle requirement questions
        qualifications_data = load_universities(metadata["universities"]) # load the qualification records for the universities mentioned in the user query
        prompting = answer_qualification_constuct(original_query, metadata, qualifications_data)
        return prompts.ANSWERER, prompting

    #route to vector database similarity search
    elif category == "general":
        #user_query = LLM_query(prompts.REWRITER, original_query, model=models.LOW_EFFORT).message.content #rewrite the user query for better retrieval
        #print(f"Rewritten query: {user_query}")

        # do sub routing for soruce type (module, course_info, guild, scholarship, fee, general) and then do vector search for each source type and combine the results
        source_type = LLM_query(prompts.SOURCE_TYPE_ROUTER, original_query, model=models.LOW_EFFORT).message.content.strip() # detect what type of source it is (module, course_info, guild, scholarship, fee, general)
        print(source_type)
        if source_type not in {"module", "course_info", "guild", "scholarship", "fee", "general"}:
            source_type = "general" # if source type is not one of the known types, default to general
        vector_search_results = vector_similarity_search(original_query, user_query, source_type, n_results=20) # get a search result as a list of dicts with keys "distance", "source_type", and "document"
        prompting = answer_vector_search_construct(original_query, vector_search_results) # include search results in the query
        return prompts.GENERAL_ANSWERER, prompting

    else:
        return "You act as a helpful assistant at the University of Liverpool. Ask the user to explain more about their query if it is unclear", user_query


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