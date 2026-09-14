import logging
import os
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from render import RenderAsync

logger = logging.getLogger(__name__)

WORKFLOW_TASK = os.getenv(
    "WORKFLOW_TASK",
    "pydantic-render-workflows-validation/run_agent",
)

api = FastAPI(title="Pydantic Render Workflows validation agent")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    response: Any
    task_run_id: str


@lru_cache
def render_client() -> RenderAsync:
    return RenderAsync()


@api.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "pydantic-render-workflows-agent",
        "chat_endpoint": "/chat",
        "workflow_task": WORKFLOW_TASK,
    }


@api.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@api.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        task_run = await render_client().workflows.run_task(
            WORKFLOW_TASK,
            [request.message],
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail="RENDER_API_KEY is not configured for the agent service",
        ) from exc
    except Exception as exc:
        logger.exception("Workflow task failed")
        raise HTTPException(
            status_code=502,
            detail="The agent workflow task failed",
        ) from exc

    if not task_run.results:
        raise HTTPException(
            status_code=502,
            detail="The agent workflow returned no result",
        )

    return ChatResponse(
        response=task_run.results[0],
        task_run_id=task_run.id,
    )
