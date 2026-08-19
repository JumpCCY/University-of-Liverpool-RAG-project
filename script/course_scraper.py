from bs4 import BeautifulSoup
import requests
from rich import print
from pathlib import Path
import time

URL = "https://www.liverpool.ac.uk/courses/computer-science-bsc-hons"

#other sections we want to scrape from the course page, each will be saved to its own html file
SECTIONS = [
        "about-this-course",            
        "course-content",               
        "course-options",               
        "your-experience",              
        "careers-and-employability",    
        ]


PARENT_DIR = Path(__file__).resolve().parent.parent # to the root of the project (go up two levels)

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

output_dir = PARENT_DIR / "data" / "liverpool" / "course"
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
