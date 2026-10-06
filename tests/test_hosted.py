from uuid import uuid4

import pytest
from pydantic_ai_harness.memory import InMemoryStore
from test_agent_run import RecordingTaskContext

import hosted
from hosted import memory_agents, run_memory, run_nested, run_validation


async def test_memory_survives_new_runs_and_respects_configured_limits(monkeypatch):
    store = InMemoryStore()
    for _, _, capability in memory_agents.values():
        monkeypatch.setattr(capability, "store", store)
    context = RecordingTaskContext()
    token = str(uuid4())
    written = await run_memory.func(context, token, "write", 64)
    assert written["answer"] == "abcdefghij\n"
    for limit in (4, 8):
        read = await run_memory.func(context, token, "read", limit)
        assert read["answer"].startswith("abcdefghij"[:limit] + "\n\n[Truncated:")
    assert "memory_validation_64__function_toolset__memory.call_tool" in context.task_names


async def test_validation_rejects_invalid_input_before_database_access():
    context = RecordingTaskContext()
    with pytest.raises(ValueError):
        await run_validation.func(context, "retry", "not-a-uuid")
    with pytest.raises(ValueError, match="Expected"):
        await run_memory.func(context, str(uuid4()), "read", 999)


async def test_hosted_nested_agent_dispatches_both_models_and_tool(monkeypatch):
    async def attempt(token, phase):
        return 1

    monkeypatch.setattr(hosted, "next_attempt", attempt)
    context = RecordingTaskContext()
    token = str(uuid4())
    result = await run_nested.func(context, token)
    assert result["answer"]["token"] == token
    assert "nested_validation__model.request" in context.task_names
    assert "validation__model.request" in context.task_names
    assert "validation__function_toolset__<agent>.call_tool" in context.task_names


async def test_effects_preserve_nested_usage_and_events():
    token = str(uuid4())
    result = await hosted.run_effects.func(RecordingTaskContext(), token)
    assert result["requests"] == 3
    assert result["events"] == [{"token": token, "sequence": 1}, {"token": token, "sequence": 2}]
