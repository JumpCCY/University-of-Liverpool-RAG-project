import os
import chromadb
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)
import re
from rich import print
import models
from json_search import UNIVERSITY_FOLDER

CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db")

client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

ollama_ef = OllamaEmbeddingFunction(
    url=models.OLLAMA_URL,
    model_name=models.EMBEDDING,
)

collection = client.get_collection("my_collection", embedding_function=ollama_ef)

# a handful of societies and modules exist on the site as a name with no description.
# embedded as a bare name they land near the centre of the vector space, which makes
# them moderately close to EVERY query - "Indie Society" was the most retrieved guild
# document in testing, ahead of every society that actually has content. we keep them
# (they are real) but only let them through on a strong, direct match.
MIN_INFO_CHARS = 40
LOW_INFO_MAX_DISTANCE = 0.30

# these are noises which containes in almost every chunk so we have to match them up and then push them back by penalty
BOILERPLATE_SECTIONS = re.compile(
    r"completing your application|submitting your application|personal statement|"
    r"application step|supporting your application|additional information|"
    r"decisions|how to apply|how do i apply",
    re.I,
)
BOILERPLATE_PENALTY = 0.15

SCHOLARSHIP_POOL = 100      # every scholarship chunk, so no scholarship is missed
MODULE_POOL = 100           # every module chunk, so no module is missed from a year/semester list
FOCUS_MARGIN = 0.12         # one scholarship this much closer than the next = a question about that one

# each university has its own collection, so rebuilding one does not re-embed the others
UNIVERSITY_COLLECTIONS = {
    "University of Liverpool":  "my_collection",
    "University of Manchester": "manchester",
    "University of Sheffield":  "sheffield",
    "University of Leeds":      "leeds",
    "Newcastle University":     "newcastle",
    "University of Nottingham": "nottingham",
    "University of York":       "york",
    "University of Lancaster":  "lancaster",
}

# these share a city name with a university we hold, so strip them before matching
OTHER_INSTITUTIONS = re.compile(
    r"liverpool john moores|ljmu|manchester metropolitan|mmu|leeds beckett|"
    r"leeds trinity|york st john|sheffield hallam|nottingham trent|northumbria",
    re.I,
)


# the related information we group it together so that if the user is searching for one of them we can return all of them (n).
SCOPE_GROUPS = {
    "module":      ["module", "course_info", "fee"],
    "course_info": ["module", "course_info", "fee"],
    "fee":         ["module", "course_info", "fee"],
}


def normalise(text: str) -> str:
    """cleaning the text make it lower case remove additional space and symbol"""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def title_keys(title: str) -> set[str]:
    """
    clearn the text and creates different versions that could appear in a question.
    """
    base = normalise(title)
    keys = {base, re.sub(r"^the ", "", base)}
    for k in list(keys):
        words = k.split()
        if words and words[-1].endswith("s"):
            keys.add(" ".join(words[:-1] + [words[-1][:-1]]))
    # return a dict of scholarship variations with char > 8
    long_enough = set()
    for k in keys:
        if len(k) > 8:
            long_enough.add(k)
    return long_enough


SCHOLARSHIP_TITLES = {} # every scholarship name in the vector database

scholarships = collection.get(where={"source_type": "scholarship"},include=["metadatas"])["metadatas"]

# get all name of scholarships in the database and then store it in a dict with different variations 
for m in scholarships:
    if m.get("scholarship_title"):
        title = m["scholarship_title"]
        SCHOLARSHIP_TITLES[title] = title_keys(title) 

def named_scholarship(query: str) -> str | None:
    """Return the scholarship the query names, if it names one."""
    q = normalise(query)

    matched_titles = []

    # if theres any match title in the query if there's one we exit the loop 
    for title, keys in SCHOLARSHIP_TITLES.items():
        for key in keys:
            if key in q:
                matched_titles.append(title)
                break

    if not matched_titles:
        return None

    longest_title = max(matched_titles, key=len) # just incase there are the same name but with shorter ones

    return longest_title


def informative_body(document: str) -> str:
    """
    Strip the prefix added at ingest so only the descriptive text is measured.
    Covers the four document shapes built in populate_vector_db.py.
    """
    if "\n" in document:                      # scholarship / general: "[crumb] heading\nbody"
        return document.split("\n", 1)[1].strip()
    if "] " in document:                      # module: "CODE: Title [credits, year...] description"
        return document.split("] ", 1)[1].strip()
    if " : " in document:                     # guild / fee / course_info: "Name : description"
        return document.split(" : ", 1)[1].strip()
    return document.strip()


def is_low_info(document: str) -> bool:
    """A document with no body carries no signal beyond its own name."""
    return len(informative_body(document)) < MIN_INFO_CHARS


def to_answer(doc: str, meta: dict, dist: float) -> dict:
    """Build the result dict used everywhere in this module."""
    return {"distance": dist, "source_type": meta.get("source_type"), "document": doc, "metadata": meta}


def query_rows(results: chromadb.QueryResult) -> list[tuple]:
    """get the query result from chroma and turn it into a lists"""
    return list(zip(results["documents"][0], results["metadatas"][0], results["distances"][0]))


def drop_low_info(rows: list[tuple]) -> list[tuple]:
    """
    Remove name-only documents unless they are a strong direct match.
    """
    filtered_rows = []
    for r in rows:
        document = r[0]
        distance = r[2]

        # get only rows that is not low information such as empty page or the one that has low distance ex. direct name match 
        if not is_low_info(document) or distance < LOW_INFO_MAX_DISTANCE:
            filtered_rows.append(r)

    return filtered_rows


def metadata_search(search_result: chromadb.GetResult, result_list: list):
    """
    helper function to process search results from metadata search to list of dicts with keys "distance", "source_type", and "document".
    """
    doc = search_result["documents"]
    meta = search_result["metadatas"]

    for d, m in zip(doc, meta):
        answer = {}
        answer["distance"] = 0.0  # exact match, so distance is 0
        answer["source_type"] = m.get("source_type")
        answer["document"] = d
        answer["metadata"] = m  # include the metadata in the answer
        result_list.append(answer)


def extract_year(q) -> list[int]:
    """
    Extracts the year information from the query. if the query asking about year. for searching a module
    """
    q = q.lower()
    years = []
    for x in re.findall(r"year\s*([123])", q):
        years.append(int(x))
    for x in re.findall(r"([123])(?:st|nd|rd)\s*year", q):
        years.append(int(x))
    for w, n in {"first": 1, "second": 2, "third": 3, "final": 3}.items():
        if re.search(rf"\b{w}\s+year", q):
            years.append(n)
    return sorted(set(years))

def extract_semester(q) -> list[str]:
    """
    Extracts the semester information from the query. for searching a module
    """
    q = q.lower()
    words = {"one": "1", "two": "2", "first": "1", "second": "2"}
    NUM = r"(?:one|two|first|second|[12])"

    # "semester 1 and 2", "semester one and two", "semester 2 and 1", "semesters 1, 2"
    m = re.search(rf"semesters?\s*({NUM}(?:\s*(?:and|,|&|or)\s*{NUM})*)", q)
    if m:
        nums = re.findall(NUM, m.group(1))
        found = []
        for n in nums:
            found.append(f"Semester {words.get(n, n)}")
        return found

    # "1st semester", "first semester", "2nd and 1st semester"
    m = re.search(
        rf"({NUM}(?:st|nd)?(?:\s*(?:and|,|&|or)\s*{NUM}(?:st|nd)?)*)\s*semesters?", q
    )
    if m:
        nums = re.findall(NUM, m.group(1))
        found = []
        for n in nums:
            found.append(f"Semester {words.get(n, n)}")
        return found

    if re.search(r"\b(?:whole|entire)\s+(?:session|year)", q):
        return ["Whole Session"]

    return []


def scholarship_search(search_query: str, n_results: int) -> list[dict]:
    """
    Retrieve at the SCHOLARSHIP level instead of the chunk level.

    Ranking chunks lets a few scholarships fill every slot with near-identical
    application paperwork while most of the 15 never reach the answerer - staff were
    being told "we hold details for six scholarships" when there are 15. Scoring each
    scholarship by its best substantive chunk guarantees breadth instead.
    """

    named = named_scholarship(search_query) # detect scholarship name in the query, if theres any match 
    # work like search in modules. search that scholarship directly by its name and return all chunks of that scholarship if the query is about a specific scholarship
    if named:
        record = collection.get(where={"scholarship_title": named}, include=["documents", "metadatas"])
        results = []
        for d, m in zip(record["documents"], record["metadatas"]):
            results.append(to_answer(d, m, 0.0))
        return results

    # search all scholarship rank with them in a list of tuples 
    rows = query_rows(collection.query(
        query_texts=[search_query],
        where={"source_type": "scholarship"},
        n_results=SCHOLARSHIP_POOL,
    ))

    # keep the best chunk per scholarship, preferring sections that actually the closest 
    best = {}
    for doc, meta, dist in rows:
        title = meta.get("scholarship_title")
        if not title:
            continue
        score = dist + (BOILERPLATE_PENALTY if BOILERPLATE_SECTIONS.search(meta.get("section", "")) else 0.0) # if there's some noise such as apply step, completing application we add penalty 
        # so we test for every title which one is the best match then we keep those in dict, there are multiple best from different titles.
        if title not in best or score < best[title][0]:
            best[title] = (score, dist, doc, meta)

    ordered = sorted(best.values())

    # if one scholarship distance is clearly seperated then we return only that scholarship, otherwise we return the top n_results (normal search) scholarships
    if len(ordered) >= 2 and ordered[1][0] - ordered[0][0] > FOCUS_MARGIN:
        focused = collection.get(
            where={"scholarship_title": ordered[0][3]["scholarship_title"]},
            include=["documents", "metadatas"],
        )
        results = []

        for d, m in zip(focused["documents"], focused["metadatas"]):
            answer = to_answer(d, m, ordered[0][1])
            results.append(answer)

        return results

    results = []

    for item in ordered[:n_results]:
        dist = item[1]
        doc = item[2]
        meta = item[3]

        answer = to_answer(doc, meta, dist)
        results.append(answer)

    return results


def vector_similarity_search(original_query: str, search_query: str = None, source_type: str = None, n_results: int = 5) -> list[dict]:
    """
    Performs a vector similarity search on the ChromaDB collection.

    return: A list of dictionaries containing the search results, each with keys "distance", "source_type", and "document".

    source_type can be one of the following: "module", "course_info", "guild", "scholarship", "fee", "general"
    """

    # this is for rewriting 
    if search_query is None:
        search_query = original_query

    #find all things related to module codes, credits, years, and semesters in the original query (this is for modules searching)
    module_codes = re.findall(r"\b[A-Z]{2,4}\d{3}\b", original_query.upper())  # return list
    credits = []  # return list
    for c in re.findall(r"(\d+)[- ]?credits?", original_query.lower()):
        credits.append(int(c))
    years = extract_year(original_query)  # return list
    semesters = extract_semester(original_query)  # return list

    result_list = []

    # a module code is an exact identifier, so look it up directly instead of searching
    if module_codes:
        results = collection.get(where={"code": {"$in": module_codes}}, include=["documents", "metadatas"])
        metadata_search(results, result_list)
        return result_list

    # scholarship questions are about scholarships, not chunks - handled separately
    if source_type == "scholarship":
        return scholarship_search(search_query, n_results)

    # now we check for multiple filters credits year semester ex. "modules with 20 credits in year 2 semester 1" or "modules in year 3 semester 2 with 10 credits"
    facets = []
    if credits:
        facets.append({"credits": {"$in": credits}})
    if years:
        facets.append({"year": {"$in": years}})
    if semesters:
        facets.append({"semester": {"$in": semesters}})

    # general means "search everything", so it has no scope of its own. anything else
    # widens to its scope group, or to just itself when it is big enough to stand alone.
    if source_type in (None, "general"):
        scope = None
    else:
        scope = SCOPE_GROUPS.get(source_type, [source_type])

    clauses = []
    if scope:
        if len(scope) == 1:
            scope_filter = {"source_type": scope[0]}
        else:
            scope_filter = {"source_type": {"$in": scope}}
        clauses.append(scope_filter)

    # when the router already said "module", the facets ARE the question, so apply them
    # straight. course_info and fee chunks have no year, semester or credits field, so
    # the $or below lets every one of them through unfiltered - and they match a phrase
    # like "year 2" BETTER than a module does, because a module only carries the year
    # inside its bracketed metadata while year_two_course_info says it in a sentence.
    # they took 12 of the 20 slots on "what modules are in year 2 semester 1" and pushed
    # COMP219 down to rank 27, so it never reached the answerer.
    # any other scope still needs the $or: "what is year 2 like" names a year but wants
    # course_info, which has no year field to match on and would otherwise be filtered out.
    if facets:
        if source_type == "module":
            clauses.extend(facets)
        else:
            module_filter = facets[0] if len(facets) == 1 else {"$and": facets} # if there is only one filter we just use that, if there are multiple filters we use $and to combine them.
            clauses.append({"$or": [module_filter, {"source_type": {"$ne": "module"}}]})

    if not clauses:
        filters = None # normal similarity search.
    elif len(clauses) == 1:
        filters = clauses[0]
    else:
        filters = {"$and": clauses}

    # search more then we need then drop low information documents and return only the top n_results
    # Semantic search + metadata filters

    # a module question WITH facets ("year 3 semester 2") is asking for a complete list,
    # and the filter already bounds it, so take the lot. we also keep the name-only
    # modules here - COMP346 has no description but it is still a real module the staff
    # member asked for, and a list that quietly misses one is worse than a short answer.
    # without the facets it is just a topic ranking, so it stays capped at n_results.
    if source_type == "module" and facets:
        results = collection.query(query_texts=[search_query], where=filters, n_results=MODULE_POOL)
        rows = query_rows(results)
    else:
        results = collection.query(query_texts=[search_query], where=filters, n_results=n_results * 3)
        rows = drop_low_info(query_rows(results))[:n_results] # get only top n_results after dropping low information documents.

    # normal function for returning the results as a list of dicts with keys "distance", "source_type", and "document"
    for doc, meta, dist in rows:
        result_list.append(to_answer(doc, meta, dist))

    return result_list


def named_universities(query: str) -> list[str]:
    """Universities the query names. Liverpool is always first, we compare against it."""
    q = OTHER_INSTITUTIONS.sub(" ", query.lower()) # so "liverpool john moores" is not us

    found = ["University of Liverpool"]
    for uni, folder in UNIVERSITY_FOLDER.items(): # the folder name is also the city keyword
        if uni not in found and re.search(rf"\b{folder}\b", q):
            found.append(uni)

    return found


def rival_search(university: str, search_query: str, n_results) -> list[dict]:
    """Rivals are lazily embedded, so no scope groups or facets here. Just the closest n."""
    name = UNIVERSITY_COLLECTIONS.get(university)
    if not name:
        print(f"no collection for {university}")
        return []

    try:
        rival = client.get_collection(name, embedding_function=ollama_ef)
    except Exception:
        return [] 

    results = []
    rival_search_results = rival.query(query_texts=[search_query], n_results=n_results)
    for doc, meta, dist in query_rows(rival_search_results):
        results.append(to_answer(doc, meta, dist))

    return results


def search_all_universities(original_query: str, search_query: str = None, source_type: str = None, n_results: int = 10) -> dict[str, list[dict]]:
    """
    Search every university the query names. Liverpool gets the full pipeline, rivals get a summary.
    If theres not any university name in the query we just search for University of Liverpool.

    return: dict of university name -> list of result dicts
    """
    if search_query is None:
        search_query = original_query

    if len(named_universities(original_query)) == 1 and named_universities(original_query)[0] == "University of Liverpool":
        n_results = 20

    results = {}
    for uni in named_universities(original_query):
        if uni == "University of Liverpool":
            results[uni] = vector_similarity_search(original_query, search_query, source_type, n_results) # main function to search for University of Liverpool DB 
        else:
            results[uni] = rival_search(uni, search_query, n_results)

    return results


if __name__ == "__main__":
    query = input("Enter your query for vector similarity search: ")
    # s = input("Enter the source type (module, course_info, guild, scholarship, fee, general) or leave blank for all: ")
    # r = search_all_universities(original_query=query, search_query=query, source_type=s or None)

    r = rival_search("University of Manchester" , query, 20)
    print(r)
