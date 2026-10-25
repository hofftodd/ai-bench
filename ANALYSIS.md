# Analysis of the October 2026 runs

An analysis of the first full sweep: 10 models on the R9700 (32 GB, llama.cpp b11850 on Vulkan), quick profile on Oct 23 and overnight profile (terminal-x3 + LiveCodeBench) on Oct 23–24. The numbers are in [RESULTS.md](RESULTS.md). Open work is tracked in [TODO.md](TODO.md).

**In short:**

- The rankings are mostly what we expected.
- Two benchmark problems distort the top of the table. LiveCodeBench mostly measures which models finish thinking within 32k tokens, and one terminal task is broken, which caps everyone at 94.4%.
- Both are cheap to fix. Fixing them is the most valuable next experiment, more valuable than adding models.
- For daily agentic coding, **qwen3.8-27b / ThinkingCap** are the best all-rounders. **Strata** is the strongest solver but too slow for interactive work.

---

## 1. Did we get the results we expected?

### Mostly yes

| expectation | result | verdict |
|---|---|---|
| The biggest model wins on quality. Strata runs Qwen3.8-Flash-Next with ~50 GB of experts in RAM, much larger than anything that fits in VRAM. | Best LiveCodeBench (83.3%, the only model with 0 cut-offs) and tied best terminal-x3 (94.4%). | ✅ as expected |
| A dense 27B reasoning model beats ~3B-active MoEs on agentic work. | qwen3.8-27b ties Strata on terminal-x3 with the fewest turns (6.0) and no bad tool calls. | ✅ |
| Older non-reasoning coders fall behind. | qwen3-coder-30b: 10% LCB, 51.9% terminal-x3, and it ran out of turns in 12 of 54 episodes. | ✅ It's a 2025 instruct model with no thinking, so this was expected. |
| ThinkingCap matches the base model with ~37% fewer reasoning tokens. | Quality is the same within noise (terminal 92.6 vs 94.4, LCB 63.3 vs 56.7). It used **31% fewer** output tokens on terminal tasks (1,229 vs 1,787) and finished them 30% faster. On LCB, only **9% fewer** (18.5k vs 20.3k). | ⚠️ The claim holds for agentic work but not for hard competitive programming. Note: the two use different quants. |
| Nemotron Bolt (74B-A9B) beats Lightning (30B-A3B). | Terminal: 87.0 vs 70.4, as expected. LCB: 46.7 vs 50.0, a tie within noise, both dominated by cut-offs. | ✅ on terminal, inconclusive on LCB |
| Speculative decoding helps the models that ship a drafter. | Draft acceptance is 63–77% (Strata 77%, qwen3.8 70%, Lightning 68%, Bolt 63%). Lightning has the fastest generation of any model (131 tok/s at 8k). | ✅ |
| Laguna XS 2.1 (poolside, 33B-A3B coder) is competitive with the other ~3B-active coders. | The weakest of the 2026 models: 33.3% LCB, 74.1% terminal-x3. Only 10 of its 23 LCB answers that weren't cut off passed. All the other thinking models passed at least 79%, and most passed 93% or more. Its failures are mostly plain wrong answers. | ❌ below expectations |

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
| laguna-xs-2.1 | 33.3 | 7 | 10/23 (43%) |

Most cut-offs are on the hard problems, so not every cut-off answer would pass with more room. Still, today's LCB ranking among the reasoning models is mostly a ranking of **token efficiency**, not problem-solving ability. Gemma and Strata look strong partly because they think concisely.

**2. One terminal task is broken, which caps terminal-x3 at 94.4%.**
- `backup-rotation` failed in 29 of 30 runs across all models. Its instructions say "Test it", but every test run leaves another today-dated archive. The checker then runs the script twice more and expects the 2024-01-05 archive to survive, which is impossible once three newer archives exist.
- So a model that follows the instructions fails. The only pass (one Laguna run) was a model that didn't test its script, or cleaned up afterwards.
- With 17 of 18 tasks passable, the ceiling is 94.4%, exactly where Strata and qwen3.8-27b landed.
- **The top of terminal-x3 is saturated.** Strata, qwen3.8 and ThinkingCap can't be separated by this suite as it stands.

### Other observations

- **Tool calling is clean everywhere.** There were zero malformed tool calls and zero tool calls written as plain text, across all 540 terminal episodes. llama-swap's chat templates and tool parsers work for every model tested, so `terminal-text` isn't urgent.
- **Gemma 4 is verbose in agentic loops.** It used 6,455 output tokens per episode (3.6× qwen3.8) and 12.7 turns, ran out of turns 4 times, and took 80 minutes for terminal-x3. It's the opposite in LCB, where it was among the most concise.
- **Strata's prompt processing is slow.** 158 tok/s at 512 tokens and 780 tok/s at 8k, with 10.5 s to the first token at 8k. That's 4–20× slower than the llama.cpp models, and it hurts agent loops, which re-read growing context on every turn.
- **Laguna's decode speed in terminal-x3 was 12 tok/s, against 34 tok/s in LCB.** No other model shows a gap that large. It might be a server or KV-cache problem rather than the model. The pending `speed-quick` run will help tell.
- **Energy:** qwen3.8-27b's LCB run used the most energy of any (2.9 MJ in 3 hours at 271 W). Gemma solved more problems with about a third of that (1.1 MJ).

---

## 2. Should we run more tuning experiments?

Yes. These are in priority order, by value per GPU-hour:

1. **Fix `backup-rotation` and re-run just that task.** The checker should reset `/work/backups` to its starting state before running the script, or ignore archives the model created. Re-running one task × 3 repeats × 10 models takes about an hour. Until then, read terminal-x3 as "out of 17".
2. **Raise LiveCodeBench's `max_tokens` to 65,536** for the models with 7 or more cut-offs: nemotron-bolt, nemotron-lightning, qwen3.6, qwen3.8, ThinkingCap, flint and laguna.
   - First make sure the context allows it. Each server has 4 slots, so unless the KV cache is shared, each slot gets `ctx-size / 4`. That's only 31,744 tokens for Laguna. For the rerun, use `--parallel 1`–`2` or a larger context.
   - This is the experiment most likely to reorder the leaderboard. Expect qwen3.8/ThinkingCap and the Nemotrons to move toward Gemma and Flint.
3. **Make terminal harder.** The top three models are at the ceiling.
   - Add longer-horizon tasks: multi-file refactors, debugging a failing test suite, tasks that need 20+ turns.
   - Or report `avg turns` and tokens per task alongside pass rate as the tie-breakers.
4. **Re-run Strata on a clean GPU.** It loaded while another model's VRAM was still in use, and it peaked at 31.6 of 31.9 GiB. Its quality numbers are probably fine, but its speed numbers may be pessimistic.
5. **Compare ThinkingCap and its base on the same quant.** We have ThinkingCap at Q4_K_M and the base at UD-Q4_K_XL, so part of the 30% speed-up on terminal-x3 could come from the quant rather than the fine-tune.
6. **Measure single-user server settings.** llama-swap runs every model with 4 slots. Generation drops from ~52 tok/s alone to ~15–20 tok/s per request with 4 in flight (qwen3.8). For one person driving one agent, `--parallel 1` gives each request the full context and maximum speed. Run `speed-concurrent` to put numbers on it.
7. **Sample more LCB problems for the top contenders.** With 30 problems, the standard error is about ±9 points, so Gemma (73.3) vs. Flint/ThinkingCap (63.3) isn't a significant difference yet. 60–90 problems would settle the top five.
8. **Benchmark `gemma-4-e4b`.** It's the `small` model in `claude-local`, so it handles background tasks every day, and it has never been measured. The quick profile is enough.

Not worth the time: more HumanEval+ (every model scores 95–100%), and more runs of qwen3-coder-30b or Laguna.

---

## 3. Which models to use, and for what

Recommendations for this machine (R9700 32 GB, 90 GB RAM, llama-swap), based on the current numbers and the caveats above:

| role | recommendation | why | runner-up |
|---|---|---|---|
| **Main coding agent** (Claude Code via `claude-local`, opencode, pi) | **qwen3.8-27b**, switching to **ThinkingCap** once its speed numbers are in | Top terminal-x3 scores (94.4 / 92.6), fewest turns (6.0 / 5.6), no bad tool calls. ThinkingCap finishes agentic tasks ~30% faster at the same quality. | flint |
| **Hard algorithmic problems, "think harder" escalation** | **strata** | Best LCB by a wide margin (83.3%), never ran out of tokens, solved 80% of hard problems. But it's slow to read prompts and needs ~60 GB RAM and the whole GPU, so use it for batch jobs or stubborn problems, not as the always-on agent. | gemma-4-26b |
| **One-shot code generation** (write this function or script, no tool loop) | **gemma-4-26b** | 73.3% LCB with only 2 cut-offs: it reaches answers quickly and concisely. Decent speed (76 tok/s at 8k). | flint |
| **Fast all-round coder** (good quality, high throughput) | **flint** | Good at everything: 88.9% terminal, 63.3% LCB, 2,650 tok/s prompt processing, 79 tok/s generation, never ran out of turns. The best choice when qwen3.8's ~52 tok/s feels slow. | qwen3.6-35b-a3b |
| **Quick edits, short agent tasks** | **qwen3.6-35b-a3b** | Fastest terminal-x3 run (11 minutes, 4× faster than Flint), 95 tok/s at 8k, 2.5 s to first token, and a small VRAM footprint (23.7 GiB). Its 79.6% terminal score is fine for simple tasks. | nemotron-lightning |
| **Long-context reading** (big logs, whole-repo questions) | **nemotron-lightning** | The only model fitted to a 786k context. Fastest generation (131 tok/s), with fast prompt processing (3,000 tok/s at 8k). Weaker on hard agentic tasks (70.4%), so use it for reading, not multi-step changes. | — |
| **Small, background model** (titles, summaries, classification) | **gemma-4-e4b** (current choice) | Not benchmarked yet; see experiment 8. | — |

**Retire or skip:**
- **qwen3-coder-30b**: superseded on every metric except raw prompt speed.
- **laguna-xs-2.1**: the weakest of the 2026 models, even when it finishes thinking. Revisit only if poolside ships an update.
- **nemotron-bolt**: decent agent (87%), but it's the slowest llama.cpp model (45.7 tok/s at 8k) and took twice as long as Flint on terminal-x3 (85 vs 44 minutes) for a lower score.

**Waiting on:**
- **Inkling Small (276B-A12B)** could challenge Strata for the escalation role, but it needs mainline llama.cpp support first.
- **gpt-oss-20b** is configured but hasn't been run.
