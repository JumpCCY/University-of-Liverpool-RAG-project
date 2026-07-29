from llm import LLM_query
import prompts
import json
from json_search import load_universities
from vector_search import vector_similarity_search

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
    data = query_to_json(prompts.EXTRACTOR, user_query, model="qwen3.6:27b") # extracted qualification and university information mentioned from the user query
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

def main(user_query: str) -> str:
    original_query = user_query
    router = query_to_json(prompts.ROUTER, original_query, model="qwen3.6:27b") # detect what type of question it is (requirement, general, unclear)

    category = router.get("category", "unclear") # get category from dict if not present default to unclear
    if category not in {"requirement", "general", "unclear"}: #if category is not one of the three known categories default to unclear
        category = "unclear"

    # route to JSON data for accuracy
    if category == "requirement":
        metadata = extract_metadata(original_query) # handle requirement questions
        qualifications_data = load_universities(metadata["universities"]) # load the qualification records for the universities mentioned in the user query
        prompting = answer_qualification_constuct(original_query, metadata, qualifications_data)
        answer = LLM_query(prompts.ANSWERER, prompting, model="qwen3.6:27b").message.content # construct the context and query the LLM for an answer
        return answer

    #route to vector database similarity search
    elif category == "general":
        user_query = LLM_query(prompts.REWRITER, original_query, model="qwen3.5:9b").message.content #rewrite the user query for better retrieval
        vector_search_results = vector_similarity_search(original_query, user_query, n_results=10) # get a search result as a list of dicts with keys "distance", "source_type", and "document"
        prompting = answer_vector_search_construct(original_query, vector_search_results)
        answer = LLM_query(prompts.GENERAL_ANSWERER, prompting, model="qwen3.6:27b").message.content
        return answer
    else:
        return (f"{original_query}: Unclear")
        ... # if dont know just use LLM to answer the question without any context ?

if __name__ == "__main__":
    user_query = input("Enter your query: ")
    print(main(user_query))