import chromadb

client = chromadb.PersistentClient(path="chroma_db")

collection = client.get_collection("my_collection")
results = collection.query(query_texts=[input("Enter your query: ")], n_results=5)

for doc, meta, dist in zip(
    results["documents"][0], results["metadatas"][0], results["distances"][0]
):
    print(f"\n[{dist:.3f}] ({meta.get('source_type')}) {doc}")
