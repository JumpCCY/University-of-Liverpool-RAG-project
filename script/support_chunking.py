from pathlib import Path
from bs4 import BeautifulSoup, Comment
from langchain_text_splitters import (
    HTMLSemanticPreservingSplitter,
    RecursiveCharacterTextSplitter,
)
import re
from rich import print

folder = Path(__file__).parent.parent / "data" / "liverpool" / "support"

MAIN_SECTION = "student support"

# chunks whose body matches any of these are CMS boilerplate, not content
NOISE_PATTERNS = [
    re.compile(r"lorem ipsum", re.I),
    re.compile(r"^skip navigation|^university home >", re.I), # breadcrumb and skip link
    re.compile(r"student services menu", re.I), # the side nav repeated on every page
    re.compile(r"^(?:read more|find out more|learn more|view all|back to top)\b", re.I),
]

# the side nav lists every support page by name, so a chunk that is just those names
# carries no information. it is short and made only of the known page titles.
NAV_LINKS = re.compile(
    r"in a crisis now|mental wellbeing|disabled students|money advice|"
    r"visas and immigration|safe and welcoming campus|staff hub|gender identity support|"
    r"support in global crises|book an appointment|renters' rights",
    re.I,
)
MAX_NAV_HITS = 4  # this many page names in one chunk means it is the nav, not content

MIN_CHARS = 120  # anything shorter is merged back or dropped


def preprocess_html(html):
    soup = BeautifulSoup(html, "html.parser")

    # remove non-content tags ex. JS
    for tag in soup.find_all(
        ["script", "style", "noscript", "iframe", "svg", "img", "picture", "dialog", "nav"]
    ):
        tag.decompose()

    # HTML comments leak into the text otherwise (commented-out cards, layout markers)
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()

    # drop the side menu and the breadcrumb
    for tag in soup.find_all(
        class_=re.compile(r"menu|breadcrumb|side-nav|section-nav|skip", re.I)
    ):
        tag.decompose()

    for a in soup.find_all("a"):
        href = a.get("href", "")
        if href.startswith("mailto:") or "@" in a.get_text():
            a.replace_with(" " + a.get_text() + " ") # keep advice@liverpool.ac.uk, staff read it out
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
    if not text:
        return True
    for p in NOISE_PATTERNS:
        if p.search(text):
            return True
    return False


def is_nav(text):
    """A chunk listing this many of the support page names is the side nav."""
    return len(set(m.group().lower() for m in NAV_LINKS.finditer(text))) >= MAX_NAV_HITS


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
    """Chunk one support page for retrieval, prefixed with the page it came from."""

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
            # if the body is noise or just the side nav we skip it
            if is_noise(body) or is_nav(body):
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
        # fallback file name in case the page has no <h1> or the <h1> is too short or too long
        fallback = file.stem.replace("_", " ").replace("-", " ")

        all_chunks.extend(ingest_page(html, f"{page_title(html, fallback)}", MAIN_SECTION))
    return all_chunks


if __name__ == "__main__":
    docs = chunking()
    with open("test_support_chunk.txt", "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(f"Metadata: {doc.metadata}\n")
            f.write(f"Content: {doc.page_content}\n")
            f.write("=" * 80 + "\n")
    print(f"{len(docs)} support chunks written to test_support_chunk.txt")
