import re
from langchain_text_splitters import HTMLSemanticPreservingSplitter, RecursiveCharacterTextSplitter
from pathlib import Path
from rich import print
from bs4 import BeautifulSoup

folder = Path(__file__).parent.parent / "data" / "scholarships"

def preprocess_html(html):
    """Flatten inline tags into reading-order text BEFORE splitting.

    HTMLSemanticPreservingSplitter pulls <strong>/<b>/<a> text out of order,
    which scrambles sentences (e.g. 'first'/'not' jump to the front and invert
    meaning) and displaces email addresses. Resolving these tags in-place first
    keeps the text in document order.
    """
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a"):
        href = a.get("href", "")
        if href.startswith("mailto:") or "@" in a.get_text():
            a.replace_with(" ")          # drop email links entirely
        else:
            a.replace_with(" " + a.get_text() + " ")   # keep normal links as text

    for tag in soup.find_all(["strong", "b", "em", "i", "span", "u"]):
        tag.unwrap()

    return str(soup)

def _table_to_md(table):
    """Convert a BeautifulSoup <table> element to Markdown so rows/cols survive."""
    rows = table.find_all("tr")
    md = []
    for i, tr in enumerate(rows):
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if not cells:
            continue
        md.append("| " + " | ".join(cells) + " |")
        if i == 0:
            md.append("| " + " | ".join("---" for _ in cells) + " |")
    return "\n".join(md)


def ingest_page(html, scholarship_name, max_chars=2000, overlap=150):
    """Chunk one scholarship HTML page for retrieval.

    - Preserves tables as Markdown (rows/cols intact)
    - Splits on headings, sub-splits only oversized *text* sections
    - Prepends the scholarship name so look-alike chunks stay separable
    """
    splitter = HTMLSemanticPreservingSplitter(
        headers_to_split_on=[("h1", "Header 1"), ("h2", "Header 2"), ("h3", "Header 3")],
        elements_to_preserve=["table"],
        preserve_parent_metadata=True,
        custom_handlers={"table": _table_to_md},
        max_chunk_size=2000,
    )
    docs = splitter.split_text(html)


    # if html section is too big we do recursive slitting so it is smaller 
    recursive = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=overlap)

    out = []
    for d in docs:
        d.page_content = re.sub(r"\S+@\S+", "", d.page_content).strip()
        if not d.page_content:
            continue

        # never sub-split a table; only split long prose sections
        has_table = "|" in d.page_content and "---" in d.page_content
        pieces = [d] if has_table else recursive.split_documents([d])

        for p in pieces:
            heading = " > ".join(str(v) for v in p.metadata.values())
            p.page_content = f"[{scholarship_name}] {heading}\n{p.page_content}"
            p.metadata["scholarship"] = scholarship_name
            out.append(p)
    return out

def combine_small_sections(docs, min_chars=200):
    """Merge each scholarship's small sections into ONE 'misc' chunk,
    leave substantive sections untouched.
    Fixing small sections that are too small and not useful
    """
    from collections import defaultdict

    big = []                       # substantive chunks, kept as-is
    small = defaultdict(list)      # small chunks grouped by scholarship

    for doc in docs:
        name = doc.metadata["scholarship"]
        body = doc.page_content.split("\n", 1)[-1].strip()
        if len(body) < min_chars:
            small[name].append(body)
        else:
            big.append(doc)

    # build one combined chunk per scholarship from its small pieces
    from langchain_core.documents import Document
    for name, pieces in small.items():
        big.append(Document(
            page_content=f"[{name}] Additional information\n" + "  ".join(pieces),
            metadata={"scholarship": name, "section": "misc"},
        ))

    return big

def chunking():
    all_chunks = []

    for file in folder.glob("*.html"):
        with open(file, "r", encoding="utf-8") as f:
            html = f.read()
            html = preprocess_html(html)

        name = file.stem.replace("_", " ")
        all_chunks.extend(ingest_page(html, name))
    all_chunks = combine_small_sections(all_chunks, min_chars=200)
    return all_chunks