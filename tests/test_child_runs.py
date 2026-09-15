"""Cover the paginated child-run lineage walk in workflow_client.

Every Render list call is replaced by a recorder that serves prepared pages, so
these tests assert exactly which cursors the client asked for.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

import workflow_client
from workflow_client import RenderWorkflowRunner

WORKFLOW_ID = "wkf-1"
SLUG = "researcher"
ROOT = "run-root"
PAGE_SIZE = workflow_client._PAGE_SIZE


@dataclass(frozen=True)
class FakeRun:
    """The TaskRun fields workflow_client reads."""

    id: str
    parent_task_run_id: str
    task_id: str = "tsk-model"
    status: str = "running"


def run_page(runs: list[FakeRun]) -> list[Any]:
    """Wrap runs the way TaskRunWithCursor does, cursor last."""
    return [SimpleNamespace(task_run=run, cursor=f"cur-{run.id}") for run in runs]


def task_page(names: dict[str, str]) -> list[Any]:
    """Wrap task definitions the way TaskWithCursor does."""
    return [
        SimpleNamespace(task=SimpleNamespace(id=task_id, name=name), cursor=f"cur-{task_id}")
        for task_id, name in names.items()
    ]


def filler_runs(count: int, parent: str = ROOT, prefix: str = "fill") -> list[FakeRun]:
    return [FakeRun(id=f"{prefix}-{index}", parent_task_run_id=parent) for index in range(count)]


class Endpoint:
    """Serve prepared pages in order, repeating the last one, and record cursors."""

    def __init__(self, *pages: list[Any]) -> None:
        self.pages = list(pages) or [[]]
        self.cursors: list[str | None] = []
        self.root_filters: list[list[str] | None] = []

    async def __call__(self, **kwargs: Any) -> SimpleNamespace:
        self.cursors.append(kwargs.get("cursor"))
        if kwargs.get("cursor") is None:
            self.root_filters.append(kwargs.get("root_task_run_id"))
        index = min(len(self.cursors) - 1, len(self.pages) - 1)
        return SimpleNamespace(parsed=self.pages[index])

    @property
    def call_count(self) -> int:
        return len(self.cursors)


@dataclass
class Harness:
    runner: RenderWorkflowRunner
    runs: Endpoint
    tasks: Endpoint
    workflows: Endpoint


def build(
    monkeypatch: pytest.MonkeyPatch,
    runs: Endpoint,
    tasks: Endpoint | None = None,
) -> Harness:
    monkeypatch.setenv("WORKFLOW_SLUG", SLUG)
    monkeypatch.setenv("RENDER_API_KEY", "unused")
    tasks = tasks or Endpoint(task_page({"tsk-model": "researcher__model.request"}))
    workflows = Endpoint([SimpleNamespace(workflow=SimpleNamespace(id=WORKFLOW_ID))])

    monkeypatch.setattr(workflow_client.list_task_runs, "asyncio_detailed", runs)
    monkeypatch.setattr(workflow_client.list_tasks, "asyncio_detailed", tasks)
    monkeypatch.setattr(workflow_client.list_workflows, "asyncio_detailed", workflows)
    monkeypatch.setattr(
        RenderWorkflowRunner,
        "_client",
        lambda self: SimpleNamespace(client=SimpleNamespace(internal=object())),
    )
    return Harness(RenderWorkflowRunner(), runs, tasks, workflows)


async def test_task_runs_paginate_until_a_short_page(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = build(
        monkeypatch,
        Endpoint(
            run_page(filler_runs(PAGE_SIZE, prefix="a")),
            run_page(filler_runs(PAGE_SIZE, prefix="b")),
            run_page(filler_runs(50, prefix="c")),
        ),
    )

    children = await harness.runner._child_runs(ROOT)

    assert len(children) == 2 * PAGE_SIZE + 50
    assert harness.runs.cursors == [None, f"cur-a-{PAGE_SIZE - 1}", f"cur-b-{PAGE_SIZE - 1}"]
    assert {child.depth for child in children} == {1}


async def test_task_definitions_paginate_to_resolve_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    late_task = "tsk-delegate"
    harness = build(
        monkeypatch,
        Endpoint(run_page([FakeRun(id="child-1", parent_task_run_id=ROOT, task_id=late_task)])),
        Endpoint(
            task_page({f"tsk-filler-{index}": f"filler-{index}" for index in range(PAGE_SIZE)}),
            task_page({late_task: "researcher__delegate_task"}),
        ),
    )

    children = await harness.runner._child_runs(ROOT)

    assert harness.tasks.cursors == [None, f"cur-tsk-filler-{PAGE_SIZE - 1}"]
    assert [child.task_name for child in children] == ["researcher__delegate_task"]


async def test_nested_delegation_reports_increasing_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build(
        monkeypatch,
        Endpoint(
            run_page(
                [
                    FakeRun(id="grandchild", parent_task_run_id="child"),
                    FakeRun(id="child", parent_task_run_id=ROOT),
                    FakeRun(id="great-grandchild", parent_task_run_id="grandchild"),
                ]
            )
        ),
    )

    children = await harness.runner._child_runs(ROOT)

    assert [(child.task_run_id, child.depth) for child in children] == [
        ("child", 1),
        ("grandchild", 2),
        ("great-grandchild", 3),
    ]


async def test_runs_from_other_roots_are_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = build(
        monkeypatch,
        Endpoint(
            run_page(
                [
                    FakeRun(id="mine", parent_task_run_id=ROOT),
                    FakeRun(id="other-root", parent_task_run_id=""),
                    FakeRun(id="other-child", parent_task_run_id="other-root"),
                ]
            )
        ),
    )

    children = await harness.runner._child_runs(ROOT)

    assert [child.task_run_id for child in children] == ["mine"]


async def test_workflow_id_and_task_names_are_fetched_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build(
        monkeypatch,
        Endpoint(run_page([FakeRun(id="child-1", parent_task_run_id=ROOT)])),
    )

    first = await harness.runner._child_runs(ROOT)
    second = await harness.runner._child_runs(ROOT)

    assert first == second
    assert harness.workflows.call_count == 1
    assert harness.tasks.call_count == 1
    assert harness.runs.call_count == 2


async def test_local_mode_resolves_task_names_without_a_workflow_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build(
        monkeypatch,
        Endpoint(run_page([FakeRun(id="child-1", parent_task_run_id=ROOT)])),
    )
    monkeypatch.delenv("WORKFLOW_SLUG")

    children = await harness.runner._child_runs(ROOT)

    assert [child.task_name for child in children] == ["researcher__model.request"]
    assert harness.workflows.call_count == 0
    assert harness.tasks.call_count == 1


async def test_a_repeated_cursor_stops_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    # A full page whose cursor never advances would otherwise loop forever.
    harness = build(monkeypatch, Endpoint(run_page(filler_runs(PAGE_SIZE))))

    children = await harness.runner._child_runs(ROOT)

    assert harness.runs.cursors == [None, f"cur-fill-{PAGE_SIZE - 1}"]
    assert len(children) == PAGE_SIZE


async def test_the_root_filter_scopes_the_query_to_one_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Listing the whole workflow on every poll grows with history, not with the run.
    harness = build(
        monkeypatch,
        Endpoint(run_page([FakeRun(id="child-1", parent_task_run_id=ROOT)])),
    )

    children = await harness.runner._child_runs(ROOT)

    assert [child.task_run_id for child in children] == ["child-1"]
    assert harness.runs.call_count == 1
    assert harness.runs.root_filters == [[ROOT]]


async def test_an_unpopulated_root_falls_back_to_the_parent_walk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build(
        monkeypatch,
        Endpoint([], run_page([FakeRun(id="child-1", parent_task_run_id=ROOT)])),
    )

    children = await harness.runner._child_runs(ROOT)

    assert [child.task_run_id for child in children] == ["child-1"]
    assert harness.runs.root_filters == [[ROOT], None]


async def _completed_run(task_run_id: str) -> SimpleNamespace:
    return SimpleNamespace(status="completed", results=[{"answer": "an answer"}])


async def test_a_slow_lineage_lookup_drops_children_not_the_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The answer is the product; lineage is decoration and must not fail the poll.
    async def never_returns(**_: Any) -> SimpleNamespace:
        await asyncio.sleep(workflow_client._CHILD_TIMEOUT_SECONDS + 1)
        raise AssertionError("should have timed out")

    harness = build(
        monkeypatch, Endpoint(run_page([FakeRun(id="child-1", parent_task_run_id=ROOT)]))
    )
    monkeypatch.setattr(workflow_client.list_task_runs, "asyncio_detailed", never_returns)
    monkeypatch.setattr(workflow_client, "_CHILD_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        RenderWorkflowRunner,
        "_client",
        lambda self: SimpleNamespace(
            client=SimpleNamespace(internal=object()),
            workflows=SimpleNamespace(
                get_task_run=_completed_run,
            ),
        ),
    )

    progress = await harness.runner.progress(ROOT)

    assert progress.state == "completed"
    assert progress.response == "an answer"
    assert progress.children == ()
    assert progress.error_code is None


async def test_pagination_stops_at_the_page_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    class Endless(Endpoint):
        async def __call__(self, **kwargs: Any) -> SimpleNamespace:
            self.cursors.append(kwargs.get("cursor"))
            page = filler_runs(PAGE_SIZE, prefix=f"p{self.call_count}")
            return SimpleNamespace(parsed=run_page(page))

    harness = build(monkeypatch, Endless())

    children = await harness.runner._child_runs(ROOT)

    assert harness.runs.call_count == workflow_client._MAX_PAGES
    assert len(children) == workflow_client._MAX_PAGES * PAGE_SIZE
