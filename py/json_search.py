import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# every university has its own folder under data/, all built the same way, so adding a
# rival is one line here plus a data/<folder>/json/qualifications.json beside it.
UNIVERSITY_FOLDER = {
    "University of Liverpool":  "liverpool",
    "University of York":       "york",
    "University of Leeds":      "leeds",
    "University of Manchester": "manchester",
    "Newcastle University":     "newcastle",
    "University of Sheffield":  "sheffield",
    "University of Nottingham": "nottingham",
    "University of Lancaster":  "lancaster",
}

def load_universities(universities: list) -> dict[str, list[dict]]:
    """
    Loads the qualification records for the given list of universities.

    return: dictionary where the keys are university names and the values are lists of qualification records (as dictionaries).
    """
    records = {}
    for uni in universities:
        folder = UNIVERSITY_FOLDER.get(uni)
        if not folder:
            continue  # skip unknown universities
        path = os.path.join(DATA_DIR, folder, "json", "qualifications.json")
        with open(path, "r") as f:
            records[uni] = json.load(f) # return list of dict of qualifications for each university
    return records #return can be multiple universities
