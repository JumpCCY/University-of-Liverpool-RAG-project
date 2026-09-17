"""
Numbered sources for an answer.

Everything the answerer is given - a retrieved passage or an entry-requirement
record - is numbered [1], [2], ... in its context. The answerer cites those numbers,
and once the answer is finished the code, not the model, lists what each cited
number was. The model never writes a source itself, so it cannot invent one.
"""

import json
import re
from pathlib import Path

from universities import MAIN_UNIVERSITY

# [3], or [3, 5] if the model groups them. [3][5] is simply two matches.
CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

# a whole run of citations as the model writes it: " [3]", "[3][5]", " [3, 5]"
CITATION_RUN = re.compile(r"(?:\s?\[\d+(?:\s*,\s*\d+)*\])+")

# what a line names exactly enough to look up in a passage word for word
MODULE_CODE = re.compile(r"\b[A-Z]{3,4}\d{3,5}\b")
FIGURE = re.compile(r"£\s?\d[\d,]*(?:\.\d+)?|\d+(?:\.\d+)?\s?%")
BOLD = re.compile(r"\*\*([^*]+?)\*\*")

# first line of the sources list. strip_sources() splits on it too
SOURCES_HEADING = "**Sources**"

# liverpool sources that all sit on one page between them
COURSE_URL = "https://www.liverpool.ac.uk/courses/computer-science-bsc-hons"
MODULES_URL = f"{COURSE_URL}#course-content"
FEES_URL = f"{COURSE_URL}#fees-and-funding"
REQUIREMENTS_URL = f"{COURSE_URL}#entry-requirements"
GUILD_URL = "https://www.liverpoolguild.org/groups/"
LIVERPOOL_URLS = {
    "module": MODULES_URL,       # only used if a module is missing its own page
    "course_info": MODULES_URL,  # the hand-written year and pathway notes
    "guild": GUILD_URL,
    "scholarship": FEES_URL,
    "fee": FEES_URL,
}

# each of those pages is listed under its own name, not under whichever society,
# scholarship or requirement on it happened to be cited first
PAGE_NAMES = {
    MODULES_URL: "Course content",
    FEES_URL: "Fees and funding",
    REQUIREMENTS_URL: "Entry requirements",
    GUILD_URL: "Guild of Students clubs and societies",
}

# page title -> URL for the general, support and course-page chunks, plus each
# university's course page. built from the scrapers by script/source_urls.py
SOURCE_URLS_FILE = Path(__file__).resolve().parents[1] / "data" / "liverpool" / "json" / "source_urls.json"
try:
    SOURCE_URLS = json.loads(SOURCE_URLS_FILE.read_text(encoding="utf-8"))
except FileNotFoundError:
    SOURCE_URLS = {}  # answers still get their sources list, only without links

# every other university was scraped from its one course page, so each is one source
RIVAL_PAGE = "Computer Science course page"


def source_number(sources: list[tuple[str, str | None]], label: str, url: str | None = None) -> int:
    """
    The [n] for a source, adding it to sources if it is new. There is one source per
    link: anything that opens the same page shares a number, so the sources list
    never shows two entries that go to the same place. Without a link, the label
    decides instead.
    """
    key = url or label
    for n, (listed_label, listed_url) in enumerate(sources, start=1):
        if (listed_url or listed_label) == key:
            return n
    sources.append((label, url))
    return len(sources)


def passage_url(meta: dict) -> str | None:
    """The web page a retrieved passage came from."""
    university, kind = meta.get("university"), meta.get("source_type")
    if university != MAIN_UNIVERSITY:
        return SOURCE_URLS.get("course_pages", {}).get(university)  # each other university is one course page
    return (
        meta.get("url")  # modules store their own page
        or SOURCE_URLS.get(kind, {}).get(meta.get("page_title", ""))  # general, support and course-page sections
        or LIVERPOOL_URLS.get(kind)
    )


def passage_source(meta: dict) -> tuple[str, str | None]:
    """(label, url) for a retrieved passage, built from whatever its metadata holds."""
    university, kind = meta.get("university", ""), meta.get("source_type")
    if university != MAIN_UNIVERSITY:
        # one label and one link for all of a university's passages, so they share a number
        return f"{university} – {RIVAL_PAGE}", passage_url(meta)
    if kind == "module":
        name = f"Module: {meta.get('code', '')} {meta.get('title', '')}"
    elif kind == "guild":
        name = f"Guild of Students: {meta.get('guild_name', '')}"
    elif kind == "scholarship":
        name = f"Scholarship: {meta.get('scholarship_title', '')}"
    elif kind == "fee":
        name = "Tuition fees"
    else:
        # course_info, general and support pages. a few course chunks only have a
        # file-style title such as "year_one_pathway"
        name = meta.get("page_title") or meta.get("title", "").replace("_", " ").capitalize() or "Course information"
    url = passage_url(meta)
    return f"{university} – {PAGE_NAMES.get(url, name)}", url


def requirements_source(university: str) -> tuple[str, str | None]:
    """
    (label, url) for a university's entry-requirement records. They all come from
    its one entry-requirements page, so they are one source per university.
    """
    if university != MAIN_UNIVERSITY:
        return f"{university} – {RIVAL_PAGE}", SOURCE_URLS.get("course_pages", {}).get(university)
    return f"{university} – {PAGE_NAMES[REQUIREMENTS_URL]}", REQUIREMENTS_URL


def _plain(text: str) -> str:
    """Lowercase, one kind of apostrophe and dash, no thousands commas - so "£1,955" matches "£1955"."""
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[‐-―]", "-", text)
    text = re.sub(r"(?<=\d),(?=\d{3})|(?<=£)\s+|\s+(?=%)", "", text)
    return re.sub(r"\s+", " ", text).lower()


def passage_texts(context: str) -> dict[int, str]:
    """
    The numbered text of an answerer's context, read back out of it: n -> everything
    under [n], put through _plain() for matching. Works for passages ("[n] text") and
    requirement records ("[n]" on its own line).
    """
    texts = {}
    for m in re.finditer(r"\[(\d+)\][ \n](.*?)(?=\n\n\[\d+\][ \n]|\n=== |\Z)", context, re.S):
        n = int(m.group(1))
        texts[n] = texts.get(n, "") + " " + _plain(m.group(2))
    return texts


def _checkable(text: str) -> list[str]:
    """
    The module codes, prices, percentages and bold names in some answer text. A bold
    name must be two words or more: a bullet's label ("**Fees:**") and a one-word bold
    ("**Yes.**", "**Maths**") say nothing about which page a line came from.
    """
    found = [_plain(m.group()) for m in MODULE_CODE.finditer(text)]
    found += [_plain(m.group()) for m in FIGURE.finditer(text)]
    for m in BOLD.finditer(text):
        name = m.group(1).strip()
        if " " in name and not name.endswith(":") and not text.startswith(":", m.end()):
            found.append(_plain(name))
    return found


def correct_citations(line: str, texts: dict[int, str]) -> str:
    """
    Points one answer line's citations at the passages that actually hold what it names.
    """
    if not texts or "[" not in line:
        return line

    out, last = [], 0
    for run in CITATION_RUN.finditer(line):
        cited = {int(n) for n in re.findall(r"\d+", run.group())}
        holders = []
        for item in _checkable(line[last:run.start()]):
            pattern = re.compile(rf"(?<![\w.]){re.escape(item)}(?!\w)")
            found = {n for n, text in texts.items() if pattern.search(text)}
            if found:
                holders.append(found)

        missing = [found for found in holders if not found & cited]
        numbers = cited
        if missing:
            wrong_passage = len(cited) == 1 and not any(found & cited for found in holders)
            numbers = set() if wrong_passage else set(cited)
            for found in missing:
                if not found & numbers:
                    # the passage that holds the most of what is missing, then the lowest number
                    numbers.add(min(found, key=lambda n: (-sum(n in f for f in missing), n)))

        out.append(line[last:run.start()])
        if numbers == cited:
            out.append(run.group())
        else:
            lead = run.group()[: len(run.group()) - len(run.group().lstrip())]  # keep the space before "["
            out.append(lead + "".join(f"[{n}]" for n in sorted(numbers)))
        last = run.end()

    out.append(line[last:])
    return "".join(out)


def cited_numbers(answer: str) -> list[int]:
    """Every number the answer cites, in ascending order, each once."""
    return sorted({int(n) for group in CITATION.findall(answer) for n in re.findall(r"\d+", group)})


def sources_footer(answer: str, sources: list[tuple[str, str | None]]) -> str:
    """
    The sources list that goes under an answer: only what it actually cited, under
    the same numbers. A number that matches no source is skipped rather than listed.
    Returns "" when the answer cited nothing.
    """
    lines = []
    for n in cited_numbers(answer):
        if 1 <= n <= len(sources):
            label, url = sources[n - 1]
            lines.append(f"- **[{n}]** [{label}]({url})" if url else f"- **[{n}]** {label}")
    if not lines:
        return ""
    return f"\n\n{SOURCES_HEADING}\n" + "\n".join(lines)


def strip_sources(answer: str) -> str:
    """
    An earlier answer without its citations and sources list, for the conversation
    history. The condenser needs what was said, not where it came from - and the
    numbers only meant something to the context that answer was written from.
    """
    answer = answer.split(f"\n\n{SOURCES_HEADING}\n")[0]
    return re.sub(r" ?" + CITATION.pattern, "", answer)
