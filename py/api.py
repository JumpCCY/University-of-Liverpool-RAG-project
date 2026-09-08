"""
LLM assited the coding for writing this file.
"""

import json
import time
import uuid

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from llm import LLM_query
import models
from RAG_main import MAX_HISTORY_TURNS, main_stream

app = FastAPI(title="University RAG")

# what Open WebUI shows in its model dropdown. one entry, because the RAG picks its
# own models internally (see models.py) - the caller does not get to choose.
MODEL_ID = "university-rag"


class Message(BaseModel):
    role: str
    content: str | None = None


class ChatRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[Message]
    stream: bool = False

    class Config:
        extra = "allow"  # Open WebUI sends temperature, max_tokens etc. - ignore them


def conversation(messages: list[Message]) -> tuple[str, str]:
    """
    Splits the request into the earlier turns and the question being asked now.

    Open WebUI resends the whole conversation on every call, so the history is
    already here - it only has to be kept apart from the question itself. Only
    user and assistant turns count: the system prompt is Open WebUI's own and is
    not something the staff member said.

    Returns:
        (history, question). history is "" on the first turn, which is what keeps
        the condenser off the critical path for most queries. question is "" when
        there is no user turn at all - route_and_build() reports that.
    """
    turns = [m for m in messages if m.role in ("user", "assistant") and m.content]

    # walk back to the question being asked now - the last turn is not always the
    # user's, because Open WebUI resends the conversation when regenerating an answer
    latest = -1
    for i in range(len(turns) - 1, -1, -1):
        if turns[i].role == "user":
            latest = i
            break

    if latest == -1:
        return "", ""

    prior = turns[:latest][-MAX_HISTORY_TURNS:]
    history = "\n".join(f"{m.role}: {m.content.strip()}" for m in prior)
    return history, turns[latest].content.strip()


def is_openwebui_task(messages: list[Message]) -> bool:
    """
    Open WebUI quietly reuses the chat endpoint for its own housekeeping - naming the
    conversation, tagging it, suggesting follow-ups. Those prompts arrive marked with
    "### Task:" and are self-contained, so they must not go through retrieval.
    """
    for message in messages:
        if message.content and "### Task:" in message.content:
            return True
    return False


def answer_task(messages: list[Message]) -> str:
    """Answers an Open WebUI housekeeping prompt with a plain LLM call, no retrieval."""
    system_prompt = ""
    user_content = ""
    for message in messages:
        if message.role == "system" and message.content:
            system_prompt += message.content + "\n"
        elif message.content:
            user_content += message.content + "\n"

    if not system_prompt.strip():
        system_prompt = "Follow the task in the message exactly. Reply with nothing else."

    return LLM_query(system_prompt, user_content, model=models.LOW_EFFORT).message.content


def chunk(completion_id: str, created: int, delta: dict, finish_reason: str | None) -> str:
    """One server-sent event in the shape OpenAI streams."""
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": MODEL_ID,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n"


def stream_answer(user_query: str, history: str = ""):
    """
    Yields the answer as OpenAI-style SSE.
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    yield chunk(completion_id, created, {"role": "assistant"}, None)

    try:
        for piece in main_stream(user_query, history):
            yield chunk(completion_id, created, {"content": piece}, None)
    except Exception as error:
        # the stream has already started, so a 500 is no longer possible - the only
        # place left to report the failure is inside the answer itself
        yield chunk(completion_id, created, {"content": f"\n\n[error: {error}]"}, None)

    yield chunk(completion_id, created, {}, "stop")
    yield "data: [DONE]\n\n"


@app.get("/models")
@app.get("/v1/models")
def list_models():
    """
    Model discovery. Open WebUI calls this to populate model name.
    """
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "university-rag",
            }
        ],
    }


@app.post("/chat/completions")
@app.post("/v1/chat/completions")
def chat_completions(request: ChatRequest):
    """
    The one endpoint Open WebUI actually chats through.

    Declared with def rather than async def on purpose: the RAG is blocking all the
    way down, so FastAPI runs this in a thread pool instead of on the event loop.
    """
    if is_openwebui_task(request.messages):
        answer = answer_task(request.messages)
        return completion_response(answer)

    history, user_query = conversation(request.messages)

    if request.stream:
        return StreamingResponse(
            stream_answer(user_query, history),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    answer = ""
    for piece in main_stream(user_query, history):
        answer += piece
    return completion_response(answer)


def completion_response(answer: str) -> dict:
    """A whole answer in the shape OpenAI returns when stream is false."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        # token counts are not tracked, but Open WebUI expects the key to exist
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
