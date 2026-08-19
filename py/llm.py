from types import SimpleNamespace
import ollama
from dotenv import load_dotenv
from openai import OpenAI
import models
import os

# Open ai functiosn from https://developers.openai.com/api/docs/quickstart?language=python
# Reads OPENAI_API_KEY from the .env (gitignored)
load_dotenv()

# check if we use openai or ollama if open AI then call OpenAI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if models.PROVIDER == "openai" else None

def _as_ollama_shape(text: str):
    """
    Wrap an API answer so it has the same .message.content shape as an Ollama
    response. Keeps the rest of the project working without changes.
    """
    return SimpleNamespace(message=SimpleNamespace(content=text))


def _messages(system_prompt: str, user_query: str) -> list[dict]:
    """Ollama's message format. The API path uses instructions/input instead."""
    return [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": user_query
        }
    ]


def LLM_query(system_prompt: str, user_query: str, model: str):
    """
    Queries the LLM model with the given user query and returns the response.
    Args:
        system_prompt (str): The system prompt to set the context for the LLM.
        user_query (str): The query to send to the LLM.
        model (str): The LLM model to use.
    Returns:
        a response with .message.content, whichever provider is in use
    """

    if models.PROVIDER == "openai":
        response = client.responses.create(
            model=model,
            instructions=system_prompt,
            input=user_query,
            reasoning={"effort": "medium"},
        )
        return _as_ollama_shape(response.output_text)

    # ---- ollama for qwen ----
    return ollama.chat(
        model=model,
        messages=_messages(system_prompt, user_query),
        think=False, # disable thinking mode for faster responses
        options={
            "temperature": 0,
            "num_ctx": 16384,
        }
    )


def LLM_query_stream(system_prompt: str, user_query: str, model: str):
    """
    Same as LLM_query, but yields the answer in pieces as the model writes it.

    Use this ONLY for the final answer. The router, sub-router and extractor all need
    the complete string before they can decide anything, so they keep using LLM_query.

    Yields:
        str: the next piece of the answer (a few characters at a time)
    """
    print(f"Call LLM {model} (streaming)")

    if models.PROVIDER == "openai":
        stream = client.responses.create(
            model=model,
            instructions=system_prompt,
            input=user_query,
            reasoning={"effort": "medium"},
            stream=True,
        )
        for event in stream:
            # the stream also carries the model's reasoning as
            # response.reasoning_summary_text.delta events - we only want the answer
            if event.type == "response.output_text.delta" and event.delta:
                yield event.delta
        return

    # ---- ollama for qwen ----
    stream = ollama.chat(
        model=model,
        messages=_messages(system_prompt, user_query),
        think=False, # disable thinking mode for faster responses
        stream=True, # send each piece as it is generated instead of waiting for the whole answer
        options={
            "temperature": 0,
            "num_ctx": 16384,
        }
    )
    for chunk in stream:
        piece = chunk.message.content
        if piece:
            yield piece


if __name__ == "__main__":
    print(f"PROVIDER = {models.PROVIDER}")
    user_query = input("Enter your query: ")
    for piece in LLM_query_stream("You are a helpful assistant.", user_query, models.LOW_EFFORT):
        print(piece, end="", flush=True)
    print()
