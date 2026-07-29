import RAG_main

test_query = [
    # --- prompt-rule fixes (negative-claim + Yes-bolding) ---
    "what are the short 7-credit modules?",                 # -> partial list, NO "only"
    "is there a placement year?",                           # -> "we don't hold that", not "No"

    # --- separate-file fixes (router example + code-shortcut) ---
    "anything on robotics?",                                # -> COMP329 + COMP341 (router fix)
    "my daughter did CS A level — does she skip the intro programming module?",  # -> general branch (router fix)
    "is COMP105 a first year or second year module?",       # -> BOTH years (code-shortcut fix)

    # --- false-premise calibration (already passed, confirm no regression) ---
    "if a student has A level maths, which first year module do they take?",     # -> correct the premise
    "does having an A level in computing help with any specific modules?",        # -> correct the premise
    "if a student is good at maths, are there modules that suit them?",           # -> normal answer, NO over-fire

    # --- controls (must still pass) ---
    "do we have modules on AI?",                            # -> Yes + list + pathway
    "what's the music intelligence module about?",          # -> exists, no description held
    "do we have a blockchain module?",                      # -> confident No
    "can students specialise?",                             # -> four pathways
]

answers = {}
print(f"Loaded {len(test_query)} general branch test questions.")
for i, query in enumerate(test_query):
    print(f"Testing question {i+1}")
    answers[query] = RAG_main.main(query)
    print(f"Answer from question {i+1} -> Done")

with open("test_answers.txt", "w") as f:
    for query, answer in answers.items():
        f.write(f"Question: {query}\nAnswer: {answer}\n\n")