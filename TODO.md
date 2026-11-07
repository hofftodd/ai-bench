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

- [x] **Finish DeepSeek V4 Flash** (below). `quick`, terminal-x3, LiveCodeBench at 32k (60.0%, re-run after the 2026-10-28 power outage) and at 64k (80.0%, 27 h, server context raised to 200,704 for 3 × 64k) are done. *Done 2026-10-30; see ANALYSIS.md.*
- [x] **A medium-effort alias in llama-swap.** `qwen3.8-27b-medium` is a llama-swap model now (llama-config `<new>=<base>` variant in models.conf, `--chat-template-kwargs`).
- [ ] **ThinkingCap at `medium`** on terminal-x3 (~20 min).
- [x] **ThinkingCap at the base's UD-Q4_K_XL**, to tell its fine-tune apart from its quant. No UD-Q4_K_XL of ThinkingCap exists, so it's bottlecap's f16 quantized locally with the base file's exact per-tensor types and Unsloth's imatrix (model `thinkingcap-qwen3.8-27b-udq4kxl`). It runs `overnight`, `livecodebench-64k` and `speed-quick` (~8 h), queued 2026-10-29 behind the DeepSeek 64k run (`logs/thinkingcap-udq4kxl.sh`). *Done 2026-10-31:* 80% at 64k again, so the gain is the fine-tune's (ANALYSIS.md).
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
- [x] **ThinkingCap vs. Qwen3.8-27B isn't an exact comparison.** ThinkingCap is Q4_K_M, while the base model is Unsloth UD-Q4_K_XL. *Resolved 2026-10-31:* ThinkingCap rebuilt at the base's UD-Q4_K_XL mix scores the same 80% at 64k.
  - ThinkingCap claims about 37% fewer reasoning tokens. On LCB it averaged 18.5k output tokens vs. 20.3k for the base, about 9% fewer.
- [ ] **LiveCodeBench uses only 30 problems.** That leaves a standard error of roughly ±9 points, so differences under about 10 points are noise. Consider sampling 60+ problems, or the whole v6 release (175), for the top few models.
- [ ] **HumanEval+ is saturated.** Nearly every model scores 95–100%, so it barely separates them. MBPP+ or more LiveCodeBench would be more informative.

## Not yet run

- [ ] `gpt-oss-20b` is in `bench.yaml` and its GGUF is in `~/models`, but it has never been benchmarked.
- [ ] The `full` profile (`speed` up to 64k prompts, `speed-concurrent`, full HumanEval+ and MBPP+, `terminal`) has never been run.
- [ ] The `kernels` suite (raw `llama-bench`) has run for six models (stage A). Extend it to the rest when we move off b11850. llama-bench suites now unload the served model first, so put them last in a run.
- [ ] `terminal-text` hasn't been run. It would show whether any model's terminal failures come from llama-swap's tool-call parsing rather than the model itself.

## Mac Studio (future)

The first queue (32k, 64k, 128k) is done. Since then (2026-11-06): Qwen3.8-Flash-Next on llama.cpp and Inkling-Small on oMLX, both in [ANALYSIS-mac.md](ANALYSIS-mac.md).

- [ ] **Upgrade sushi 1.4.1 → 1.5.0** (released 2026-11-04). Nothing in it changes output for our three packs (checked 2026-11-05); the useful parts are `sushi pull` verifying every file (re-pull to confirm our packs are intact) and, on main, per-request draft acceptance in `/metrics` (would explain MiMo's faster-at-8k reading) and ~6% faster Flash-Next decode on trellis-trunk packs. Re-measure sushi speeds after the upgrade.
- [ ] **DeepSeek V4.1 Flash.** The successor to our best model (V4 Flash on DwarfStar, 93.3% LCB at 64k), but much bigger: 763B parameters plus Engram tables, which both engines keep on the SSD. Options as of 2026-11-05:
  - **sushi `beamster/DeepSeek-V4.1-Flash-1017-Sushi-STQ-1.75bpw`** (first choice): 332 GB download, about 129 GB resident, so it fits fully in memory here. Needs sushi 1.5.0. sushi reports 89% top-1 agreement with the full model and 77 tok/s on code on a 128 GB Mac streaming from SSD.
  - **DwarfStar `antirez/deepseek-v4.1-flash-gguf` Q2** (366 GB): more than 256 GB, so it needs DwarfStar's SSD streaming; speed would partly measure the SSD. Check that our ds4 build (2026-11-03) supports V4.1.
  - Unsloth (300–500 GB) and ISTA's GSQ-RCO GGUFs (138 GB + 111 GB Engram) are too big or too tight.
  - V4.1 adds a reasoning-effort setting (`--think-level 1–100` on DwarfStar). Use each engine's default and record it.
  - Run `speed-quick-eos` and `livecodebench-64k`, the same as the best V4 Flash runs. Disk: 2.8 TB free.
- [ ] **Inkling 2 Small** (Thinking Machines, US; announced 2026-11-05): MoE, 594B total / 17B active, image input, variable reasoning effort. Only on Tinker so far; Apache 2.0 weights promised "next week" after safety testing, no firm date. On 256 GB it fits at 2–3 bits only (by scale from Inkling-Small's GGUFs: roughly 175–210 GB), the same tier as DeepSeek V4.1. Engine support is the catch: mainline llama.cpp doesn't run even the first Inkling (`inkling` arch, PR ggml-org/llama.cpp#25731 still open), so the options are that PR, Unsloth's llama.cpp fork, or MLX/oMLX (mlx-community has Inkling-Small builds). Run speed + `livecodebench-64k` once weights and a GGUF or MLX build exist. `~/dev/ai-tools/hf-watch` watches Hugging Face for the weights (its LaunchAgent still needs loading). *Warm-up done 2026-11-06: Inkling-Small (mlx-community 4-bit, 153 GB) on oMLX 0.7.3, 70.0% LCB at both 32k and 64k, 63 tok/s at 8k. oMLX is the engine to use when Inkling 2 Small arrives.*
- [ ] **oMLX** ([jundot/omlx](https://github.com/jundot/omlx)): standard MLX models (mlx-community conversions, oMLX's own oQ quants) with continuous batching and an SSD prompt cache. *Installed 2026-11-06 (0.7.3, Homebrew `jundot/omlx`); `omlx` backend in `bench-mac.yaml` serves `~/models/omlx/` (symlinks named after model ids). `~/.omlx/settings.json`: `max_context_window` raised from 32,768 to 135,168. First run: Inkling-Small.* Runs still to do, in order of value:
  - [x] **Qwen3.8-Flash-Next at 4 bits** (done 2026-11-06, `Jundot/Qwen3.8-Flash-Next-oQ4e-mtp`): 73.3% LCB at 64k, same depth as llama.cpp at twice the speed, best batching (211 tok/s at 8 in flight). The MTP-off speed run had MTP on (oMLX enables it for MTP checkpoints on first load) and is re-queued.
  - **Strata's answer lengths and sampling** from the R9700's run.json: Strata scored 83.3% at 32k with nothing cut off, where llama.cpp at 32k had 14 of 30 cut off.
  - [x] **qwen3.8-27b and flint as oQ4e vs the GGUF on llama.cpp (Metal)** (done 2026-11-07): same quality within noise, 1.3–1.6× faster 64k runs, much better batching (flint 351 vs 220 tok/s at 8 in flight). oMLX is the Mac default.
  - [ ] **Is oMLX's ~3-point deficit the quant?** oMLX scored 1 problem lower in 6 of 7 LCB pairs (net 6 of 210 problems, not significant). Run `Jundot/Qwen3.8-27B-oQ6e-mtp` at 64k (~3 h) against the oQ4e's 66.7% and llama.cpp's 70.0%.
  - [x] **Concurrency** (`speed-concurrent-eos`, 1/2/4/8 in flight): done for Flash-Next on all three Mac engines; queued for flint and qwen3.8-27b. Still to do: DwarfStar (ds4-q4), which batched worst.
- [ ] **Push role recommendations to Foreman** (`~/dev/foreman`) once the Mac benchmarking above is done. Draft as of 2026-11-05: planner, reviewer and escalation on ds4-q4 (Mac); executors on ThinkingCap (R9700) and flint (Mac, llama.cpp). Before that: terminal-x3 on the Mac (needs Docker) for ds4-q4 and flint, to check tool calling. Revisit with the oMLX results, which could change the Mac executor pool (MLX builds of flint or qwen3.8-27b, continuous batching for several executors) and the planner (Qwen3.8-Flash-Next). Also update the "Mac prefill latency" risk row in Foreman's `specs/000-orchestrator/plan.md`, which rests on the old assumption.
- [ ] **Disk wear, re-check monthly** (`smartctl -a disk0`; smartmontools installed 2026-11-06). Baseline 2026-11-06: internal APPLE SSD AP4096Z 2.47 TB written, 0% used, 100% spare; data1 (Crucial P310 4 TB, `disk6`) 1.85 TB written; data2 (Crucial P3 Plus 4 TB, `disk8`) 5.04 TB written; all 0% used. Disk speeds (uncached, through the AZW dock for the externals): internal 11.5 GB/s read, 7.9 write; data1 3.2 / 2.9; data2 2.9 / 2.8; random 64 KiB reads 6.4, 1.2 and 0.5 GB/s. Keep models on the internal SSD; data1 for overflow and disk caches, data2 for backups.
- [ ] **Tuning phase**: KV cache q8_0 vs f16 and `--cache-ram 0` on llama.cpp (`llama-bench -d 0,8192,32768`), MTP draft length, DwarfStar `--batched-session` and DSpark, sushi `--kv-quant 16` and MTP depth. Check quality on the winners.

## Tooling and housekeeping

- [x] **Add tests.** *Done 2026-10-31:* `uv run pytest` covers `report.build`/`load_runs` and `dashboard.build_rows`/`quant`/`write_data`/`write_markdown` (16 tests, fixtures in `tests/conftest.py`).
- [x] **Refresh the dashboard automatically.** *Done 2026-10-31:* `aibench run` rebuilds `dashboard/data/` and RESULTS.md when it ends (`--no-dashboard` to skip; never after `-n` runs, which the dashboard now ignores). Committing and the hosted copy are still manual.
- [ ] **Delete the old CSVs from the hosted dashboard.** Seven old copies of `models.csv` were no longer referenced. Two were deleted on 2026-10-31, and the permission check blocked the other five: `03899cd1dfb17c0d936342a8fee9247c`, `8cd1cb731c334cd75420d31cfe97c9ac`, `447e24477dac7746f2dec1fc91085ac5`, `c3e714fc68358e7ce75da30eb51e55a9`, `a45f3dcfb04957885c7f09c1669cbb74`. Only `datasets/models`' current CSV is in use.
- [x] **Update the dashboard's wording.** *Done 2026-10-31* (tiles, the model list and the summary line now read as a standing leaderboard).
- [x] **Make "running" detection more reliable.** *Done 2026-10-31:* the runner records `current` in run.json. Before, `dashboard.py` marked a model as running only once it had a result, so a model still on its first suite didn't show.
- [x] **Upgrade the `hf` CLI.** *Done 2026-10-31:* 2.4.0 (hf_xet 1.8.0). It was on 1.18.0, whose xet download stalled on 2026-10-29. Also note that `hf download` treats a second `--include` pattern as a filename, so pass multiple patterns to one flag, or run separate downloads.
