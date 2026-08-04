import RAG_main

test_query = [
    # --- clearly modules ---
    "is there a machine learning module?",
    "what cyber security modules are there?",
    "do you teach game development?",
    "any modules on databases?",

    # --- clearly societies/clubs ---
    "is there a gaming society?",
    "what clubs can students join?",
    "is there a christian society?",
    "are there any social groups for freshers?",

    # --- genuinely ambiguous: could be module OR society ---
    "is there anything on biology?",
    "do you have anything about business?",          # ULMS254 module AND possibly a society
    "is there anything for people into AI?",         # AI modules AND possibly an AI society
    "anything music related?",                        # COMP346 Music Intelligence AND music societies
    "is there something for people who like maths?", # maths modules AND possibly a maths society
    "what's available for someone interested in robotics?",  # COMP329/341 AND possibly robotics club

    # --- the trap: word appears in a module as an EXAMPLE, not as the subject ---
    "is there a biology subject?",                    # COMP324 mentions biology as an example only
    "do you teach anything about finance?",           # COMP226 (trading) — finance as application

    # --- clean controls ---
    "what's COMP305 about?",                          # specific module, no ambiguity
    "is there a blockchain module?",                  # true negative
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