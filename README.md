# Pydantic AI Harness Render Workflows validation

This small consumer application validates the Render Workflows integration from
the public Harness fork. It is separate from the Harness implementation.

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
