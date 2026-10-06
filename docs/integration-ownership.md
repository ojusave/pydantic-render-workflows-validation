# Integration ownership

This version consumes the [Pydantic AI fork](https://github.com/ojusave/pydantic-ai/tree/codex/render-review-fixes), with core, Graph, and Harness pinned to the same revision. It replaces the older dependency on the separate Harness repository only on the `pydantic-ai-v2` example branch.

| Concern | Owner | Validation in this example |
| --- | --- | --- |
| Dispatch model and supported tool calls as Render tasks | Harness Render adapter | Researcher and sub-agent child-task records |
| Use configured Memory limits in durable tool calls | Shared Harness Memory | PostgreSQL write followed by separate reads with limits of four and eight characters |
| Retry failed task attempts and cancel descendants | Render SDK and hosted runtime | Synthetic retry, interruption, and cancellation probes |
| Keep API calls bounded and display task lineage | Example | FastAPI tests and browser polling |
| Store model credentials and database connections | Deployment configuration | Environment variables, never task arguments |

The validation branch uses unchanged upstream Memory. Each limit has its own configured agent because a custom Memory `for_run` override of `max_memory_size` is still ignored upstream, including without Render. No separate Memory patch is included. The example makes no changes to Pydantic's other execution engines.

The web client first queries by root task ID and falls back to walking parent links within the workflow. This accommodates the lineage responses observed in the earlier deployment. Both queries have pagination and time budgets, and lineage lookup failure does not replace a completed research answer with an error.

The example explicitly truncates oversized tool results because hosted task instances do not share a local filesystem. The Memory probes instead use `PostgresMemoryStore`, opening a database connection in the process that needs it. They use isolated synthetic namespaces and do not transport connection strings in task inputs.

Root interruption intentionally repeats the agent. A successful retry is evidence of restart behavior, not checkpoint recovery. Likewise, cancellation checks cover the runs created by this test, not external side effects that have already completed.
