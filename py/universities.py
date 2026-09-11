import re

MAIN_UNIVERSITY = "University of Liverpool"

# the one list of universities we hold. adding a university is one line here, plus its
# data/<folder>/ files and a rebuild of the vector database (embeddings/populate_vector_db.py).
#   folder     - its directory under data/. also the city name we look for in a question
#   collection - its Chroma collection
UNIVERSITIES = {
    "University of Liverpool":  {"folder": "liverpool",  "collection": "my_collection"},
    "University of York":       {"folder": "york",       "collection": "york"},
    "University of Leeds":      {"folder": "leeds",      "collection": "leeds"},
    "University of Manchester": {"folder": "manchester", "collection": "manchester"},
    "Newcastle University":     {"folder": "newcastle",  "collection": "newcastle"},
    "University of Sheffield":  {"folder": "sheffield",  "collection": "sheffield"},
    "University of Nottingham": {"folder": "nottingham", "collection": "nottingham"},
    "University of Lancaster":  {"folder": "lancaster",  "collection": "lancaster"},
}

# these share a city name with a university we hold, so strip them before matching
OTHER_INSTITUTIONS = re.compile(
    r"liverpool john moores|ljmu|manchester metropolitan|mmu|leeds beckett|"
    r"leeds trinity|york st john|sheffield hallam|nottingham trent|northumbria",
    re.I,
)


def named_universities(query: str) -> list[str]:
    """Search the query for any of the universities we hold, returning a list of their names."""
    q = OTHER_INSTITUTIONS.sub(" ", query.lower())  # so "liverpool john moores" is not us

    found = [MAIN_UNIVERSITY]
    for uni, info in UNIVERSITIES.items():
        if uni not in found and re.search(rf"\b{info['folder']}\b", q):
            found.append(uni)

    return found
