# Analysis of the Mac Studio runs

The first sweep on the Mac Studio (Apple M5 Ultra, 256 GB unified memory), Nov 3–6, 2026: three of the R9700's models on llama.cpp (Metal), DeepSeek V4 Flash on [DwarfStar](https://github.com/antirez/ds4) (`ds4`), and three large MoE models on [sushi](https://github.com/beamivalice/sushi) (MLX). The numbers are in [RESULTS-mac.md](RESULTS-mac.md); [ANALYSIS-compare.md](ANALYSIS-compare.md) sets them against the R9700. Last updated 2026-11-06 06:00.

> **The benchmark queue is complete.** Section 1 covers LiveCodeBench at 64k and 128k; sections 2–3 are from the first (32k) sweep; section 4 has the picks. Next on this machine: tuning, sushi 1.5.0, oMLX and DeepSeek V4.1 ([TODO.md](TODO.md#mac-studio-future)).

**In short:**

- **DeepSeek V4 Flash at Q4 on DwarfStar (`ds4-q4`) is the best model on either machine: 93.3% on LiveCodeBench at 64k** (28 of 30), with nothing cut off, 14 of 15 hard problems, and the shortest answers of any DeepSeek build. All three DeepSeek builds score 83–93% at 64k.
- **The 32k budget was hiding most of the differences.** Every model except MiMo gained 3–7 problems at 64k. The 32k ranking was mostly a ranking of who finished thinking in time.
- **qwen3.8-27b is a slow thinker, not a weak one: 86.7% at 128k** (12 of 15 hard problems), up from 70.0% at 64k and 56.7% at 32k. A 17.5 GB dense model ties DeepSeek at 2 bits once it has room, but its answers average 39k tokens and the run took 5 hours.
- **flint is the best value:** 80.0% at 64k in 79 minutes, from a ~20 GB model. The DeepSeek builds take 174–230 minutes for 3–4 more problems.
- **GLM-5.3-Flash and MiMo-V2.6-Flash are verbose and weaker.** Even at 128k they score 63–70%, with 5–8 answers still cut off and 48–55k-token answers on average. Neither is worth running here for coding.
- **Qwen3.8-Flash-Next on sushi scores below Strata's run of the same model.** Three runs on sushi gave 70.0%, 63.3% and 63.3%, against 83.3% twice on Strata (R9700). That gap is now too consistent to be noise.
- **Everything that runs on both machines scores the same here.** qwen3.8-27b and DeepSeek V4 Flash got exactly their R9700 LiveCodeBench scores (56.7% and 60.0%), with nearly the same number of cut-off answers. The harness and the Metal build are sound.
- **Qwen3.8-Flash-Next on sushi is the fastest model here:** 138 tok/s at 8k context and 2.4 s to first token. Its LiveCodeBench runs take under 32 minutes because its answers are short (about 7k tokens), and none was cut off at 64k.
- **No throttling.** macOS logged no thermal or performance warnings over about 70 hours of near-continuous load, and llama-bench speeds before and after long runs agree within 2%.

---

## What ran

| | |
|---|---|
| Machine | Mac Studio, M5 Ultra, 256 GB unified memory, macOS 27.2 |
| Engines | llama.cpp b12098 (Metal, started by aibench with llama-swap's flags: q8_0 KV cache, flash attention, 4 slots), DwarfStar (`ds4-server --metal --batched-session 4`), sushi 1.4.1 (MLX) |
| Profile | `mac`: `speed-quick`, `humaneval-quick` (40 problems), `livecodebench` (15 medium + 15 hard, 32k tokens), `kernels` (llama-bench). The sushi and ds4 models run `mac-engine` (no llama-bench) and measure speed with `speed-quick-eos`. |
| Config | [`bench-mac.yaml`](bench-mac.yaml): same model keys, GGUFs and sampling as the R9700's `bench.yaml`, so results compare model for model |

What this machine **doesn't** measure, and why:

- **No terminal suites.** They need Docker, which isn't installed here.
- **No power, energy or memory figures.** aibench reads those from amdgpu sysfs or nvidia-smi only. On macOS they need `sudo powermetrics`.
- **Different speed suite for sushi and ds4.** Both servers reject `ignore_eos`: DwarfStar allows it only at temperature 0, sushi only on `/v1/completions`. `speed-quick-eos` is identical except that the model may stop early. The prompt asks for a long story, so 128 tokens are always reached.

## 1. LiveCodeBench at 64k

Same 30 problems (15 medium, 15 hard) as the 32k run, with `max_tokens` 65,536 and 3 requests in flight. Qwen3.8-Flash-Next ran twice at 64k, as extra samples: only 1 of its answers was cut off at 32k.

| model | engine, quant | 32k | **64k** | cut off 32k → 64k | medium / hard at 64k | avg answer | 64k min |
|---|---|---|---|---|---|---|---|
| ds4-q4 | DwarfStar, Q4_K experts | 76.7 | **93.3** | 7 → **0** | 93.3 / **93.3** | **18.0k** | 174 |
| ds4-q2 | DwarfStar, IQ2_XXS experts | 73.3 | 86.7 | 8 → 2 | 93.3 / 80.0 | 21.8k | 204 |
| deepseek-v4-flash | llama.cpp, UD-Q2_K_XL | 60.0 | 83.3 | 10 → **0** | 93.3 / 73.3 | 22.3k | 230 |
| flint | llama.cpp, UD-Q4_K_XL | 66.7 | 80.0 | 7 → 2 | 93.3 / 66.7 | 23.0k | **79** |
| qwen3.8-27b | llama.cpp, UD-Q4_K_XL | 56.7 | 70.0 | 12 → 8 | 93.3 / 46.7 | 33.1k | 224 |
| Qwen3.8-Flash-Next | sushi, 4bpw | 70.0 | 63.3, 63.3 | 1 → 0, 0 | 80.0 / 46.7 (mean of 2) | 7.3k | 31, 27 |
| GLM-5.3-Flash | sushi, 2.4bpw | 50.0 | 60.0 | 15 → 11 | 80.0 / 40.0 | 30.7k | 183 |
| MiMo-V2.6-Flash | sushi, 2.3bpw | 63.3 | 56.7 | 9 → 11 | 66.7 / 46.7 | 32.6k | 148 |

What it shows:

- **Medium problems are saturated; the hard half ranks the models.** Five models solve 14 of 15 medium problems. On the hard 15 the spread is 40–93%, and each problem is worth 6.7 points.
- **DeepSeek V4 Flash is in a class of its own on hard problems,** and the build matters: Q4 on DwarfStar 93.3%, 2-bit on DwarfStar 80.0%, 2-bit on llama.cpp 73.3%. That's the same order as at 32k (76.7 > 73.3 > 60.0). Any single gap is within noise, but the same order twice suggests both the larger quant and DwarfStar help a little.
- **ds4-q4 thinks least and solves most.** Its answers average 18k tokens against 22k for the 2-bit builds, so the higher-precision experts seem to reach answers more directly. That's also why it was the fastest DeepSeek run at 64k despite generating at the same speed as ds4-q2.
- **DwarfStar's 32k lead over llama.cpp was mostly the budget.** llama.cpp's DeepSeek had 10 answers cut off at 32k and none at 64k; with room to finish, it came within 1 problem of ds4-q2.
- **Qwen3.8-Flash-Next on sushi is consistently below Strata.** Three runs (70.0, 63.3, 63.3; mean 65.6%) against Strata's 83.3% twice on the R9700, with almost nothing cut off on either engine. Five runs in two tight clusters 18 points apart is a real gap, not noise. sushi's pack has more bits (4bpw vs IQ3_S), so the suspects are sushi's quantization method or how it applies the chat template and reasoning effort. Its very short answers (7k tokens against 18–39k for the other strong models) fit the second: the model may be thinking less than it does on Strata. Checking Strata's answer lengths in the R9700's run.json, and running the same model on oMLX, would tell them apart.
- **flint solves 24 problems in 79 minutes,** about 18 an hour, against 9.7 an hour for ds4-q4 and (at 32k) 46 an hour for Qwen3.8-Flash-Next on sushi.
- **qwen3.8-27b, GLM and MiMo still need more room:** 8–11 cut-offs and 31–33k-token average answers. MiMo's drop (63.3 → 56.7) is 2 problems, within noise; its medium score (66.7%) is the weakest here.
- **Noise is real at this sample size.** flint scored 80.0% here and 66.7% on the R9700 at 64k with the same GGUF (see [ANALYSIS-compare.md](ANALYSIS-compare.md#the-same-gguf-at-64k)). A 4-problem swing between two identical setups is the scale of difference these runs can't resolve.

### 128k, for the models still cut off at 64k

| model | 32k | 64k | **128k** | cut off at 128k | medium / hard at 128k | avg answer | 128k min |
|---|---|---|---|---|---|---|---|
| qwen3.8-27b | 56.7 | 70.0 | **86.7** | 2 | 93.3 / 80.0 | 39.0k | 307 |
| ds4-q2 | 73.3 | 86.7 | 83.3 | 1 | 93.3 / 73.3 | 25.0k | 235 |
| flint | 66.7 | 80.0 | 73.3 | 0 | 86.7 / 60.0 | 21.3k | 78 |
| MiMo-V2.6-Flash | 63.3 | 56.7 | 70.0 | 5 | 86.7 / 53.3 | 48.4k | 228 |
| GLM-5.3-Flash | 50.0 | 60.0 | 63.3 | 8 | 93.3 / 33.3 | **55.3k** | 319 |

The llama.cpp DeepSeek build and ds4-q4 had nothing cut off at 64k, so they skip 128k.

- **qwen3.8-27b gained 5 more problems,** all on hard ones. Its ceiling is far higher than its 32k score suggested; it just needs room. For an agent this means a 128k output budget on hard tasks, and patience: it generates about 24 tok/s per request that deep into the context.
- **GLM and MiMo are verbose, not hidden strong solvers.** Their answers average 48–55k tokens (GLM's are the longest of any model here), they still had 5–8 answers cut off at 128k, and on hard problems they solve 33–53%, where qwen3.8-27b solves 80% and ds4-q4 93% with far shorter answers.
- **flint and ds4-q2 each lost 2 problems.** Both had only 2 answers cut off at 64k, so the bigger budget couldn't add much, and the drop is the run-to-run noise of a 30-problem sample: about ±2 problems. Read flint as 73–80% and ds4-q2 as 83–87%.

## 2. Did we get the results we expected? (32k sweep)

### Yes, for everything we could check

The three llama.cpp models ran the same GGUF, sampling and server flags as on the R9700:

| model | LCB pass@1 here / R9700 | cut off here / R9700 | HumanEval+ here / R9700 |
|---|---|---|---|
| qwen3.8-27b | 56.7 / 56.7 | 12 / 12 | 95.0 / 97.5 |
| flint | 66.7 / 63.3 | 7 / 7 | 95.0 / 97.5 |
| deepseek-v4-flash | 60.0 / 60.0 | 10 / 9 | 97.5 / 97.5 |

Every difference is one problem, which is sampling noise at temperature 0.6–1.0. HumanEval-quick is saturated (92.5–100% for every model) and only works as a check that a model and server are wired up correctly.

### DwarfStar vs llama.cpp on the same Mac

DeepSeek V4 Flash ran three ways here. All three are 2-bit or 4-bit quants of the same model:

| | engine, quant | LCB pass@1 | cut off | LCB min | tokens generated |
|---|---|---|---|---|---|
| deepseek-v4-flash | llama.cpp, Unsloth UD-Q2_K_XL (96 GB) | 60.0 | 10 | 121 | 567k |
| ds4-q2 | DwarfStar, antirez IQ2_XXS experts (87 GB) | **73.3** | 8 | 174 | 567k |
| ds4-q4 | DwarfStar, antirez Q4_K experts (153 GB) | **76.7** | 7 | 168 | |

- **Quality:** ds4-q4 solved 23 problems and ds4-q2 22, to llama.cpp's 18. antirez's quant keeps attention, the shared experts and the output layer at Q8 (its filename says so), so the quant is a plausible cause, as is the engine. But two 30-problem runs differ by about 12 points (one standard error) by chance alone. ds4-q4 repeating the gain with different expert weights makes chance less likely, though both runs share the engine and the same 30 problems.
- **Throughput: DwarfStar is faster per request but batches worse.**
  - One request at a time, DwarfStar generates 62.5 tok/s (58.0 at 8k) against llama.cpp's 36.0 (35.6). It's 1.6–1.7× faster per stream, and 8k prompts get their first token in 7.8 s instead of 10.0.
  - Yet in LiveCodeBench both engines generated almost exactly the same number of tokens (567,324 vs 567,334) and DwarfStar took 44% longer. With 4 requests in flight, that's about 54 tok/s in total on DwarfStar against 78 on llama.cpp.
  - So llama.cpp gains about 2.2× from 4 concurrent requests and DwarfStar less than 1×. For one user at a time DwarfStar is the faster engine; for parallel agents or batch jobs llama.cpp is. `--batched-session` is on the tuning list.
- **Q4 costs nothing in speed.** ds4-q4 reads about 1.75× the expert bytes of ds4-q2, yet generates at the same 62.7 tok/s. DwarfStar isn't memory-bandwidth-bound at this size, so the bigger quant is free apart from memory (153 GB vs 87 GB) and slower prompt processing (605 vs 796 tok/s at 512 tokens).

### Three large MoE models on sushi

| | quant (size) | HumanEval+ | LCB pass@1 | cut off | LCB min | avg answer | gen @512 / @8k | pp @8k | TTFT @8k |
|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-Flash-Next | 4bpw (159 GB) | 95.0 | 70.0 | 1 | 27.3 | 7.1k tokens | 134 / 138 | 3508 | 2.4 s |
| MiMo-V2.6-Flash | 2.3bpw (101 GB) | 90.0 | 63.3 | 9 | 75.8 | 19.1k | 62 / 99 | 2827 | 3.0 s |
| GLM-5.3-Flash | 2.4bpw (93 GB) | 97.5 | 50.0 | 15 | 110 | 20.4k | 67 / 65 | 1629 | 5.1 s |

Speeds are tok/s for one request (`speed-quick-eos`).

- **Qwen3.8-Flash-Next** is in a class of its own: the fastest generator here at 159 GB, and the most efficient solver. It solves 70% while writing about a third as many tokens as the others, and only one answer ran out of room. Its chat template defaults to `reasoning_effort: xhigh`, the same setting the R9700's runs used, so this isn't a lower effort setting.
- **GLM-5.3-Flash's 50%** is mostly the cap: half its answers were cut off. It needs a 64k run before its score means anything.
- **MiMo-V2.6-Flash** had the lowest HumanEval+ (90%). One of those was a 60 s timeout, but two were plain wrong answers.
- **MiMo's generation speed is 60% *higher* at 8k than at 512 tokens,** which shouldn't happen. It's a single sample of each; the likeliest cause is MTP speculative decoding, whose acceptance rate depends on the text. Treat MiMo's speed as 60–100 tok/s until repeats narrow it.
- **sushi reports one slot** (`slots=1`) to aibench, but that's its `--max-concurrent` queue setting. Its help says requests batch at any value, so the 4 parallel LiveCodeBench requests did run together.

### The MTP drafter helps less at long context

qwen3.8-27b runs with an MTP drafter. Its server speed is 94 tok/s after a 512-token prompt but 58 after 8k: a 38% drop, against 24% on the R9700. Raw llama-bench generation without the drafter is 47 tok/s. So the drafter doubles speed at short context, but adds only 25% at 8k. Two likely causes:

- Verifying drafted tokens costs relatively more compute on this GPU.
- Metal's attention over a q8_0 KV cache slows down at depth.

`llama-bench -d 8192` would tell them apart: it measures generation after 8k tokens, without the drafter. Repeats also varied by 10 tok/s (68 vs 58), so part of the gap is the drafter's acceptance rate.

### No throttling

- `pmset -g therm` shows no thermal or performance warning since boot, through about 13 hours of near-constant GPU load.
- llama-bench measured qwen3.8-27b at 47.0 tok/s cold, then 46.8 after 91 minutes of LiveCodeBench. flint went from 120.6 to 118.1.
- DeepSeek's speed per request fell only as its answers got longer, which is the normal cost of a growing context, and then held steady.

## 3. What to run next on this machine

In order of value:

1. **A second 64k pass for ds4-q4 and flint,** the two results the recommendations below lean on most.
2. **Qwen3.8-Flash-Next on oMLX,** and Strata's answer lengths from the R9700, to find out why sushi scores 18 points below Strata.
3. **`llama-bench -d 8192`** for qwen3.8-27b, to explain the drafter's long-context drop (a couple of minutes).
4. **Install Docker** (OrbStack or Docker Desktop) and run `terminal-x3`, the agentic suite. It's the R9700's main ranking signal, and it's missing here.
5. **ThinkingCap and Strata's model on llama.cpp.** ThinkingCap is the R9700's best model that fits in VRAM, so it's the obvious next llama.cpp comparison.

[TODO.md](TODO.md#mac-studio-future) lists the later work: sushi 1.5.0, DeepSeek V4.1 Flash, oMLX and the tuning experiments.

## 4. Which models to use on this machine, and for what

| role | pick | why |
|---|---|---|
| Hardest problems | **DeepSeek V4 Flash on DwarfStar (ds4-q4)** | 93.3% at 64k, 14 of 15 hard; same speed as ds4-q2, so take Q4 when 153 GB is free. Give it a 64k output budget. |
| Hard problems, small footprint | **qwen3.8-27b** (llama.cpp) | 86.7% at 128k from 17.5 GB, but 39k-token answers; give it a 128k budget |
| Strong and fast | **flint** (llama.cpp) | 73–80% at 64k–128k in under 80 min; 99 tok/s at 8k, 1.9 s TTFT, 4 slots in ~20 GB |
| Fastest, interactive | **Qwen3.8-Flash-Next on sushi** | 138 tok/s at 8k, 2.4 s TTFT, but 63–70% on LiveCodeBench; good for quick turns, not hard problems |
| Not recommended | GLM-5.3-Flash, MiMo-V2.6-Flash | 63–70% even at 128k, with 48–55k-token answers |

This table may change once the terminal suite can run here, and with the oMLX and DeepSeek V4.1 runs.
