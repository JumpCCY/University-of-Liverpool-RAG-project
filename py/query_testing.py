import RAG_main

general_branch_tests = [
    # topic-module questions (confirm -> list -> explain shape)
    "do we have any cyber security modules?",
    "any modules about game development?",
    "do we teach data science?",
    "anything on robotics?",
    "do we have modules on quantum computing?",

    # specific-module questions
    "what's COMP226 about?",
    "what does the music intelligence module cover?",
    "tell me about the final year project",

    # course-info questions
    "what do students learn in first year?",
    "my daughter did CS A level — does she skip the intro programming module?",
    "what pathways can they graduate with?",
    "when do students start choosing options?",

    # edge cases
    "is COMP105 a first year or second year module?",
    "are there any modules outside the COMP department?",
    "do we have a blockchain module?",
    "what are the short 7-credit modules?",
    "is there a placement year?",
]

answers = {}
print(f"Loaded {len(general_branch_tests)} general branch test questions.")
for i, query in enumerate(general_branch_tests):
    answers[query] = RAG_main.main(query)
    print(f"Answer from question {i+1} -> Done")

with open("test_answers.txt", "w") as f:
    for query, answer in answers.items():
        f.write(f"Question: {query}\nAnswer: {answer}\n\n")