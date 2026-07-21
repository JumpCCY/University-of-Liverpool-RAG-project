import chromadb
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)
import re
from rich import print

client = chromadb.PersistentClient(path="chroma_db")

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


def extract_year(q):
    q = q.lower()
    m = re.search(r"year\s*([123])", q)  # "year 2", "year2"
    if m:
        return int(m.group(1))
    m = re.search(r"([123])(?:st|nd|rd)\s*year", q)  # "2nd year", "1st year"
    if m:
        return int(m.group(1))
    words = {"first": 1, "second": 2, "third": 3, "final": 3}
    for w, n in words.items():
        if re.search(rf"\b{w}\s*year", q):  # "first year", "final year"
            return n
    return None


def extract_semester(q):
    q = q.lower()
    m = re.search(r"semester\s*([12])", q)  # "semester 1", "semester2"
    if m:
        return f"Semester {m.group(1)}"
    m = re.search(r"([12])(?:st|nd)\s*semester", q)  # "1st semester"
    if m:
        return f"Semester {m.group(1)}"
    if re.search(r"\b(whole|entire)\s+(session|year)", q):  # "whole semester" modules
        return "Whole Session"
    return None


def vector_similarity_search(query: str, n_results: int = 5) -> list[dict]:
    """
    Performs a vector similarity search on the ChromaDB collection.

    return: A list of dictionaries containing the search results, each with keys "distance", "source_type", and "document".
    """

    filters = {}

    module_codes = re.findall(r"\b[A-Z]{2,4}\d{3}\b", query.upper())
    credit = re.search(r"(\d+)[- ]?credit", query.lower())
    year = extract_year(query)
    semester = extract_semester(query)

    if module_codes:
        filters["code"] = {"$in": module_codes}
    if credit:
        filters["credits"] = int(credit.group(1))
    if year:
        filters["year"] = year
    if semester:
        filters["semester"] = semester

    result_list = []

    if filters:
        results = collection.get(where=filters, include=["documents", "metadatas"])
        metadata_search(results, result_list)
    else:
        # pure vector similarity search
        results = collection.query(query_texts=[query], n_results=n_results)
        for doc, meta, dist in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            answer = {}
            answer["distance"] = dist
            answer["source_type"] = meta.get("source_type")
            answer["document"] = doc
            result_list.append(answer)

    return result_list


if __name__ == "__main__":
    # Example usage
    query = input("Enter your query for vector similarity search: ")
    k = input("Enter the number of results to return (default 5): ")
    r = vector_similarity_search(query, n_results=int(k) if k.isdigit() else 5)
    print(r)
