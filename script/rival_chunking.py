from pathlib import Path
from bs4 import BeautifulSoup, Comment
from langchain_text_splitters import (
    HTMLSemanticPreservingSplitter,
    RecursiveCharacterTextSplitter,
)
import re
from rich import print

DATA_DIR = Path(__file__).parent.parent / "data"

# chunks whose body matches any of these are CMS boilerplate, not content
NOISE_PATTERNS = [
    re.compile(r"lorem ipsum", re.I),
    re.compile(r"^(?:read more|find out more|learn more|view all|back to top)\b", re.I),
    re.compile(r"^you are here|^skip to", re.I),
    re.compile(r"cookie|newsletter|follow us on", re.I),
]

MIN_CHARS = 120  # anything shorter is merged back or dropped


def preprocess_html(html):
    soup = BeautifulSoup(html, "html.parser")

    # remove non-content tags ex. JS
    for tag in soup.find_all(
        ["script", "style", "noscript", "iframe", "svg", "img", "picture", "dialog", "nav"]
    ):
        tag.decompose()

    # HTML comments leak into the text otherwise
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()

    for tag in soup.find_all(class_=re.compile(r"breadcrumb|menu|video|gallery", re.I)):
        tag.decompose()

    for a in soup.find_all("a"):
        a.replace_with(" " + a.get_text() + " ")

    for tag in soup.find_all(["strong", "b", "em", "i", "span", "u"]):
        tag.unwrap()

    return str(soup)


def clean_text(text):
    """Tidy up the spacing that unwrapping links/inline tags leaves behind."""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_noise(text):
    if not text:
        return True
    for p in NOISE_PATTERNS:
        if p.search(text):
            return True
    return False


def section_title(html, fallback):
    """Prefer the section's own heading over the filename."""
    soup = BeautifulSoup(html, "html.parser")

    heading = soup.find(["h1", "h2"])
    if heading:
        title = clean_text(heading.get_text(" "))
        if 3 < len(title) < 120:
            return title
    return fallback


def ingest_page(html, name, university, max_chars=1000, overlap=100):
    """Chunk one section of a rival course page, prefixed with the university it belongs to."""

    splitter = HTMLSemanticPreservingSplitter(
        headers_to_split_on=[
            ("h2", "Header 2"),
            ("h3", "Header 3"),
            ("h4", "Header 4"),
        ],
        max_chunk_size=max_chars,
        chunk_overlap=overlap,
        preserve_parent_metadata=True,
        preserve_links=True,
    )
    docs = splitter.split_text(html)

    recursive = RecursiveCharacterTextSplitter(chunk_size=max_chars, chunk_overlap=overlap)

    out = []
    prev_heading = None
    for d in docs:
        for p in recursive.split_documents([d]):
            heading = " > ".join(str(v) for v in p.metadata.values())
            body = clean_text(p.page_content)
            if is_noise(body):
                continue
            if len(body) < MIN_CHARS:
                if out and heading == prev_heading:
                    out[-1].page_content += " " + body
                continue
            crumb = "" if heading == name else heading
            # the university is in the text as well as the metadata, so a chunk read on its
            # own can never be mistaken for one of ours
            p.page_content = f"[{university} > {name}] {crumb}".rstrip() + f"\n{body}"
            p.metadata["university"] = university
            p.metadata["page"] = name
            out.append(p)
            prev_heading = heading
    return out


def chunking(university: str):
    """Chunk every scraped section for one rival university."""
    folder = DATA_DIR / university / "course"

    all_chunks = []
    for file in sorted(folder.glob("*.html")):
        with open(file, "r", encoding="utf-8") as f:
            raw = f.read()

        html = preprocess_html(raw)
        fallback = file.stem.replace("_", " ").replace("-", " ")

        all_chunks.extend(ingest_page(html, section_title(html, fallback), university))
    return all_chunks


if __name__ == "__main__":
    docs = chunking("nottingham")
    with open("test_rival_chunk.txt", "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(f"Metadata: {doc.metadata}\n")
            f.write(f"Content: {doc.page_content}\n")
            f.write("=" * 80 + "\n")
    print(f"{len(docs)} rival chunks written to test_rival_chunk.txt")
