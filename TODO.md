# TODO

Open work, known caveats in the current results, and ideas we deliberately left for later. Last reviewed 2026-10-25.

## In progress

- [ ] **Quick-profile speed and HumanEval for ThinkingCap and Laguna.** Queued on 2026-10-25 to start once the Inkling download finishes:
  ```bash
  uv run aibench run -m thinkingcap-qwen3.8-27b -m laguna-xs-2.1 -s speed-quick -s humaneval-quick --tag baseline
  ```
  The log goes to `logs/baseline-thinkingcap-laguna.log`. Afterwards, refresh the dashboard. `terminal-quick` was skipped because both models already have the more thorough `terminal-x3`, so their "Terminal %" stays empty in the quick table.

## Blocked

- [ ] **Inkling Small (Thinking Machines, 276B-A12B MoE).** The GGUF (`unsloth/Inkling-Small-GGUF`, UD-Q2_K_XL, 88 GB, plus `mmproj-F16.gguf`) is in `~/models/inkling-small/`. It needs about 88 GB split across VRAM and RAM via `--n-cpu-moe`.
  - **Blocked on llama.cpp support.** Our build, b11850, doesn't know the `inkling` architecture. The only implementation is a draft pull request, [ggml-org/llama.cpp#25731](https://github.com/ggml-org/llama.cpp/pull/25731). Its new banded flash-attention kernel is CUDA-only, and Vulkan gets only small changes.
  - **Decision (2026-10-25):** wait until support is merged and released, then build it alongside b11850, add an `inkling-small` entry to llama-swap and `bench.yaml`, and run `quick` then `overnight`.
  - Still unchecked: recommended sampling settings, and whether thinking is on by default.

## Caveats in the current results

- [ ] **The `backup-rotation` terminal task is broken.** Its instructions say "Test it", but every test run leaves another today-dated archive. The checker then runs the script twice more and expects the 2024-01-05 archive to survive, which is impossible once three newer archives exist. It failed in 29 of 30 runs across all models, which caps terminal-x3 at 94.4% (17/18).
  - Fix: have `verify` reset `/work/backups` to its starting state before running the script.
  - Then re-run just that task for every model, using a terminal suite with `tasks: [backup-rotation]` and `repeats: 3`.
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

  To fix this, re-run `livecodebench` for those models with `max_tokens: 65536`. Before doing that, check that the context actually allows it: each server has 4 slots, so unless llama.cpp shares one KV cache across slots, each slot gets `ctx-size / 4`. That's 31,744 tokens for Laguna, already below the current cap. Raise `--ctx-size` in llama-swap, or use `--parallel 2` or a unified KV cache.
- [ ] **Strata's numbers may be contaminated.** Strata loaded while VRAM from the previous model was still in use. Re-run its suites on a clean GPU.
- [ ] **ThinkingCap vs. Qwen3.8-27B isn't an exact comparison.** ThinkingCap is Q4_K_M, while the base model is Unsloth UD-Q4_K_XL. Grab the same quant of both for a clean comparison.
  - ThinkingCap claims about 37% fewer reasoning tokens. On LCB it averaged 18.5k output tokens vs. 20.3k for the base, about 9% fewer.
- [ ] **LiveCodeBench uses only 30 problems.** That leaves a standard error of roughly ±9 points, so differences under about 10 points are noise. Consider sampling 60+ problems, or the whole v6 release (175), for the top few models.
- [ ] **HumanEval+ is saturated.** Nearly every model scores 95–100%, so it barely separates them. MBPP+ or more LiveCodeBench would be more informative.

## Not yet run

- [ ] `gemma-4-e4b` is the `small` model in `claude-local`, so it's used every day, but it isn't in `bench.yaml` and has never been benchmarked.
- [ ] `gpt-oss-20b` is in `bench.yaml` and its GGUF is in `~/models`, but it has never been benchmarked.
- [ ] The `full` profile (`speed` up to 64k prompts, `speed-concurrent`, full HumanEval+ and MBPP+, `terminal`) has never been run.
- [ ] The `kernels` suite (raw `llama-bench`) has never been run. It's the cleanest number for comparing llama.cpp builds, which will matter when we move off b11850.
- [ ] The `llamacpp-rocm` backend is configured, but `~/src/llama.cpp/build-rocm/` doesn't exist. Build llama.cpp with HIP to compare ROCm against Vulkan on the same GGUFs.
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
