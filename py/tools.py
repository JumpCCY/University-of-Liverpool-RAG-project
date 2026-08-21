"""
The tools the agent node can call, and the code that runs them.

Shaped after the LangGraph agentic RAG tutorial
(https://docs.langchain.com/oss/python/langgraph/agentic-rag): the model is given a
set of retrieval tools and decides for itself whether to call one, call several, or
answer without retrieving anything. Written against our own llm.py instead of
LangGraph, so there is no new dependency and the ollama/openai switch in models.py
still works.

The tool descriptions are NOT written fresh here. They are the routing prompts we
already tuned in prompts.py, with only their "return one word" scaffolding removed -
so ROUTER, REWRITER and SOURCE_TYPE_ROUTER remain the single source of truth for how
questions are classified and how a search query is written.
"""

from json_search import load_universities
import prompts
from vector_search import search_all_universities, named_universities


# how many source types ONE search may widen to. Two source types means two searches
# merged into one context, and the answerer starts naming societies and bursaries that
# are not in the retrieved text once the context gets big - testing showed invented
# fees, scholarships and societies at three types. Note this does NOT limit how many
# TOOLS the model calls: an entry question that also asks about modules still gets both
# lookup_entry_requirements and search_knowledge_base. It also does not narrow a search
# to one slice, because SCOPE_GROUPS in vector_search already widens module to
# module + course_info + fee.
MAX_SOURCE_TYPES = 1

SOURCE_TYPES = ["module", "course_info", "guild", "scholarship", "fee", "general"]


def cut(text: str, start: str, end: str | None) -> str:
    """
    Remove everything from start up to end. end=None cuts to the end of the text.
    Raises if a marker is missing, so an edit to prompts.py that moves one of these
    headings fails loudly here instead of silently shipping a half-stripped prompt.
    """
    i = text.index(start)
    if end is None:
        return text[:i]
    j = text.index(end, i)
    return text[:i] + text[j:]


# ROUTER decides the KIND of question. Everything that makes that decision - the
# categories, the rules and the examples - is kept. Only the parts telling it to print
# a single word are removed, because here the choice is expressed as a tool call.
AGENT = cut(prompts.ROUTER, "OUTPUT FORMAT", "CATEGORIES (choose exactly one)")
AGENT = cut(AGENT, "8. Never output anything except the single category word.", "EXAMPLES")
AGENT = cut(AGENT, "FINAL INSTRUCTION", None)
AGENT += """
HOW TO ACT ON YOUR CHOICE

You do not output the category word. You act on it with tools:

  requirement -> call lookup_entry_requirements
  general     -> call search_knowledge_base
  unclear     -> call no tool, and ask the staff member what you need to know

CALLING A TOOL IS THE DEFAULT, and the rules above have already decided which one.
If the question has an identifiable topic it is requirement or general, and it gets
a tool call - that holds however short the question is, however vaguely it is worded,
and whoever it is about. Answering without a tool is only for the genuine fragments
described under unclear, where there is no topic to look anything up with. If you can
tell what you would search for, the question is not unclear and you must search.

A question can be under-specified and still perfectly searchable. When it does not
name the kind of help or information wanted, but it does describe the student or
their situation, that situation IS the topic: search for what we offer someone in it.
Do not ask the staff member to narrow it down first - they are mid-call, and the
search is how you find out what we have. Only when nothing whatever is named - no
topic, no situation, no thing - do you answer without a tool.

CALL BOTH TOOLS when the question genuinely has an entry part AND a non-entry part
(for example: what grades do we need, and what will she study in year 1). Do not
call both to hedge - only when both parts were actually asked.

In the examples above, the category word shown is the tool you would call.
"""

# REWRITER is already written as "turn this question into one search query", which is
# exactly what this argument is, so it is used whole.
SEARCH_QUERY_ARG = prompts.REWRITER

# SOURCE_TYPE_ROUTER minus the "return exactly one category name" scaffolding.
SOURCE_TYPE_ARG = cut(prompts.SOURCE_TYPE_ROUTER, "Return ONLY the category name.", "CATEGORY DEFINITIONS:")
SOURCE_TYPE_ARG = cut(SOURCE_TYPE_ARG, "FINAL OUTPUT:", None)
SOURCE_TYPE_ARG += """
Usually ONE category is right. Give a SECOND only when the question asks about two
genuinely different kinds of thing that live in different parts of the knowledge
base (for example tuition cost AND scholarships). Never add a second to hedge.
"""


TOOLS = [
    {
        "type": "function",
        "name": "lookup_entry_requirements",
        "description": (
            "Look up our structured entry-requirement records (grades, accepted "
            "qualifications, required subjects, contextual offers) for every university "
            "the question names. Use this for the requirement category. Takes no "
            "arguments - the universities are detected from the question text."
        ),
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "search_knowledge_base",
        "description": (
            "Semantic search over our knowledge base of prospectus pages: modules, course "
            "structure and pathways, fees, scholarships, societies, accommodation, student "
            "support and life in Liverpool. Use this for the general category."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "search_query": {"type": "string", "description": SEARCH_QUERY_ARG},
                "source_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": SOURCE_TYPES},
                    "description": SOURCE_TYPE_ARG,
                },
            },
            "required": ["search_query", "source_types"],
            "additionalProperties": False,
        },
    },
]


def knowledge_base_search(original_query: str, search_query: str, source_types: list[str], n_results: int = 20):
    """
    Runs one search per source type and merges them, keeping each document once.

    Args:
        original_query (str): what the staff member typed. University detection, module
            codes, years and semesters are all read off this, never off the rewrite.
        search_query (str): the embedding query the model wrote.
        source_types (list[str]): the scopes to search, already capped.
    Returns:
        dict: university name -> list of result dicts, nearest first.
    """
    if not source_types:
        source_types = ["general"]

    merged = {}
    for source_type in source_types:
        results = search_all_universities(original_query, search_query, source_type, n_results)
        for university, rows in results.items():
            bucket = merged.setdefault(university, [])
            seen = set()
            for existing in bucket:
                seen.add(existing["document"])
            for row in rows:
                if row["document"] not in seen:
                    bucket.append(row)
                    seen.add(row["document"])

    # one merged list per university, so the closest match leads regardless of which
    # search it came from
    for university in merged:
        merged[university].sort(key=lambda row: row["distance"])
    return merged


def run(name: str, arguments: dict, original_query: str) -> tuple:
    """
    Executes one tool call.

    Args:
        name (str): the tool the model asked for.
        arguments (dict): the arguments it filled in.
        original_query (str): what the staff member typed.
    Returns:
        (kind, payload). kind is "requirement" or "general" and says which answering
        prompt and which context builder the result needs.
    """
    if name == "lookup_entry_requirements":
        universities = named_universities(original_query)
        return "requirement", load_universities(universities)

    search_query = arguments.get("search_query")
    if not search_query:
        search_query = original_query

    source_types = arguments.get("source_types")
    if not source_types:
        source_types = ["general"]
    source_types = source_types[:MAX_SOURCE_TYPES]

    print(f"Search: {search_query} {source_types}")
    return "general", knowledge_base_search(original_query, search_query, source_types)
