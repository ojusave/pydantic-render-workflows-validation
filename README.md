# Harness researcher on Render Workflows

A consumer of the proposed Pydantic AI Harness `RenderWorkflows` capability,
built from the written-out [research agent
example](https://github.com/ojusave/pydantic-ai-harness-render-workflows/blob/539b2279eec9c4c7a3b51d079ec45537d01759a6/examples/research_agent.py).
Submit a question from the DDS interface. The parent agent can search, fetch,
and delegate focused sub-questions. Each model request and each `delegate_task`
runs as its own Render task.

The Harness integration is pinned to commit
[`539b2279`](https://github.com/ojusave/pydantic-ai-harness-render-workflows/commit/539b2279eec9c4c7a3b51d079ec45537d01759a6)
until it is available in an upstream release.

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

Render Blueprints do not yet support Workflow services. Create the Workflow
first, then deploy the web service from `render.yaml`.

### 1. Create the Workflow

In the Render Dashboard, select **New > Workflow** and connect this repository.

| Setting | Value |
| --- | --- |
| Name | `pydantic-render-workflows-validation` |
| Runtime | Python 3 |
| Build command | `uv sync --frozen` |
| Start command | `uv run python app.py` |

Set these Workflow environment variables before enabling the UI:

| Variable | Required | Purpose |
| --- | --- | --- |
| `PYDANTIC_AI_MODEL` | Yes for real answers | Pydantic AI model string, for example `openai:gpt-5-mini` |
| `OPENAI_API_KEY` | Only with an `openai:` model | Provider credential |

Without `PYDANTIC_AI_MODEL` the Workflow uses Pydantic AI's `TestModel` for
keyless tests. TestModel echoes tool results and cannot research the web.

After the first deploy, confirm the Dashboard lists `run_research`,
`researcher__model.request`, and the generated function-tool tasks.

### 2. Deploy the web service

Create a Blueprint from this repository. `render.yaml` builds the React
interface and FastAPI service into one Docker image, binds to Render's `$PORT`,
and configures `/healthz`.

Set `RENDER_API_KEY` to a Render API key that can start Workflow tasks. If you
changed the Workflow name, update `WORKFLOW_TASK` to
`<workflow-slug>/run_research`.

`WORKFLOWS_ENABLED` defaults to `false` so a public deploy does not spend model
or Workflow credits until you turn it on after the provider key is in place.
Blueprint preview environments stay disabled.

## Configuration

| Variable | Service | Default | Purpose |
| --- | --- | --- | --- |
| `RENDER_API_KEY` | Web | None | Authenticates Workflow API requests |
| `RENDER_API_URL` | Web | `https://api.render.com` | Override for a custom API host |
| `RENDER_USE_LOCAL_DEV` | Web | unset | Point the SDK at the local task server |
| `WORKFLOW_TASK` | Web | `pydantic-render-workflows-validation/run_research` | Registered task slug |
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
  -d '{"message":"Compare Render Workflows and Temporal for long-running AI research."}'
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
- Render Workflows provides task logs, retry history, and run status in the
  Dashboard.
