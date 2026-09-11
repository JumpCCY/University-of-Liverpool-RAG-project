import os
import re

import chromadb
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)
from rich import print

import models
from universities import MAIN_UNIVERSITY, UNIVERSITIES, named_universities

CHROMA_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db"
)

client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

ollama_ef = OllamaEmbeddingFunction(
    url=models.OLLAMA_URL,
    model_name=models.EMBEDDING,
)

collection = client.get_collection(
    UNIVERSITIES[MAIN_UNIVERSITY]["collection"], embedding_function=ollama_ef
)

# these are noises which containes in almost every chunk so we have to match them up and then push them back by penalty
BOILERPLATE_SECTIONS = re.compile(
    r"completing your application|submitting your application|personal statement|"
    r"application step|supporting your application|additional information|"
    r"decisions|how to apply|how do i apply",
    re.I,
)
BOILERPLATE_PENALTY = 0.15

SCHOLARSHIP_POOL = 100  # every scholarship chunk, so no scholarship is missed
MODULE_POOL = (
    100  # every module chunk, so no module is missed from a year/semester list
)
FOCUS_MARGIN = (
    0.12  # one scholarship this much closer than the next = a question about that one
)

# regex for scholarship related terms.
SCHOLARSHIP_WORDS = re.compile(
    r"scholarship|bursar|funding|financial (?:support|help|aid)|hardship", re.I
)
GUILD_WORDS = re.compile(r"\b(?:societ(?:y|ies)|clubs?|guild|union|freshers)\b", re.I)
# regex on curriculum wording scopes the search to what is taught.
# a match drives a hard source_type filter, not a re-rank, so it must only fire on
# wording that names teaching. "anything on/about x" used to be in here and matched
# "anything on campus" and "anything about accommodation", which made guild and
# general documents unreturnable for those questions. a miss only costs an unfiltered
# search, so the miss is the cheaper failure and the wording here biases that way.
CURRICULUM_WORDS = re.compile(
    # "machine learning" is a subject name, not a request to be taught - without
    # these it made every AI question, including a Liverpool-vs-Sheffield
    # comparison, filter down to modules and drop the general and support pages.
    r"\b(?:modules?|teach(?:es|ing)?|taught|stud(?:y|ies|ied|ying)|subjects?|"
    r"syllabus|curriculum|cover(?:s|ed)?|content|"
    r"(?<!machine )(?<!deep )(?<!reinforcement )(?<!statistical )learn(?:s|ing|t)?)\b",
    re.I,
)
CURRICULUM_SCOPE = ["module", "course_info", "fee"]


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


SCHOLARSHIP_TITLES = {}  # every scholarship name in the vector database

scholarships = collection.get(
    where={"source_type": "scholarship"}, include=["metadatas"]
)["metadatas"]

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

    longest_title = max(
        matched_titles, key=len
    )  # just incase there are the same name but with shorter ones

    return longest_title


def to_answer(doc: str, meta: dict, dist: float) -> dict:
    """Build the result dict used everywhere in this module."""
    return {
        "distance": dist,
        "source_type": meta.get("source_type"),
        "document": doc,
        "metadata": meta,
    }


def query_rows(results: chromadb.QueryResult) -> list[tuple]:
    """get the query result from chroma and turn it into a lists"""
    return list(
        zip(results["documents"][0], results["metadatas"][0], results["distances"][0])
    )


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
    """

    named = named_scholarship(
        search_query
    )  # detect scholarship name in the query, if theres any match
    # work like search in modules. search that scholarship directly by its name and return all chunks of that scholarship if the query is about a specific scholarship
    if named:
        record = collection.get(
            where={"scholarship_title": named}, include=["documents", "metadatas"]
        )
        results = []
        for d, m in zip(record["documents"], record["metadatas"]):
            results.append(to_answer(d, m, 0.0))
        return results

    # search all scholarship rank with them in a list of tuples
    rows = query_rows(
        collection.query(
            query_texts=[search_query],
            where={"source_type": "scholarship"},
            n_results=SCHOLARSHIP_POOL,
        )
    )

    # keep the best chunk per scholarship, preferring sections that actually the closest
    best = {}
    for doc, meta, dist in rows:
        title = meta.get("scholarship_title")
        if not title:
            continue
        score = dist + (
            BOILERPLATE_PENALTY
            if BOILERPLATE_SECTIONS.search(meta.get("section", ""))
            else 0.0
        )  # if there's some noise such as apply step, completing application we add penalty
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


def vector_similarity_search(
    original_query: str, search_query: str, n_results: int
) -> list[dict]:
    """
    Performs a vector similarity search on the ChromaDB collection.

    return: A list of dictionaries containing the search results, each with keys "distance", "source_type", and "document".

    Which retrieval path runs is decided here from the query itself - a module code,
    scholarship wording, society wording, or a year/semester/credit facet. Anything
    else is an unfiltered search.
    """

    # find all things related to module codes, credits, years, and semesters in the original query (this is for modules searching)
    module_codes = re.findall(
        r"\b[A-Z]{2,4}\d{3}\b", original_query.upper()
    )  # return list
    credits = []  # return list
    for c in re.findall(r"(\d+)[- ]?credits?", original_query.lower()):
        credits.append(int(c))
    years = extract_year(original_query)  # return list
    semesters = extract_semester(original_query)  # return list

    result_list = []

    # a module code is an exact identifier, so look it up directly instead of searching
    if module_codes:
        results = collection.get(
            where={"code": {"$in": module_codes}}, include=["documents", "metadatas"]
        )
        for doc, meta in zip(results["documents"], results["metadatas"]):
            result_list.append(to_answer(doc, meta, 0.0))  # exact match, so distance is 0
        return result_list

    # if the regex detexts any scholarship wording in the query we search for scholarships only.
    if SCHOLARSHIP_WORDS.search(original_query):
        return scholarship_search(search_query, n_results)

    # if there are any guild/society wording in the query we search for guilds/societies only.
    if GUILD_WORDS.search(original_query):
        results = collection.query(
            query_texts=[search_query],
            where={"source_type": "guild"},
            n_results=n_results,
        )
        for doc, meta, dist in query_rows(results):
            result_list.append(to_answer(doc, meta, dist))
        return result_list

    # now we check for multiple filters credits year semester ex. "modules with 20 credits in year 2 semester 1" or "modules in year 3 semester 2 with 10 credits"
    facets = []
    if credits:
        facets.append({"credits": {"$in": credits}})
    if years:
        facets.append({"year": {"$in": years}})
    if semesters:
        facets.append({"semester": {"$in": semesters}})

    curriculum = bool(
        CURRICULUM_WORDS.search(original_query)
    )  # check if the query contains any curriculum wording, if so we search for modules only. ex. "modules in year 2 semester 1" or "modules with 20 credits"

    # if there are any facets and the query is about curriculum we search for modules only, otherwise we search for everything
    if facets and curriculum:
        module_filter = facets[0] if len(facets) == 1 else {"$and": facets}
        rows = query_rows(
            collection.query(
                query_texts=[search_query], where=module_filter, n_results=MODULE_POOL
            )
        )
        context = collection.query(
            query_texts=[search_query],
            where={"source_type": {"$ne": "module"}},
            n_results=n_results,
        )
        rows += query_rows(context)
    elif curriculum:
        # something related to course but didnt specify any year/semester/credits
        results = collection.query(
            query_texts=[search_query],
            where={"source_type": {"$in": CURRICULUM_SCOPE}},
            n_results=n_results,
        )
        rows = query_rows(results)
    else:
        results = collection.query(query_texts=[search_query], n_results=n_results)
        rows = query_rows(results)

    # normal function for returning the results as a list of dicts with keys "distance", "source_type", and "document"
    for doc, meta, dist in rows:
        result_list.append(to_answer(doc, meta, dist))

    return result_list


def rival_search(university: str, search_query: str, n_results: int) -> list[dict]:
    """
    search for rival universities that are not University of Liverpool. the rival universities are detected from the query by regex. if theres any match we search for that university's collection.
    """
    info = UNIVERSITIES.get(university)
    if not info:
        print(f"no collection for {university}")
        return []
    name = info["collection"]

    try:
        rival = client.get_collection(name, embedding_function=ollama_ef)
    except Exception:
        # incase the rival collections are empty.
        print(f"collection '{name}' unavailable for {university}")
        return []

    results = []
    rival_search_results = rival.query(query_texts=[search_query], n_results=n_results)
    for doc, meta, dist in query_rows(rival_search_results):
        results.append(to_answer(doc, meta, dist))

    return results


def search_all_universities(
    original_query: str, search_query: str, n_results: int
) -> dict[str, list[dict]]:
    """
    Search every university the query names. Liverpool between liverpool and rivals (detected from regex).

    dict of university name -> list of result dicts with keys "distance", "source_type", and "document".
    n_results is how many each university gets - set by the caller (RAG_main.N_RESULTS).

    return: dict of university name -> list of result dicts
    """
    universities = named_universities(original_query)

    results = {}
    for uni in universities:
        if uni == MAIN_UNIVERSITY:
            results[uni] = vector_similarity_search(
                original_query, search_query, n_results
            )  # main function to search for University of Liverpool DB
        else:
            results[uni] = rival_search(uni, search_query, n_results)

    return results


if __name__ == "__main__":
    # try the retrieval on its own, no LLM calls: python vector_search.py
    from rich.markup import escape

    from RAG_main import N_RESULTS  # the same number the pipeline uses

    query = input("\nEnter your query for vector similarity search (blank to quit): ")
    if not query.strip():
        exit()

    for uni, rows in search_all_universities(query, query, N_RESULTS).items():
        print(f"\n[bold]{uni}[/bold] - {len(rows)} results")
        for r in rows:
            snippet = " ".join(r["document"].split())
            print(f"  {r['distance']:.3f}  {str(r['source_type']):<12} {escape(snippet)}")
            print("-" * 80)
