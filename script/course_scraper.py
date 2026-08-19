from bs4 import BeautifulSoup
import requests
from rich import print
from pathlib import Path
import time

URL = "https://www.liverpool.ac.uk/courses/computer-science-bsc-hons"

# unlike the other scrapers this is ONE page, but it is built out of <section id="...">
# blocks. we save each wanted section as its own file so the chunker can treat them
# like separate pages (same as data/general).
SECTIONS = [
        "about-this-course",            # overview, what you'll learn, BCS accreditation
        "course-content",               # year by year + how you'll learn / how you're assessed
        "course-options",               # year in industry, year abroad, related degrees
        "your-experience",              # the school, REF result, facilities, support
        "careers-and-employability",    # graduate jobs, employers, graduate outcomes
        ]

# sections we deliberately DON'T take:
# fees-and-funding      -> already scraped by fee_scraper.py into fees.json
# scholarships-list     -> already scraped by scholar_scraper.py
# entry-requirements    -> entry requirements are answered from data/json, not the vector db
# pre-sessional-english, contact-us, virtual-tour -> no answerable content

PARENT_DIR = Path(__file__).resolve().parent.parent # to the root of the project (go up two levels)

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

output_dir = PARENT_DIR / "data" / "course"
output_dir.mkdir(parents=True, exist_ok=True) # this folder is new, the other scrapers write into folders that already exist

try:
    response = requests.get(URL, headers=headers, timeout=20)
    response.raise_for_status()

    html = response.content
    soup = BeautifulSoup(html, "html.parser")

    # loop for each wanted section, pull that section out of the page and save it to its own html file
    for section_id in SECTIONS:
        r = soup.find("section", id=section_id)

        if r is None:
            print(f"Warning: No content found for section {section_id}. Skipping.")
            continue

        output_path = output_dir / f"{section_id}.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(str(r))

        print(f"Content saved: {section_id}")

        time.sleep(1)

except Exception as e:
    print(f"Error {URL}: {e}")

print("done!")
