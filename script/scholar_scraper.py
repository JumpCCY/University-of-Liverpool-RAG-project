from bs4 import BeautifulSoup
import requests
import time
from rich import print
import json

BASE_URL = "https://www.liverpool.ac.uk/courses/computer-science-bsc-hons"

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

response = requests.get(BASE_URL, headers=headers, timeout=20)
response.raise_for_status()

html = response.content
soup = BeautifulSoup(html, "html.parser")

scholarship_section = soup.find("section", id="scholarships-list")
links = scholarship_section.find_all("a", href=True)


scholarships = []


# find schorlarship links and scrape each scholarship page start from the main course page
for link in links:
    scholar_url = link.get("href")

    scholar_name = scholar_url.split("/")[-2]
    print(f"Scraping {scholar_name}...")

    response = requests.get(scholar_url, headers=headers, timeout=20)
    response.raise_for_status()
    html = response.content
    soup = BeautifulSoup(html, "html.parser")

    article = soup.find("article")
    h1 = article.find("h1")
    title = h1.text.strip()

    scholarship = {"title": title, "content": [], "sections": []}

    current_section = None

    # if we find p before section title, we will add it to the main content of the scholarship (in else statement)

    for element in article.find_all(["h2", "h3", "p", "ul", "ol", "table"]):

        # sections titles 

        if element.name in ["h2", "h3"]:

            section_title = element.get_text(" ", strip=True)

            if not section_title:
                continue

            current_section = {"title": section_title, "content": []} #check if there are sections before adding to the list

            scholarship["sections"].append(current_section)


        # tables data

        elif element.name == "table":

            rows = []

            for tr in element.find_all("tr"):

                cells = tr.find_all(["th", "td"])

                row = [cell.get_text(" ", strip=True) for cell in cells]

                if row:
                    rows.append(" | ".join(row))

            text = "\n".join(rows)

            if not text:
                continue

            if current_section is not None:
                current_section["content"].append(text)
            else:
                scholarship["content"].append(text)

        # normal text content (paragraphs, lists, etc.)

        else:

            text = element.get_text(" ", strip=True)
            text = text.replace("\u00a0", " ")

            if not text:
                continue

            if current_section is not None: # if there are no sections, we will add the content to the main content of the scholarship 
                current_section["content"].append(text)
            else:
                scholarship["content"].append(text)

    scholarships.append(scholarship)

    time.sleep(1)

json_data = json.dumps(scholarships, indent=4, ensure_ascii=False)
with open("data/json/scholarships.json", "w", encoding="utf-8") as f:
    f.write(json_data)
