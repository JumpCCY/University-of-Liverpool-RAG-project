"""
Single place to choose which model does what.
"""

#embedding model

# Turns text into vectors for retrieval.
# WARNING: this one is not free to change. The vectors already stored in chroma_db
EMBEDDING = "qwen3-embedding:8b"

# 127.0.0.1 rather than localhost: on Windows "localhost" tries IPv6 first, which Ollama
# does not listen on, and every new connection waited ~2s before falling back to IPv4.
OLLAMA_URL = "http://127.0.0.1:11434"


PROVIDER = "openai" # "ollama" or "openai"

if PROVIDER == "openai":
    LOW_EFFORT = "gpt-5.6-luna"
    HIGH_EFFORT = "gpt-5.6-luna"

elif PROVIDER == "ollama":
    LOW_EFFORT = "qwen3.5:9b"
    HIGH_EFFORT = "qwen3.6:27b"