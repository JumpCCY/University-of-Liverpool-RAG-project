from pathlib import Path
from bs4 import BeautifulSoup, Comment
from langchain_text_splitters import (
    HTMLSemanticPreservingSplitter,
    RecursiveCharacterTextSplitter,
)
import re
from rich import print

folder = Path(__file__).parent.parent / "data" / "general"

# chunks whose body matches any of these are CMS boilerplate, not content
NOISE_PATTERNS = [
    re.compile(r"lorem ipsum", re.I),
    re.compile(
        r"^(?:\s*[\w-]+\s*/\s*[\w-]+\s*)+$"
    ),  # for webpage cleaning like horizontal /horizontal or foo/bar
    re.compile(
        r"^get a feel for your new home", re.I
    ),  # virtual-tour blurb repeated on every hall page
    re.compile(r"search now\s+load virtual tour", re.I), # for some seach box 
    re.compile(r"^top level page$", re.I),
]

MIN_CHARS = 120  # anything shorter is merged back or dropped


def preprocess_html(html):
    soup = BeautifulSoup(html, "html.parser")

    # remove non-content tags ex. JS
    for tag in soup.find_all(
        ["script", "style", "noscript", "iframe", "svg", "img", "picture", "dialog"]
    ):
        tag.decompose()

    # HTML comments leak into the text otherwise (commented-out cards, layout markers)
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()

    # drop the gallery or videos
    for tag in soup.find_all(
        class_=re.compile(r"gallery|video|virtual-tour|accommodation-finder", re.I)
    ):
        tag.decompose()

    for a in soup.find_all("a"):
        href = a.get("href", "")
        if href.startswith("mailto:") or "@" in a.get_text():
            a.replace_with(" ")
        else:
            a.replace_with(" " + a.get_text() + " ")

    for tag in soup.find_all(["strong", "b", "em", "i", "span", "u"]):
        tag.unwrap()

    return str(soup)


def clean_text(text):
    """Tidy up the spacing that unwrapping links/inline tags leaves behind."""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)  # " communities ." -> " communities."
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_noise(text):
    return not text or any(p.search(text) for p in NOISE_PATTERNS)


def page_title(html, fallback):
    """Prefer the page's own <h1> over the filename slug."""
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    if h1:
        title = clean_text(h1.get_text(" "))
        if 3 < len(title) < 120:
            return title
    return fallback


def ingest_page(html, name, main_section, max_chars=1000, overlap=100):
    """Chunk one scholarship HTML page for retrieval.
    - Splits on headings, sub-splits only oversized *text* sections
    - Prepends the scholarship name so look-alike chunks stay separable
    """

    # when: You need to split the document into chunks while preserving semantic elements like tables and lists REF. LangChain
    splitter = HTMLSemanticPreservingSplitter(
        headers_to_split_on=[
            ("h1", "Header 1"),
            ("h2", "Header 2"),
            ("h3", "Header 3"),
        ],
        max_chunk_size=max_chars,
        chunk_overlap=overlap,
        preserve_parent_metadata=True,
        preserve_links=True,
    )
    docs = splitter.split_text(html)

    # splitter in case the section is too big than max_chars, we do recursive splitting so it is smaller
    recursive = RecursiveCharacterTextSplitter(
        chunk_size=max_chars, chunk_overlap=overlap
    )

    out = []
    prev_heading = None
    for d in docs:
        pieces = recursive.split_documents([d])
        for p in pieces:
            heading = " > ".join(str(v) for v in p.metadata.values()) # join with > 
            body = clean_text(p.page_content)
            # if the body is noise we skip it
            if is_noise(body):
                continue
            # a fragment too small to stand alone belongs on the end of the previous chunk
            if len(body) < MIN_CHARS:
                if out and heading == prev_heading:
                    out[-1].page_content += " " + body
                continue
            # don't repeat the page title when the heading already is it
            crumb = "" if heading == name else heading
            p.page_content = f"[{main_section} > {name}] {crumb}".rstrip() + f"\n{body}"
            p.metadata["main_section"] = main_section
            p.metadata["page"] = name # usually h1 of that page
            out.append(p)
            prev_heading = heading
    return out


def chunking():
    all_chunks = []
    for file in folder.glob("*.html"):
        with open(file, "r", encoding="utf-8") as f:
            raw = f.read()

        # html file preprocessing to remove unwanted tags and comments
        html = preprocess_html(raw)
        # fellback file name in case the page has no <h1> or the <h1> is too short or too long
        fallback = file.stem.replace("_", " ").replace("-", " ")

        main_section_name = re.match(r"^[a-z-]+", file.name).group().replace("-", " ")
        all_chunks.extend(
            ingest_page(html, f"{page_title(html, fallback)}", main_section_name)
        )
    return all_chunks


if __name__ == "__main__":
    with open("test_chunk.txt", "w", encoding="utf-8") as f:
        for doc in chunking():
            f.write(f"Metadata: {doc.metadata}\n")
            f.write(f"Content: {doc.page_content}\n")
            f.write("=" * 80 + "\n")
