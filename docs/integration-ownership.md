# Integration ownership and acceptance criteria

This example exists to find the seams between three codebases that have to agree
before a Pydantic AI agent runs cleanly as a set of Render tasks:

- **Harness**: [`pydantic-ai-harness-render-workflows`](https://github.com/ojusave/pydantic-ai-harness-render-workflows). Two layers matter separately here: the `RenderWorkflows` capability under `pydantic_ai_harness/render/`, and shared capabilities like `SubAgents` that know nothing about Render.
- **Render SDK and platform**: the `render` Python package, its generated `public_api` client, the Workflows runtime, and the `/task-runs` and `/tasks` endpoints.
- **Example**: this repository, which consumes both and runs the researcher behind a FastAPI gateway.

Anything the example works around is a defect somewhere upstream. The point of
writing the ownership down is that a workaround with no owner turns into
permanent example code, and then the next consumer writes it again.

## Ownership at a glance

| Concern | Owner | Example's role today |
| --- | --- | --- |
| Toolset IDs on leaf `FunctionToolset`s | Harness Render integration | Fixed by pinned harness commit `43a44b4` |
| Model access inside a child task | Harness Render integration | Fixed by pinned harness commit `43a44b4` |
| Root and parent task-run lineage | Render platform | Parent-link BFS in `workflow_client.py` |
| Cursor pagination over list endpoints | Example, with optional SDK helper | Owns it outright |
| Local and deployed test coverage | Split, see below | Owns the keyless suite |

## Handoff sequencing

The example pins the harness to a git commit in `pyproject.toml` rather than a
release. Commit `43a44b4` keeps both fixes below in
`pydantic_ai_harness/render/`, so the pin and the removal of the `app.py`
compatibility shims move together. Future workarounds follow the same sequence:
publish the upstream fix, update the pin, prove it through a local Workflow
process, then delete the workaround.

Where the fix lands matters as much as whether it exists. A requirement that only
Render has belongs to the Render integration, not to a shared capability: a
capability like `SubAgents` runs under Temporal, DBOS, and no engine at all, and
each of those would otherwise get a say in how its toolset is named. Both fixes
below are implemented where the requirement comes from, and `subagents` and
`tool_output_limits` are untouched.

## Toolset IDs

Render Workflows binds one task per leaf `FunctionToolset` and needs a stable
unique id to name it. A capability that builds its own toolset has nowhere to
take an id from: nobody writing `capabilities=[SubAgents(...)]` ever touches the
`FunctionToolset` underneath. Commit `43a44b4` derives the id when
`RenderWorkflows` binds, from the `id` of the capability that contributed the
toolset, which is already unique per agent and identical in the worker process.

**Requirements**

- Harness Render integration: name every unnamed capability-contributed leaf
  before registration reads the ids. Keep an id the toolset already has, fall
  back to a numbered variant when another toolset holds the name, and leave an
  unnamed leaf under an unnamed capability alone so the original error still
  tells the user what to set.
- Harness shared capabilities: no Render-specific parameters. A capability does
  not need to know which engine will bind it.
- Example: no subclass exists purely to copy an id downward.

**Acceptance criteria**

1. An agent built from `SubAgents` and `ToolOutputLimits` with no explicit `id`
   binds successfully and registers tasks with stable, human-readable names.
2. Passing `id="web_search"` to a capability produces a task name containing
   `web_search`, and the name does not change between two processes.
3. `WorkflowSubAgents`, `WorkflowToolOutputLimits`, and `_ensure_toolset_id` are
   deleted from `app.py` and the registration test still passes.

## Model access inside a child task

`delegate_task` runs in a child task, against a serialized projection of the
parent run context. That projection carried no model, so delegation failed on a
read of `ctx.model` that had nothing to answer with. Serializing the model is not
an option: it holds a provider client and credentials.

It does not have to travel. The worker imports the same agent module, so the
model is already in that process, and the capability registers the default model
and the `models={...}` entries by id. Commit `43a44b4` carries the run's model id
in the projection and resolves the instance on the child side, so `ctx.model`
answers for any reader in a child task: a delegating toolset, a summarizing
capability, or a user's own tool.

**Requirements**

- Harness Render integration: resolve the run's model id against the process's
  own registry and report that instance on the reconstructed context. Resolve to
  the plain model, not the workflow-side model wrapper, so a child task's
  work stays in the task already running it. Leave `model` unavailable when the
  id resolves to nothing, so the restriction error still explains itself.
- Harness shared capabilities: read `ctx.model` as normal. A capability should
  not need a Render-shaped code path.
- Render SDK: document that task inputs do not transport model objects.
  Serializing provider clients or credentials is not an inheritance mechanism.
- Example: chooses a model once, in `resolve_model()`, and does not reach into
  harness internals.

**Acceptance criteria**

1. A `SubAgent` wrapping `Agent(model=X)` runs with model `X` inside a Render
   child task with no patching by the caller.
2. A tool that reads `ctx.model` inside a child task gets the model the run is
   using, and a model id this process cannot resolve still raises the guarded
   error rather than a wrong model.
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
- Harness: any change to toolset naming or child-task context carries a test in
  `tests/render/`. The example is not the harness's test suite.
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
