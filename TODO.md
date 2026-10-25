# TODO

Open work, known caveats in the current results, and ideas we deliberately left for later. Last reviewed 2026-10-25.

## In progress

A queue started on 2026-10-25 runs these one at a time, once the Inkling download finishes. It's `logs/queue.sh`, running detached, so it survives the session. Progress goes to `logs/queue.log`, with one log per stage. It rebuilds `dashboard/data/` and `RESULTS.md` after each stage. Committing them, refreshing the hosted dashboard and updating ANALYSIS.md are still manual.

- [ ] **0. Quick-profile speed and HumanEval for ThinkingCap and Laguna** (`baseline` tag, ~40 min). `terminal-quick` is skipped because both already have the more thorough `terminal-x3`. This stage also runs the full `quick` profile for `gemma-4-e4b` (~15 min).
- [ ] **A. ROCm vs. Vulkan speed** (`rocm-compare` tag, ~2 h). See [ROCm](#rocm-vs-vulkan) below.
- [ ] **B. Re-run the fixed `backup-rotation` task** for all ten models (`terminal-backup-rotation` suite, `overnight-fix` tag, ~1 h). See the first caveat below.
- [ ] **C. LiveCodeBench with a 64k thinking budget** (`livecodebench-64k` suite, `overnight-64k` tag, roughly 15–25 h). It covers qwen3.8, ThinkingCap, flint, gemma, qwen3.6 and both Nemotrons. It skips Strata and qwen3-coder (no cut-offs) and Laguna (recommended for retirement).
- [ ] **D. Re-run Strata's overnight profile on a clean GPU** (~3 h).

Once results land, add the `livecodebench-64k` result and the corrected terminal-x3 score (with the new `backup-rotation` result) to the dashboard and RESULTS.md, and revise ANALYSIS.md.

### ROCm vs. Vulkan

Quality scores don't depend on the backend (same GGUF, same sampling), so only speed is being compared.

- llama.cpp b11850 is built with HIP for gfx1201 in `~/src/llama.cpp-b11850/build-rocm/` (ROCm 7.1, no rocWMMA).
- The `llamacpp-rocm` backend and the `*-rocm` models in `bench.yaml` reproduce each model's llama-swap flags: context, MTP drafter, q8_0 KV cache, flash attention auto.
- Six models get `speed-quick` plus raw `kernels-rocm` (llama-bench), labeled `--hardware r9700-rocm`. The same six get `kernels` on Vulkan for the matching number.
- qwen3.8-27b-rocm and flint-rocm also run `humaneval-quick`. It's a check for a broken build, not a quality comparison.
- Compare with `uv run aibench report --hardware r9700-vulkan --hardware r9700-rocm -s speed-quick -s kernels -s kernels-rocm`.
- **If ROCm clearly wins,** move llama-swap's `server` macro to the ROCm build. Re-run quality suites only if outputs look different.

## Blocked

- [ ] **Inkling Small (Thinking Machines, 276B-A12B MoE).** The GGUF (`unsloth/Inkling-Small-GGUF`, UD-Q2_K_XL, 88 GB, plus `mmproj-F16.gguf`) is in `~/models/inkling-small/`. It needs about 88 GB split across VRAM and RAM via `--n-cpu-moe`.
  - **Blocked on llama.cpp support.** Our build, b11850, doesn't know the `inkling` architecture. The only implementation is a draft pull request, [ggml-org/llama.cpp#25731](https://github.com/ggml-org/llama.cpp/pull/25731). Its new banded flash-attention kernel is CUDA-only, and Vulkan gets only small changes.
  - **Decision (2026-10-25):** wait until support is merged and released, then build it alongside b11850, add an `inkling-small` entry to llama-swap and `bench.yaml`, and run `quick` then `overnight`.
  - Still unchecked: recommended sampling settings, and whether thinking is on by default.

## Caveats in the current results

- [ ] **The `backup-rotation` terminal task was broken.** Its instructions say "Test it", but every test run leaves another today-dated archive. The old checker then ran the script twice more and expected the 2024-01-05 archive to survive, which is impossible once three newer archives exist. It failed in 29 of 30 runs across all models, which caps the existing terminal-x3 scores at 94.4% (17/18).
  - **Fixed 2026-10-25:** `verify` now restores the starting set of archives before running the script. The self-test passes both untouched and after the solution has been run twice, as a model testing its work would.
  - The re-run for every model is queued (stage B). Existing terminal-x3 numbers still include the old result until the corrected score is wired into the dashboard.
- [ ] **LiveCodeBench is capped by `max_tokens: 32768`.** Answers cut off at the cap count as failures, so these models' LCB scores are understated:

  | model | cut off (of 30) |
  |---|---|
  | nemotron-bolt | 17 |
  | nemotron-lightning | 16 |
  | qwen3.6-35b-a3b | 16 |
  | qwen3.8-27b | 12 |
  | thinkingcap-qwen3.8-27b | 11 |
  | flint | 7 |
  | laguna-xs-2.1 | 7 |

  A re-run at `max_tokens: 65536` is queued (stage C, suite `livecodebench-64k`, which uses `max_tokens_override` so it wins over each model's own limit).
  - **Context check:** llama-swap doesn't set `--parallel`, so llama-server uses one KV cache shared by its 4 slots (`--kv-unified` is the default when the slot count is automatic). A single answer can therefore use the whole context.
  - Four 66k-token answers at once would overflow a 262k pool, so the suite runs 3 requests at a time.
- [ ] **Strata's numbers may be contaminated.** Strata loaded while VRAM from the previous model was still in use. A clean re-run of its overnight profile is queued (stage D).
- [ ] **ThinkingCap vs. Qwen3.8-27B isn't an exact comparison.** ThinkingCap is Q4_K_M, while the base model is Unsloth UD-Q4_K_XL. Grab the same quant of both for a clean comparison.
  - ThinkingCap claims about 37% fewer reasoning tokens. On LCB it averaged 18.5k output tokens vs. 20.3k for the base, about 9% fewer.
- [ ] **LiveCodeBench uses only 30 problems.** That leaves a standard error of roughly ±9 points, so differences under about 10 points are noise. Consider sampling 60+ problems, or the whole v6 release (175), for the top few models.
- [ ] **HumanEval+ is saturated.** Nearly every model scores 95–100%, so it barely separates them. MBPP+ or more LiveCodeBench would be more informative.

## Not yet run

- [ ] `gpt-oss-20b` is in `bench.yaml` and its GGUF is in `~/models`, but it has never been benchmarked.
- [ ] The `full` profile (`speed` up to 64k prompts, `speed-concurrent`, full HumanEval+ and MBPP+, `terminal`) has never been run.
- [ ] The `kernels` suite (raw `llama-bench`) runs for six models in stage A. Extend it to the rest when we move off b11850. llama-bench suites now unload the served model first, so put them last in a run.
- [ ] `terminal-text` hasn't been run. It would show whether any model's terminal failures come from llama-swap's tool-call parsing rather than the model itself.

## Tooling and housekeeping

- [ ] **Add tests.** The only automated check is `aibench selftest` for terminal tasks. Unit tests for `report.build` and `dashboard.build_rows`, using a small fixture `run.json`, would catch regressions cheaply.
- [ ] **Refresh the dashboard automatically.** Today `uv run aibench dashboard` is run by hand after each run, `RESULTS.md` and `models.csv` are committed by hand, and the hosted copy is updated from a Claude Code session. Options:
  - Rebuild `dashboard/data/` at the end of every `aibench run`.
  - Add a `post_run:` hook to `bench.yaml`.
- [ ] **Delete the old CSV from the hosted dashboard.** Asset `03899cd1dfb17c0d936342a8fee9247c` is no longer referenced. Removing it was blocked by a permission prompt on 2026-10-25.
- [ ] **Update the dashboard's wording.** It still describes the overnight sweep as in progress ("so far", "Overnight run progress"). Rewrite it as a standing leaderboard now that all ten models have finished.
- [ ] **Make "running" detection more reliable.** `dashboard.py` marks a model as running only if it has a result in a run with no `finished` timestamp, so a model still on its first suite isn't shown yet. Writing the current model into `run.json` before its first suite would fix this.
- [ ] **Upgrade the `hf` CLI.** It's on 1.18.0 and 2.3.0 is available. Also note that `hf download` treats a second `--include` pattern as a filename, so pass multiple patterns to one flag, or run separate downloads.
