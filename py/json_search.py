import json

DATA_DIR = "json/"
QUALIFICATION_MAP = {
    "University of Liverpool":  "liverpool_qualifications.json",
    "University of York":       "york_qualifications.json",
    "University of Leeds":      "leeds_qualifications.json",
    "University of Manchester": "manchester_qualifications.json",
    "Newcastle University":  "newcastle_qualifications.json",
    "University of Sheffield":  "sheffield_qualifications.json",
    "University of Nottingham": "nottingham_qualifications.json",
    "University of Lancaster":  "lancaster_qualifications.json",
}

def load_universities(universities: list) -> dict[str, list[dict]]:
    """
    Loads the qualification records for the given list of universities.

    return: dictionary where the keys are university names and the values are lists of qualification records (as dictionaries).
    """
    records = {}
    for uni in universities:
        file_name = QUALIFICATION_MAP.get(uni)
        if not file_name:
            continue  # skip unknown universities
        with open(f"{DATA_DIR}/{file_name}", "r") as f:
            records[uni] = json.load(f) # return list of dict of qualifications for each university
    return records #return can be multiple universities 
