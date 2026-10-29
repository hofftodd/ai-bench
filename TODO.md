# TODO

Open work, known caveats in the current results, and ideas we deliberately left for later. Last reviewed 2026-10-25.

## Done: the Oct 25–26 queue

A queue started on 2026-10-25 runs these one at a time, once the Inkling download finishes. It's `logs/queue.sh`, running detached, so it survives the session. Progress goes to `logs/queue.log`, with one log per stage. It rebuilds `dashboard/data/` and `RESULTS.md` after each stage. Committing them, refreshing the hosted dashboard and updating ANALYSIS.md are still manual.

- [x] **0. Quick-profile speed and HumanEval for ThinkingCap and Laguna** (`baseline` tag, ~40 min). `terminal-quick` is skipped because both already have the more thorough `terminal-x3`. This stage also runs the full `quick` profile for `gemma-4-e4b` (~15 min). *Done 10:02.*
- [x] **A. ROCm vs. Vulkan speed** (`rocm-compare` tag, 40 min). *Done 10:41: Vulkan wins.* See [ROCm](#rocm-vs-vulkan) below.
- [x] **B. Re-run the fixed `backup-rotation` task** for all ten models (`terminal-backup-rotation` suite, `overnight-fix` tag, 1 h). *Done 11:38;* folded into terminal-x3.
- [x] **C. LiveCodeBench with a 64k thinking budget** (`livecodebench-64k` suite, `overnight-64k` tag, roughly 15–25 h). It covers qwen3.8, ThinkingCap, flint, gemma, qwen3.6 and both Nemotrons. It skips Strata and qwen3-coder (no cut-offs) and Laguna (recommended for retirement).
- [x] **D. Re-run Strata's overnight profile on a clean GPU** (~3 h). *Done Oct 26: same scores, clean VRAM baseline.*
- [x] **E. qwen3.8-27b at `reasoning_effort: medium`** (model `qwen3.8-27b-medium`, `overnight` profile, `effort-medium` tag, ~3 h). Qwen3.8's chat template defaults to `xhigh`, which tells the model to "think carefully through the task, validate key assumptions, consider plausible alternatives…", and nothing in aibench or llama-swap overrides it. So every qwen3.8 and ThinkingCap number so far is at maximum effort. Even at 64k, qwen3.8 still had 9 of 30 LiveCodeBench answers cut off. If `medium` keeps the terminal score and finishes inside 32k, it's the better setting both for the benchmark and for daily use. Run by `logs/after-queue.sh` once the queue ends.
- [x] **Then: download DeepSeek V4 Flash** (`unsloth/DeepSeek-V4-Flash-GGUF`, UD-Q2_K_XL, ~97 GB) into `~/models/deepseek-v4-flash/`. The detached `logs/after-queue.sh` starts the download when the queue finishes and logs to `logs/deepseek-download.log`. Until then (and during stage E) it records the GPU's PCIe link every 5 minutes in `logs/pcie-link.log`. See [DeepSeek V4 Flash](#deepseek-v4-flash) below.

**All stages finished on 2026-10-26** (queue 13:36, stage E 16:48, DeepSeek download 17:41, 91 GB). ANALYSIS.md has the write-up.

### ROCm vs. Vulkan

Quality scores don't depend on the backend (same GGUF, same sampling), so only speed is being compared.

- llama.cpp b11850 is built with HIP for gfx1201 in `~/src/llama.cpp-b11850/build-rocm/` (ROCm 7.1, no rocWMMA).
- The `llamacpp-rocm` backend and the `*-rocm` models in `bench.yaml` reproduce each model's llama-swap flags: context, MTP drafter, q8_0 KV cache, flash attention auto.
- Six models get `speed-quick` plus raw `kernels-rocm` (llama-bench), labeled `--hardware r9700-rocm`. The same six get `kernels` on Vulkan for the matching number.
- qwen3.8-27b-rocm and flint-rocm also run `humaneval-quick`. It's a check for a broken build, not a quality comparison.
- Compare with `uv run aibench report --hardware r9700-vulkan --hardware r9700-rocm -s speed-quick -s kernels -s kernels-rocm`.
- **Result (2026-10-25): stay on Vulkan.** ROCm generation at 8k context is 13–25% slower for five of the six models; only Nemotron Lightning is faster (+8%). Prompt processing is the same or slower, and much slower for Gemma (−43%). llama-bench agrees. Both HumanEval checks passed (100 / 97.5%), so the build itself is fine. RESULTS.md has the table.
- Worth re-checking only with a rocWMMA build or a newer ROCm/llama.cpp.

### Next

- [ ] **Finish DeepSeek V4 Flash** (below). `quick` and terminal-x3 are done (ANALYSIS.md). The overnight run's LiveCodeBench was lost to a power outage on 2026-10-28; re-run it alone with `-s livecodebench` (16+ h).
- [x] **A medium-effort alias in llama-swap.** `qwen3.8-27b-medium` is a llama-swap model now (llama-config `<new>=<base>` variant in models.conf, `--chat-template-kwargs`).
- [ ] **ThinkingCap at `medium`** on terminal-x3 (~20 min).
- [ ] **qwen3.8-27b at Q4_K_M** on `livecodebench-64k`, to tell ThinkingCap's fine-tune apart from its quant (~6 h).
- [ ] **Harder terminal tasks.** terminal-x3 is saturated (100 / 100 / 98.1).

### DeepSeek V4 Flash

The 284B mixture-of-experts model that [DwarfStar](https://github.com/antirez/ds4) was built for. It's a candidate for the "hard problems" role that Strata holds now.

- **Engine:** run it with llama.cpp, not DwarfStar. b11850 already supports the `deepseek4` architecture. DwarfStar's AMD support is Strix Halo-only: it needs more than 62 GB the GPU can address directly, and has no VRAM/RAM split for a 32 GB card.
- **Version:** V4.1 Flash GGUFs (233 GB and up) don't fit this machine.
- **Setup after the download:**
  - Add a llama-swap entry with `--n-cpu-moe`, so attention runs in VRAM and about 65 GB of experts stay in RAM.
  - Smoke-test it, then add `deepseek-v4-flash` to `bench.yaml` with DeepSeek's recommended sampling.
  - Run `quick` and `overnight`. *Done except LiveCodeBench.*
- **Speed:** much slower than Strata: ~9 tok/s generation, 42 tok/s prompt processing (CPU-side experts). It can't be loaded alongside Strata.

### PCIe link

The R9700 sits behind a 4-lane link. The root port supports 16 GT/s, but the link runs at 8 GT/s (PCIe 3.0, ~3.9 GB/s). `logs/pcie-link.log` shows 8 GT/s even at 93–96% GPU load, so it isn't idle power-saving: the link trains at half speed. Model loading and every RAM-offloaded model (Strata, Inkling, DeepSeek) are slower than they need to be.
- [ ] Check the BIOS PCIe speed setting and the OCuLink/riser cable; a marginal cable often makes a link fall back to Gen3. `sudo lspci -vv -s 03:00.0` shows `LnkSta` and whether the card itself reports a downgrade.

## Blocked

- [ ] **Inkling Small (Thinking Machines, 276B-A12B MoE).** The GGUF (`unsloth/Inkling-Small-GGUF`, UD-Q2_K_XL, 88 GB, plus `mmproj-F16.gguf`) is in `~/models/inkling-small/`. It needs about 88 GB split across VRAM and RAM via `--n-cpu-moe`.
  - **Blocked on llama.cpp support.** Our build, b11850, doesn't know the `inkling` architecture. The only implementation is a draft pull request, [ggml-org/llama.cpp#25731](https://github.com/ggml-org/llama.cpp/pull/25731). Its new banded flash-attention kernel is CUDA-only, and Vulkan gets only small changes.
  - **Decision (2026-10-25):** wait until support is merged and released, then build it alongside b11850, add an `inkling-small` entry to llama-swap and `bench.yaml`, and run `quick` then `overnight`.
  - Still unchecked: recommended sampling settings, and whether thinking is on by default.

## Caveats in the current results

- [x] **The `backup-rotation` terminal task was broken.** Its instructions say "Test it", but every test run leaves another today-dated archive. The old checker then ran the script twice more and expected the 2024-01-05 archive to survive, which is impossible once three newer archives exist. It failed in 29 of 30 runs across all models, which caps the existing terminal-x3 scores at 94.4% (17/18).
  - **Fixed 2026-10-25:** `verify` now restores the starting set of archives before running the script. The self-test passes both untouched and after the solution has been run twice, as a model testing its work would.
  - Re-run for every model on 2026-10-25 (stage B). The task now separates models (from 3/3 down to 0/3), and every failure checked was the model's fault. `dashboard.py` substitutes the new per-task result into terminal-x3; the original score is the "as run" column.
- [ ] **terminal-x3 is saturated.** With the fix, Strata and qwen3.8-27b score 100% and ThinkingCap 98.1%. The suite can no longer rank the top models; see ANALYSIS.md experiment 3.
- [x] **LiveCodeBench is capped by `max_tokens: 32768`.** *Re-run at 64k on Oct 25–26; results in ANALYSIS.md and RESULTS.md.* The original note: Answers cut off at the cap count as failures, so these models' LCB scores are understated:

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
- [x] **Strata's "VRAM already in use" warning was a measurement bug.** The `process` backend ran its `pre:` hook (which empties llama-swap) after the runner had recorded the VRAM baseline, so the baseline still included the previous model. Fixed 2026-10-25: `pre:` now runs in `free_gpu()`, before the baseline. Strata most likely had the GPU to itself all along. Stage D re-runs it anyway and will confirm with the corrected measurement.
- [ ] **ThinkingCap vs. Qwen3.8-27B isn't an exact comparison.** ThinkingCap is Q4_K_M, while the base model is Unsloth UD-Q4_K_XL. Grab the same quant of both for a clean comparison.
  - ThinkingCap claims about 37% fewer reasoning tokens. On LCB it averaged 18.5k output tokens vs. 20.3k for the base, about 9% fewer.
- [ ] **LiveCodeBench uses only 30 problems.** That leaves a standard error of roughly ±9 points, so differences under about 10 points are noise. Consider sampling 60+ problems, or the whole v6 release (175), for the top few models.
- [ ] **HumanEval+ is saturated.** Nearly every model scores 95–100%, so it barely separates them. MBPP+ or more LiveCodeBench would be more informative.

## Not yet run

- [ ] `gpt-oss-20b` is in `bench.yaml` and its GGUF is in `~/models`, but it has never been benchmarked.
- [ ] The `full` profile (`speed` up to 64k prompts, `speed-concurrent`, full HumanEval+ and MBPP+, `terminal`) has never been run.
- [ ] The `kernels` suite (raw `llama-bench`) has run for six models (stage A). Extend it to the rest when we move off b11850. llama-bench suites now unload the served model first, so put them last in a run.
- [ ] `terminal-text` hasn't been run. It would show whether any model's terminal failures come from llama-swap's tool-call parsing rather than the model itself.

## Tooling and housekeeping

- [ ] **Add tests.** The only automated check is `aibench selftest` for terminal tasks. Unit tests for `report.build` and `dashboard.build_rows`, using a small fixture `run.json`, would catch regressions cheaply.
- [ ] **Refresh the dashboard automatically.** Today `uv run aibench dashboard` is run by hand after each run, `RESULTS.md` and `models.csv` are committed by hand, and the hosted copy is updated from a Claude Code session. Options:
  - Rebuild `dashboard/data/` at the end of every `aibench run`.
  - Add a `post_run:` hook to `bench.yaml`.
- [ ] **Delete the old CSVs from the hosted dashboard.** Assets `03899cd1dfb17c0d936342a8fee9247c` and `8cd1cb731c334cd75420d31cfe97c9ac` are no longer referenced. Removing it was blocked by a permission prompt on 2026-10-25.
- [ ] **Update the dashboard's wording.** It still describes the overnight sweep as in progress ("so far", "Overnight run progress"). Rewrite it as a standing leaderboard now that all ten models have finished.
- [ ] **Make "running" detection more reliable.** `dashboard.py` marks a model as running only if it has a result in a run with no `finished` timestamp, so a model still on its first suite isn't shown yet. Writing the current model into `run.json` before its first suite would fix this.
- [ ] **Upgrade the `hf` CLI.** It's on 1.18.0 and 2.3.0 is available. Also note that `hf download` treats a second `--include` pattern as a filename, so pass multiple patterns to one flag, or run separate downloads.
