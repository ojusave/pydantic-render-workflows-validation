"""Hosted validation tasks alongside the research example.

All probes use synthetic data. Database credentials stay in environment variables,
and each probe uses a caller-supplied UUID so concurrent checks remain isolated.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from uuid import UUID

import asyncpg
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai_harness import RenderWorkflows, SubAgent, SubAgents
from pydantic_ai_harness.memory import Memory, PostgresMemoryStore
from render import Options, Retry, TaskContext
from typing_extensions import TypedDict

from app import app


class ProbeDeps(TypedDict):
    token: str
    case: str
    limit: int


class DatabaseConnections:
    """Open connections in the task process that actually uses them."""

    @asynccontextmanager
    async def acquire(self):
        connection = await asyncpg.connect(os.environ["DATABASE_URL"], timeout=15)
        try:
            yield connection
        finally:
            await connection.close()


connections = DatabaseConnections()
memory_store = PostgresMemoryStore(connections, table="validation_memory")


async def next_attempt(token: str, phase: str) -> int:
    async with connections.acquire() as connection:
        await connection.execute(
            "CREATE TABLE IF NOT EXISTS validation_attempts "
            "(token TEXT, phase TEXT, attempts INTEGER, PRIMARY KEY (token, phase))"
        )
        return await connection.fetchval(
            "INSERT INTO validation_attempts VALUES ($1, $2, 1) "
            "ON CONFLICT (token, phase) DO UPDATE "
            "SET attempts = validation_attempts.attempts + 1 RETURNING attempts",
            token,
            phase,
        )


def probe_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del info
    returns = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
    if returns:
        return ModelResponse(parts=[TextPart(json.dumps(returns[-1].content))])
    return ModelResponse(parts=[ToolCallPart("probe", {}, tool_call_id="probe")])


probe_runtime = RenderWorkflows(
    app,
    name="validation",
    deps_type=ProbeDeps,
    tool_options=Options(
        retry=Retry(max_retries=1, wait_duration_ms=1000), timeout_seconds=300, plan="flex"
    ),
)
probe_agent = Agent(
    FunctionModel(probe_model),
    name="validation",
    deps_type=ProbeDeps,
    capabilities=[probe_runtime],
)


@probe_agent.tool
async def probe(ctx: RunContext[ProbeDeps]) -> dict[str, int | str]:
    """Exercise a tool retry, interruption, or cancellation with synthetic input."""
    attempt = await next_attempt(ctx.deps["token"], "tool")
    if ctx.deps["case"] == "retry" and attempt == 1:
        raise RuntimeError("Deliberate first-attempt failure for hosted validation")
    if ctx.deps["case"] == "cancel":
        await asyncio.sleep(240)
    return {"attempt": attempt, "process": os.getpid(), "token": ctx.deps["token"]}


@probe_runtime.task(
    name="run_validation", retry=Retry(max_retries=1, wait_duration_ms=1000), timeout_seconds=600
)
async def run_validation(ctx: TaskContext, case: str, token: str) -> dict:
    del ctx
    UUID(token)
    if case not in {"retry", "interrupt", "cancel"}:
        raise ValueError("Expected retry, interrupt, or cancel")
    attempt = await next_attempt(token, "root")
    result = await probe_agent.run(
        "Run the probe", deps={"token": token, "case": case, "limit": 64}
    )
    if case == "interrupt" and attempt == 1:
        # Terminate this disposable root after its tool completed. A root retry
        # repeats the agent, so the database must record the repeated tool call.
        os._exit(17)
    return {"root_attempt": attempt, "root_process": os.getpid(), "tool": json.loads(result.output)}


def nested_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del info
    returns = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
    if returns:
        return ModelResponse(parts=[TextPart(str(returns[-1].content))])
    return ModelResponse(
        parts=[ToolCallPart("delegate_task", {"agent_name": "validation", "task": "Run the probe"})]
    )


nested_runtime = RenderWorkflows(app, name="nested_validation", deps_type=ProbeDeps)
nested_agent = Agent(
    FunctionModel(nested_model),
    name="nested_validation",
    deps_type=ProbeDeps,
    capabilities=[SubAgents(agents=[SubAgent(probe_agent)], agent_folders=None), nested_runtime],
)


@nested_runtime.task(name="run_nested", timeout_seconds=300)
async def run_nested(ctx: TaskContext, token: str) -> dict:
    del ctx
    UUID(token)
    result = await nested_agent.run(
        "Delegate the probe", deps={"token": token, "case": "nested", "limit": 64}
    )
    return {"answer": json.loads(result.output)}


class LimitedMemory(Memory[ProbeDeps]):
    async def for_run(self, ctx: RunContext[ProbeDeps]) -> Memory[ProbeDeps]:
        clone = await super().for_run(ctx)
        clone.max_memory_size = ctx.deps["limit"]
        return clone


def memory_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del info
    returns = [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
    if returns and returns[-1].tool_name == "read_memory":
        return ModelResponse(parts=[TextPart(str(returns[-1].content))])
    # The first request contains the synthetic mode, never database credentials.
    mode = next(p.content for m in messages for p in m.parts if p.part_kind == "user-prompt")
    if mode == "write" and not returns:
        return ModelResponse(parts=[ToolCallPart("write_memory", {"content": "abcdefghij"})])
    return ModelResponse(parts=[ToolCallPart("read_memory", {"file": "MEMORY.md"})])


memory_runtime = RenderWorkflows(app, name="memory_validation", deps_type=ProbeDeps)
memory_capability = LimitedMemory(
    store=memory_store, namespace=lambda ctx: ctx.deps["token"], inject_memory=False
)
memory_agent = Agent(
    FunctionModel(memory_model),
    name="memory_validation",
    deps_type=ProbeDeps,
    capabilities=[
        memory_capability,
        memory_runtime,
    ],
)


@memory_runtime.task(name="run_memory", timeout_seconds=300)
async def run_memory(ctx: TaskContext, token: str, mode: str, limit: int = 64) -> dict:
    del ctx
    UUID(token)
    if mode not in {"write", "read"} or limit not in {4, 8, 64}:
        raise ValueError("Expected write/read mode and limit 4, 8, or 64")
    result = await memory_agent.run(mode, deps={"token": token, "case": mode, "limit": limit})
    return {"answer": result.output, "root_process": os.getpid(), "limit": limit}


@app.task(name="cleanup_validation", timeout_seconds=60)
async def cleanup_validation(ctx: TaskContext, token: str) -> dict:
    del ctx
    UUID(token)
    # Initialize schema through the public store API, then remove only this probe's data.
    await memory_store.list_paths(prefix=token + "/", limit=10)
    async with connections.acquire() as connection:
        memory_count = await connection.execute(
            "DELETE FROM validation_memory WHERE path LIKE $1", token + "/%"
        )
        attempts = await connection.fetch(
            "DELETE FROM validation_attempts WHERE token = $1 RETURNING phase, attempts", token
        )
    return {"memory": memory_count, "attempts": [dict(row) for row in attempts]}


if __name__ == "__main__":
    app.start()
