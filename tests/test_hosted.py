from uuid import uuid4

import pytest
from pydantic_ai_harness.memory import InMemoryStore
from test_agent_run import RecordingTaskContext

from hosted import memory_capability, run_memory, run_validation


async def test_memory_survives_new_runs_and_respects_each_run_limit(monkeypatch):
    monkeypatch.setattr(memory_capability, "store", InMemoryStore())
    context = RecordingTaskContext()
    token = str(uuid4())
    written = await run_memory.func(context, token, "write", 64)
    assert written["answer"] == "abcdefghij\n"
    for limit in (4, 8):
        read = await run_memory.func(context, token, "read", limit)
        assert read["answer"].startswith("abcdefghij"[:limit] + "\n\n[Truncated:")
    assert "memory_validation__function_toolset__memory.call_tool" in context.task_names


async def test_validation_rejects_invalid_input_before_database_access():
    context = RecordingTaskContext()
    with pytest.raises(ValueError):
        await run_validation.func(context, "retry", "not-a-uuid")
    with pytest.raises(ValueError, match="Expected"):
        await run_memory.func(context, str(uuid4()), "read", 999)
