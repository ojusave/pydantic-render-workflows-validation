# Hosted validation, 29 September 2026

The seven deterministic checks below passed on hosted Render in the `samples` workspace. They exercise actual task instances and PostgreSQL, using Pydantic `FunctionModel` to control tool selection. They do not use a live model provider.

- Example code: [`7960900`](https://github.com/ojusave/pydantic-render-workflows-validation/commit/79609006d9c158730e6cbcb6c950f02331d7ffc7).
- Integration: [`121c8854`](https://github.com/ojusave/pydantic-ai/commit/121c8854e538ba835fffd96999d1fbd5f562fe73), combining the Render adapter and the standalone Memory correction.
- Hosted workflow version: `wfv-dau4nvg93c1s73cng30g`.
- Web deployment: `dep-dau4nvhsrm7s73apfufg`.
- [Example web service](https://pydantic-ai-researcher-v2.onrender.com), protected by a generated demo password.

| Check | Final state | Root task run |
| --- | --- | --- |
| nested agents | completed | `trn-08l4gdau4op7lot8c739lq27g` |
| retry | completed | `trn-08l4gdau4ou7lot8c739lqgtg` |
| interrupt | completed | `trn-08l4gdau4p1o93c1s73cnkot0` |
| memory write | completed | `trn-08l4gdau4p8o93c1s73cnlkf0` |
| memory limit 4 | completed | `trn-08l4gdau4pdnavr4c73fmd4cg` |
| memory limit 8 | completed | `trn-08l4gdau4pdg93c1s73cnm87g` |
| cancellation | canceled | `trn-08l4gdau4pi093c1s73cnmot0` |

The retry check observed a failed first tool attempt and a successful second attempt under the same root attempt. The interruption check observed two root attempts and two completed tool executions, demonstrating that a root retry repeats work. The Memory checks wrote once and then read concurrently in separate runs with character limits of four and eight. Cancellation stopped both the root and its active child; no descendant remained pending, running, or paused.

All five cleanup tasks succeeded and removed their probe's Memory files and attempt counters. Task history and Memory operation receipts remain available.

Local checks also passed: 277 Memory/Render tests (three skipped), two process-isolation tests using the Render development runtime, one Prefect Memory regression test, and 28 example tests. Scoped type checking, Ruff, the frontend build, and Render Blueprint validation passed. The existing `main` example deployment and the fork's `main` and standalone Memory branches were preserved.

## Remaining validation

The real-provider research flow has not passed in this run. It requires a valid Render API key on the web service and an available model-provider account on the workflow. Do not treat the deterministic checks as proof of real web research or of compatibility with every Pydantic capability.

To repeat the runtime checks, set `RENDER_API_KEY` and `WORKFLOW_SLUG=pydantic-ai-researcher-v2-workflow`, then run `uv run python verify_hosted.py`. Use a fresh UUID for each manually submitted probe and cancel only runs created for that test.
