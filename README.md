Setup and run — steps

Before installing anything with pip
- Python 3.10 or newer — the whole project (developed on 3.13)
- Ollama — always needed, because the embedding model runs there even when answers come from OpenAI
- Docker Desktop — only for the Open WebUI website. If Docker and Open WebUI are not installed yet, follow Open WebUI's quick start guide first: https://docs.openwebui.com/getting-started/quick-start/
- cloudflared — only to publish the site on a public address
- An OpenAI API key — only if PROVIDER = "openai" in py/models.py

Steps, in order (run from the project root)
- Install the libraries: pip install -r requirements.txt
- Download the embedding model: ollama pull qwen3-embedding:8b
- Add the API key: create .env in the project root with OPENAI_API_KEY=sk-...
- Refresh the data (optional — data/ is already in the repository**):** python script/scraper/run_all_scrapers.py, which scrapes all 8 universities and rebuilds the citation links at the end; add python script/json_converter.py if a spreadsheet in data/raw/ changed
- Build the vector database: python py/embeddings/populate_vector_db.py — required once, as chroma_db/ is not in the repository
- Use it in the terminal: python py/RAG_main.py
- Or start the API: python py/api.py, which serves an OpenAI-compatible API on http://localhost:8000
- Install Open WebUI if you have not already: see the quick start above, then start it with docker run -d -p 3000:8080 --add-host=host.docker.internal:host-gateway -v open-webui:/app/backend/data --name open-webui --restart always ghcr.io/open-webui/open-webui:main
- Connect the website to the API: open http://localhost:3000, create an account, then Settings → Admin Settings → Connections → OpenAI API, URL http://host.docker.internal:8000/v1, key anything; pick university-rag in the model list
- Make it public (optional for phone access demo): cloudflared tunnel --url http://localhost:3000 prints a public HTTPS address, no Cloudflare account needed, and it lasts until you close the terminal