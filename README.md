# Harness researcher on Render Workflows

A consumer of the proposed Pydantic AI Harness `RenderWorkflows` capability,
built from the written-out [research agent
example](https://github.com/ojusave/pydantic-ai-harness-render-workflows/blob/43a44b405e61239b72fd220717ef85d3acab0885/examples/research_agent.py).
Submit a question from the DDS interface. The parent agent can search, fetch,
and delegate focused sub-questions. Each model request and each `delegate_task`
runs as its own Render task.

The Harness integration is pinned to commit
[`43a44b4`](https://github.com/ojusave/pydantic-ai-harness-render-workflows/commit/43a44b405e61239b72fd220717ef85d3acab0885)
until it is available in an upstream release.
[`docs/integration-ownership.md`](docs/integration-ownership.md) records which of
the three codebases owns each rough edge this sample works around, and what has
to be true before the workarounds come out.

## How it works

- `app.py` duplicates the harness researcher graph and registers `run_research`
  at module load.
- `RenderWorkflows` is attached to the parent only. Sub-agent search and fetch
  stay inside each `delegate_task` process.
- `api.py` starts `run_research` and polls it. Submitting returns a task run ID
  immediately, so a long research run can outlive the request that started it.
- Polling also lists child runs under that root ID, so the UI can show research
  branches without a database.

The Workflow is the run system of record. This sample does not need Postgres,
Key Value, or a background worker.

## Deploy on Render

Create a Blueprint from this repository. `render.yaml` defines both resources:
the Docker web service that bundles the React interface with FastAPI, and the
Python Workflow that runs the researcher.

Blueprints accept `type: workflow` as of Render's September 2026 release. Verify
against your own CLI before relying on it, since the published Blueprint
reference still lists Workflows as unsupported:

```bash
render blueprints validate render.yaml
```

The web service reads the Workflow slug through `fromService`, so nothing
hardcodes the task path:

```yaml
- key: WORKFLOW_SLUG
  fromService:
    name: pydantic-render-workflows-researcher
    type: workflow
    property: slug
```

Render prompts for the `sync: false` variables on the first sync:

| Variable | Service | Purpose |
| --- | --- | --- |
| `RENDER_API_KEY` | Web | Starts and polls Workflow task runs |
| `PYDANTIC_AI_MODEL` | Workflow | Model string, for example `openai:gpt-5-mini` |
| `OPENAI_API_KEY` | Workflow | Provider credential for an `openai:` model |

Without `PYDANTIC_AI_MODEL` the Workflow uses Pydantic AI's `TestModel` for
keyless tests. TestModel echoes tool results and cannot research the web.

`WORKFLOWS_ENABLED` defaults to `false` so a public deploy does not spend model
or Workflow credits until you turn it on after the provider key is in place.
Preview environments inherit that `false`.

After the first deploy, confirm the Dashboard lists `run_research`,
`researcher__model.request`, and the generated function-tool tasks.

## Configuration

| Variable | Service | Default | Purpose |
| --- | --- | --- | --- |
| `RENDER_API_KEY` | Web | None | Authenticates Workflow API requests |
| `RENDER_API_URL` | Web | `https://api.render.com` | Override for a custom API host |
| `RENDER_USE_LOCAL_DEV` | Web | unset | Point the SDK at the local task server |
| `WORKFLOW_SLUG` | Web | unset | Workflow slug, set by the Blueprint via `fromService` |
| `WORKFLOW_TASK` | Web | `<WORKFLOW_SLUG>/run_research`, or `run_research` | Overrides the resolved task path |
| `WORKFLOWS_ENABLED` | Web | `true` in code, `false` in the Blueprint | Kill switch for new submissions |
| `PYDANTIC_AI_MODEL` | Workflow | `TestModel` | Real provider string when set |
| `OPENAI_API_KEY` | Workflow | None | Provider credential for an `openai:` model |

## Local validation

Prerequisites: Python 3.12+, `uv`, Node 22+, `pnpm`, and Render CLI 2.28+.

Use CLI 2.28 or newer. Older builds of the local task server omit the `attempt`
field from task attempts, which the Python SDK requires.

Install dependencies:

```bash
uv sync
pnpm --dir frontend install
pnpm --dir frontend build
```

Start the local Workflow server:

```bash
render workflows dev -- uv run python app.py
```

It listens on port 8120 and prints the registered tasks.

Point the API at that server. The local task server registers bare task names,
so `WORKFLOW_TASK` drops the workflow slug:

```bash
RENDER_USE_LOCAL_DEV=true \
WORKFLOW_TASK=run_research \
WORKFLOWS_ENABLED=true \
uv run uvicorn api:api --host 127.0.0.1 --port 8000
```

`RENDER_USE_LOCAL_DEV=true` points the SDK at `http://localhost:8120` and does
not require `RENDER_API_KEY`. Override the port with `RENDER_LOCAL_DEV_URL` if
needed.

For real research answers locally, set `PYDANTIC_AI_MODEL` and the matching
provider key in the Workflow process environment before starting
`render workflows dev`.

Open `http://localhost:8000`, or call the API directly. Submitting returns
`202` with a task run ID:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"What are the tradeoffs of running long-lived AI research agents as distributed background tasks?"}'
```

Then poll that run. A completed payload includes the answer, the model, and
any child task runs:

```bash
curl http://localhost:8000/api/runs/<task_run_id>
```

```bash
render workflows tasks runs list --local
```

## Tests

Tests use fake Workflow runners or `TestModel` and make no provider API calls:

```bash
uv run pytest
uv run ruff check .
pnpm --dir frontend build
```

## Operational behavior

- REST calls to start or poll a run allow 30 seconds. The research task itself
  allows 30 minutes.
- Parent model requests run on the `starter` plan. Tool tasks, including
  `delegate_task` and local search/fetch, use `standard`. Render fixes those
  Options when the agent is bound, so they cannot differ per tool.
- `WORKFLOWS_ENABLED=false` disables submissions without taking down the UI or
  health endpoint.
- Child-run lookups page the task-run and task-definition endpoints to
  exhaustion, so a busy Workflow does not silently truncate the branches shown
  for a run. Pagination stops on a short page, a repeated cursor, or a fixed
  page budget.
- Render Workflows provides task logs, retry history, and run status in the
  Dashboard.
