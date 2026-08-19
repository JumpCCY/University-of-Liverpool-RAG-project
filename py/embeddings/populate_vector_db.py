from pathlib import Path
import sys
import chromadb
import json
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)
PROJECT_ROOT = Path(__file__).parent.parent.parent

sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "py"))  # so the shared model config can be imported

import models

from script import scholar_chunking, general_chunking

# anchored to the project root so this script reads and writes the same files no
# matter which directory it is run from. a relative path here built a second, empty
# chroma_db inside py/ whenever the script was run from there, while vector_search.py
# kept reading the one in the project root.
CHROMA_DB_PATH = PROJECT_ROOT / "chroma_db"

PATH = {
    "cs_modules": PROJECT_ROOT / "data/json/bsc_cs_modules.json",
    "courses_info": PROJECT_ROOT / "data/json/courses_info.json",
    "guilds": PROJECT_ROOT / "data/json/liverpool_guilds.json",
    "scholarships": PROJECT_ROOT / "data/json/scholarships.json",
    "fees": PROJECT_ROOT / "data/json/fees.json"
}


def pull_data(path):
    with open(PATH[path], "r", encoding="utf-8") as f:
        data = json.load(f)
        return data
    
ollama_ef = OllamaEmbeddingFunction(
    url=models.OLLAMA_URL,
    model_name=models.EMBEDDING,
)
    
#create chroma client save on the file
chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))

# delete the collection if it exists and rewrite it with the new data
try:
    chroma_client.delete_collection("my_collection")
except Exception:
    pass

collection = chroma_client.create_collection(
    name="my_collection",
    embedding_function=ollama_ef #pass ollama embedding function (see models.EMBEDDING)
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
    if guild.get("short_description") is None or guild.get("short_description")  == "":
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

    # in case guild short description is the duplicate of long desctiption so we just embedd long des to prevent dupe.
    elif guild.get("short_description") in guild.get("long_description"):
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
            "main_section": md.get("main_section", ""),
            "section": md.get("Header 2") or md.get("Header 3") or md.get("Header 1") or "general", # if no header, default to "general"
            "page_title": md.get("page", ""),
        }],
    )

print("General data added to the collection.")