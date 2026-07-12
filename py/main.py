from llm import LLM_query
import prompts
import json
from retriever import load_universities

KNOWN_UNIVERSITIES = ["University of Liverpool", "University of York", "University of Leeds",
    "University of Manchester", "Newcastle University",
    "University of Sheffield", "University of Nottingham",
    "University of Lancaster",]

def query(prompt, query) -> dict:
    """
    Queries the LLM with the given prompt and query, and returns the parsed JSON response.
    """
    response = LLM_query(prompt, query).message.content
    try:
        response = json.loads(response)
    except json.JSONDecodeError:
        response = {}
    return response

def extract_metadata(user_query) -> dict:
    """
    Extracts metadata from the user query and adds the University of Liverpool if not present.
    """
    data = query(prompts.EXTRACTOR, user_query) # extracted qualification and university information mentioned from the user query
    unis = data.get("universities") or []

    #insert University of Liverpool because this is from University of Liverpool staff and we want to compare against it.
    if "University of Liverpool" not in unis:
        unis.insert(0, "University of Liverpool")

    return {
        "universities": unis,
        "student_grades": data.get("student_grades") or "",
        "qualification_type": data.get("qualification_type") or ""
    }

def answer_qualification_constuct(user_query, extracted_meta, qualifications_data):
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

user_query = input("Enter your query: ")
router = query(prompts.ROUTER, user_query) # detect what type of question it is (requirement, general, unclear)

category = router.get("category", "unclear") # get category from dict if not present default to unclear
if category not in {"requirement", "general", "unclear"}: #if category is not one of the three known categories default to unclear
    category = "unclear"

if category == "requirement":
    metadata = extract_metadata(user_query) # handle requirement questions
    qualifications_data = load_universities(metadata["universities"]) # load the qualification records for the universities mentioned in the user query
    answer = LLM_query(prompts.ANSWERER, answer_qualification_constuct(user_query, metadata, qualifications_data)).message.content # construct the context and query the LLM for an answer
    print(answer)

elif category == "general":
    print("Need more work now")
    ... # handle general questions (vector search) ?
else:
    print("UNCLEAR")
    ... # if dont know just use LLM to answer the question without any context ?

