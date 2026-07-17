import chromadb
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)
import re

client = chromadb.PersistentClient(path="chroma_db")

ollama_ef = OllamaEmbeddingFunction(
    url="http://localhost:11434",
    model_name="qwen3-embedding:8b",
)

collection = client.get_collection("my_collection", embedding_function=ollama_ef)


def vector_similarity_search(query: str, n_results: int = 5) -> list[dict]:
    """
    Performs a vector similarity search on the ChromaDB collection.

    return: A list of dictionaries containing the search results, each with keys "distance", "source_type", and "document".
    """
    module_codes = re.findall(r"\b[A-Z]{2,4}\d{3}\b", query.upper())

    result_list = []

    if module_codes:
        # exact match search for module codes by metadata
        results = collection.get(where={"code": {"$in": module_codes}}, include=["documents", "metadatas"])
        doc = results["documents"]
        meta = results["metadatas"]

        for d, m in zip(doc, meta):
            answer = {}
            answer["distance"] = 0.0  # exact match, so distance is 0
            answer["source_type"] = m.get("source_type")
            answer["document"] = d
            result_list.append(answer)
    else:
        #pure vector similarity search
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
