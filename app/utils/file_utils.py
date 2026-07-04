import chromadb

client = chromadb.HttpClient(host="localhost", port=8000)

client.delete_collection("candidate_chunks")

print("Collection deleted.")