"""Run the researcher end to end with no provider key.

`TestModel` keeps the agent loop real, so delegation still travels through the
Render task boundary. The recording context executes each child task locally
while capturing the task names Render would have run.
"""

import inspect
from typing import Any, ParamSpec, TypeVar

import pytest
from pydantic_ai.models import Model
from render.workflows import TaskContext, TaskDefinition

import app as workflow_app
from app import run_research

P = ParamSpec("P")
R = TypeVar("R")


class RecordingTaskContext(TaskContext):
    """Execute child tasks locally and record the Render task boundary."""

    def __init__(self) -> None:
        self.task_names: list[str] = []

    async def run(
        self, task: TaskDefinition[P, R], *args: P.args, **kwargs: P.kwargs
    ) -> R:
        self.task_names.append(task.name)
        result = task.func(self, *args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result


def test_configured_model_is_resolved_before_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workflow_app, "DEFAULT_MODEL", "test")

    assert isinstance(workflow_app.resolve_model(), Model)


async def test_researcher_dispatches_delegate_child_task() -> None:
    context = RecordingTaskContext()

    pending: Any = run_research.func(
        context, "What are the tradeoffs of distributed background research agents?"
    )
    output = await pending

    assert isinstance(output["answer"], str)
    assert output["model"] == "pydantic-ai TestModel"
    assert "researcher__model.request" in context.task_names
    assert any("sub_agents.call_tool" in name for name in context.task_names)
