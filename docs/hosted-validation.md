# Hosted validation

## 8 October 2026: current Render PR head

The `samples` workflow version `wfv-db42sbajnfac73bb3ue0` and web deployment `dep-db42sbnlot8c73ch651g` built [example commit `3af4fb8`](https://github.com/ojusave/pydantic-render-workflows-validation/commit/3af4fb8b3a4d9cfe40ea752b38f6e948ebeed2a9). Its three Pydantic packages are pinned to [Render PR head `b58b68b6`](https://github.com/ojusave/pydantic-ai/commit/b58b68b69ce3133461dffbf812dc10c0f5b52e1b). The web health endpoint returned HTTP 200.

Eight deterministic checks passed on that hosted version:

| Check | Root task run | Result |
| --- | --- | --- |
| Nested agents | `trn-08l4gdb43crhkjpkg00eqd4ig` | Completed and returned the input token |
| Child usage and events | `trn-08l4gdb43d0hutons738p5rl0` | Three model requests and two ordered events |
| Tool retry | `trn-08l4gdb43d4gm3shc73b8pvs0` | Tool succeeded on attempt two without restarting the root |
| Root interruption | `trn-08l4gdb43d8pkjpkg00eqd4m0` | Root and tool each ran twice |
| Memory write | `trn-08l4gdb43dhnntkc000fng1dg` | Wrote ten characters |
| Memory read, limit four | `trn-08l4gdb43dn7ntkc000fng1e0` | Returned four characters and a truncation notice |
| Memory read, limit eight | `trn-08l4gdb43dr7ntkc000fng1fg` | Returned eight characters and a truncation notice |
| Root cancellation | `trn-08l4gdb43du1utons738p5ru0` | Root reached canceled state |

All six data-cleanup runs completed. The CLI check did not independently inspect the canceled root's child state, and it did not run a real model-provider request on this revision. Local checks on the same pin passed: 29 example tests and Ruff. On the PR head, the Render test directory passed 156 tests with three process tests skipped in that command; the three real local Render process tests passed separately. The Harness CI jobs passed on Python 3.11 through 3.14, as did quality and combined coverage checks. The PR remains blocked by the repository's protected `.github/` rule and a missing `pkg:harness` label, both of which require maintainer action.

## 6 October 2026

All eight hosted checks passed in the `samples` workspace against [integration revision `0f7e20e39`](https://github.com/ojusave/pydantic-ai/commit/0f7e20e39299b06bacb6c5e930d3c64b975796b2), using [example revision `df50c45`](https://github.com/ojusave/pydantic-render-workflows-validation/commit/df50c45a5951402e3025388b126e2cd447644456). The integration uses unchanged upstream core and Memory, with no separate Memory patch.

- Workflow version: `wfv-db2l5vom7kps73a3dlv0`.
- Web deployment: `dep-db2l62egekts73c8t9ig`.
- All three Pydantic packages use the same Git pin; Render SDK is 1.2.0.
- [Example web service](https://pydantic-ai-researcher-v2.onrender.com), protected by the demo password.

The deterministic checks use `FunctionModel` to control tool selection while crossing real hosted task and PostgreSQL boundaries.

| Check | Final state | Root task run |
| --- | --- | --- |
| nested agents | completed | `trn-08l4gdb2l6orlhmac73aq0je0` |
| usage and events | completed | `trn-08l4gdb2l6urlhmac73aq0jf0` |
| retry | completed | `trn-08l4gdb2l72jlhmac73aq0jfg` |
| interrupt | completed | `trn-08l4gdb2l778m3shc73ef8fig` |
| memory write | completed | `trn-08l4gdb2l7gfif34c73am7ahg` |
| memory configured limit 4 | completed | `trn-08l4gdb2l7m3lhmac73aq0jgg` |
| memory configured limit 8 | completed | `trn-08l4gdb2l7m23hc8c73fuajkg` |
| cancellation | canceled | `trn-08l4gdb2l7qa3hc8c73fuajlg` |

Child retry completed after one failed tool attempt without restarting the root. Terminating the entry task caused a second root attempt and repeated the completed tool, confirming restart behavior rather than checkpoint replay. Memory persisted in PostgreSQL across separate runs and respected configured limits of four and eight characters. Cancellation stopped the root and active child. All five cleanup tasks completed, removing synthetic files and counters; task history and operation receipts remain.

The real application path also passed. After repairing the web service's Render credential, an authenticated POST to `/api/chat` returned `202 Accepted`, and polling `/api/runs/{id}` returned a completed `openai:gpt-5.4-mini` answer. Run `trn-08l4gdb2l6uom3shc73ef8fi0` included the research sub-agent, a web fetch, and five completed child tasks. Unauthenticated API access returned 401 and the health endpoint returned 200. This establishes execution of the research flow, not the factual correctness of every model-generated answer.

Local verification on the pinned revision: 160 Render tests, 100% scoped source/test coverage across installed and absent SDK configurations, scoped type checking, and repository lint/format checks passed. The three manually enabled local process tests passed separately after their fixture move. All 29 example tests pass with installed pinned packages; one pre-existing Starlette deprecation warning remains. Full integration CI and maintainer review are tracked in [PR #9439](https://github.com/pydantic/pydantic-ai/pull/9439), which remains draft.

A custom `Memory.for_run` override that changes `max_memory_size` still fails on upstream without Render. These checks use distinct configured Memory instances and shared storage; they do not establish support for that override or for arbitrary local files shared between hosts.

To repeat the hosted checks, set `RENDER_API_KEY` and `WORKFLOW_SLUG=pydantic-ai-researcher-v2-workflow`, then run `uv run python verify_hosted.py`. Each run creates fresh synthetic identifiers and cleans them up. Auto-deploy remains off, so later documentation-only commits do not change the verified deployment.

The September record below describes its own revisions and limitations. The October results above supersede its unverified real-provider status.

## Historical validation, 29 September 2026

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

### Remaining validation at that date

The real-provider research flow has not passed in this run. It requires a valid Render API key on the web service and an available model-provider account on the workflow. Do not treat the deterministic checks as proof of real web research or of compatibility with every Pydantic capability.

To repeat the runtime checks, set `RENDER_API_KEY` and `WORKFLOW_SLUG=pydantic-ai-researcher-v2-workflow`, then run `uv run python verify_hosted.py`. Use a fresh UUID for each manually submitted probe and cancel only runs created for that test.
