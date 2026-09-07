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

    "I have offers from Liverpool and Manchester for Computer Science. What are the main differences between the two courses?",
    "I am particularly interested in Artificial Intelligence and machine learning. Would Liverpool or Sheffield be the better choice for me?",
    "How does Liverpool compare with Leeds for graduate prospects and employability in Computer Science?",
    "What placement year or industrial experience opportunities are available at Liverpool, and how do they compare with Newcastle?",
    "I have an offer from Liverpool and Lancaster. What are the main differences in the student experience and the type of university environment?",
    "Which university gives me more flexibility to choose optional modules later in the degree: Liverpool or York?",
    "What are the main advantages of studying Computer Science at Liverpool compared with Nottingham?",
    "Manchester is ranked more highly for Computer Science. Why should I still choose Liverpool?",
    "I am interested in cybersecurity. Which relevant modules and opportunities are available at Liverpool compared with Sheffield?",
    "I am not completely sure which area of Computer Science I want to specialise in yet. Would Liverpool give me enough flexibility to decide later?",
    "How does the cost of living and accommodation in Liverpool compare with the other university I am considering?",
    "What is Liverpool like as a city for students? How would the student experience compare with somewhere such as Lancaster or York?",
    "What support is available at Liverpool if I struggle academically during the first year?",
    "Are there opportunities at Liverpool to work on real projects, undertake internships, or gain experience that would help me get a job after graduating?",
    "If you were comparing Liverpool with my other offer, what are the strongest reasons for choosing Liverpool, and are there any areas where the other university might actually be stronger?"
]

answers = {}
print(f"Loaded {len(test_query)} general branch test questions.")
for i, query in enumerate(test_query):
    print(f"Testing question {i+1}")
    answers[query] = RAG_main.main(query)
    print(f"Answer from question {i+1} -> Done")

with open("test_answers.txt", "w", encoding="utf-8") as f:  # answers contain en/em dashes and non-breaking hyphens, which the Windows default codec cannot write
    for query, answer in answers.items():
        f.write(f"Question: {query}\nAnswer: {answer}\n\n")