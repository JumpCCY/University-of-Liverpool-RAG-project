"""
Builds data/liverpool/json/source_urls.json: the web page each chunk in the vector
database came from, so an answer's sources list can link to it.

The chunks only store the page title the chunker gave them. So this titles every saved
page again with the chunkers' own functions, and works out each file's URL from the
scrapers' own URL lists and file naming rules. Nothing is fetched and the vector
database is not touched. Run it again after re-scraping:

    python script/source_urls.py
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "script" / "chunking"))
sys.path.insert(0, str(ROOT / "py"))

import course_chunking
import general_chunking
import support_chunking
from universities import MAIN_UNIVERSITY, UNIVERSITIES

DATA = ROOT / "data" / "liverpool"
SCRAPERS = ROOT / "script" / "scraper"
OUTPUT = DATA / "json" / "source_urls.json"


def constant(script: str, name: str):
    """A top-level constant from a scraper, read from its source so the scraper does not run."""
    tree = ast.parse((SCRAPERS / script).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(f"{name} not found in {script}")


def general_file(url: str) -> str:
    """The file name general_info_scraper.py saves a URL under - the same rule as the scraper."""
    if "https://www.liverpool.ac.uk/student-life/" in url:
        return url.replace("https://www.liverpool.ac.uk/student-life/", "").replace("/", "_").strip("_")
    return url.replace("https://www.liverpool.ac.uk/", "").replace("/", "_").strip("_")


def support_file(url: str) -> str:
    """The file name support_scraper.py saves a URL under - the same rule as the scraper."""
    return url.replace("https://www.liverpool.ac.uk/studentsupport/", "").replace("/", "_").strip("_")


def page_urls(chunker, title_function, folder: Path, url_for) -> dict[str, str]:
    """Page title -> URL for every saved page in folder, titled exactly as the chunker titles it."""
    urls = {}
    for file in sorted(folder.glob("*.html")):
        html = chunker.preprocess_html(file.read_text(encoding="utf-8"))
        fallback = file.stem.replace("_", " ").replace("-", " ")  # same fallback as chunking()
        title = title_function(html, fallback)
        url = url_for(file.stem)
        if url is None:
            sys.exit(f"{file.name} is not in its scraper's URL list")
        if urls.get(title, url) != url:
            sys.exit(f"two pages share the title {title!r}, so a chunk could not tell them apart")
        urls[title] = url
    return urls


general = {general_file(u): u for u in constant("general_info_scraper.py", "URLS")}
support = {support_file(u): u for u in constant("support_scraper.py", "URLS")}
course_url = constant("course_scraper.py", "URL")
rivals = constant("rival_scraper.py", "RIVALS")

course_pages = {MAIN_UNIVERSITY: course_url}
for university, info in UNIVERSITIES.items():
    if info["folder"] in rivals:
        course_pages[university] = rivals[info["folder"]]["url"]

source_urls = {
    "general": page_urls(general_chunking, general_chunking.page_title, DATA / "general", general.get),
    "support": page_urls(support_chunking, support_chunking.page_title, DATA / "support", support.get),
    # course_scraper.py saves each section under its id on the page, so the id is the anchor
    "course_info": page_urls(course_chunking, course_chunking.section_title, DATA / "course",
                             lambda stem: f"{course_url}#{stem}"),
    "course_pages": course_pages,
}

OUTPUT.write_text(json.dumps(source_urls, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
for kind, urls in source_urls.items():
    print(f"{kind:12} {len(urls)} URLs")
print(f"written to {OUTPUT.relative_to(ROOT)}")
