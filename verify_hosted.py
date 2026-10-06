"""Run synthetic checks against an already deployed validation workflow.

Requires RENDER_API_KEY and WORKFLOW_SLUG. Writes a JSON evidence report to
stdout with run IDs and results, excluding credentials and task inputs.
"""

import asyncio
import json
import os
from uuid import uuid4

from render import RenderAsync

from workflow_client import RenderWorkflowRunner


async def main():
    client = RenderAsync()
    slug = os.environ["WORKFLOW_SLUG"]
    runner = RenderWorkflowRunner()
    evidence = []
    tokens = []
    active = set()

    async def start(task, inputs):
        run = await client.workflows.start_task(f"{slug}/{task}", inputs)
        active.add(run.id)
        print(json.dumps({"started": task, "id": run.id}), flush=True)
        return run.id

    async def wait(run_id):
        async with asyncio.timeout(600):
            while True:
                run = await client.workflows.get_task_run(run_id)
                if str(run.status) in {"completed", "succeeded", "failed", "canceled"}:
                    active.discard(run_id)
                    return run
                await asyncio.sleep(3)

    async def record(label, run):
        children = await runner._child_runs(run.id)
        details = [await client.workflows.get_task_run(child.task_run_id) for child in children]
        item = {
            "check": label,
            "id": run.id,
            "status": str(run.status),
            "attempts": [a.to_dict() for a in run.attempts],
            "results": run.results,
            "children": [
                {
                    "id": child.task_run_id,
                    "name": child.task_name,
                    "status": str(detail.status),
                    "parent": child.parent_task_run_id,
                    "attempts": [
                        {"attempt": a.attempt, "status": str(a.status)}
                        for a in sorted(detail.attempts, key=lambda attempt: attempt.attempt)
                    ],
                }
                for child, detail in zip(children, details)
            ],
        }
        evidence.append(item)
        print(json.dumps(item), flush=True)
        return item

    try:
        token = str(uuid4())
        tokens.append(token)
        nested = await wait(await start("run_nested", {"token": token}))
        item = await record("nested_agents", nested)
        assert str(nested.status) in {"completed", "succeeded"}, item
        assert nested.results[0]["answer"]["token"] == token, item
        names = {child["name"] for child in item["children"]}
        assert {
            "nested_validation__model.request",
            "validation__model.request",
            "validation__function_toolset__<agent>.call_tool",
        } <= names, item

        token = str(uuid4())
        effects = await wait(await start("run_effects", {"token": token}))
        item = await record("usage_and_events", effects)
        assert str(effects.status) in {"completed", "succeeded"}, item
        assert effects.results[0]["requests"] == 3, item
        assert effects.results[0]["events"] == [
            {"token": token, "sequence": 1},
            {"token": token, "sequence": 2},
        ], item

        for case in ("retry", "interrupt"):
            token = str(uuid4())
            tokens.append(token)
            run = await wait(await start("run_validation", {"case": case, "token": token}))
            item = await record(case, run)
            assert str(run.status) in {"completed", "succeeded"}, item
            result = run.results[0]
            assert result["root_attempt"] == (1 if case == "retry" else 2), item
            assert result["tool"]["attempt"] == 2, item
            tool_runs = [c for c in item["children"] if c["name"].endswith(".call_tool")]
            if case == "retry":
                assert len(run.attempts) == 1 and len(tool_runs) == 1, item
                assert len(tool_runs[0]["attempts"]) == 2, item
                assert tool_runs[0]["attempts"][0]["status"] == "failed", item
                assert tool_runs[0]["attempts"][1]["status"] in {"completed", "succeeded"}, item
            else:
                assert len(run.attempts) == 2 and len(tool_runs) == 2, item

        token = str(uuid4())
        tokens.append(token)
        written = await wait(await start("run_memory", {"token": token, "mode": "write"}))
        item = await record("memory_write", written)
        assert str(written.status) in {"completed", "succeeded"}, item
        assert written.results[0]["answer"] == "abcdefghij\n", item
        read_ids = [
            await start("run_memory", {"token": token, "mode": "read", "limit": limit})
            for limit in (4, 8)
        ]
        for limit, run_id in zip((4, 8), read_ids):
            read = await wait(run_id)
            item = await record(f"memory_configured_limit_{limit}", read)
            assert str(read.status) in {"completed", "succeeded"}, item
            assert read.results[0]["answer"].startswith("abcdefghij"[:limit] + "\n\n[Truncated:"), (
                item
            )
            assert any("memory.call_tool" in c["name"] for c in item["children"]), item

        token = str(uuid4())
        tokens.append(token)
        run_id = await start("run_validation", {"case": "cancel", "token": token})
        async with asyncio.timeout(180):
            while True:
                children = await runner._child_runs(run_id)
                if any(
                    c.task_name.endswith(".call_tool") and c.status == "running" for c in children
                ):
                    break
                await asyncio.sleep(3)
        await client.workflows.cancel_task_run(run_id)
        canceled = await wait(run_id)
        async with asyncio.timeout(60):
            while any(
                c.status in {"pending", "running", "paused"}
                for c in await runner._child_runs(run_id)
            ):
                await asyncio.sleep(3)
        item = await record("cancellation", canceled)
        assert str(canceled.status) == "canceled", item
        assert any(c["status"] == "canceled" for c in item["children"]), item
        assert all(c["status"] not in {"pending", "running", "paused"} for c in item["children"]), (
            item
        )
    finally:
        for run_id in tuple(active):
            run = await client.workflows.get_task_run(run_id)
            if str(run.status) in {"pending", "running", "paused"}:
                await client.workflows.cancel_task_run(run_id)
                await wait(run_id)
        for token in tokens:
            cleaned = await wait(await start("cleanup_validation", {"token": token}))
            print(json.dumps({"cleanup": cleaned.id, "status": str(cleaned.status)}), flush=True)
            assert str(cleaned.status) in {"completed", "succeeded"}
    print(json.dumps({"passed": len(evidence), "checks": [e["check"] for e in evidence]}))


if __name__ == "__main__":
    asyncio.run(main())
