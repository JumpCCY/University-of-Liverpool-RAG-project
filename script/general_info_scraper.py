from bs4 import BeautifulSoup
import requests
from rich import print
from pathlib import Path
import time

URLS = [
        #life on campus
        "https://www.liverpool.ac.uk/student-life/life-on-campus/study-spaces/",
        "https://www.liverpool.ac.uk/student-life/life-on-campus/accommodation/",
        "https://www.liverpool.ac.uk/student-life/life-on-campus/living-costs/",
        "https://www.liverpool.ac.uk/student-life/life-on-campus/resources/",
        "https://www.liverpool.ac.uk/student-life/life-on-campus/health/",

        #living in liverpool
        "https://www.liverpool.ac.uk/student-life/living-in-liverpool/",
        "https://www.liverpool.ac.uk/student-life/living-in-liverpool/getting-around/",
        "https://www.liverpool.ac.uk/student-life/living-in-liverpool/art-museums-festivals/",
        "https://www.liverpool.ac.uk/student-life/living-in-liverpool/getting-here/",
        "https://www.liverpool.ac.uk/student-life/living-in-liverpool/nightlife-music/",
        "https://www.liverpool.ac.uk/student-life/living-in-liverpool/theatre-and-performance/",
        "https://www.liverpool.ac.uk/student-life/living-in-liverpool/relaxing-eating-out/",
        "https://www.liverpool.ac.uk/student-life/living-in-liverpool/shopping/",
        "https://www.liverpool.ac.uk/student-life/living-in-liverpool/sport/",
        "https://www.liverpool.ac.uk/student-life/living-in-liverpool/hidden-gems/",

        #guilds info
        "https://www.liverpool.ac.uk/student-life/guild-of-students/",
        "https://www.liverpool.ac.uk/student-life/guild-of-students/clubs-and-societies/",

        #commuting
        
        "https://www.liverpool.ac.uk/student-life/local-commuter-students/why-commute/",
        "https://www.liverpool.ac.uk/student-life/local-commuter-students/things-to-do/",
        "https://www.liverpool.ac.uk/student-life/local-commuter-students/commuting/",

        #accommodation
        "https://www.liverpool.ac.uk/accommodation/applying/",
        "https://www.liverpool.ac.uk/accommodation/how-to-pay-your-fees/accommodation-discount/",
        "https://www.liverpool.ac.uk/accommodation/how-to-pay-your-fees/whatsincluded/",
        "https://www.liverpool.ac.uk/accommodation/how-to-pay-your-fees/",
        "https://www.liverpool.ac.uk/accommodation/life-in-halls/getting-around/",

        "https://www.liverpool.ac.uk/accommodation/find-accommodation/crown-place/",
        "https://www.liverpool.ac.uk/accommodation/find-accommodation/greenbank-student-village/",
        "https://www.liverpool.ac.uk/accommodation/find-accommodation/dover-court/",
        "https://www.liverpool.ac.uk/accommodation/find-accommodation/melville-grove/",
        "https://www.liverpool.ac.uk/accommodation/find-accommodation/philharmonic-court/",
        "https://www.liverpool.ac.uk/accommodation/find-accommodation/tudor-close/",
        "https://www.liverpool.ac.uk/accommodation/find-accommodation/vine-court/"

        ]

PARENT_DIR = Path(__file__).resolve().parent.parent # to the root of the project (go up two levels)

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

for url in URLS:
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        html = response.content
        soup = BeautifulSoup(html, "html.parser")

    #loop for each scholarship link, scrape the scholarship page and save the content to an html file just the content from div that contains the data 
        if "https://www.liverpool.ac.uk/student-life/" in url:
            title = url.replace("https://www.liverpool.ac.uk/student-life/", "").replace("/", "_").strip("_")

        elif "https://www.liverpool.ac.uk/accommodation/" in url:
            title = url.replace("https://www.liverpool.ac.uk/", "").replace("/", "_").strip("_")

        r = soup.find('main')

        if r is None:
            print(f"Warning: No content found for {url}. Skipping.")
            continue


        output_path = PARENT_DIR / "data" / "general" / f"{title}.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(str(r))

        print(f"Content saved: {title}")

        time.sleep(1)
    except Exception as e:
        print(f"Error {url}: {e}")

print("done!")