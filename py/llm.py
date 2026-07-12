import ollama


def LLM_query(system_prompt: str, user_query: str) -> dict:
    """
    Queries the LLM model with the given user query and returns the response.
    Args:
        system_prompt (str): The system prompt to set the context for the LLM.
        user_query (str): The query to send to the LLM.
    Returns:
        ollama response 
    """
    response = ollama.chat(
        model="qwen3.6:27b",
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_query
            }
        ],
        think=False, # disable thinking mode for faster responses
        options={
            "temperature": 0,
            "num_ctx": 16384,
        }
    )
    return response


if __name__ == "__main__":
    user_query = input("Enter your query: ")
    response = LLM_query(user_query)
    print(response.message.content)