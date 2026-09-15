from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal, Protocol

from render import RenderAsync
from render.client.errors import RenderError, TaskRunError
from render.public_api.api.workflow_tasks import list_task_runs
from render.public_api.api.workflows import list_workflows

logger = logging.getLogger(__name__)

WorkflowErrorCode = Literal[
    "WORKFLOWS_DISABLED",
    "WORKFLOWS_NOT_CONFIGURED",
    "WORKFLOW_START_FAILED",
    "WORKFLOW_LOOKUP_FAILED",
    "WORKFLOW_FAILED",
    "WORKFLOW_EMPTY_RESULT",
]

RunState = Literal["running", "completed", "failed"]

_IN_FLIGHT = frozenset({"pending", "running", "paused"})
_SUCCEEDED = frozenset({"completed", "succeeded"})
_LOCAL_DEV_VALUES = frozenset({"1", "t", "true"})
_API_TIMEOUT_SECONDS = 30
_TASK_NAME = "run_research"


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in _LOCAL_DEV_VALUES


def _resolve_task() -> str:
    """Name the research task, preferring the Blueprint-supplied Workflow slug.

    The local task server registers bare task names, so the slug is optional.
    """
    explicit = os.getenv("WORKFLOW_TASK")
    if explicit:
        return explicit
    slug = os.getenv("WORKFLOW_SLUG")
    return f"{slug}/{_TASK_NAME}" if slug else _TASK_NAME


@dataclass(frozen=True)
class StartedRun:
    """Identify a submitted run, or explain why submission failed."""

    task_run_id: str | None = None
    error_code: WorkflowErrorCode | None = None


@dataclass(frozen=True)
class ChildRun:
    """One Render child task spawned by a research run."""

    task_run_id: str
    task_id: str
    status: str


@dataclass(frozen=True)
class RunProgress:
    """Report where a run is, plus its answer once it finishes."""

    state: RunState | None = None
    response: str | None = None
    model: str | None = None
    children: tuple[ChildRun, ...] = field(default_factory=tuple)
    error_code: WorkflowErrorCode | None = None


class WorkflowRunner(Protocol):
    """Submit prompts to the workflow task and read back run progress."""

    async def start(self, prompt: str) -> StartedRun: ...

    async def progress(self, task_run_id: str) -> RunProgress: ...


class RenderWorkflowRunner:
    """Start and poll the research task through Render's asynchronous client."""

    def __init__(self) -> None:
        self._task = _resolve_task()
        self._enabled = os.getenv("WORKFLOWS_ENABLED", "true").lower() == "true"
        self._api_key = os.getenv("RENDER_API_KEY")
        self._api_url = os.getenv("RENDER_API_URL", "https://api.render.com")
        self._local = _env_flag("RENDER_USE_LOCAL_DEV")
        self._workflow_id: str | None = None

    def _client(self) -> RenderAsync:
        if self._local:
            return RenderAsync()
        return RenderAsync(token=self._api_key, base_url=self._api_url)

    async def start(self, prompt: str) -> StartedRun:
        if not self._enabled:
            return StartedRun(error_code="WORKFLOWS_DISABLED")
        if not self._api_key and not self._local:
            return StartedRun(error_code="WORKFLOWS_NOT_CONFIGURED")

        try:
            async with asyncio.timeout(_API_TIMEOUT_SECONDS):
                task_run = await self._client().workflows.start_task(self._task, [prompt])
        except (TimeoutError, RenderError, TaskRunError):
            logger.exception("Could not start workflow", extra={"workflow_task": self._task})
            return StartedRun(error_code="WORKFLOW_START_FAILED")

        return StartedRun(task_run_id=task_run.id)

    async def progress(self, task_run_id: str) -> RunProgress:
        if not self._api_key and not self._local:
            return RunProgress(error_code="WORKFLOWS_NOT_CONFIGURED")

        try:
            async with asyncio.timeout(_API_TIMEOUT_SECONDS):
                details = await self._client().workflows.get_task_run(task_run_id)
                children = await self._child_runs(task_run_id)
        except (TimeoutError, RenderError, TaskRunError):
            logger.exception("Could not read workflow run", extra={"task_run_id": task_run_id})
            return RunProgress(error_code="WORKFLOW_LOOKUP_FAILED")

        status = str(details.status)
        if status in _IN_FLIGHT:
            return RunProgress(state="running", children=children)
        if status not in _SUCCEEDED:
            logger.warning(
                "Workflow run ended without success",
                extra={"task_run_id": task_run_id, "status": status},
            )
            return RunProgress(state="failed", children=children, error_code="WORKFLOW_FAILED")

        payload = details.results[0] if details.results else None
        if not isinstance(payload, dict) or not isinstance(payload.get("answer"), str):
            logger.error(
                "Workflow returned an unexpected result shape",
                extra={"task_run_id": task_run_id},
            )
            return RunProgress(
                state="failed",
                children=children,
                error_code="WORKFLOW_EMPTY_RESULT",
            )

        model = payload.get("model")
        return RunProgress(
            state="completed",
            response=payload["answer"],
            model=model if isinstance(model, str) else None,
            children=children,
        )

    async def _resolve_workflow_id(self) -> str | None:
        """Look up the Workflow id behind WORKFLOW_SLUG, once per process."""
        if self._workflow_id:
            return self._workflow_id

        slug = os.getenv("WORKFLOW_SLUG")
        if not slug:
            return None

        response = await list_workflows.asyncio_detailed(
            client=self._client().client.internal, name=[slug], limit=1
        )
        parsed = response.parsed
        if isinstance(parsed, list) and parsed:
            self._workflow_id = parsed[0].workflow.id
        return self._workflow_id

    async def _child_runs(self, root_task_run_id: str) -> tuple[ChildRun, ...]:
        """List the runs a research root spawned. Empty if the list call fails.

        Render links spawned runs through parentTaskRunId and leaves
        rootTaskRunId empty, so walk the parent links instead of filtering on
        the root. Sub-agent delegation nests, so descendants count too.
        """
        try:
            workflow_id = await self._resolve_workflow_id()
            filters = {"workflow_id": [workflow_id]} if workflow_id else {}
            response = await list_task_runs.asyncio_detailed(
                client=self._client().client.internal,
                limit=100,
                **filters,
            )
        except (TimeoutError, RenderError, TaskRunError):
            logger.warning(
                "Could not list child task runs",
                extra={"task_run_id": root_task_run_id},
            )
            return ()

        parsed = response.parsed
        if not isinstance(parsed, list):
            return ()

        runs = {item.task_run.id: item.task_run for item in parsed}
        by_parent: dict[str, list[str]] = {}
        for run in runs.values():
            by_parent.setdefault(run.parent_task_run_id, []).append(run.id)

        children: list[ChildRun] = []
        seen: set[str] = {root_task_run_id}
        queue = list(by_parent.get(root_task_run_id, ()))
        while queue:
            run = runs[queue.pop(0)]
            if run.id in seen:
                continue
            seen.add(run.id)
            children.append(
                ChildRun(task_run_id=run.id, task_id=run.task_id, status=str(run.status))
            )
            queue.extend(by_parent.get(run.id, ()))
        return tuple(children)


@lru_cache
def workflow_runner() -> WorkflowRunner:
    """Return the process-wide Workflow runner."""
    return RenderWorkflowRunner()
