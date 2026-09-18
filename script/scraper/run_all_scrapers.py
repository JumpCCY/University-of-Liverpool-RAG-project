import subprocess
import sys
from pathlib import Path

SCRAPER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRAPER_DIR.parents[1]
THIS_FILE = Path(__file__).name

# the citation links are worked out from the pages that were saved, so they go stale as soon as a
# page is added, removed or renamed. rebuilding them here means a re-scrape is never left half done
SOURCE_URLS = PROJECT_ROOT / "script" / "source_urls.py"


def run(script: Path) -> bool:
    """Runs one script from the project root and says whether it worked."""
    print("")
    print("=" * 60)
    print(f"Running {script.name}")
    print("=" * 60, flush=True)

    result = subprocess.run([sys.executable, str(script)], cwd=PROJECT_ROOT)

    print(f"{'OK' if result.returncode == 0 else 'FAILED'}: {script.name}", flush=True)
    return result.returncode == 0


scrapers = []
for file in sorted(SCRAPER_DIR.glob("*.py")):
    if file.name == THIS_FILE:
        continue
    if file.name.startswith("__"):
        continue
    scrapers.append(file)

print(f"Found {len(scrapers)} scrapers")

# source_urls.py runs even when a scraper failed: the pages that did save still need their links,
# and it stops with its own error if what is on disk does not match the scrapers' URL lists
steps = scrapers + [SOURCE_URLS]

failed = []
for step in steps:
    if not run(step):
        failed.append(step.name)

print("")
print("=" * 60)
print("Summary")
print("=" * 60)

if failed:
    for name in failed:
        print(f"Failed: {name}")
else:
    print("All scrapers finished without errors, and the citation links were rebuilt")

print(f"{len(steps) - len(failed)} of {len(steps)} succeeded")
print("")
print("Next: python py/embeddings/populate_vector_db.py   (the database still holds the old pages)")
print("      python script/json_converter.py              (only if you edited a spreadsheet in data/raw)")
