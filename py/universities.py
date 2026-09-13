import difflib
import re

MAIN_UNIVERSITY = "University of Liverpool"

# the one list of universities we hold. adding a university is one line here, plus its
# data/<folder>/ files and a rebuild of the vector database (embeddings/populate_vector_db.py).
#   folder     - its directory under data/. also the city name we look for in a question
#   collection - its Chroma collection
#   aliases    - optional. abbreviations and misspellings, matched as whole words. the only
#                typo cover york and leeds get, as they are too short to fuzzy match (below)
UNIVERSITIES = {
    "University of Liverpool":  {"folder": "liverpool",  "collection": "my_collection"},
    "University of York":       {"folder": "york",       "collection": "york",       "aliases": ["uoy", "yrok", "yokr"]},
    "University of Leeds":      {"folder": "leeds",      "collection": "leeds",      "aliases": ["leesd", "leeeds"]},
    "University of Manchester": {"folder": "manchester", "collection": "manchester"},
    "Newcastle University":     {"folder": "newcastle",  "collection": "newcastle",  "aliases": ["ncl"]},
    "University of Sheffield":  {"folder": "sheffield",  "collection": "sheffield"},
    "University of Nottingham": {"folder": "nottingham", "collection": "nottingham", "aliases": ["uon"]},
    "University of Lancaster":  {"folder": "lancaster",  "collection": "lancaster"},
}

# these share a city name with a university we hold, so strip them before matching
OTHER_INSTITUTIONS = re.compile(
    r"liverpool john moores|ljmu|manchester metropolitan|mmu|leeds beckett|"
    r"leeds trinity|york st john|sheffield hallam|nottingham trent|northumbria",
    re.I,
)

# a name this long is also found when misspelled ("manchestr", "sheffeild"). short name are ignored because they are too common and fuzzy matching them would produce too many false positives.
FUZZY_MIN_LENGTH = 7
FUZZY_CUTOFF = 0.85  # one-letter typos score about 0.89 and up, the nearest everyday words about 0.80


def _mentioned(info: dict, q: str, words: list[str]) -> bool:
    """True if q names this university: by its name, one of its aliases, or a close misspelling of a long name."""
    for name in [info["folder"], *info.get("aliases", [])]:
        if re.search(rf"\b{re.escape(name)}\b", q): # stand alone word, not part of another word can only match
            return True
    if len(info["folder"]) < FUZZY_MIN_LENGTH:
        return False
    return bool(difflib.get_close_matches(info["folder"], words, n=1, cutoff=FUZZY_CUTOFF))


def named_universities(query: str) -> list[str]:
    """Search the query for any of the universities we hold, returning a list of their names."""
    q = OTHER_INSTITUTIONS.sub(" ", query.lower())  # so "liverpool john moores" is not us
    words = re.findall(r"[a-z]+", q)  # the fuzzy match compares whole words

    found = [MAIN_UNIVERSITY]
    for uni, info in UNIVERSITIES.items():
        # if the first main match doesnt match we use misspellings and fuzzy matching to find the university instead.
        if uni not in found and _mentioned(info, q, words):
            found.append(uni)

    return found
