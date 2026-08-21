from bs4 import BeautifulSoup
import requests
from rich import print
from pathlib import Path
from urllib.parse import urljoin
import re
import time

# "sections" = ids on the page. "headings" = sections buried in auto generated ids,
# so we grab the block around the heading text instead.
RIVALS = {
    "sheffield": {
        "url": "https://sheffield.ac.uk/undergraduate/courses/2027/computer-science-bsc",
        "sections": [
            "coursedescription",    # overview and why study this course
            "accreds",              # BCS accreditation
            "plstudyabroad",        # placement year and study abroad
            "modules",              # the module list
            "learningassessment",   # how it is taught and assessed
            "careers",              # graduate careers
            "department",           # the school and its stats
            "stats",                # university rankings
            "fees",                 # tuition fees
        ],
    },
    "york": {
        "url": "https://www.york.ac.uk/study/undergraduate/courses/bsc-computer-science",
        "sections": [
            "overview",
            "course-content",       # year by year
            "teaching-assessment",
            "careers",
            "fees",
        ],
        "headings": ["Accreditation"],
    },
    "leeds": {
        "url": "https://courses.leeds.ac.uk/3260/computer-science-bsc",
        # the tabs are only hidden with css, every section is already in the html
        "sections": [
            "section-overview",
            "section-content",      # course details and modules
            "section-careers",
            "section-abroad",       # study abroad and industrial placements
            "section-fees",
        ],
    },
    "nottingham": {
        "url": "https://www.nottingham.ac.uk/studywithus/ugstudy/courses/UG/Computer-Science-BSc-Hons.html",
        "sections": [
            "overview",
            "year-tabs",            # the module accordions
        ],
        "headings": [
            "Why choose this course?",
            "Teaching and learning",
            "Careers",
            "Accreditation",
        ],
    },
    "manchester": {
        "url": "https://www.manchester.ac.uk/study/undergraduate/courses/2026/00560/bsc-computer-science/",
        # no <main> on this page, the sections are found by id directly.
        # the module accordions are only hidden with css so the list is in the html,
        # but each unit's description sits on its own page and is not scraped.
        "sections": [
            "overview",
            "course-details",
            "careers",
            "fees-and-funding",
        ],
        "unit_details": True, # each module sits behind an ajax call, see fetch_unit_details
    },
    "lancaster": {
        "url": "https://www.lancaster.ac.uk/study/undergraduate/courses/computer-science-bsc-hons-g400/2026/",
        "headings": ["Overview", "Careers", "Course structure", "Fees and funding"],
        "max_block": 32000, # the course structure section holds every module accordion
    },
    "newcastle": {
        "url": "https://www.ncl.ac.uk/undergraduate/degrees/g400/",
        # the tabs are javascript but every panel is already in the html
        "sections": [
            "course-overview",
            "quality-ranking",          # accreditation and rankings
            "modules-learning",
            "work-placement",           # study abroad and industry placements
            "your-future",              # careers
            "facilities-environment",
            "tuition-fees-scholarships",
        ],
    },
}


PARENT_DIR = Path(__file__).resolve().parent.parent # to the root of the project (go up two levels)

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

MIN_BLOCK = 250     # below this we have not climbed out of the heading yet
MAX_BLOCK = 14000   # above this we have climbed too far, into the whole page


def block_for_heading(soup, wanted, max_block=MAX_BLOCK) -> BeautifulSoup | None:
    """Find a heading by its text and climb until the block around it is a sensible size."""
    for h in soup.find_all(["h2", "h3"]):
        if h.get_text(" ", strip=True).lower().startswith(wanted.lower()):
            parent = h.parent
            for _ in range(8):
                if parent is None:
                    break
                text = re.sub(r"\s+", " ", parent.get_text(" ")).strip()
                if MIN_BLOCK < len(text) < max_block:
                    return parent
                parent = parent.parent
    return None


UNIT_KEEP = ["Overview", "Aims", "Syllabus"] # the rest is assessment, reading lists and staff


def fetch_unit_details(soup, page_url, output_dir, university):
    """
    Manchester lists its modules as buttons, not links - clicking one fires an ajax
    call for that unit. We make the same call. The X-Requested-With header is what
    makes it work, without it the endpoint answers 404.
    """
    endpoint = urljoin(page_url, "../../unit/?unitpath=")
    units = []
    ajax = dict(headers)
    ajax["X-Requested-With"] = "XMLHttpRequest"
    ajax["Referer"] = page_url

    for button in soup.find_all("button", class_="open-unit-details"):
        code = button.get("data-contentid")
        path = button.get("data-unitpath")
        if not code or not path:
            continue

        try:
            response = requests.get(endpoint + path, headers=ajax, timeout=20)
            response.raise_for_status()
        except Exception as e:
            print(f"Error {university} unit {code}: {e}")
            continue

        unit = BeautifulSoup(response.content, "html.parser")
        title = unit.find(["h1", "h2"])

        # keep only the sections that say what the module covers. the splitter only
        # records the nearest heading, so the module code goes into EVERY section
        # heading - otherwise a chunk comes back as just "Overview" with no module.
        unit_name = title.get_text(" ", strip=True) if title else code
        kept = []
        for heading in unit.find_all("h2"):
            section = heading.get_text(" ", strip=True)
            if section not in UNIT_KEEP:
                continue
            kept.append(f"<h3>{code} {unit_name} - {section}</h3>")
            for sibling in heading.find_next_siblings():
                if sibling.name in ("h1", "h2"):
                    break
                kept.append(str(sibling))

        if kept:
            units.append("".join(kept))

        time.sleep(1)

    # one file, so the folder stays one-file-per-section. the h1 gives every chunk the
    # same page name and each unit keeps its own h3 in the crumb.
    if units:
        save(output_dir, university, "course-units", "<h1>Course units</h1>" + "".join(units))


def save(output_dir, university, name, element):
    output_path = output_dir / f"{name}.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(str(element))
    print(f"Content saved: {university} / {name}")


for university, config in RIVALS.items(): # keys and value
    output_dir = PARENT_DIR / "data" / university / "course"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        response = requests.get(config["url"], headers=headers, timeout=20)
        response.raise_for_status()

        html = response.content
        soup = BeautifulSoup(html, "html.parser")

        # loop for each wanted section, pull it out of the page and save it to its own html file
        for section_id in config.get("sections", []):
            r = soup.find(id=section_id)

            if r is None:
                # no content
                continue

            save(output_dir, university, section_id, r)

        # the ones with no usable id, found by heading text instead
        for heading in config.get("headings", []):
            r = block_for_heading(soup, heading, config.get("max_block", MAX_BLOCK))

            if r is None:
                # no content
                continue

            name = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
            save(output_dir, university, name, r)

        if config.get("unit_details"):
            fetch_unit_details(soup, config["url"], output_dir, university)

        time.sleep(1)

    except Exception as e:
        print(f"Error {config['url']}: {e}")

print("rival scraper done!")
