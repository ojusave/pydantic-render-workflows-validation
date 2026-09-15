import logging
import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from workflow_client import (
    ChildRun,
    RunState,
    WorkflowErrorCode,
    WorkflowRunner,
    workflow_runner,
)

logging.basicConfig(
    level=logging.INFO,
    format='{"level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
api = FastAPI(title="Pydantic AI Researcher on Render Workflows")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class StartData(BaseModel):
    task_run_id: str


class ChildRunData(BaseModel):
    task_run_id: str
    task_id: str
    task_name: str
    parent_task_run_id: str
    depth: int
    status: str


class RunData(BaseModel):
    task_run_id: str
    state: RunState
    response: str | None = None
    model: str | None = None
    children: list[ChildRunData] = Field(default_factory=list)


class StatusData(BaseModel):
    submissions_enabled: bool


class ApiError(BaseModel):
    code: WorkflowErrorCode
    message: str


class Envelope(BaseModel):
    data: StartData | RunData | StatusData | None = None
    error: ApiError | None = None
    meta: dict[str, str] = Field(default_factory=dict)


ERROR_MESSAGES: dict[WorkflowErrorCode, tuple[int, str]] = {
    "WORKFLOWS_DISABLED": (
        503,
        "Research submissions are disabled until a real model and provider key are set on the Workflow.",
    ),
    "WORKFLOWS_NOT_CONFIGURED": (503, "The Workflow API key is not configured."),
    "WORKFLOW_START_FAILED": (502, "The research Workflow could not be started."),
    "WORKFLOW_LOOKUP_FAILED": (502, "The research Workflow run could not be read."),
    "WORKFLOW_FAILED": (502, "The research Workflow failed."),
    "WORKFLOW_EMPTY_RESULT": (502, "The research Workflow returned no answer."),
}


def _error_response(code: WorkflowErrorCode) -> JSONResponse:
    status, message = ERROR_MESSAGES[code]
    envelope = Envelope(error=ApiError(code=code, message=message))
    return JSONResponse(status_code=status, content=envelope.model_dump())


def _child_payload(children: tuple[ChildRun, ...]) -> list[ChildRunData]:
    return [
        ChildRunData(
            task_run_id=child.task_run_id,
            task_id=child.task_id,
            task_name=child.task_name,
            parent_task_run_id=child.parent_task_run_id,
            depth=child.depth,
            status=child.status,
        )
        for child in children
    ]


@api.get("/healthz")
async def health() -> dict[str, object]:
    """Report process readiness without calling external dependencies."""
    return {"data": {"status": "ok"}, "error": None, "meta": {}}


@api.get("/api/status", response_model=Envelope)
async def status() -> Envelope:
    """Tell the UI whether new research submissions are accepted."""
    enabled = os.getenv("WORKFLOWS_ENABLED", "true").lower() == "true"
    return Envelope(data=StatusData(submissions_enabled=enabled))


@api.post("/api/chat", response_model=Envelope, status_code=202)
async def chat(
    request: ChatRequest,
    runner: Annotated[WorkflowRunner, Depends(workflow_runner)],
) -> Envelope | JSONResponse:
    """Submit a research prompt and return its task run ID without waiting."""
    started = await runner.start(request.message)
    if started.error_code is not None:
        return _error_response(started.error_code)

    assert started.task_run_id is not None
    return Envelope(data=StartData(task_run_id=started.task_run_id))


@api.get("/api/runs/{task_run_id}", response_model=Envelope)
async def read_run(
    task_run_id: str,
    runner: Annotated[WorkflowRunner, Depends(workflow_runner)],
) -> Envelope | JSONResponse:
    """Report the current state of one research run and its child tasks."""
    progress = await runner.progress(task_run_id)
    if progress.error_code is not None:
        return _error_response(progress.error_code)

    assert progress.state is not None
    return Envelope(
        data=RunData(
            task_run_id=task_run_id,
            state=progress.state,
            response=progress.response,
            model=progress.model,
            children=_child_payload(progress.children),
        )
    )


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    api.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
