# Analysis of the October 2026 runs

An analysis of the first full sweep: 10 models on the R9700 (32 GB, llama.cpp b11850 on Vulkan), quick profile on Oct 23 and overnight profile (terminal-x3 + LiveCodeBench) on Oct 23–24, plus the follow-up runs of Oct 25–26 (fixed terminal task, ROCm comparison, baselines, LiveCodeBench at 64k, a Strata re-run and qwen3.8 at medium reasoning effort), and DeepSeek V4 Flash on Oct 27–29. Last updated 2026-10-29 21:00. The numbers are in [RESULTS.md](RESULTS.md). Open work is tracked in [TODO.md](TODO.md).

**In short:**

- The rankings are mostly what we expected.
- Two benchmark problems distorted the top of the table, and both are now dealt with:
  - One terminal task was broken, capping everyone at 94.4%. With it fixed, **Strata and qwen3.8-27b score 100%** on terminal-x3 and ThinkingCap 98.1%. The suite is now saturated at the top and needs harder tasks.
  - LiveCodeBench at 32k mostly measured who finishes thinking in time. At 64k most reasoning models land at 63–67%, within noise of each other, while **ThinkingCap (80%)** and **Strata (83.3%)** pull clear.
- **ThinkingCap is the best model that fits in VRAM:** 98.1% terminal-x3, 80% LiveCodeBench at 64k, and 28% fewer tokens than its base on hard problems. It's the new main-agent pick. **Strata** is still the strongest solver, but too slow for interactive work.
- **Qwen3.8 thinks at maximum effort by default.** Its chat template defaults to `reasoning_effort: xhigh`. At `medium`, qwen3.8-27b finished terminal-x3 twice as fast with 62% fewer tokens (92.6% vs 100%), but LiveCodeBench didn't change at all.
- **Give reasoning models at least 64k output tokens.** At 32k, a third or more of hard answers are cut off.
- **Stay on Vulkan.** ROCm is 13–25% slower at generation for most models.
- **DeepSeek V4 Flash is accurate but very slow here, and doesn't beat Strata.** 96.3% terminal-x3 and 97.5% HumanEval+, but at ~9 tok/s it took 250 minutes for terminal-x3 (14× ThinkingCap). LiveCodeBench at 32k: 60.0% in 15 hours, against Strata's 83.3% in 1.9 hours, with 9 answers cut off. A 64k run is under way.

---

## 1. Did we get the results we expected?

### Mostly yes

| expectation | result | verdict |
|---|---|---|
| The biggest model wins on quality. Strata runs Qwen3.8-Flash-Next with ~50 GB of experts in RAM, much larger than anything that fits in VRAM. | Best LiveCodeBench (83.3%, the only reasoning model with no cut-offs) and tied best terminal-x3 (100%). A second run on Oct 26 gave exactly the same scores. ThinkingCap at 64k comes within 3.3 points. | ✅ as expected |
| A dense 27B reasoning model beats ~3B-active MoEs on agentic work. | qwen3.8-27b ties Strata on terminal-x3 (100%) with the fewest turns (6.0) and no bad tool calls. The ~3B-active MoEs score 74–94%. | ✅ |
| Older non-reasoning coders fall behind. | qwen3-coder-30b: 10% LCB, 51.9% terminal-x3 (0/3 on the fixed task too), and it ran out of turns in 12 of 54 episodes. | ✅ It's a 2025 instruct model with no thinking, so this was expected. |
| ThinkingCap matches the base model with ~37% fewer reasoning tokens. | Terminal is the same within noise (98.1 vs 100). It used **31% fewer** output tokens there (1,229 vs 1,787) and finished 30% faster. At a 32k budget LCB showed only 9% fewer tokens, because both were cut off so often. At 64k the gap is **28%** (24.1k vs 33.3k), and ThinkingCap scores *higher*: 80% vs 66.7%, with 5 cut-offs vs 9. | ✅ The claim holds once the budget is big enough to see it. Note: the two use different quants. |
| Nemotron Bolt (74B-A9B) beats Lightning (30B-A3B). | Terminal: 92.6 vs 74.1, as expected. LCB at 64k: 63.3 vs 66.7, still a tie; Bolt still had 10 cut-offs, Lightning only 2. | ✅ on terminal, ❌ on LCB |
| Speculative decoding helps the models that ship a drafter. | Draft acceptance is 63–77% (Strata 77%, qwen3.8 70%, Lightning 68%, Bolt 63%). Lightning has the fastest generation of any model (131 tok/s at 8k). | ✅ |
| Laguna XS 2.1 (poolside, 33B-A3B coder) is competitive with the other ~3B-active coders. | The weakest of the 2026 models: 33.3% LCB, 77.8% terminal-x3. Only 10 of its 23 LCB answers that weren't cut off passed. All the other thinking models passed at least 79%, and most passed 93% or more. Its failures are mostly plain wrong answers. | ❌ below expectations |

### Two things we did *not* expect, and they change how to read the table

**1. LiveCodeBench mostly measures who finishes inside 32k tokens.** Among answers that weren't cut off at `max_tokens`, the thinking models are nearly perfect:

| model | LCB pass@1 | cut off | passed when not cut off |
|---|---:|---:|---:|
| thinkingcap-qwen3.8-27b | 63.3 | 11 | 18/19 (95%) |
| qwen3.8-27b | 56.7 | 12 | 17/18 (94%) |
| nemotron-lightning | 50.0 | 16 | 13/14 (93%) |
| qwen3.6-35b-a3b | 50.0 | 16 | 13/14 (93%) |
| nemotron-bolt | 46.7 | 17 | 12/13 (92%) |
| flint | 63.3 | 7 | 19/23 (83%) |
| gemma-4-26b | 73.3 | 2 | 22/28 (79%) |
| strata | 83.3 | 0 | 25/30 (83%) |
| deepseek-v4-flash | 60.0 | 9 | 18/21 (86%) |
| laguna-xs-2.1 | 33.3 | 7 | 10/23 (43%) |

Most cut-offs are on the hard problems, so not every cut-off answer would pass with more room. Still, the 32k LCB ranking among the reasoning models was mostly a ranking of **token efficiency**, not problem-solving ability.

**The 64k re-run confirms it.** The same 30 problems with `max_tokens: 65536` (3 requests at a time):

| model | 32k | cut off | 64k | cut off | avg output at 64k | 64k run time |
|---|---:|---:|---:|---:|---:|---:|
| thinkingcap-qwen3.8-27b | 63.3 | 11 | **80.0** | 5 | 24.1k | 4.5 h |
| nemotron-lightning | 50.0 | 16 | 66.7 | 2 | 36.7k | 2.8 h |
| qwen3.6-35b-a3b | 50.0 | 16 | 66.7 | 7 | 40.9k | 2.9 h |
| qwen3.8-27b | 56.7 | 12 | 66.7 | 9 | 33.3k | 6.5 h |
| flint | 63.3 | 7 | 66.7 | 1 | 20.5k | 1.6 h |
| gemma-4-26b | 73.3 | 2 | 66.7 | 1 | 17.1k | 1.4 h |
| nemotron-bolt | 46.7 | 17 | 63.3 | 10 | 34.3k | 3.5 h |
| strata (32k only, for reference) | 83.3 | 0 | | | 16.5k | 1.9 h |

- **The models that were cut off most gained 10–17 points.** Six of the seven now sit at 63–67%. With 30 problems that spread is noise, so they're effectively tied.
- **Gemma shows the noise level.** It barely needed more room (2 → 1 cut-off), yet scored 6.7 points lower than at 32k. A re-run of the same problems can therefore move a score by about ±7 points.
- **ThinkingCap and Strata are the real outliers.** ThinkingCap gained 17 points by finishing more hard problems (67% of the hard half, against 40% for its base). Strata matched its earlier 83.3% exactly on a second run.
- **qwen3.8-27b and Bolt still need more than 64k on hard problems** at their default effort (9 and 10 cut-offs).

**2. One terminal task was broken, which capped terminal-x3 at 94.4%.**
- `backup-rotation` failed in 29 of 30 runs across all models. Its instructions say "Test it", but every test run leaves another today-dated archive. The checker then ran the script twice more and expected the 2024-01-05 archive to survive, which is impossible once three newer archives exist.
- So a model that followed the instructions failed. The only pass (one Laguna run) was a model that didn't test its script, or cleaned up afterwards.
- **Fixed and re-run on Oct 25.** The checker now restores the starting archives first. The fixed task separates the models:

  | backup-rotation (fixed) | models |
  |---|---|
  | 3/3 | qwen3.8-27b, ThinkingCap, Strata, Flint, Nemotron Bolt, Laguna |
  | 2/3 | Nemotron Lightning |
  | 1/3 | qwen3.6-35b-a3b |
  | 0/3 | gemma-4-26b, qwen3-coder-30b |

  Every failure checked was the model's own: deleting `README.keep` or the whole backups directory while testing, leaving a stray file behind, or archiving the wrong paths.
- With the new result substituted, terminal-x3 is **100% for Strata and qwen3.8-27b**, 98.1% for ThinkingCap and 94.4% for Flint. Bolt (+5.6), Flint (+5.6) and ThinkingCap (+5.5) gain the most; Gemma and qwen3-coder don't move. Strata's Oct 26 re-run, which included the fixed task, also scored 100%.
- **The top of terminal-x3 is now saturated.** Strata, qwen3.8 and ThinkingCap can't be separated by this suite.

### A third finding: qwen3.8 runs at maximum reasoning effort by default

Qwen3.8's chat template takes `reasoning_effort` (`xhigh`, `medium` or `low`) and defaults to `xhigh`, which adds an instruction to "think carefully through the task, validate key assumptions, consider plausible alternatives…". Nothing in aibench or llama-swap set it, so every qwen3.8 and ThinkingCap result above is at `xhigh`. A run at `medium` (`qwen3.8-27b-medium`, sent per request as `chat_template_kwargs`) on Oct 26:

| qwen3.8-27b | xhigh (default) | medium |
|---|---:|---:|
| terminal-x3 pass | 100% | 92.6% |
| terminal-x3 avg output per episode | 1,787 tok | **686 tok** (−62%) |
| terminal-x3 avg turns | 6.0 | 4.8 |
| terminal-x3 wall time | 25.1 min | **11.7 min** |
| LiveCodeBench pass@1 (32k) | 56.7% | 56.7% |
| LiveCodeBench cut off | 12 | 12 |
| LiveCodeBench avg output | 20.3k tok | 19.6k tok |

- **On agentic work, medium halves the time** for a small loss. It failed `backup-rotation` three times: each time it left its own test files (`keepme.txt`, `other.tar.gz`…) in the backups directory, the kind of cleanup that `xhigh`'s "validate key assumptions" catches. It also failed one `fix-c-build` run.
- **On hard problems it changes nothing.** The model thinks just as long, so the instruction matters for routine work but not when the problem itself demands thought.
- So `medium` is a good setting for quick, routine agent tasks: qwen3.8 at medium is as fast end-to-end as qwen3.6-35b-a3b (11.7 vs 11.3 min) and scores 11 points higher. Keep `xhigh` for hard problems.

### DeepSeek V4 Flash: first results

DeepSeek V4 Flash (284B total, 13B active) at Unsloth UD-Q2_K_XL (91 GB) runs through llama-swap with the experts of 34 of its 43 layers in system RAM (`--n-cpu-moe 34`, `--threads 8`). It ran `quick` and terminal-x3 on Oct 27–28:

| | deepseek-v4-flash | thinkingcap-qwen3.8-27b | strata |
|---|---:|---:|---:|
| terminal-x3 | 96.3% | 98.1% | 100% |
| terminal-x3 wall time | **250 min** | 17.5 min | 50.8 min |
| terminal-x3 avg turns | 7.5 | 5.6 | |
| terminal-x3 avg output per episode | 1,643 tok | 1,229 tok | |
| HumanEval / HumanEval+ (quick) | 97.5 / 97.5 | 100 / 95 | |
| generation @8k | 9.0 tok/s | 53.2 tok/s | |
| prompt processing @8k | 42 tok/s | 902 tok/s | 780 tok/s |
| time to first token @8k | 197 s | 9.5 s | 10.5 s |

- **Quality is in the top group.** It passed all 6 quick terminal tasks and 52 of 54 terminal-x3 episodes; it lost one run each of `git-bisect` and `log-error-report`. It passed the fixed `backup-rotation` 3/3. Tool calls were clean (0 bad calls), and it never ran out of turns.
- **Speed rules it out for interactive work.** Prompt processing at 42 tok/s is the real problem: an agent turn that re-reads 8k tokens of context waits over 3 minutes before it writes anything. Generation is also ~6× slower than the 27B dense models.
- **LiveCodeBench at 32k: 60.0%, well behind Strata.** The overnight run's LCB was lost to a power outage on Oct 28, so it was re-run alone on Oct 28–29 (run `20261028-205421-247e`):

  | LCB at 32k | deepseek-v4-flash | strata | thinkingcap-qwen3.8-27b |
  |---|---:|---:|---:|
  | pass@1 | 60.0% | **83.3%** | 63.3% |
  | medium / hard | 12/15 · 6/15 | | |
  | cut off | 9 (7 hard) | 0 | 11 |
  | passed when not cut off | 18/21 (86%) | 25/30 (83%) | 18/19 (95%) |
  | avg output | 18.2k tok | 16.5k tok | |
  | run time | **15.2 h** | 1.9 h | 2.6 h |

  - It belongs with the models the 32k cap holds back: 7 of its 12 misses were hard problems cut off at 32,768 tokens, each after 3.4–3.7 hours. Of the answers it finished, it got 18 of 21 right, the same as the others.
  - With 4 requests in flight it decoded at only ~2.7 tok/s each, so one 32k answer takes over 3 hours.
  - Strata had no cut-offs at 32k, so a bigger budget can't change its score. DeepSeek would need to gain more than 23 points at 64k to match it, which no model has done (the best gain was ThinkingCap's 17). **A 64k run started on Oct 29** to settle it; it will likely take more than 20 hours.

### Other observations

- **Tool calling is clean everywhere.** There were zero malformed tool calls and zero tool calls written as plain text, across all 540 terminal episodes. llama-swap's chat templates and tool parsers work for every model tested, so `terminal-text` isn't urgent.
- **Gemma 4 is verbose in agentic loops.** It used 6,455 output tokens per episode (3.6× qwen3.8) and 12.7 turns, ran out of turns 4 times, and took 80 minutes for terminal-x3. It's the opposite in LCB, where it was among the most concise.
- **Strata had the GPU to itself after all.** Its "VRAM already in use" warning was a measurement bug: the llama-swap unload ran after aibench recorded the VRAM baseline, so the baseline still counted the previous model. Fixed on Oct 25. Strata simply fills the card (31.5 of 31.9 GiB) by design.
- **Strata's prompt processing is slow.** 158 tok/s at 512 tokens and 780 tok/s at 8k, with 10.5 s to the first token at 8k. That's 4–20× slower than the llama.cpp models, and it hurts agent loops, which re-read growing context on every turn.
- **Laguna's decode speed in terminal-x3 was 12 tok/s, against 34 tok/s in LCB.** No other model shows a gap that large. It isn't the server: `speed-quick` measured 131 tok/s at 512 tokens and 122 tok/s at 8k, among the fastest of any model. The cause is something about how Laguna behaves in the agent loop, and isn't worth chasing for a model we recommend retiring.
- **Nemotron Bolt's IQ2_XXS is the official release, not a cut-down quant.** The Quant column shows it at a much lower precision than the other models (mostly 4–6 bit). NVIDIA built the 24 GB version to run at 2 bits: it quantized the experts to 2-bit and then trained further (quantization-aware distillation) to recover the accuracy, and reports little to no loss. NVIDIA's own benchmarks are for this file. Higher quants exist (Unsloth's, up to Q8_0), but they're made from the full-precision weights without that training, and from Q3 up they no longer fit in VRAM. We didn't test them: Bolt is already the slowest llama.cpp model here, and the retire recommendation stands.
- **ROCm is slower than Vulkan on this card.** Same GGUFs, same llama.cpp release, built with HIP for gfx1201:

  | model | gen @8k Vulkan → ROCm | prompt 8k Vulkan → ROCm |
  |---|---|---|
  | qwen3.6-35b-a3b | 95 → 72 (−25%) | 3,559 → 3,113 (−13%) |
  | flint | 79 → 62 (−21%) | 3,391 → 3,057 (−10%) |
  | thinkingcap-qwen3.8-27b | 53 → 44 (−18%) | 902 → 910 (+1%) |
  | qwen3.8-27b | 53 → 46 (−13%) | 907 → 857 (−6%) |
  | gemma-4-26b | 76 → 66 (−13%) | 3,482 → 1,969 (−43%) |
  | nemotron-lightning | 131 → 142 (+8%) | 3,023 → 2,774 (−8%) |

  Raw llama-bench numbers agree. The build has no rocWMMA, which mainly affects prompt processing, but generation is where ROCm loses most. No reason to switch.
- **Energy:** qwen3.8-27b's 32k LCB run used 2.9 MJ in 3 hours at 271 W, and its 64k run 6.5 MJ. Gemma solved as many problems with about a sixth of that (1.1 MJ).

---

## 2. Should we run more tuning experiments?

Yes. These are in priority order, by value per GPU-hour:

1. ~~**Fix `backup-rotation` and re-run just that task.**~~ *Done Oct 25; see section 1.*
2. ~~**Raise LiveCodeBench's `max_tokens` to 65,536.**~~ *Done Oct 25–26; see section 1.* ThinkingCap rose to 80%; most others converged at 63–67%.
3. **Make terminal harder.** This is now the top priority: two models score 100% and a third 98.1%.
   - Add longer-horizon tasks: multi-file refactors, debugging a failing test suite, tasks that need 20+ turns.
   - Or report `avg turns` and tokens per task alongside pass rate as the tie-breakers.
4. ~~**Re-run Strata on a clean GPU.**~~ *Done Oct 26:* VRAM before loading was 0.06 GiB, confirming the earlier warning was the measurement bug. The scores repeated exactly: 100% terminal-x3, 83.3% LCB.
5. **Compare ThinkingCap and its base on the same quant.** We have ThinkingCap at Q4_K_M and the base at UD-Q4_K_XL. Its 80% vs 66.7% at 64k makes this more interesting: is it the fine-tune or the quant? Run the base at Q4_K_M on `livecodebench-64k` (~6 h).
6. **Measure single-user server settings.** llama-swap runs every model with 4 slots. Generation drops from ~52 tok/s alone to ~15–20 tok/s per request with 4 in flight (qwen3.8). For one person driving one agent, `--parallel 1` gives each request the full context and maximum speed. Run `speed-concurrent` to put numbers on it.
7. **Sample more LCB problems for the top contenders.** With 30 problems, the standard error is about ±9 points, and the Gemma re-run moved 6.7 points with no real change. ThinkingCap (80) vs Strata (83.3) and the 63–67% cluster need 60–90 problems to settle.
8. ~~**Benchmark `gemma-4-e4b`.**~~ *Done Oct 25:* 100% HumanEval (95% HumanEval+), 3 of 6 quick terminal tasks, 85 tok/s generation and the fastest prompt processing measured (4,349 tok/s at 8k, 2.0 s to first token).
9. ~~**Compare ROCm and Vulkan.**~~ *Done Oct 25:* Vulkan wins (see above).
10. ~~**Try a lower reasoning effort.**~~ *Done Oct 26 for qwen3.8-27b at `medium`; see section 1.* Next: ThinkingCap at `medium` on terminal-x3 (~20 min) to see whether the two savings stack.
11. **Finish DeepSeek V4 Flash.** `quick`, terminal-x3 and LiveCodeBench at 32k (60.0%) are done (see section 1). `livecodebench-64k` started Oct 29 (20+ h).
12. **Find out why the PCIe link runs at half speed.** The R9700's x4 link trains at 8 GT/s even under full load, against 16 GT/s supported. It matters most for model loading and RAM-offloaded models (Strata, DeepSeek V4 Flash). It's a BIOS or cable check, not a benchmark.

Not worth the time: more HumanEval+ (every model scores 95–100%), and more runs of qwen3-coder-30b or Laguna.

---

## 3. Which models to use, and for what

Recommendations for this machine (R9700 32 GB, 90 GB RAM, llama-swap), based on the current numbers and the caveats above:

| role | recommendation | why | runner-up |
|---|---|---|---|
| **Main coding agent** (Claude Code via `claude-local`, opencode, pi) | **ThinkingCap** (thinkingcap-qwen3.8-27b) | 98.1% terminal-x3 with the fewest turns (5.6), 80% LCB at 64k (second only to Strata), no bad tool calls, and ~30% fewer tokens than its base. Set the client's max output to 64k or more. | qwen3.8-27b |
| **Hard algorithmic problems, "think harder" escalation** | **strata** | Best LCB (83.3%, twice), never ran out of tokens, solved 73–80% of hard problems. But it's slow to read prompts and needs ~60 GB RAM and the whole GPU, so use it for batch jobs or stubborn problems, not as the always-on agent. | ThinkingCap with a 64k budget |
| **One-shot code generation** (write this function or script, no tool loop) | **gemma-4-26b** | 67–73% LCB with the shortest answers (17k tokens) and the fastest runs (1.4 h for 30 problems at 64k, vs 4.5 h for ThinkingCap). Use ThinkingCap instead when the problem is hard. | flint |
| **Fast all-round coder** (good quality, high throughput) | **flint** | Good at everything: 94.4% terminal, 63.3% LCB, 2,650 tok/s prompt processing, 79 tok/s generation, never ran out of turns. The best choice when qwen3.8's ~52 tok/s feels slow. | qwen3.6-35b-a3b |
| **Quick edits, short agent tasks** | **qwen3.8-27b at `reasoning_effort: medium`** | 92.6% terminal-x3 in 11.7 minutes, as fast end-to-end as qwen3.6 and 11 points better, because it writes 62% fewer tokens. Needs the client to send `chat_template_kwargs: {"reasoning_effort": "medium"}`, or a llama-swap alias that sets it. | qwen3.6-35b-a3b (11.3 min, 81.5%, 95 tok/s, smaller VRAM footprint) |
| **Long-context reading** (big logs, whole-repo questions) | **nemotron-lightning** | The only model fitted to a 786k context. Fastest generation (131 tok/s), with fast prompt processing (3,000 tok/s at 8k). Weaker on hard agentic tasks (74.1%), so use it for reading, not multi-step changes. | — |
| **Small, background model** (titles, summaries, classification) | **gemma-4-e4b** (keep) | Fastest prompt processing measured (2.0 s to first token at 8k) and 85 tok/s, with 100% on HumanEval. Too weak for agent work (3 of 6 quick terminal tasks), which isn't its job. | — |

**Retire or skip:**
- **qwen3-coder-30b**: superseded on every metric except raw prompt speed.
- **laguna-xs-2.1**: the weakest of the 2026 models, even when it finishes thinking. Revisit only if poolside ships an update.
- **nemotron-bolt**: a good agent (92.6%), but it's the slowest llama.cpp model (45.7 tok/s at 8k) and took twice as long as Flint on terminal-x3 (85 vs 44 minutes) for a slightly lower score.

**Backend:** keep llama-swap on the Vulkan build.

**Waiting on:**
- **DeepSeek V4 Flash (284B-A13B)** scores near the top on terminal-x3 (96.3%) but runs at ~9 tok/s with 197 s to first token at 8k, so it can't be an interactive agent. At 32k it scored 60.0% on LiveCodeBench against Strata's 83.3%, eight times slower, so Strata stays the escalation pick unless the 64k run closes the gap.
- **Inkling Small (276B-A12B)** could too, but it needs mainline llama.cpp support first.
- **gpt-oss-20b** is configured but hasn't been run.
