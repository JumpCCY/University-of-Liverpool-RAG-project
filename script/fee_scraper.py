import json, re
from bs4 import BeautifulSoup
import requests

def clean(t): return re.sub(r"\s+", " ", t or "").strip()

URL = "https://www.liverpool.ac.uk/courses/computer-science-bsc-hons"

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

response = requests.get(URL, headers=headers, timeout=20)
response.raise_for_status()

html = response.content

section = BeautifulSoup(html, "html.parser").find("section", id="fees-and-funding")
pullout = section.find("div", class_="rb-pullout")

data = []
for h4 in pullout.find_all("h4"):
    p = h4.find_next_sibling("p")
    if not p: continue
    for br in p.find_all("br"): br.replace_with("\n")
    info = [clean(l) for l in p.get_text().split("\n") if clean(l)]
    data.append({"title": clean(h4.get_text()), "info": info})

json.dump(data, open("data/liverpool/json/fees.json", "w"), indent=4, ensure_ascii=False)