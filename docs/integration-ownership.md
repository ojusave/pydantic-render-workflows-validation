# Integration ownership and acceptance criteria

This example exists to find the seams between three codebases that have to agree
before a Pydantic AI agent runs cleanly as a set of Render tasks:

- **Harness**: [`pydantic-ai-harness-render-workflows`](https://github.com/ojusave/pydantic-ai-harness-render-workflows), the `RenderWorkflows` capability and the sub-agent toolset.
- **Render SDK and platform**: the `render` Python package, its generated `public_api` client, the Workflows runtime, and the `/task-runs` and `/tasks` endpoints.
- **Example**: this repository, which consumes both and runs the researcher behind a FastAPI gateway.

Anything the example works around is a defect somewhere upstream. The point of
writing the ownership down is that a workaround with no owner turns into
permanent example code, and then the next consumer writes it again.

## Ownership at a glance

| Concern | Owner | Example's role today |
| --- | --- | --- |
| Toolset IDs on leaf `FunctionToolset`s | Harness | Fixed by pinned harness commit `4ce2364` |
| Delegated model propagation | Harness | Explicit child model; no consumer patch |
| Root and parent task-run lineage | Render platform | Parent-link BFS in `workflow_client.py` |
| Cursor pagination over list endpoints | Example, with optional SDK helper | Owns it outright |
| Local and deployed test coverage | Split, see below | Owns the keyless suite |

## Handoff sequencing

The example pins the harness to a git commit in `pyproject.toml` rather than a
release. Commit `4ce2364` propagated capability IDs and corrected delegated
model resolution, so the pin and removal of the `app.py` compatibility shims
move together. Future workarounds must follow the same sequence: publish the
upstream fix, update the pin, prove it through a local Workflow process, then
delete the workaround.

## Toolset IDs

Render Workflows binds one task per leaf `FunctionToolset` and needs a stable
unique id to name it. Harness commit `4ce2364` makes `SubAgents` and
`ToolOutputLimits` propagate their capability IDs to the leaf toolsets. Earlier
pins required consumer subclasses to do this.

**Requirements**

- Harness: every capability that produces a toolset sets an id on the **leaf**
  toolset Render actually binds, derived from the capability's `id` with a
  documented default when the caller does not pass one.
- Render SDK: when a leaf toolset has no id, fail at bind time with an error that
  names the offending capability instead of surfacing a generic error or
  silently registering a task keyed by object identity.
- Example: no subclass exists purely to copy an id downward.

**Acceptance criteria**

1. An agent built from `SubAgents` and `ToolOutputLimits` with no explicit `id`
   binds successfully and registers tasks with stable, human-readable names.
2. Passing `id="web_search"` to a capability produces a task name containing
   `web_search`, and the name does not change between two processes.
3. `WorkflowSubAgents`, `WorkflowToolOutputLimits`, and `_ensure_toolset_id` are
   deleted from `app.py` and the registration test still passes.

## Delegated model propagation

Before harness commit `4ce2364`, `SubAgentToolset._run_delegation` read the
parent model before checking whether the delegated agent already had one. On
Render, `delegate_task` executes in a child task whose serialized run context
intentionally carries no live model object. The harness now avoids that
unnecessary read.

**Requirements**

- Harness: when a delegated agent has an explicit model, leave model selection
  to that agent without reading `ctx.model`. Use a configured model-menu choice
  when one exists. Read `ctx.model` only for model-less delegates.
- Render SDK: document that task contexts do not transport model objects.
  Serializing provider clients or credentials into task inputs is not an
  acceptable inheritance mechanism.
- Example: chooses a model once, in `resolve_model()`, and does not reach into
  harness internals.

**Acceptance criteria**

1. A `SubAgent` wrapping `Agent(model=X)` runs with model `X` inside a Render
   child task with no patching by the caller.
2. In-process model-less delegates continue to inherit the parent's model.
   Durable model-less delegates configure an explicit child model or choose one
   from `SubAgents.models`; they do not depend on a serialized parent model.
3. The `_run_delegation_with_model` patch and the `SubAgentToolset` import are
   deleted from `app.py` and a delegating run still returns an answer both under
   `render workflows dev` and on a deployed Workflow.

## Root and parent task-run lineage

Spawned task runs arrive with `parentTaskRunId` populated and `rootTaskRunId`
empty, so `GET /task-runs?rootTaskRunId=<id>` returns nothing for a run that
demonstrably has children. The example lists runs for the Workflow and walks
parent links breadth-first, which also gives it the depth the UI renders.

**Requirements**

- Render platform: populate `rootTaskRunId` on every spawned run, including runs
  nested more than one level deep, and make `rootTaskRunId` a working filter.
- Render SDK: keep `parentTaskRunId` in the response after the root filter works.
  Depth is derived from parent links and nothing else carries it.
- Example: keep depth and ordering behavior identical when the query changes, so
  the UI and the API contract in `api.py` do not move.

**Acceptance criteria**

1. For a run that spawned a nested delegation, `rootTaskRunId=<root>` returns the
   full subtree in one filtered query.
2. `parentTaskRunId` is still set on those runs, so depth stays computable.
3. Replacing the BFS with the filtered query leaves the `/api/runs/{id}` payload
   byte-identical for the same run: same children, same depths, same order.

Until then the BFS is the supported path, and it must stay correct for nested
depths and must exclude runs belonging to other roots.

## Cursor pagination

Render's list endpoints are cursor-paginated: each item in the response carries
its own `cursor`, and a client advances by passing the last item's cursor. A
single `limit=100` call silently truncates, which in this app means child runs
vanish from the UI on a busy Workflow rather than failing loudly.

**Requirements**

- Example: page `list_task_runs` and `list_tasks` to exhaustion. Terminate on a
  short page, on a repeated cursor, or at a fixed page budget. Deduplicate by id
  so a repeated page cannot duplicate children. Log both defensive exits at
  `warning`.
- Render SDK: an auto-paginating iterator over the generated list endpoints would
  remove this loop from every consumer. Optional, not blocking.
- Render platform: never return a cursor that does not advance.

**Acceptance criteria**

1. A Workflow with more task runs than one page still shows every child run.
2. A task definition that appears only on a later `/tasks` page still resolves to
   a readable task name rather than a raw task id.
3. An endpoint that returns a full page with an unchanging cursor terminates
   after the repeat is detected, and the result contains no duplicates.
4. An endpoint that never returns a short page terminates at the page budget.

Covered by `tests/test_child_runs.py`.

## Local and deployed tests

**Requirements**

- Example: `uv run pytest` and `uv run ruff check .` pass with no API keys and no
  network. Workflow lineage tests stub the generated endpoints and assert the
  cursors requested, not just the final list.
- Example: `render workflows dev -- uv run python app.py` registers
  `run_research`, the parent model-request task, and one task per function tool.
  A local `POST /api/chat` plus poll returns an answer with `TestModel`.
- Harness: any change to capability ids or delegation carries a test at the
  harness level. The example is not the harness's test suite.
- Render SDK and CLI: the local task server must return the fields the Python SDK
  requires. CLI builds before 2.28 omit `attempt` from task attempts, which fails
  local runs for reasons that look like application bugs.

**Acceptance criteria**

1. A clean clone passes `uv sync && uv run pytest && uv run ruff check .` with an
   empty environment.
2. The local run lists the expected task names and completes one research
   prompt keyless.
3. `render blueprints validate render.yaml` accepts `type: workflow`.
4. On a deployed Blueprint with `WORKFLOWS_ENABLED=true` and a real
   `PYDANTIC_AI_MODEL`, one prompt produces an answer and the Dashboard shows
   the parent run with its child tasks, matching what `/api/runs/{id}` reports.
