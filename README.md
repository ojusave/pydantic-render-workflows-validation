# Pydantic AI Harness Render Workflows validation

This small consumer application validates the Render Workflows integration from
the public Harness fork. It is separate from the Harness implementation.

It contains two deployable processes:

- `app.py` registers and runs the Pydantic agent as a Render Workflow.
- `api.py` exposes `POST /chat` and invokes the Workflow's `run_agent` task.

Install the pinned integration:

```bash
uv sync
```

Start Render's local workflow server:

```bash
render workflows dev -- uv run python app.py
```

In another terminal, list and run the registered tasks:

```bash
render workflows tasks list --local
render workflows start run_agent --local --input='["hello"]'
```

Run the agent API against the local workflow server:

```bash
RENDER_USE_LOCAL_DEV=true uv run uvicorn api:api --host 0.0.0.0 --port 8000
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello"}'
```

The deployed web service needs these environment variables:

- `RENDER_API_KEY`: a Render API key, stored only as a service secret.
- `WORKFLOW_TASK`: `pydantic-render-workflows-validation/run_agent`.
