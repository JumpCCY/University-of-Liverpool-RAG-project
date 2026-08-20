from bs4 import BeautifulSoup
import requests
from rich import print
from pathlib import Path
import time

URLS = [
        "https://www.liverpool.ac.uk/studentsupport/mental-wellbeing/",
        "https://www.liverpool.ac.uk/studentsupport/disabled-students/",
        "https://www.liverpool.ac.uk/studentsupport/trans-nonbinary-students/",
        "https://www.liverpool.ac.uk/studentsupport/support-in-global-crises/",
        "https://www.liverpool.ac.uk/studentsupport/safe-welcoming-campus/",
        "https://www.liverpool.ac.uk/studentsupport/crisis/",
        "https://www.liverpool.ac.uk/studentsupport/money-advice/",

        # the pages above are mostly index pages, the actual detail is one level down
        "https://www.liverpool.ac.uk/studentsupport/mental-wellbeing/wellbeing-advice/",
        "https://www.liverpool.ac.uk/studentsupport/mental-wellbeing/wellbeing-advice/healthassured/",
        "https://www.liverpool.ac.uk/studentsupport/mental-wellbeing/counselling-service/",
        "https://www.liverpool.ac.uk/studentsupport/mental-wellbeing/mental-health-advisory-service/",
        "https://www.liverpool.ac.uk/studentsupport/mental-wellbeing/mental-health-project/",
        "https://www.liverpool.ac.uk/studentsupport/mental-wellbeing/self-help/",
        "https://www.liverpool.ac.uk/studentsupport/disabled-students/introducing-disability-support/",
        "https://www.liverpool.ac.uk/studentsupport/disabled-students/accessing-support/",
        "https://www.liverpool.ac.uk/studentsupport/disabled-students/support/",
        # workshops-and-events skipped, 334 chars and it is an events listing that goes stale
        ]

PARENT_DIR = Path(__file__).resolve().parent.parent # to the root of the project (go up two levels)

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

output_dir = PARENT_DIR / "data" / "liverpool" / "support"
output_dir.mkdir(parents=True, exist_ok=True)

for url in URLS:
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        html = response.content
        soup = BeautifulSoup(html, "html.parser")

        title = url.replace("https://www.liverpool.ac.uk/studentsupport/", "").replace("/", "_").strip("_")

        # these pages have no <main>, the content sits in section#main-content
        r = soup.find("section", id="main-content")

        if r is None:
            print(f"Warning: No content found for {url}. Skipping.")
            continue

        output_path = output_dir / f"{title}.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(str(r))

        print(f"Content saved: {title}")

        time.sleep(1)
    except Exception as e:
        print(f"Error {url}: {e}")

print("done!")
