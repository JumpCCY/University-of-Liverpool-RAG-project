from pathlib import Path
import sys
import chromadb
import json
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)
sys.path.append(str(Path(__file__).parent.parent.parent))  

from script import scholar_chunking, general_chunking

PATH = {
    "cs_modules": "data/json/bsc_cs_modules.json",
    "courses_info": "data/json/courses_info.json",
    "guilds": "data/json/liverpool_guilds.json",
    "scholarships": "data/json/scholarships.json",
    "fees": "data/json/fees.json"
}


def pull_data(path):
    with open(PATH[path], "r", encoding="utf-8") as f:
        data = json.load(f)
        return data
    
ollama_ef = OllamaEmbeddingFunction(
    url="http://localhost:11434",
    model_name="qwen3-embedding:8b",
)
    
#create chroma client save on the file
chroma_client = chromadb.PersistentClient(path="chroma_db")

# delete the collection if it exists and rewrite it with the new data
try:
    chroma_client.delete_collection("my_collection")
except Exception:
    pass

collection = chroma_client.create_collection(
    name="my_collection",
    embedding_function=ollama_ef #pass ollama embedding function on line 18 (qwen3-embedding:8b)
)

# populating the collection with university of liverpool cs modules
for module in pull_data("cs_modules"):
    desc = module.get("description") or ""
    collection.add(
        ids=[f"{module['code']}_y{module['year']}"],
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

#populating the collection with computer science course info data
for info in pull_data("courses_info"):
    collection.add(
        ids=[info["title"]],
        documents=[f"{info['title']} : {info['text']}"],
        metadatas=[
            {
                "source_type": "course_info",
                "title" : info["title"],
            }
        ]
    )

print("Course info data added to the collection.")

# populating the collection with guild data
for guild in pull_data("guilds"):
    # if there is no short description, only add the long description to the collection
    if guild.get("short_description") is None or guild["short_description"] == "":
        collection.add(
            ids=[guild["guild_name"]],
            documents=[f"{guild['guild_name']} : {guild['long_description']}"],
            metadatas=[
                {
                    "source_type": "guild",
                    "guild_name": guild["guild_name"],
                }
            ]
        )
        # else we add both the short and long descriptions to the collection
    else:
        collection.add(
            ids=[guild["guild_name"]],
            documents=[f"{guild['guild_name']} : {guild['short_description']} {guild['long_description']}"],
            metadatas=[
                {
                    "source_type": "guild",
                    "guild_name": guild["guild_name"],
                }
            ]
        )

print("Guild data added to the collection.")

# populating the collection with scholarship data
for i, doc in enumerate(scholar_chunking.chunking()):
    md = doc.metadata
    collection.add(
        ids=[f"scholarship_{md['scholarship']}_{i}"],
        documents=[doc.page_content],
        metadatas=[{
            "source_type": "scholarship",
            "scholarship_title": md.get("scholarship", ""),
            "section": md.get("Header 2") or md.get("Header 3") or md.get("Header 1") or "general", # if no header, default to "general"
        }],
    )

print("Scholarship data added to the collection.")

for fee in pull_data("fees"):

    fee_title = fee["title"]
    text = ", ".join(fee["info"])

    collection.add(
        ids=[fee["title"]],
        documents=[f"{fee['title']} : {text}"],
        metadatas=[
            {
                "source_type": "fee",
            }
        ]
    )

print("fees data added to the collection.")

# populating the collection with general data
for i, doc in enumerate(general_chunking.chunking()):
    md = doc.metadata
    collection.add(
        ids=[f"general_{md['page']}_{i}"],
        documents=[doc.page_content],
        metadatas=[{
            "source_type": "general",
            "page_title": md.get("page", ""),
            "section": md.get("Header 2") or md.get("Header 3") or md.get("Header 1") or "general", # if no header, default to "general"
        }],
    )

print("General data added to the collection.")