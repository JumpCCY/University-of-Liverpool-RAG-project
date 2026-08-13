import os
import chromadb
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)
import re
from rich import print

CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db")

client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

ollama_ef = OllamaEmbeddingFunction(
    url="http://localhost:11434",
    model_name="qwen3-embedding:8b",
)

collection = client.get_collection("my_collection", embedding_function=ollama_ef)


def metadata_search(search_result: chromadb.GetResult, result_list: list):
    """
    helper function to process search results from metadata search to list of dicts with keys "distance", "source_type", and "document".
    """
    doc = search_result["documents"]
    meta = search_result["metadatas"]

    for d, m in zip(doc, meta):
        answer = {}
        answer["distance"] = 0.0  # exact match, so distance is 0
        answer["source_type"] = m.get("source_type")
        answer["document"] = d
        answer["metadata"] = m  # include the metadata in the answer
        result_list.append(answer)


def extract_year(q) -> list[int]:
    """
    Extracts the year information from the query. if the query asking about year. for searching a module
    """
    q = q.lower()
    years = [int(x) for x in re.findall(r"year\s*([123])", q)]
    years += [int(x) for x in re.findall(r"([123])(?:st|nd|rd)\s*year", q)]
    for w, n in {"first": 1, "second": 2, "third": 3, "final": 3}.items():
        if re.search(rf"\b{w}\s+year", q):
            years.append(n)
    return sorted(set(years))

def extract_semester(q) -> list[str]:
    """
    Extracts the semester information from the query. for searching a module
    """
    q = q.lower()
    words = {"one": "1", "two": "2", "first": "1", "second": "2"}
    NUM = r"(?:one|two|first|second|[12])"

    # "semester 1 and 2", "semester one and two", "semester 2 and 1", "semesters 1, 2"
    m = re.search(rf"semesters?\s*({NUM}(?:\s*(?:and|,|&|or)\s*{NUM})*)", q)
    if m:
        nums = re.findall(NUM, m.group(1))
        return [f"Semester {words.get(n, n)}" for n in nums]

    # "1st semester", "first semester", "2nd and 1st semester"
    m = re.search(
        rf"({NUM}(?:st|nd)?(?:\s*(?:and|,|&|or)\s*{NUM}(?:st|nd)?)*)\s*semesters?", q
    )
    if m:
        nums = re.findall(NUM, m.group(1))
        return [f"Semester {words.get(n, n)}" for n in nums]

    if re.search(r"\b(?:whole|entire)\s+(?:session|year)", q):
        return ["Whole Session"]

    return []


def vector_similarity_search(original_query: str, search_query: str = None, n_results: int = 5) -> list[dict]:
    """
    Performs a vector similarity search on the ChromaDB collection.

    return: A list of dictionaries containing the search results, each with keys "distance", "source_type", and "document".
    """

    if search_query is None:
        search_query = original_query

    module_codes = re.findall(r"\b[A-Z]{2,4}\d{3}\b", original_query.upper())  # return list
    credits = [int(c) for c in re.findall(r"(\d+)[- ]?credits?", original_query.lower())]  # return list
    years = extract_year(original_query)  # return list
    semesters = extract_semester(original_query)  # return list

    result_list = []

    # a module code is an exact identifier, so look it up directly instead of searching
    if module_codes:
        results = collection.get(where={"code": {"$in": module_codes}}, include=["documents", "metadatas"])
        metadata_search(results, result_list)
        return result_list

    facets = []
    if credits:
        facets.append({"credits": {"$in": credits}})
    if years:
        facets.append({"year": {"$in": years}})
    if semesters:
        facets.append({"semester": {"$in": semesters}})

    if not facets:
        filters = None
    else:
        # these fields only exist on module documents, so filtering on them alone would
        # exclude every guild/scholarship/fee doc. narrow the modules, leave the rest eligible.
        module_filter = facets[0] if len(facets) == 1 else {"$and": facets}
        filters = {"$or": [module_filter, {"source_type": {"$ne": "module"}}]}

    # filters narrow the candidates, the query still ranks them
    results = collection.query(query_texts=[search_query], where=filters, n_results=n_results)
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        answer = {}
        answer["distance"] = dist
        answer["source_type"] = meta.get("source_type")
        answer["document"] = doc
        answer["metadata"] = meta
        result_list.append(answer)

    return result_list


if __name__ == "__main__":
    query = input("Enter your query for vector similarity search: ")
    k = input("Enter the number of results to return (default 5): ")
    r = vector_similarity_search(query, n_results=int(k) if k.isdigit() else 5)
    print(r)
