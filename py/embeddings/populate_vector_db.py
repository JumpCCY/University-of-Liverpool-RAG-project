import chromadb
import json
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)

PATH = {
    "cs_modules": "data/json/bsc_cs_modules.json",
    "courses_info": "data/json/courses_info.json",
    "guilds": "data/json/liverpool_guilds.json",
    "scholarships": "data/json/scholarships.json",
    "fees": "data/json/fees.json"
}


def pull_data(path):
    with open(PATH[path], "r") as f:
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

# populating the collection with university of liverpool modules
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
            }
        ]
    )

print("Course info data added to the collection.")

# populating the collection with guild data
for guild in pull_data("guilds"):
    if guild.get("short_description") is None or guild["short_description"] == "":
        collection.add(
            ids=[guild["guild_name"]],
            documents=[f"{guild['guild_name']} : {guild['long_description']}"],
            metadatas=[
                {
                    "source_type": "guild",
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
                }
            ]
        )

print("Guild data added to the collection.")

# populating the collection with scholarship data
# loop for each scholarship, add the general content and then loop through each section and add the section content
# if there is no general content, only add the sections
# sections will always add along the scholarship title and section title to the document for context (hirachical)
for scholarship in pull_data("scholarships"):

    scholarship_title = scholarship["title"]
    if scholarship["content"]:
        text = "\n\n".join(scholarship["content"])
        collection.add(
            ids = [f"{scholarship_title}_general"],
            documents = [f"Scholarship: {scholarship_title}\n\n{text}"],
            metadatas = [{
                "source_type": "scholarship",
                "scholarship_title": scholarship_title,
                "section" : "general",
            }]   
        )

    for section_idx, section in enumerate(scholarship["sections"]):
        section_title = section["title"]
        section_content = "\n\n".join(section["content"])
        collection.add(
            ids = [f"{scholarship_title}_{section_title}_{section_idx}"],
            documents = [f"Scholarship: {scholarship_title}\n\nSection: {section_title}\n\n{section_content}"],
            metadatas = [{
                "source_type": "scholarship",
                "scholarship_title": scholarship_title,
                "section" : section_title,
            }]
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