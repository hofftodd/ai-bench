# Analysis of the Mac Studio runs

The first sweep on the Mac Studio (Apple M5 Ultra, 256 GB unified memory), Nov 3–6, 2026: three of the R9700's models on llama.cpp (Metal), DeepSeek V4 Flash on [DwarfStar](https://github.com/antirez/ds4) (`ds4`), three large MoE models on [sushi](https://github.com/beamivalice/sushi) (MLX), then Qwen3.8-Flash-Next on llama.cpp and on [oMLX](https://github.com/jundot/omlx) (MLX), and Inkling-Small on oMLX. The numbers are in [RESULTS-mac.md](RESULTS-mac.md); [ANALYSIS-compare.md](ANALYSIS-compare.md) sets them against the R9700. Last updated 2026-11-06 22:00.

> **The benchmark queue is complete.** Section 1 covers LiveCodeBench at 64k and 128k, plus later runs: Qwen3.8-Flash-Next on llama.cpp and oMLX, Inkling-Small on oMLX, and the [oMLX verdict](#should-we-lean-on-omlx). Sections 2–3 are from the first (32k) sweep; section 4 has the picks. Next on this machine: flint and qwen3.8-27b on oMLX (queued), tuning, sushi 1.5.0, DeepSeek V4.1 and Inkling 2 Small ([TODO.md](TODO.md#mac-studio-future)).

**In short:**

- **DeepSeek V4 Flash at Q4 on DwarfStar (`ds4-q4`) is the best model on either machine: 93.3% on LiveCodeBench at 64k** (28 of 30), with nothing cut off, 14 of 15 hard problems, and the shortest answers of any DeepSeek build. All three DeepSeek builds score 83–93% at 64k.
- **The 32k budget was hiding most of the differences.** Every model except MiMo gained 3–7 problems at 64k. The 32k ranking was mostly a ranking of who finished thinking in time.
- **qwen3.8-27b is a slow thinker, not a weak one: 86.7% at 128k** (12 of 15 hard problems), up from 70.0% at 64k and 56.7% at 32k. A 17.5 GB dense model ties DeepSeek at 2 bits once it has room, but its answers average 39k tokens and the run took 5 hours.
- **flint is the best value:** 80.0% at 64k in 79 minutes, from a ~20 GB model. The DeepSeek builds take 174–230 minutes for 3–4 more problems.
- **GLM-5.3-Flash and MiMo-V2.6-Flash are verbose and weaker.** Even at 128k they score 63–70%, with 5–8 answers still cut off and 48–55k-token answers on average. Neither is worth running here for coding.
- **Qwen3.8-Flash-Next's sushi gap is the engine, not the model.** On llama.cpp it scored **76.7% at 64k**, against 63–70% on sushi and 83.3% on Strata (R9700). Its answers average 29k tokens on llama.cpp and 7k on sushi: sushi makes the model think about a quarter as long. llama.cpp needs the room, though: at 32k it scored 53.3% with 14 of 30 answers cut off.
- **oMLX looks like the engine to lean on for MoE models here.** It ran Qwen3.8-Flash-Next at llama.cpp's quality (73.3% at 64k against 76.7%, with equally long reasoning), finished the run in half the time, and batched best of the three engines: 211 tok/s in total with 8 requests in flight, against 135 on sushi and 99 on llama.cpp. flint and qwen3.8-27b on oMLX are queued to check that it holds beyond one model.
- **Inkling-Small (Thinking Machines, 276B / 12B active) runs well on oMLX: 70.0% at both 32k and 64k,** with concise 13–16k-token answers, nothing cut off at 64k, and 63 tok/s at 8k. A solid mid-pack model, below flint and the DeepSeek builds. It's the warm-up for Inkling 2 Small, whose weights aren't out yet.
- **Everything that runs on both machines scores the same here.** qwen3.8-27b and DeepSeek V4 Flash got exactly their R9700 LiveCodeBench scores (56.7% and 60.0%), with nearly the same number of cut-off answers. The harness and the Metal build are sound.
- **Qwen3.8-Flash-Next is the fastest model here,** on sushi or oMLX: 138 tok/s at 8k on sushi and 96–154 on oMLX with MTP, about 2 s to first token. sushi's runs are shortest (under 32 minutes for LiveCodeBench) because its answers are short (about 7k tokens), which is also why it scores lower.
- **No throttling.** macOS logged no thermal or performance warnings over about 70 hours of near-continuous load, and llama-bench speeds before and after long runs agree within 2%.

---

## What ran

| | |
|---|---|
| Machine | Mac Studio, M5 Ultra, 256 GB unified memory, macOS 27.2 |
| Engines | llama.cpp b12098 (Metal, started by aibench with llama-swap's flags: q8_0 KV cache, flash attention, 4 slots), DwarfStar (`ds4-server --metal --batched-session 4`), sushi 1.4.1 (MLX), oMLX 0.7.3 (MLX, up to 8 requests at once) |
| Concurrency | `speed-concurrent-eos`: a 1k-token prompt and 256 generated tokens per request, at 1, 2, 4 and 8 requests in flight (EOS allowed, as in `speed-quick-eos`) |
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
| Qwen3.8-Flash-Next | llama.cpp, UD-Q4_K_XL | 53.3 | 76.7 | 14 → 5 | 93.3 / 60.0 | 29.0k | 208 |
| Qwen3.8-Flash-Next | oMLX, oQ4e + MTP | 50.0 | 73.3 | 14 → 7 | 93.3 / 53.3 | 34.3k | **100** |
| Inkling-Small | oMLX, 4-bit | 70.0 | 70.0 | 4 → **0** | 86.7 / 53.3 | 13.4k | 56 |
| Qwen3.8-Flash-Next | sushi, 4bpw | 70.0 | 63.3, 63.3 | 1 → 0, 0 | 80.0 / 46.7 (mean of 2) | 7.3k | 31, 27 |
| GLM-5.3-Flash | sushi, 2.4bpw | 50.0 | 60.0 | 15 → 11 | 80.0 / 40.0 | 30.7k | 183 |
| MiMo-V2.6-Flash | sushi, 2.3bpw | 63.3 | 56.7 | 9 → 11 | 66.7 / 46.7 | 32.6k | 148 |

What it shows:

- **Medium problems are saturated; the hard half ranks the models.** Five models solve 14 of 15 medium problems. On the hard 15 the spread is 40–93%, and each problem is worth 6.7 points.
- **DeepSeek V4 Flash is in a class of its own on hard problems,** and the build matters: Q4 on DwarfStar 93.3%, 2-bit on DwarfStar 80.0%, 2-bit on llama.cpp 73.3%. That's the same order as at 32k (76.7 > 73.3 > 60.0). Any single gap is within noise, but the same order twice suggests both the larger quant and DwarfStar help a little.
- **ds4-q4 thinks least and solves most.** Its answers average 18k tokens against 22k for the 2-bit builds, so the higher-precision experts seem to reach answers more directly. That's also why it was the fastest DeepSeek run at 64k despite generating at the same speed as ds4-q2.
- **DwarfStar's 32k lead over llama.cpp was mostly the budget.** llama.cpp's DeepSeek had 10 answers cut off at 32k and none at 64k; with room to finish, it came within 1 problem of ds4-q2.
- **Qwen3.8-Flash-Next depends on its engine more than any other model here.** See [the section below](#qwen38-flash-next-on-four-engines).
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

### Qwen3.8-Flash-Next on four engines

The same model on four engines, with the chat template's default `reasoning_effort: xhigh` on all of them:

| engine, quant | machine | LCB 32k | LCB 64k | cut off 32k / 64k | avg answer | gen @8k | 64k min |
|---|---|---|---|---|---|---|---|
| Strata, IQ3_S | R9700 | **83.3** (twice) | — | 0 / — | not checked | 67.8 | — |
| llama.cpp, Unsloth UD-Q4_K_XL | Mac | 53.3 | **76.7** | 14 / 5 | 21.7k / 29.0k | 47.1 | 208 |
| oMLX, oQ4e (4.8 bits/weight) + MTP | Mac | 50.0 | 73.3 | 14 / 7 | 23.7k / 34.3k | 96–154 | **100** |
| sushi, 4bpw | Mac | 70.0 | 63.3, 63.3 | 1 / 0, 0 | 7.1k / 7.3k | 138 | 27–31 |

- **sushi cuts the model's reasoning short.** On llama.cpp the same model writes about 4× as many tokens per answer and solves 4 more problems at 64k, including 9 of 15 hard ones against sushi's 7. So sushi's low score isn't a weakness of the model; it's how sushi runs it. A lower effective reasoning effort, a different template, or sushi's quantization trimming the long reasoning are all possible; sushi's quant is the least likely, since its pack has more bits than Strata's.
- **oMLX behaves like llama.cpp, not like sushi.** One problem apart at both budgets, the same 14 answers cut off at 32k, and answers just as long. So the short reasoning is specific to sushi, not to MLX.
- **llama.cpp and oMLX need a 64k budget for this model.** At 32k, 14 of 30 answers ran out on both, and they scored lowest of the engines.
- **llama.cpp at 64k and Strata at 32k are 2 problems apart,** within noise. So on hard problems the Mac's llama.cpp build is as good as the R9700's Strata, but slower per answer.
- **Strata is still the puzzle.** It scored 83.3% at 32k with nothing cut off, so its answers must be well under 32k tokens, yet it solved more than llama.cpp did. Strata's sampling also differs: aibench sent no sampling parameters to it, so it used its own defaults, where llama.cpp and sushi got Qwen's thinking-mode settings (temperature 1.0, top_p 0.95, top_k 20). Strata's answer lengths and sampling are in the R9700's run.json.
- **Speed vs depth:** sushi answers 4–7× faster than llama.cpp, at 13 points less. oMLX keeps llama.cpp's depth at twice its speed, so it replaces llama.cpp for this model. flint at 64k (80.0%, 79 min, ~20 GB) is still the better all-round pick.

### Should we lean on oMLX?

**Probably yes, for MoE models.** One model so far; flint and qwen3.8-27b on oMLX are queued to test that it generalizes. Qwen3.8-Flash-Next on oMLX 0.7.3, as oMLX's own oQ4e quant (`Jundot/Qwen3.8-Flash-Next-oQ4e-mtp`, 108 GB, 4.8 bits/weight, with the MTP head on):

**One request at a time** (tok/s):

| engine | prompt @8k | gen @512 | gen @8k | first token @8k |
|---|---|---|---|---|
| llama.cpp (no drafter) | 1,400 | 49.7 | 47.1 | 5.9 s |
| sushi (MTP) | 3,508 | 134 | 138 | 2.4 s |
| oMLX (MTP), two runs | 3,492–4,007 | 164–250 | 96–154 | 2.0–2.4 s |

**Total generation with several requests in flight** (tok/s, `speed-concurrent-eos`):

| requests in flight | 1 | 2 | 4 | 8 |
|---|---|---|---|---|
| llama.cpp (4 slots) | 39 | 61 | 99 | 99 |
| sushi | 92 | 120 | 134 | 135 |
| oMLX (MTP) | 135 | 137 | **179** | **211** |

- **Same quality as llama.cpp** (above), and the 64k run took 100 minutes instead of 208. Per request it generated 59.5 tok/s during that run against llama.cpp's 24.3, with 3 requests in flight: the most realistic speed figure here, and 2.4×.
- **oMLX batches best.** It was still gaining at 8 requests, where llama.cpp (4 slots) and sushi leveled off. That's what several agents sharing the Mac need.
- **MTP speed is noisy.** Two runs with identical settings gave 96 and 154 tok/s at 8k. oMLX's MTP adapts its draft depth to the acceptance rate and also copies tokens from the prompt, so the speed depends on the text. Its gain also fades under load: from 2 requests up, per-request speed was the same with or without it. Treat single-request oMLX speed as a range until more runs narrow it.
- **sushi keeps prompt processing fast under load** (about 2,700 tok/s per request at 8 in flight, against about 450 on oMLX). First tokens still arrived in about 2 s on both.
- **Setup notes.** oMLX turns MTP on by default for any checkpoint with MTP weights, saving that in `~/.omlx/model_settings.json` on first load; the run meant to measure oMLX without MTP had it on, so it was discarded and re-queued. It also rejects prompts over 32,768 tokens unless the model's config states a context length (raised to 135,168 in `~/.omlx/settings.json`).
- **Caveats:** the quants differ (oMLX's oQ4e vs Unsloth's UD-Q4_K_XL), so this isn't a pure engine comparison; tool calling is untested (the terminal suite needs Docker); and oMLX 0.7 is young.

### Inkling-Small on oMLX

Thinking Machines' first open model (276B total / 12B active, Apache-2.0, July 2026), as mlx-community's 4-bit MLX build: experts at 4 bits, everything else at 8, 153 GB. Mainline llama.cpp doesn't support the architecture, and the open pull request that adds it has no Metal kernels, so it ran on oMLX 0.7.3.

| | Inkling-Small |
|---|---|
| HumanEval+ (quick) | 97.5 |
| LCB 32k | 70.0 (80.0 / 60.0), 4 cut off, 16.1k-token answers, 61 min |
| LCB 64k | 70.0 (86.7 / 53.3), **0** cut off, 13.4k-token answers, **56 min** |
| prompt processing @512 / @8k | 709 / 2,050 tok/s |
| generation @512 / @8k | 66.9 / 62.8 tok/s |
| time to first token @8k | 4.0 s |
| load | 19 s cold |

- **A mid-pack solver with efficient reasoning.** It thinks less than any strong model except Flash-Next on sushi, and 32k is already enough for it. Its 64k run was the fastest of any model scoring 70% or more.
- **Not a pick over flint:** flint scored 73–80% at 64k–128k from about a seventh of the memory, and generates faster at 8k (99 tok/s).
- **Sampling is a guess.** Thinking Machines publishes no recommended settings. It ran at temperature 1.0 with oMLX's default top_p 0.95, and the chat template's default `reasoning_effort` of 0.9 (of 0–0.99).
- **oMLX works.** It loaded the model in 19 s, handled 4 concurrent LiveCodeBench requests, and separates reasoning from the answer like the other servers. One setting had to change: oMLX rejects prompts over 32,768 tokens unless a model's config states its context length, and Inkling's doesn't. It's raised to 135,168 in `~/.omlx/settings.json`.
- **For Inkling 2 Small** (594B / 17B active), this is the path: oMLX, a 2–3-bit MLX build (about 175–210 GB), and `livecodebench-64k`.

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
2. **flint and qwen3.8-27b on oMLX** (queued): does oMLX's lead hold for a small-active MoE and a dense model? Plus Flash-Next on oMLX with MTP really off.
3. **Strata's answer lengths and sampling** from the R9700's run.json, to explain how Strata scores 83.3% at 32k with nothing cut off.
4. **`llama-bench -d 8192`** for qwen3.8-27b, to explain the drafter's long-context drop (a couple of minutes).
5. **Install Docker** (OrbStack or Docker Desktop) and run `terminal-x3`, the agentic suite. It's the R9700's main ranking signal, and it's missing here.
6. **ThinkingCap and Strata's model on llama.cpp.** ThinkingCap is the R9700's best model that fits in VRAM, so it's the obvious next comparison (on llama.cpp and oMLX).

[TODO.md](TODO.md#mac-studio-future) lists the later work: sushi 1.5.0, DeepSeek V4.1 Flash, oMLX and the tuning experiments.

## 4. Which models to use on this machine, and for what

| role | pick | why |
|---|---|---|
| Hardest problems | **DeepSeek V4 Flash on DwarfStar (ds4-q4)** | 93.3% at 64k, 14 of 15 hard; same speed as ds4-q2, so take Q4 when 153 GB is free. Give it a 64k output budget. |
| Hard problems, small footprint | **qwen3.8-27b** (llama.cpp) | 86.7% at 128k from 17.5 GB, but 39k-token answers; give it a 128k budget |
| Strong and fast | **flint** (llama.cpp) | 73–80% at 64k–128k in under 80 min; 99 tok/s at 8k, 1.9 s TTFT, 4 slots in ~20 GB |
| Fastest, interactive | **Qwen3.8-Flash-Next on oMLX** | 96–154 tok/s at 8k with MTP, 2.0 s TTFT, and llama.cpp's quality (73–77% at 64k), where sushi's build scores 63–70%. Batches best of any engine here. |
| Worth watching | Inkling-Small (oMLX) | 70% at 32k and 64k with short answers; below flint. Inkling 2 Small may change this. |
| Not recommended | GLM-5.3-Flash, MiMo-V2.6-Flash | 63–70% even at 128k, with 48–55k-token answers |

This table may change once the terminal suite can run here, and with more oMLX runs, DeepSeek V4.1 and Inkling 2 Small.
