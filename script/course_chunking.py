from pathlib import Path
from bs4 import BeautifulSoup, Comment
from langchain_text_splitters import (
    HTMLSemanticPreservingSplitter,
    RecursiveCharacterTextSplitter,
)
import re
from rich import print

folder = Path(__file__).parent.parent / "data" / "course"

# every file here comes from the one BSc Computer Science course page, so the crumb
# says which course it is and the page name says which section of it.
MAIN_SECTION = "computer science bsc"

# chunks whose body matches any of these are CMS boilerplate, not content
NOISE_PATTERNS = [
    re.compile(r"lorem ipsum", re.I),
    re.compile(
        r"^(?:\s*[\w-]+\s*/\s*[\w-]+\s*)+$"
    ),  # for webpage cleaning like horizontal /horizontal or foo/bar
    re.compile(r"^(?:read more|find out more|learn more|view all)\b", re.I),
    re.compile(r"take a look around|virtual tour|watch the video", re.I),
    re.compile(r"match with an ambassador", re.I), # unibuddy widget blurb, no facts in it
    re.compile(r"read this story|describes (?:her|his|their) time at", re.I), # alumni story cards
    re.compile(r"^picture by|gallery mode", re.I), # image captions from the photo strip
    re.compile(r"talks you through", re.I), # the department tour video blurb
]

# the course page repeats the whole module list inside accordions, and we already hold
# all 57 modules as their own chunks from bsc_cs_modules.json. a chunk naming this many
# module codes is one of those accordions, so it is a duplicate and we drop it.
MODULE_CODE = re.compile(r"\b(?:COMP|ELEC|PSYC|ULMS)\d{3}\b")
MAX_MODULE_CODES = 3

# the accordions get split into pieces that fall under the max above, but they all sit
# under a "Modules" heading, so drop on the heading as well as on the codes.
SKIP_HEADINGS = re.compile(r"\bmodules\b", re.I)

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

    # drop the gallery, videos and the student testimonial cards
    for tag in soup.find_all(
        class_=re.compile(r"gallery|video|virtual-tour|unibuddy|testimonial|profile-card", re.I)
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
    if not text:
        return True
    for p in NOISE_PATTERNS:
        if p.search(text):
            return True
    return False


def is_module_list(text):
    """A chunk that names several module codes is the page's module accordion, which we already hold."""
    return len(set(MODULE_CODE.findall(text))) >= MAX_MODULE_CODES


def section_title(html, fallback):
    """Prefer the section's own heading over the filename slug."""
    soup = BeautifulSoup(html, "html.parser")

    # the page's only <h1> sits outside these sections, so each section leads with an <h2>
    heading = soup.find(["h1", "h2"])
    if heading:
        title = clean_text(heading.get_text(" "))
        if 3 < len(title) < 120:
            return title
    return fallback


def ingest_page(html, name, main_section, max_chars=1000, overlap=100):
    """Chunk one section of the course page for retrieval.
    - Splits on headings, sub-splits only oversized *text* sections
    - Prepends the course and section name so look-alike chunks stay separable
    """

    # when: You need to split the document into chunks while preserving semantic elements like tables and lists REF. LangChain
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
            # the module accordions duplicate chunks we already have, so they go
            if is_module_list(body) or SKIP_HEADINGS.search(heading):
                continue
            # a fragment too small to stand alone belongs on the end of the previous chunk
            if len(body) < MIN_CHARS:
                if out and heading == prev_heading:
                    out[-1].page_content += " " + body
                continue
            # don't repeat the section title when the heading already is it
            crumb = "" if heading == name else heading
            p.page_content = f"[{main_section} > {name}] {crumb}".rstrip() + f"\n{body}"
            p.metadata["main_section"] = main_section
            p.metadata["page"] = name # usually the h2 of that section
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
        # fallback file name in case the section has no heading or the heading is too short or too long
        fallback = file.stem.replace("_", " ").replace("-", " ")

        all_chunks.extend(
            ingest_page(html, f"{section_title(html, fallback)}", MAIN_SECTION)
        )
    return all_chunks


if __name__ == "__main__":
    docs = chunking()
    with open("test_course_chunk.txt", "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(f"Metadata: {doc.metadata}\n")
            f.write(f"Content: {doc.page_content}\n")
            f.write("=" * 80 + "\n")
    print(f"{len(docs)} course page chunks written to test_course_chunk.txt")
