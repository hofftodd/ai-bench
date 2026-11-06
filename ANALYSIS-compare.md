# R9700 vs Mac Studio

How the same models do on the two machines: the Radeon AI PRO R9700 box (32 GB VRAM, llama.cpp b11850 on Vulkan, plus Strata) and the Mac Studio (M5 Ultra, 256 GB unified memory, llama.cpp b12098 on Metal, plus DwarfStar and sushi). The tables are in [RESULTS-compare.md](RESULTS-compare.md). Each machine's own analysis is in [ANALYSIS.md](ANALYSIS.md) (R9700) and [ANALYSIS-mac.md](ANALYSIS-mac.md) (Mac). Last updated 2026-11-05 20:00.

> **Running now:** LiveCodeBench at 128k for GLM and MiMo on the Mac, then two 64k runs of Qwen3.8-Flash-Next on sushi. 128k results so far are in [ANALYSIS-mac.md](ANALYSIS-mac.md#128k-for-the-models-still-cut-off-at-64k); the R9700 never ran 128k.

**In short:**

- **The Mac now has the best score on either machine: DeepSeek V4 Flash at Q4 on DwarfStar, 93.3% on LiveCodeBench at 64k.** The R9700's best were Strata at 83.3% (32k) and ThinkingCap and DeepSeek at 80.0% (64k). The Q4 build is 153 GB, so it can't run on the R9700 box at all.
- **Same GGUF, same answers.** At 32k, qwen3.8-27b and DeepSeek V4 Flash got identical LiveCodeBench scores on both machines (56.7%, 60.0%), and flint was one problem apart. At 64k the Mac scored 1–4 problems higher on all three, which is within noise. Quality doesn't depend on the machine, so the rest is about speed and capacity.
- **For models that fit in the R9700's 32 GB, the Mac is 1.1–1.7× faster.** Raw generation is 1.3–1.6× faster, and LiveCodeBench finishes in half the time. Prompt processing on the dense 27B is a tie.
- **For models that don't fit, it isn't close.** DeepSeek V4 Flash generates 4× faster and processes prompts 20–28× faster on the Mac. Its LiveCodeBench run took 2 hours instead of 15. On the R9700, most of its experts sit in system RAM behind a PCIe 3.0 x4 link. On the Mac, all of them are in GPU memory.
- **The Mac runs a class of models the R9700 can't hold.** GLM-5.3-Flash (93 GB), MiMo-V2.6-Flash (101 GB), Qwen3.8-Flash-Next at 4 bits (159 GB) and DeepSeek at Q4 (153 GB) all run fully resident.
- **The best scores don't line up across engines yet.** The R9700's best LiveCodeBench is still Strata (Qwen3.8-Flash-Next, 83.3%). On the Mac it's DeepSeek on DwarfStar (76.7% at Q4). sushi's Qwen3.8-Flash-Next scored 70.0%, but generates 2× faster than Strata (138 vs 68 tok/s at 8k) and finished in 27 minutes against 115.

---

## 1. Same GGUF on both machines

### Quality: identical within noise

| model | LCB pass@1 R9700 / Mac | cut off | HumanEval+ |
|---|---|---|---|
| qwen3.8-27b | 56.7 / 56.7 | 12 / 12 | 97.5 / 95.0 |
| flint | 63.3 / 66.7 | 7 / 7 | 97.5 / 95.0 |
| deepseek-v4-flash | 60.0 / 60.0 | 9 / 10 | 97.5 / 97.5 |

Every difference is a single problem. Even the number of answers cut off at 32k is the same, which says the two harnesses, the two llama.cpp builds (b11850 vs b12098) and the two GPU backends produce equivalent output. Any model's R9700 quality score can be treated as valid for the Mac and vice versa, as long as the GGUF and sampling are the same.

### The same GGUF at 64k

| model | R9700 64k (cut off) | Mac 64k (cut off) | R9700 / Mac min |
|---|---|---|---|
| qwen3.8-27b | 66.7 (9) | 70.0 (8) | ~400 est. / 224 |
| flint | 66.7 (1) | 80.0 (2) | — / 79 |
| deepseek-v4-flash | 80.0 (3) | 83.3 (0) | — / 230 |

- **All three came out higher on the Mac,** by 1, 4 and 1 problems. Each gap is within noise: two 30-problem runs differ by about 12 points by chance, and flint's 13-point gap is right at that edge.
- **Three in the same direction is a weak hint, not a finding.** The likeliest explanation is chance, since the 32k runs matched exactly. The remaining differences are the llama.cpp build (b11850 vs b12098) and the GPU backend. A second Mac run of flint at 64k would settle it.
- **The cut-off counts match closely,** so both machines are giving the models the same room.
- **qwen3.8-27b reached 86.7% at 128k on the Mac,** where the R9700 stopped at 64k with 9 answers still cut off. The R9700 could run it at 128k too (the model fits in 32 GB), but at its speed that run would take roughly 9–10 hours.

### Speed: where the Mac's advantage comes from

| | R9700 | Mac | Mac ÷ R9700 |
|---|---|---|---|
| **qwen3.8-27b** (dense, 17.5 GB) | | | |
| llama-bench tg128 (raw generation) | 28.7 | 46.8 | **1.63×** |
| llama-bench pp512 (raw prompt processing) | 1098 | 1116 | 1.02× |
| server generation @8k (with MTP drafter) | 52.5 | 58.3 | 1.11× |
| server prompt processing @8k | 907 | 1029 | 1.13× |
| LiveCodeBench wall time | 181 min | 91 min | 1.99× |
| **flint** (MoE, ~2.5B active) | | | |
| llama-bench tg128 | 91.4 | 118 | 1.29× |
| llama-bench pp512 | 3388 | 4781 | 1.41× |
| server generation @8k | 79.3 | 99.1 | 1.25× |
| server prompt processing @8k | 3391 | 4335 | 1.28× |
| LiveCodeBench wall time | 78 min | 41 min | 1.91× |

The R9700's llama-bench figures are from [RESULTS.md](RESULTS.md) (its ROCm comparison table). They aren't in its `models.csv` yet, so the generated tables show them as —.

- **Generation is limited by memory bandwidth, and the Mac has more.** 17.5 GB × 46.8 tok/s means the Mac reads about 820 GB/s. The R9700 reads about 500 GB/s, from a 640 GB/s spec. That's the whole 1.6× on the dense model.
- **flint gains less,** because a model with 2.5B active parameters reads only a few GB per token and is held back by per-token overhead instead.
- **Prompt processing is a tie on the dense model** and 1.4× on flint. Prompt processing is compute-bound, and the two GPUs are close there.
- **The drafter narrows the gap.** On the R9700, qwen3.8-27b's MTP drafter lifts server speed at 8k to 1.83× its raw generation speed (52.5 vs 28.7). On the Mac it lifts it only to 1.25× (58.3 vs 46.8). Both ratios compare an 8k-context server run with an empty-context benchmark. So the Mac's 1.63× raw lead shrinks to 1.11× in real serving at 8k. [ANALYSIS-mac.md](ANALYSIS-mac.md#the-mtp-drafter-helps-less-at-long-context) has the likely causes and the test that would tell them apart.
- **LiveCodeBench finishes in half the time on both models,** which is more than the 8k speed ratio alone suggests. Most LiveCodeBench tokens are generated at 10–30k context, with 4 requests in flight. That suggests the Mac copes better with long contexts and concurrent requests than the R9700 does, but this sweep didn't measure either directly.

### DeepSeek V4 Flash: the capacity effect

| | R9700 | Mac | Mac ÷ R9700 |
|---|---|---|---|
| server prompt processing @512 | 30.0 | 852 | **28×** |
| server generation @512 | 8.0 | 36.0 | 4.5× |
| server generation @8k | 9.0 | 35.6 | 4.0× |
| time to first token @8k | 197 s | 10.0 s | 20× |
| LiveCodeBench wall time | 910 min | 121 min | 7.5× |

The same 96 GB GGUF runs very differently on the two machines:
- **On the R9700**, experts for 34 of 43 layers stay in system RAM (`--n-cpu-moe 34`) and are computed on the CPU. Prompt processing runs at CPU speed, and every token waits on DDR5 and a PCIe 3.0 x4 link (see [TODO.md](TODO.md#pcie-link)).
- **On the Mac**, the whole model sits in GPU memory, so it behaves like an ordinary GPU model: 36 tok/s generation. That's still well below what bandwidth alone would allow for ~13B active parameters at 2–3 bits (~4–5 GB read per token), so something other than memory, probably compute or per-token overhead, limits it here.

The R9700 analysis wrote DeepSeek off as "accurate but very slow here". On the Mac it's a practical model: an 8k prompt gets its first token in 10 seconds instead of 3 minutes.

## 2. Same model, different engine

These pair each machine's best engine for a model. Engine, quant and hardware all change at once, so they're not hardware comparisons.

| model | R9700 | Mac | LCB 32k R9700 / Mac | LCB 64k R9700 / Mac | LCB min (32k) |
|---|---|---|---|---|---|
| DeepSeek V4 Flash | llama.cpp, UD-Q2_K_XL | DwarfStar, IQ2_XXS (`ds4-q2`) | 60.0 / 73.3 | 80.0 / 86.7 | 910 / 174 |
| DeepSeek V4 Flash | llama.cpp, UD-Q2_K_XL | DwarfStar, Q4_K (`ds4-q4`) | 60.0 / 76.7 | 80.0 / **93.3** | 910 / 168 |
| Qwen3.8-Flash-Next | Strata, IQ3_S | sushi, 4bpw | **83.3** / 70.0 | — / *queued* | 115 / 27 |

- **DeepSeek:** at 32k, DwarfStar led llama.cpp by 13–17 points, but most of that was llama.cpp's answers being cut off. At 64k the 2-bit builds are 1–2 problems apart. The Q4 build is 3–4 problems above them, and Q4 > 2-bit DwarfStar > llama.cpp held at both budgets. So the larger quant probably helps; the engine, if at all, only a little.
- **Qwen3.8-Flash-Next:**
  - sushi's pack has more bits than Strata's IQ3_S, and both run the chat template's default `reasoning_effort: xhigh`, yet it scored 4 problems lower.
  - Neither run cut many answers off (0 and 1), so the 32k budget isn't the explanation.
  - Possible causes are sampling noise, the two engines' different quantization methods, or a difference in how each engine applies the template. One more LiveCodeBench run on sushi would show whether the gap is noise.
  - sushi's answers were also short (7.1k tokens on average), which is why its run took 27 minutes.
- **Speed, one request at a time:**

  | | R9700 | Mac | Mac ÷ R9700 |
  |---|---|---|---|
  | DeepSeek, generation @8k | 9.0 (llama.cpp) | 58.0 (ds4-q2) / 55.7 (ds4-q4) | 6.4× / 6.2× |
  | DeepSeek, time to first token @8k | 197 s | 7.8 s / 9.0 s | 25× / 22× |
  | Qwen3.8-Flash-Next, generation @8k | 67.8 (Strata) | 138 (sushi) | 2.0× |
  | Qwen3.8-Flash-Next, time to first token @8k | 10.5 s | 2.4 s | 4.4× |

  DwarfStar is 1.6× faster than llama.cpp per request on the same Mac, on top of the hardware gap. It batches worse, though: with 4 requests in flight its LiveCodeBench run was slower than llama.cpp's (see [ANALYSIS-mac.md](ANALYSIS-mac.md#dwarfstar-vs-llamacpp-on-the-same-mac)).

## 3. What can't be compared yet

| | why | to fix |
|---|---|---|
| Agentic terminal tasks | no Docker on the Mac | install Docker, run `terminal-x3` |
| Power and energy per task | aibench has no macOS reader | add a `powermetrics` sampler (needs sudo) |
| Most of the R9700's models | not copied to the Mac yet | copy ThinkingCap, gemma-4-26b, nemotron-* from the NAS and run `mac` |
| llama-bench in the generated tables | the R9700's `models.csv` predates the new columns | rebuild the dashboard on the R9700 box |
| A strict llama.cpp comparison | b11850 vs b12098 | build the same release on both |

## 4. What to run where

- **Models up to ~30 GB:** either machine gives the same answers. The Mac is 1.1–1.3× faster in serving at 8k and about 2× faster on long reasoning runs. The R9700 is good enough for these; the Mac is better.
- **Anything bigger** (DeepSeek, GLM-5.3-Flash, MiMo-V2.6-Flash, Qwen3.8-Flash-Next above 3 bits): **the Mac.** On the R9700 these models run with experts in system RAM, or not at all.
- **The R9700 no longer has the best solver.** ds4-q4's 93.3% at 64k beats Strata's 83.3%, though Strata ran at 32k and never at 64k (it had nothing cut off, so it likely wouldn't gain). Strata's remaining edge is over sushi's run of the same model (83.3% vs 70.0%); the two queued 64k runs on sushi will show whether that gap is real.
