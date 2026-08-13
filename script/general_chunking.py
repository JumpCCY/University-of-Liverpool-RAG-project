from pathlib import Path
from bs4 import BeautifulSoup
from langchain_text_splitters import HTMLSemanticPreservingSplitter, RecursiveCharacterTextSplitter
import re
from rich import print

folder = Path(__file__).parent.parent / "data" / "general"

def preprocess_html(html):
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a"):
        href = a.get("href", "")
        if href.startswith("mailto:") or "@" in a.get_text():
            a.replace_with(" ")
        else:
            a.replace_with(" " + a.get_text() + " ")

    for tag in soup.find_all(["strong", "b", "em", "i", "span", "u"]):
        tag.unwrap()

    return str(soup)    


def ingest_page(html, name, max_chars=1000, overlap=100):
    """Chunk one scholarship HTML page for retrieval.
    - Splits on headings, sub-splits only oversized *text* sections
    - Prepends the scholarship name so look-alike chunks stay separable
    """

    # when: You need to split the document into chunks while preserving semantic elements like tables and lists REF. LangChain
    splitter = HTMLSemanticPreservingSplitter(
        headers_to_split_on=[("h1", "Header 1"), ("h2", "Header 2"), ("h3", "Header 3")],
        preserve_parent_metadata=True,
        preserve_links=True,
    )
    docs = splitter.split_text(html)

    # if html section is too big we do recursive slitting so it is smaller 
    recursive = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=overlap)

    out = []
    for d in docs:
        pieces = recursive.split_documents([d])
        for p in pieces:
            heading = " > ".join(str(v) for v in p.metadata.values())
            p.page_content = f"[{name}] {heading}\n{p.page_content}"
            p.metadata["page"] = name
            out.append(p)
    return out


def chunking():
    all_chunks = []
    for file in folder.glob("*.html"):
        with open(file, "r", encoding="utf-8") as f:
            html = f.read()
            html = preprocess_html(html)

        name = file.stem.replace("_", " ").replace("-", " ")
        all_chunks.extend(ingest_page(html, name))
    return all_chunks
