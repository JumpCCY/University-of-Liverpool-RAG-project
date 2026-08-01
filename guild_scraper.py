import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin

def clean_text(text):
    """
    Cleans the scraped text by removing excessive whitespace, 
    newlines, and carriage returns.
    """
    if not text:
        return ""
    # Replace any sequence of whitespace characters (newlines, tabs, spaces) with a single space
    cleaned = re.sub(r'\s+', ' ', text)
    return cleaned.strip()

def scrape_liverpool_guilds():
    # Base URL determined from the meta tags in your HTML snippet
    base_url = "https://www.liverpoolguild.org"
    groups_page_url = f"{base_url}/groups/"
    
    print(f"Fetching main groups page at {groups_page_url}...")
    
    try:
        response = requests.get(groups_page_url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the main page: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 1. Find all guild links from the main page
    society_links = soup.find_all('a', class_='msl-gl-link')
    
    guilds_data = []
    
    print(f"Found {len(society_links)} groups. Beginning extraction...")
    
    # 2. Iterate through each link, visit the page, and extract info
    for index, link in enumerate(society_links, 1):
        href = link.get('href')
        if not href:
            continue
            
        # Construct the full absolute URL
        full_guild_url = urljoin(base_url, href)
        print(f"[{index}/{len(society_links)}] Scraping: {full_guild_url}")
        
        try:
            guild_response = requests.get(full_guild_url)
            guild_response.raise_for_status()
            guild_soup = BeautifulSoup(guild_response.text, 'html.parser')
            
            # Extract Guild Name (h1), ignoring "UPCOMING EVENTS"
            guild_name = "Name Not Found"
            for h1_tag in guild_soup.find_all('h1'):
                temp_name = h1_tag.text.strip()
                if temp_name and "UPCOMING EVENTS" not in temp_name.upper():
                    guild_name = clean_text(temp_name)
                    break # Stop looking once we find the primary h1
            
            # Extract Short Description (<p class="mslwidget grp-shrt-desc">)
            short_desc_tag = guild_soup.find('p', class_='mslwidget grp-shrt-desc')
            short_desc = clean_text(short_desc_tag.text) if short_desc_tag else ""
            
            # Extract Long Description (<div class="mslwidget grp-lng-desc">)
            long_desc_tag = guild_soup.find('div', class_='mslwidget grp-lng-desc')
            long_desc = clean_text(long_desc_tag.text) if long_desc_tag else ""
            
            # Build the dictionary for this specific guild
            guild_info = {
                "guild_name": guild_name,
                "url": full_guild_url,
                "short_description": short_desc,
                "long_description": long_desc
            }
            
            guilds_data.append(guild_info)
            
            # Be polite to the server: wait 1 second between requests
            time.sleep(1)
            
        except requests.exceptions.RequestException as e:
            print(f"  -> Failed to load page: {e}")
            continue

    # 3. Save the collected data to a JSON file
    output_filename = 'liverpool_guilds.json'
    with open(output_filename, 'w', encoding='utf-8') as json_file:
        json.dump(guilds_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"\nScraping complete! Data successfully saved to {output_filename}")

if __name__ == "__main__":
    scrape_liverpool_guilds()