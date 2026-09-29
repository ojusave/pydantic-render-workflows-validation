# Pydantic AI researcher on Render Workflows

This example runs a web-research agent in the background and shows its model and tool calls as separate Render task runs. A React interface submits a question to FastAPI, which starts the research task and returns a run ID. The browser polls that ID until it can display the answer and the child-task history.

The `pydantic-ai-v2` branch uses the integration in the Pydantic AI monorepo. `main` retains the earlier Harness example. This is a validation build of an integration that has not been released by Pydantic.

## Run it locally

Install Python 3.12, uv, Node 22 or later, pnpm 10.32.1, and [Render CLI](https://render.com/docs/cli) 2.28 or later. Clone this branch, then install and build:

```bash
git clone --branch pydantic-ai-v2 https://github.com/ojusave/pydantic-render-workflows-validation.git
cd pydantic-render-workflows-validation
uv sync --frozen
(cd frontend && corepack pnpm install --frozen-lockfile)
(cd frontend && corepack pnpm build)
render workflows dev -- uv run python app.py
```

In a second terminal, start the web application:

```bash
RENDER_USE_LOCAL_DEV=true WORKFLOW_TASK=run_research WORKFLOWS_ENABLED=true \
  uv run uvicorn api:api --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Without provider configuration, the workflow uses `TestModel` to exercise delegation and return synthetic text. To research real questions, set `PYDANTIC_AI_MODEL=openai:gpt-5.4-mini` and `OPENAI_API_KEY` in the workflow terminal before starting it.

## How the integration is used

[`app.py`](app.py) defines the parent researcher and a sub-agent. Each agent has its own `RenderWorkflows` capability, with distinct names on the same `Workflows` application. The `@render_workflows.task` decorator on `run_research` puts the agent loop in a root task and dispatches supported model and tool operations to child tasks. Each worker imports the agent definition and constructs its own provider client from environment variables.

Model requests have a two-minute task timeout and two retries; web tools have a five-minute task timeout and one retry. Both use Render's `flex` plan. Large tool results are truncated to 12,000 characters, so the example does not depend on files shared between task instances. Sub-agent delegation runs inside the parent agent loop, while the sub-agent's model and web-tool calls have their own task records.

A child task can retry while its parent waits. Retrying the root starts the agent again and can repeat completed work. This example does not provide agent checkpoint recovery or exactly-once side effects. Task progress appears through polling; it is not a live stream of model tokens.

## Deploy a separate hosted version

[`render.yaml`](render.yaml) describes a web service, a workflow, and a small PostgreSQL database in the same region. Use it to create a new Blueprint, or create equivalent resources with the Render CLI and API. The workflow starts `hosted.py`, which registers the researcher and the synthetic validation tasks below. The web service builds with the included Dockerfile.

Supply `OPENAI_API_KEY` on the workflow and `RENDER_API_KEY` on the web service. The Blueprint connects `DATABASE_URL` and `WORKFLOW_SLUG` and generates `DEMO_PASSWORD`. Sign in to the web interface with username `ojus` and the password from the web service's Environment page. The password protects submissions and run results; `/healthz` remains available to Render's health check.

`WORKFLOWS_ENABLED=false` disables new submissions. Auto-deploy is off for this validation version, so release an explicitly tested commit when updating it. The older deployment can keep using `main` independently.

The database stores synthetic Memory and retry-test records. Research prompts and results travel through Render and the configured model provider; web research also calls external sites. Use non-sensitive prompts for validation. Workflow API access is trusted, including access to generated operation tasks.

## Test the integration

```bash
uv run pytest
uv run ruff check .
(cd frontend && corepack pnpm build)
render blueprints validate render.yaml
```

The ordinary test suite needs no provider key. Hosted validation uses real Render task execution and a real model for the research example. [`hosted.py`](hosted.py) adds deterministic probes so the infrastructure checks do not depend on model choices:

| Task | What it checks |
| --- | --- |
| `run_nested` | A parent delegates to another Pydantic agent, whose model and tool calls execute as Render tasks. |
| `run_validation`, case `retry` | A tool fails once and succeeds on its registered retry while the root stays on its first attempt. |
| `run_validation`, case `interrupt` | The root process exits after a completed tool call, then retries and repeats that work. |
| `run_validation`, case `cancel` | A long-running child allows native root cancellation to be checked. |
| `run_memory` | Separate runs write and read shared PostgreSQL Memory with per-run character limits. |
| `cleanup_validation` | Removes one probe's Memory files and attempt counters by its UUID. |

Run the hosted probes from a terminal with `RENDER_API_KEY` and `WORKFLOW_SLUG` set:

```bash
uv run python verify_hosted.py
```

The script checks actual task attempts and descendant states, then removes its synthetic Memory files and attempt counters. Render retains task history, and Memory retains its operation receipts. The script prints run IDs and results for review.

All Pydantic packages are pinned to the same Git revision in `pyproject.toml` and `uv.lock`. The validation revision combines the Render adapter with the separately reviewed Memory fix; neither upstream PR needs to include this example's deployment code. See [integration ownership](docs/integration-ownership.md) for the boundaries and [Render's Python SDK reference](https://render.com/docs/workflows-sdk-python) for task configuration.
