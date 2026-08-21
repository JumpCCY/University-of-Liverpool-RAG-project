import json
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
    Wrap an API answer so it has the same .message.content shape as an Ollama response.
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


def LLM_query(system_prompt: str, user_query: str, model: str, deterministic: bool = False):
    """
    Queries the LLM model with the given user query and returns the response.
    Args:
        system_prompt (str): The system prompt to set the context for the LLM.
        user_query (str): The query to send to the LLM.
        model (str): The LLM model to use.
        deterministic (bool): temp 0 
    Returns:
        a response with .message.content
    """
    print(f"Call LLM {model}")

    if models.PROVIDER == "openai":
        if deterministic:
            response = client.responses.create(
                model=model,
                instructions=system_prompt,
                input=user_query,
                reasoning={"effort": "none"},
                temperature=0,
            )
        else:
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


def LLM_tool_call(system_prompt: str, user_query: str, tools: list, model: str):
    """
    Asks the model to either call one or more of the given tools, or answer directly.

    This is the agent node: instead of classifying the question into a word we act on,
    the model picks the tool itself and fills in its arguments. Answering directly -
    calling nothing - is a real choice, and it is what replaces the old unclear branch.

    OpenAI only. models.PROVIDER == "ollama" keeps the classification routers instead,
    because a 9b local model picks a category word far more reliably than it fills in
    structured tool arguments.

    Args:
        system_prompt (str): the instruction telling the model when to use each tool.
        user_query (str): the query to send to the LLM.
        tools (list): tool schemas in Responses API format.
        model (str): The LLM model to use.
    Returns:
        (calls, text). calls is a list of (tool_name, arguments dict) and is empty when
        the model chose to answer instead; text is that direct answer.
    """
    print(f"Call LLM {model} (tools)")

    response = client.responses.create(
        model=model,
        instructions=system_prompt,
        input=user_query,
        tools=tools,
        tool_choice="auto",
        reasoning={"effort": "none"},
        temperature=0,
    )

    calls = []
    for item in response.output:
        if item.type == "function_call":
            # arguments is a JSON string, and is absent when the tool takes none
            if item.arguments:
                arguments = json.loads(item.arguments)
            else:
                arguments = {}
            calls.append((item.name, arguments))

    return calls, response.output_text


def LLM_query_stream(system_prompt: str, user_query: str, model: str):
    """
    Same as LLM_query, but we make it generate each word like chatgpt.

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
