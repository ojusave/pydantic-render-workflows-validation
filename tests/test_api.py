import pytest
from fastapi.testclient import TestClient

from api import api
from workflow_client import (
    ChildRun,
    RunProgress,
    StartedRun,
    WorkflowRunner,
    workflow_runner,
)


class FakeRunner(WorkflowRunner):
    def __init__(self, started: StartedRun, progress: RunProgress) -> None:
        self.started = started
        self.progress_result = progress

    async def start(self, prompt: str) -> StartedRun:
        assert prompt == "hello"
        return self.started

    async def progress(self, task_run_id: str) -> RunProgress:
        assert task_run_id == "run-123"
        return self.progress_result


def override(started: StartedRun, progress: RunProgress) -> None:
    api.dependency_overrides[workflow_runner] = lambda: FakeRunner(started, progress)


def test_healthz() -> None:
    with TestClient(api) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "data": {"status": "ok"},
        "error": None,
        "meta": {},
    }


def test_status_reports_submissions_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKFLOWS_ENABLED", "false")
    with TestClient(api) as client:
        response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json()["data"] == {"submissions_enabled": False}


def test_chat_returns_run_id_without_waiting() -> None:
    override(StartedRun(task_run_id="run-123"), RunProgress(state="running"))
    try:
        with TestClient(api) as client:
            response = client.post("/api/chat", json={"message": "hello"})
    finally:
        api.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["data"] == {"task_run_id": "run-123"}


def test_run_reports_in_flight_state() -> None:
    override(
        StartedRun(task_run_id="run-123"),
        RunProgress(
            state="running",
            children=(
                ChildRun(
                    task_run_id="child-1",
                    task_id="tsk-1",
                    task_name="researcher__model.request",
                    parent_task_run_id="run-123",
                    depth=1,
                    status="running",
                ),
            ),
        ),
    )
    try:
        with TestClient(api) as client:
            response = client.get("/api/runs/run-123")
    finally:
        api.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"] == {
        "task_run_id": "run-123",
        "state": "running",
        "response": None,
        "model": None,
        "children": [
            {
                "task_run_id": "child-1",
                "task_id": "tsk-1",
                "task_name": "researcher__model.request",
                "parent_task_run_id": "run-123",
                "depth": 1,
                "status": "running",
            }
        ],
    }


def test_run_reports_completed_answer() -> None:
    override(
        StartedRun(task_run_id="run-123"),
        RunProgress(state="completed", response="Hi there", model="test-model"),
    )
    try:
        with TestClient(api) as client:
            response = client.get("/api/runs/run-123")
    finally:
        api.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"] == {
        "task_run_id": "run-123",
        "state": "completed",
        "response": "Hi there",
        "model": "test-model",
        "children": [],
    }


def test_chat_maps_typed_workflow_error() -> None:
    override(
        StartedRun(error_code="WORKFLOW_START_FAILED"),
        RunProgress(state="running"),
    )
    try:
        with TestClient(api) as client:
            response = client.post("/api/chat", json={"message": "hello"})
    finally:
        api.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["error"] == {
        "code": "WORKFLOW_START_FAILED",
        "message": "The research Workflow could not be started.",
    }


def test_run_maps_failed_workflow() -> None:
    override(
        StartedRun(task_run_id="run-123"),
        RunProgress(state="failed", error_code="WORKFLOW_FAILED"),
    )
    try:
        with TestClient(api) as client:
            response = client.get("/api/runs/run-123")
    finally:
        api.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "WORKFLOW_FAILED"
