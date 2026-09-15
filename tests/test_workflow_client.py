import pytest

from workflow_client import RenderWorkflowRunner


@pytest.mark.asyncio
async def test_start_returns_disabled_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFLOWS_ENABLED", "false")
    monkeypatch.setenv("RENDER_API_KEY", "unused")

    started = await RenderWorkflowRunner().start("hello")

    assert started.error_code == "WORKFLOWS_DISABLED"


@pytest.mark.asyncio
async def test_start_returns_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKFLOWS_ENABLED", "true")
    monkeypatch.delenv("RENDER_USE_LOCAL_DEV", raising=False)
    monkeypatch.delenv("RENDER_API_KEY", raising=False)

    started = await RenderWorkflowRunner().start("hello")

    assert started.error_code == "WORKFLOWS_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_progress_returns_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RENDER_API_KEY", raising=False)
    monkeypatch.delenv("RENDER_USE_LOCAL_DEV", raising=False)

    progress = await RenderWorkflowRunner().progress("run-123")

    assert progress.error_code == "WORKFLOWS_NOT_CONFIGURED"
