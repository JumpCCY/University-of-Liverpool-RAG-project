import json
import os

from universities import UNIVERSITIES

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

def load_universities(universities: list) -> dict[str, list[dict]]:
    """
    Loads the qualification records for the given list of universities.

    return: dictionary where the keys are university names and the values are lists of qualification records (as dictionaries).
    """
    records = {}
    for uni in universities:
        info = UNIVERSITIES.get(uni)
        if not info:
            continue  # skip unknown universities
        path = os.path.join(DATA_DIR, info["folder"], "json", "qualifications.json")
        with open(path, "r") as f:
            records[uni] = json.load(f) # return list of dict of qualifications for each university
    return records #return can be multiple universities
