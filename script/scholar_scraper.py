from bs4 import BeautifulSoup
import requests
from rich import print
from pathlib import Path

BASE_URL = "https://www.liverpool.ac.uk/courses/computer-science-bsc-hons"
PARENT_DIR = Path(__file__).resolve().parent.parent # to the root of the project (go up two levels)

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

response = requests.get(BASE_URL, headers=headers, timeout=20)
response.raise_for_status()

html = response.content
soup = BeautifulSoup(html, "html.parser")

scholarship_section = soup.find("section", id="scholarships-list")
links = scholarship_section.find_all("a", href=True)

#loop for each scholarship link, scrape the scholarship page and save the content to an html file just the content from div that contains the data 
for link in links: 
    link_url = link.get("href")
    request = requests.get(link_url, headers=headers, timeout=20)
    request.raise_for_status()
    link_soup = BeautifulSoup(request.content, "html.parser")

    title = link_soup.find('h1').get_text(strip=True).replace(" ", "_")
    r = link_soup.find('div', class_='rb-content-flow')

    output_path = PARENT_DIR / "data" / "scholarships" / f"{title}.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(str(r))