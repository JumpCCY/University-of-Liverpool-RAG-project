import chromadb
import json
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)

PATH = {
    "cs_modules": "json/bsc_cs_modules.json",
    "courses_info": "json/courses_info.json"
}


def pull_data(path):
    with open(PATH[path], "r") as f:
        data = json.load(f)
        return data
    
ollama_ef = OllamaEmbeddingFunction(
    url="http://localhost:11434",
    model_name="qwen3-embedding:8b",
)
    
#create chroma client
chroma_client = chromadb.PersistentClient(path="chroma_db")

try:
    chroma_client.delete_collection("my_collection")
except Exception:
    pass

collection = chroma_client.create_collection(
    name="my_collection",
    embedding_function=ollama_ef
)

# for populating the collection with modules
for module in pull_data("cs_modules"):
    desc = module.get("description") or ""
    collection.add(
        ids=[module["code"]],
        documents=[f"{module['code']}: {module['title']} [{module['credits']} credits, year {module['year']}, semester {module['semester']}, {'Compulsory' if module['core'] else 'Optional'}] {desc}"],
        metadatas=[
            {
                "source_type": "module",
                "code": module["code"],
                "title": module["title"],
                "year": module["year"],
                "core": module["core"],
                "credits": module["credits"],
                "semester": module["semester"],
                "url": module["url"],
            }
        ]
    )
print("Module data added to the collection.")

for info in pull_data("courses_info"):
    collection.add(
        ids=[info["title"]],
        documents=[f"{info['title']} : {info['text']}"],
        metadatas=[
            {
                "source_type": "course_info",
            }
        ]
    )
print("Course info data added to the collection.")