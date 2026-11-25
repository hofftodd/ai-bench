# Analysis of the Mac Studio runs

The first sweep on the Mac Studio (Apple M5 Ultra, 256 GB unified memory), Nov 3–6, 2026: three of the R9700's models on llama.cpp (Metal), DeepSeek V4 Flash on [DwarfStar](https://github.com/antirez/ds4) (`ds4`), three large MoE models on [sushi](https://github.com/beamivalice/sushi) (MLX), then Qwen3.8-Flash-Next on llama.cpp and on [oMLX](https://github.com/jundot/omlx) (MLX), and Inkling-Small on oMLX. Nov 18–20 added Strata's settings on oMLX (a thinking budget and greedy decoding), 60-problem LiveCodeBench runs, Laguna S 2.1 and the [Splash](https://github.com/incoai/splash) engine; Nov 20 added DeepSeek V4.1 Flash on oMLX 0.8.0, Nov 21 a recheck of oMLX's native kernels, Nov 23–24 flint on Splash with several agents and Ripple's DFlash2 drafter, and Nov 24–25 Splash 1.7.2 with Inkling 2 Mini. The numbers are in [RESULTS-mac.md](RESULTS-mac.md); [ANALYSIS-compare.md](ANALYSIS-compare.md) sets them against the R9700. Last updated 2026-11-25.

> **[Nov 24–25](#nov-2425-splash-172-and-inkling-2-mini) is the newest:** Inkling 2 Mini on Splash 1.7.2 matches flint's LiveCodeBench score and joins ai-swap; flint stays on 1.7.0. **[Nov 23–24](#nov-2324-flint-moves-to-splash-ripples-drafter):** flint moves to Splash in ai-swap, flint on the 60-problem LiveCodeBench, and Ripple's DFlash2 drafter (1.4–1.9× on one request, no change batched). **[Nov 20](#nov-20-deepseek-v41-omlxs-kernels-inkling-2):** DeepSeek V4.1 Flash, oMLX's native kernels, and why Inkling 2 Small doesn't run here. **Section 0 (Nov 18–20)** changed the picks in section 4. Section 1 covers LiveCodeBench at 64k and 128k, plus later runs: Qwen3.8-Flash-Next on llama.cpp and oMLX, Inkling-Small on oMLX, [Ripple-65B Preview](#ripple-65b-preview), the [oMLX verdict](#should-we-lean-on-omlx) with its 6-bit check, and the [terminal suite](#tool-calling-the-terminal-suite). Sections 2–3 are from the first (32k) sweep; section 4 has the picks. The kernels stay (rechecked Nov 21). What's next is in [section 3](#3-what-to-run-next-on-this-machine).

**In short:**

- **Inkling 2 Mini on Splash 1.7.2 is a second fast executor** (Nov 25). At medium effort it scored 70.0% on the 60 at 64k (flint's score) and 98.1% on terminal-x3 in 5 minutes, at 135 tok/s at 8k and 267 in total with 8 in flight, from ~20 GB. That's half flint's speed and four times what the R9700 gets from llama.cpp. ai-swap serves it on demand as `inkling-2-mini`, beside flint.
- **ai-swap's flint now runs on Splash** (Nov 24). It stays ahead of oMLX with several agents at once: 453 tok/s in total with 8 in flight against 358, 263 tok/s alone against 161, and 0.11 s to the first token at 1k against 0.37. Same LiveCodeBench score with bf16 activations. oMLX stays configured as `flint-omlx`.
- **flint is the fast pick, not the strong one:** 70.0% on the 60 at 64k (42 of 60), against 88% for tuned Flash-Next and ThinkingCap on the same problems.
- **DeepSeek V4.1 Flash on oMLX is the Mac's highest LiveCodeBench score, but not a pick.** 90.0% on the 60 at 64k (54 of 60, 2 cut off) in 169 minutes, and 88.3% at 32k with the thinking budget in 109. That's one problem above tuned Flash-Next (88.3% at 32k) and two above ds4-q4 (86.7% at 64k): a tie inside the 95% intervals (about 80–95%). It decodes at 51 tok/s, holds ~207 GB with its Engram tables on the SSD, and leaves room for nothing else. See [Nov 20](#nov-20-deepseek-v41-omlxs-kernels-inkling-2).
- **oMLX's native kernels stay.** Three alternating rounds each way on Nov 21 found no consistent speed difference (flint 148.0 against 147.3 tok/s at 8k, and 348 against 351 in total with 8 in flight). The Nov 20 drop came from comparing against older runs on 0.7.3. DeepSeek V4.1's format needs the kernels.
- **Tuned Qwen3.8-Flash-Next on oMLX is now the Mac's best model for its speed.** With Strata's two settings, a 24,576-token thinking budget and greedy decoding, it scored **90.0% on LiveCodeBench at 32k** (up from 50.0%), none cut off, in 46 minutes. On a 60-problem sample at 64k it ties ds4-q4 (52 of 60 each) in 155 minutes against ds4-q4's 346, and at 32k it solves 53 of 60 in 87. terminal-x3: 98.1%. ai-swap now serves it this way. See [section 0](#0-tuned-flash-next-splash-and-laguna-nov-1820).
- **The 60-problem runs pulled ds4-q4 back to the pack:** 86.7% at 64k, against 93.3% on the 30. Its 30-problem lead was partly the sample.
- **Splash (DFlash2) matches oMLX's quality in less time.** Flash-Next on Splash scored 85.0% on the 60 in 53 minutes, with 100% on terminal-x3. Flint on Splash scored 66.7% at 32k with bf16 activations (the same as llama.cpp and oMLX) and decodes 2.4× faster than llama.cpp: 260 tok/s at 8k. Laguna S 2.1 and the 6-bit Flash-Next didn't beat what we have.
- **DeepSeek V4 Flash at Q4 on DwarfStar (`ds4-q4`) scored 93.3% on LiveCodeBench at 64k** (28 of 30), with nothing cut off, 14 of 15 hard problems, and the shortest answers of any DeepSeek build. All three DeepSeek builds score 83–93% at 64k.
- **The 32k budget was hiding most of the differences.** Every model except MiMo gained 3–7 problems at 64k. The 32k ranking was mostly a ranking of who finished thinking in time.
- **qwen3.8-27b is a slow thinker, not a weak one: 86.7% at 128k** (12 of 15 hard problems), up from 70.0% at 64k and 56.7% at 32k. A 17.5 GB dense model ties DeepSeek at 2 bits once it has room, but its answers average 39k tokens and the run took 5 hours.
- **flint is the best value:** 80.0% at 64k in 79 minutes, from a ~20 GB model. The DeepSeek builds take 174–230 minutes for 3–4 more problems.
- **GLM-5.3-Flash and MiMo-V2.6-Flash are verbose and weaker.** Even at 128k they score 63–70%, with 5–8 answers still cut off and 48–55k-token answers on average. Neither is worth running here for coding.
- **Qwen3.8-Flash-Next's sushi gap is the engine, not the model.** On llama.cpp it scored **76.7% at 64k**, against 63–70% on sushi and 83.3% on Strata (R9700). Its answers average 29k tokens on llama.cpp and 7k on sushi: sushi makes the model think about a quarter as long. llama.cpp needs the room, though: at 32k it scored 53.3% with 14 of 30 answers cut off.
- **oMLX is the engine to lean on here.** On flint, qwen3.8-27b and Qwen3.8-Flash-Next it matched llama.cpp's LiveCodeBench scores within noise (a possible ~3-point loss, likely the quant), finished 64k runs 1.3–2.1× sooner, and batched best: flint reached 351 tok/s in total with 8 requests in flight, against 220 on llama.cpp. A 6-bit rerun of qwen3.8-27b showed the earlier hint of a ~3-point loss was noise (37 of 60 solved, against 36 at 4 bits and 38 on llama.cpp). See [Should we lean on oMLX?](#should-we-lean-on-omlx).
- **Inkling-Small (Thinking Machines, 276B / 12B active) runs well on oMLX: 70.0% at both 32k and 64k,** with concise 13–16k-token answers, nothing cut off at 64k, and 63 tok/s at 8k. A solid mid-pack model, below flint and the DeepSeek builds. It was the warm-up for Inkling 2 Small: its weights are out (Nov 17), a partial llama.cpp run scored 70% at 32k with attention on the CPU, and the oMLX run waits for oMLX 0.8.0.
- **Ripple-65B Preview (Ricursive, 65B dense) has excellent tool use but is slow and mid-pack at coding:** 100% on `terminal-x3`, 76.7% on LiveCodeBench at 64k (the same as flint), at about 22 tok/s. flint on oMLX matches it at 7× the speed, so it isn't a pick here.
- **Tool calling works on both engines the picks rely on.** On `terminal-x3` (18 shell tasks × 3), ds4-q4 on DwarfStar passed all 54 (100%, 35 minutes) and flint on oMLX 52 of 54 (96.3%, 7 minutes), with no malformed tool calls. On the R9700, DeepSeek V4 Flash at 2 bits scored 96.3% and flint on llama.cpp 94.4%.
- **Everything that runs on both machines scores the same here.** qwen3.8-27b and DeepSeek V4 Flash got exactly their R9700 LiveCodeBench scores (56.7% and 60.0%), with nearly the same number of cut-off answers. The harness and the Metal build are sound.
- **Qwen3.8-Flash-Next is the fastest model here,** on sushi or oMLX: 138 tok/s at 8k on sushi and 96–154 on oMLX with MTP, about 2 s to first token. sushi's runs are shortest (under 32 minutes for LiveCodeBench) because its answers are short (about 7k tokens), which is also why it scores lower.
- **No throttling.** macOS logged no thermal or performance warnings over about 70 hours of near-continuous load, and llama-bench speeds before and after long runs agree within 2%.

---

## Nov 24–25: Splash 1.7.2 and Inkling 2 Mini

Queue `queues/mac-queue27.sh`. Splash 1.7.2 added Inkling 2 Mini (Unsloth's GGUFs, with Inco's DFlash2 drafter `incoai/Inkling-2-Mini-DFlash2`), but it also changes MoE outputs (each expert's `.scale` now applies), so it was unpacked side by side in `~/src/splash-1.7.2` (backend `splash-172`). Production flint stayed on Homebrew's 1.7.0. Inkling ran Unsloth's UD-Q4_K_XL, the quant the R9700 runs, at medium effort (`reasoning_effort: medium`), temperature 1.0, `--activations bf16`.

### flint on 1.7.2

| splash-flint-bf16 | 1.7.0 | 1.7.2 |
|---|---:|---:|
| generation @512 | 270 tok/s | **299** |
| generation @8k | **260** | 238 |
| prompt @8k | 12,798 tok/s | 12,573 |
| first token @8k | 0.66 s | 0.68 s |
| LCB, the 30 at 32k | 66.7% (7 cut off) | 63.3% (7 cut off) |

One problem lower and mixed on speed: within noise either way. There's no reason to move production flint. terminal-x3 and concurrency weren't rerun on 1.7.2.

### Inkling 2 Mini on Splash

| | **Splash 1.7.2, Mac** | flint, Splash 1.7.0 | Inkling, llama.cpp fork, R9700 | Inkling, Strata, R9700 |
|---|---:|---:|---:|---:|
| generation @512 | 158 tok/s | 270 | 31.6 | 76.2 |
| generation @8k | 135 | 260 | 25.3 | 64.6 |
| total, 8 in flight | 267 | 453 | | |
| first token @8k | 1.32 s | 0.66 s | 16.0 s | 10.2 s |
| terminal-x3 | **98.1%** in 5.1 min | 94.4% in 3.6 min (through ai-swap) | 96.3% in 38.5 min | 100% in 48.4 min |
| LCB-60 at 64k | **70.0%** (42/60) in 85 min | 70.0% (oMLX, 91 min) | 68.3% at effort high | |
| memory | ~20 GB | ~40 GB | | |

- **It's flint's equal on quality** on both suites (one terminal-x3 episode either way is noise), at about half the decode speed and half the memory.
- **It's the fastest Inkling we have:** twice Strata on the R9700 and four to five times llama.cpp. The 213 tok/s reported for an M5 Max (on a pre-release build) didn't reproduce here; 135–158 tok/s is in line with its 85–149 for M5 Pro chips.
- **In ai-swap from Nov 25:** `inkling-2-mini`, on demand next to flint (28 GB budget, `--default-reasoning-effort medium`, binary overridden to `~/src/splash-1.7.2/bin/splash`). A check through ai-swap loaded it and answered in 33 s from cold. With flint resident there's still room for Flash-Next (68 of 220 GB used with both small models in).

**Against qwen3.8-27b**, the other ~20 GB model here: Inkling is faster (135 tok/s at 8k against 112 on oMLX with MTP and 58 on llama.cpp, and 1.3 s to the first token against 4.4–8.0) and level at 64k, going by the R9700's runs on the same 30 problems (22 against 20). But qwen3.8-27b reaches 83–87% at 128k, and Inkling has never had 128k. Queue 28 (`queues/mac-queue28.sh`) runs Inkling on the 30 at 64k and at 128k on the Mac to settle it, plus `terminal-x3` through ai-swap and `terminal-hard`.

**Verdict: a second executor, not a replacement.** flint stays the default for speed; Inkling is a different model at the same level, useful as a second pair of hands or a second opinion on executor work. Hard problems still go to tuned Flash-Next (88% on the same 60).

---

## Nov 23–24: flint moves to Splash, Ripple's drafter

Queues `queues/mac-queue25.sh` and `queues/mac-queue26.sh`.

### flint with several agents

`speed-concurrent-eos`, same day, both with flint's GGUF or oQ4e quant:

| | Splash, bf16 activations, DFlash2 | oMLX oQ4e |
|---|---:|---:|
| prompt, 1k | **11,977 tok/s** | 2,811 |
| generation, 1k, one request | **263 tok/s** | 161 |
| first token, 1k | **0.11 s** | 0.37 s |
| total generation, 8 in flight | **453 tok/s** | 358 |

Splash's lead shrinks as requests are added (1.6× alone, 1.27× at 8), because speculative decoding helps most when the GPU is idle between tokens, but it never falls behind. With LiveCodeBench already level (66.7% at 32k on both, with bf16), it replaces oMLX as ai-swap's `flint` from Nov 24: the Splash entry with `--activations bf16 --language-only`, 40 GB. The oMLX entry stays as `flint-omlx`. A check through ai-swap gave 600 tokens in 1.6 s with reasoning returned as before. `terminal-x3` through ai-swap (`swap-flint`, queue 26): **94.4% in 3.6 minutes** with no bad tool calls, against 96.3% in 7.3 on oMLX. The only failures were all three `kill-rogue` episodes, the task flint already failed 2 of 3 times on oMLX, so that's one episode of difference: noise.

### flint on the 60 at 64k

oMLX: **70.0%** (42 of 60) in 91 minutes. On the same 60, tuned Flash-Next scored 88.3% (at 32k), ds4-q4 86.7%, and on the R9700 ThinkingCap 88.3%, Radiance's qwen3.8-27b 80.0% and Inkling 2 Mini 68.3%. Its 76.7–80% on the 30 was the easier half of the sample. flint is the executor for speed; hard problems go to Flash-Next.

### Ripple's DFlash2 drafter

ashbash's Q8_0 conversion (4.3 GB) made llama.cpp b12192 abort on load (`GGML_ASSERT(obj_new)` in `build_dflash2_selector`). b12192 predates llama.cpp's Ripple DFlash2 support (#31904, Nov 15) and the converter fix for the drafter's NoPE layer (#32363, Nov 16), and that GGUF is from Nov 6. Queue 26 builds llama.cpp master (2e779d5e7, `metal-1124`), converts Ricursive's own drafter with it, and runs `speed-quick-eos` and `speed-concurrent-eos` with and without the drafter. Both conversions carry the same RoPE pattern (no RoPE on draft layer 4), and master ignores ashbash's extra `context_window` key, so the crash was the engine, not the file. Same day, llama.cpp master, 4 slots:

| Ripple-65B | gen @512 | gen @1k | gen @8k | total, 8 in flight | first token @8k |
|---|---:|---:|---:|---:|---:|
| alone | 21.8 tok/s | 21.8 | 21.1 | 39.6 | 18.9 s |
| **+ DFlash2 drafter** (Q8_0, `--spec-type draft-dflash2`) | **41.3** | **32.5** | **28.8** | 39.5 | 18.4 s |

- **The drafter speeds up one request 1.4–1.9×,** most on short context, on the speed suite's random-word prompt (code drafts better, so real work may gain more).
- **It adds nothing with several requests:** 39.5 against 39.6 tok/s in total, because all 40 GB of weights are already read once per step for the whole batch.
- **Verdict unchanged:** at 29–41 tok/s Ripple is still 5–9× slower than flint on Splash for the same LiveCodeBench score. `ripple-65b-dflash2` is the setup to use if Ripple is ever wanted (for example, for a harder terminal suite).

### Hy4-Flash: not yet

Tencent's Hy4-Flash (220B, 12B active, built-in DFly2 drafter) runs on oMLX 0.8.1+ (#5463) as `Jundot/Hy4-flash-oQ4h-mtp`, 132 GB; we're on 0.8.0, and llama.cpp support is still a PR (#32517). Tencent positions it for search, documents and computer use, and recommends the larger Hy4 for long-horizon coding. At 132 GB it can't sit beside Flash-Next and flint. Worth one run after an oMLX upgrade, mainly for research roles (see section 3).

---

## Nov 20: DeepSeek V4.1, oMLX's kernels, Inkling 2

Queues 21–23 (`queues/mac-queue21.sh` … `mac-queue23.sh`), on oMLX 0.8.0.

### oMLX's native kernels

**Homebrew installs of oMLX ship none of its native Metal kernels** (oMLX's `docs/custom-kernels.md`: only `brew install omlx --with-custom-kernel`, the DMG app and `make install` build them). Every earlier oMLX number here ran on the fallback MLX path. DeepSeek V4.1's oQh format has no fallback, so its first run failed to load. We rebuilt with `--with-custom-kernel`, which needs full Xcode with the Metal Toolchain component, and reran the speed tests (`queues/mac-queue22.sh`, one run each):

| model | context | before (fallback) | with kernels |
|---|---|---|---|
| flint | 512 / 8k | 177 / 161 tok/s | 164 / 145 tok/s |
| tuned Flash-Next (greedy) | 512 / 8k | 166 / 127 | 141 / 122 |
| Flash-Next with MTP | 512 / 8k | 250 / 154 | 162 / 128 |
| flint, 8 in flight (total) | 1k | 351 | 347 |

Decode got 3–35% slower; prefill is about the same; batched throughput is unchanged. The flint and MTP "before" runs are from Nov 6 on 0.7.3, so part of the gap may be the version, but the tuned Flash-Next pair is the same day and version. The quality numbers are unaffected. The tables now show the kernel build's speeds where a model was rerun. Production ai-swap uses the same install, so whether to keep the kernels was left open.

**Rechecked Nov 21 (`queues/mac-queue24.sh`): the kernels make no consistent difference, so they stay.** Three rounds of `speed-quick-eos` each way, alternating on the same install. For "without", the five native extensions were moved aside, which gives the fallback path a default Homebrew install takes. Means of three, decode tok/s at 512 / 8k:

| model | with kernels | without |
|---|---|---|
| flint | 161.5 / 148.0 | 161.7 / 147.3 |
| tuned Flash-Next (greedy) | 189 / 120.6 | 146 / 128.2 |
| Flash-Next with MTP | 176 / 152.5 | 191 / 138.8 |
| flint, 8 in flight (total) | 348 | 351 |

Flint is identical. The two Flash-Next setups move in opposite directions at 8k (greedy 6% slower with kernels, MTP 10% faster), and their 512 figures swing by up to 95 tok/s between rounds of the same build, so neither is a real effect. Prompt speed is about equal (flint at 1k: 2,886 vs 2,766 tok/s). The Nov 20 drops came mostly from comparing against Nov 6 runs on oMLX 0.7.3 plus single-run noise. DeepSeek V4.1's oQh format needs the kernels, so the install keeps them.

### DeepSeek V4.1 Flash (oMLX, oQ2.5h)

The 335 GB oQ2.5h export with `deepseek_v41_engram_ssd_offload` on and MTP off; oMLX keeps ~207 GB resident. **The first runs were void:** oMLX's default (balanced) memory guard left about 0.1 GB for prefill beside the model and rejected 59 of 60 prompts (scored 1.7% and 10%). With `--memory-guard aggressive` (model `args` in `bench-mac.yaml`) nothing was rejected:

| run | score | cut off | time | notes |
|---|---|---|---|---|
| LiveCodeBench-60 at 64k | **90.0%** (54/60) | 2 | 169 min | median answer 7.3k tokens |
| LiveCodeBench-60 at 32k, 24,576-token thinking budget | 88.3% (53/60) | 1 | 109 min | median 8.8k tokens |
| speed (one request) | 51.9 tok/s at 512, 51.2 at 8k | | | 27 s to first token at 8k (618 tok/s prefill) |

With 3 requests at once each decodes at about 30 tok/s. Against the field on the same 60 problems: tuned Flash-Next 88.3% at 32k (87 min), ds4-q4 86.7% at 64k (346 min), Flash-Next on Splash 85.0% (53 min). The 95% intervals overlap almost entirely (90.0%: 80–95; 86.7%: 76–93), so the DeepSeek V4.1 lead is not established. It's the Mac's strongest model on paper, faster than ds4-q4 for the same job, but at 207 GB it can't sit beside ai-factory's other models. Not a pick; at most an occasional second opinion loaded on purpose, the role ds4-q4 has now (153 GB).

### Inkling 2 Small doesn't fit

Hygaard's oQe 3.07-bit build (213 GB on disk) is over oMLX's dynamic memory ceiling: at 224 GB oMLX admitted it and then died while loading; at 215.6 GB later it refused it. The publisher's "fits 256 GB" claim came from a direct Python load on a dedicated machine with a 220 GiB wiring policy and one 8k request. A 2.61-bit oQ2e (195 GB) exists, but a model that fills the Mac can't be a pick, and the llama.cpp Q2 run had already scored 70% at 32k. Skipped; the 3.07-bit build is backed up to the NAS and deleted here.

---

## 0. Tuned Flash-Next, Splash and Laguna (Nov 18–20)

Queues 13–18 (`queues/mac-queue13.sh` … `mac-queue18.sh`). The aim: get Strata's 83.3% at 32k (R9700) or better on the Mac's engines, then check the winner against ds4-q4 on a bigger sample, through ai-swap, and on another engine.

### Strata's settings on oMLX

The R9700's run.json showed what Strata does differently ([TODO.md](TODO.md#mac-studio-future)): it ends thinking at 24,576 tokens when `max_tokens` is 32k, decodes greedily when the request sends no sampling, and stops a reply that repeats one token 256 times. oMLX 0.7.3 takes a `thinking_budget` per request (it only forces `</think>`, with no wrap-up sentence) and `temperature: 0`; it has no loop guard. Same oQ4e-mtp checkpoint throughout.

| Qwen3.8-Flash-Next on oMLX | LCB 32k (30) | LCB 64k (30) | LCB-60 32k | LCB-60 64k | terminal-x3 |
|---|---|---|---|---|---|
| no budget, sampled (earlier) | 50.0 (14 cut off) | 73.3 (7) | — | — | — |
| budget, sampled | 80.0 (1), 53 min | 86.7 (0), 88 min | — | — | — |
| **budget + greedy** | **90.0** (0), **46 min** | **90.0** (0), 80 min | **88.3** (53/60), 87 min | 86.7 (52/60), 155 min | **98.1%**, 15 min |
| budget + greedy, 6-bit oQ6e | — | — | 86.7 (52/60), 96 min | — | — |
| budget + greedy through ai-swap | — | — | 86.7 (52/60), 80 min | — | 98.1%, 20 min |

- **The budget is most of the gain:** it lifts 32k from 50.0% to 80.0% by ending runaway thinking (14 cut-offs → 1). **Greedy adds 3 more problems** at 32k. Together they reach 90.0%, past Strata's 83.3%.
- **64k doesn't help once the budget is on:** 90.0% on the 30 again, and on the 60 one problem fewer (52 vs 53) in 1.8× the time. **Use the 32k budget (24,576 thinking tokens).**
- **No loops showed up** in the greedy runs (no answer ran to the cap), so a loop guard isn't needed yet.
- **6 bits buys nothing:** 52 of 60 against 53 for the 4-bit, about 10% slower. This matches the 27B's 6-bit check. Keep oQ4e.
- **ai-swap now serves it tuned.** oMLX's model settings for `qwen3.8-flash-next-oq4e` (the id ai-swap serves, MTP off) set `temperature: 0` with `force_sampling` (which overrides the sampling agents send) and `thinking_budget_tokens: 24576`. The check sent an agent's usual sampling on purpose: 52 of 60 and 98.1% on terminal-x3, the same as calling oMLX directly within noise. The previous settings are in `~/.omlx/model_settings.json.pre-tuning`.

### Against ds4-q4 on 60 problems

| | LCB 30, 64k | **LCB-60, 64k** | LCB-60 min | terminal-x3 | gen @8k | memory |
|---|---|---|---|---|---|---|
| ds4-q4 (DwarfStar) | 93.3 | **86.7** (52/60) | 346 | 100% | 56 tok/s | 153 GB |
| Flash-Next, budget + greedy (oMLX) | 90.0 | **86.7** (52/60) | **155** | 98.1% | 102 tok/s | 108 GB |
| same, 32k budget | 90.0 (32k) | 88.3 (53/60, 32k) | **87** | | | |

- **A tie at 52 of 60,** and Flash-Next gets there in 45% of the time at 64k, or a quarter at 32k. One problem is 1.7 points on 60 and the standard error is about ±4.5, so neither is ahead.
- **ds4-q4's 93.3% was partly the 30-problem sample.** On the 60 (which contain the 30) it's 86.7%. It still has no thinking budget, so it isn't tuned the way Flash-Next now is.
- **So Flash-Next takes the hard-problem role** for anything time-sensitive. ds4-q4 stays useful as a second, different model (a reviewer or escalation that fails on different problems).

### ThinkingCap-Qwen3.8-Flash-Next (llama.cpp)

BottleCap AI's fine-tune of Flash-Next that thinks less, as their Q4_K_M on llama.cpp b12098 (no MLX build exists).

| | LCB 32k | LCB 64k | terminal-x3 |
|---|---|---|---|
| ThinkingCap, no budget | 76.7 (7 cut off), 60 min | 83.3 (2), 118 min | 98.1% |
| ThinkingCap, budget (sampled) | 86.7 (0), 56 min | 86.7 (0), 105 min | — |
| Flash-Next on llama.cpp, no budget | 53.3 (14) | 76.7 (5) | — |

- **It thinks less, as claimed:** 76.7% at 32k without a budget, where the base scored 53.3% on the same engine.
- **The budget helps it too, but less**, and it ends up where the base does with the budget and sampling (86.7 vs 80.0–86.7). It never ran greedy. Without an MLX build it's slower than the base on oMLX, so it isn't a pick.

### Laguna S 2.1 (oMLX)

poolside's 118B-A8B agentic-coding MoE, as their NVFP4 MLX build (72 GB), thinking on, poolside's sampling.

| LCB 64k | terminal-quick | terminal-x3 | gen @512 / @8k | prompt @8k |
|---|---|---|---|---|
| 50.0 (0 cut off), 93 min | 100% | 96.3% (17 min) | 62 / 60 tok/s | 2,446 tok/s |

- **Solid tool use, weak coder.** 96.3% on terminal-x3 is flint's score; 50.0% at 64k is the lowest of any model that finished its answers. Not adopted, like Laguna XS on the R9700.

### Splash (DFlash2 speculative decoding)

[Splash](https://github.com/incoai/splash) 1.7.0 is a Metal engine built around Inco's DFlash2 drafts. It serves GGUFs only for these two models, so it ran Unsloth's UD-Q4_K_XL rather than the oQ4e builds: the comparison is engine and quant together. Text only, 128K context, INT8 KV cache (its default), batched requests.

| | LCB | terminal-x3 | gen @512 / @8k | prompt @512 / @8k | first token @8k |
|---|---|---|---|---|---|
| **Flash-Next on Splash**, budget + greedy | **85.0** (51/60), **53 min** | **100%**, 6 min | 147 / 133 | 3,281 / 4,880 | 1.7 s |
| Flash-Next on oMLX, budget + greedy (MTP) | 88.3 (53/60), 87 min | 98.1%, 15 min | 166 / 127 | 1,778 / 3,916 | 2.1 s |
| Flash-Next on oMLX, no MTP (as ai-swap serves it) | — | 98.1% via ai-swap | 111 / 102 | 1,879 / 4,164 | 2.0 s |
| **Flint on Splash** | **63.3** (30, 7 cut off), 21 min | 94.4%, 6 min | **280 / 252** | **9,224 / 13,165** | **0.6 s** |
| Flint on Splash, bf16 activations | **66.7** (30, 7 cut off), 20 min | — | 270 / 260 | 9,165 / 12,798 | 0.7 s |
| Flint on oMLX / llama.cpp | 66.7 / 66.7 at 32k (7 cut off each) | 96.3% / — | 177 / 161, 100 / 99 | 1,348 / 5,245, 4,079 / 4,335 | 1.6 / 1.9 s |

- **Flash-Next on Splash is competitive.** Two problems fewer on the 60 (within noise), a perfect terminal score, and the 60-problem run took 40% less time than on oMLX: it batches 4 concurrent requests well. One request at a time it decodes faster than oMLX without MTP (133 vs 102 tok/s at 8k), about the same as oMLX with MTP (127).
- **Flint on Splash is the fastest thing on this machine** (2.4× llama.cpp's decode, 2.5–3× oMLX's prompt processing, 0.6 s to first token at 8k), at the same quality: 63.3% with its default 8-bit activations and 66.7% with bf16, against 66.7% for llama.cpp and oMLX at 32k, with the same 7 answers cut off on every engine. The one-problem gap is noise, and bf16 costs no measurable speed, so use bf16 for evaluations anyway. It's the strongest case for adding Splash to ai-swap, for executors.
- **To use it in production** ai-swap would need a Splash engine. Splash's SSD cache is capped (32 GiB by default) and dropped at exit, unlike oMLX's, which filled 1 TB over these queues.

---

## What ran

| | |
|---|---|
| Machine | Mac Studio, M5 Ultra, 256 GB unified memory, macOS 27.2 |
| Engines | llama.cpp b12098 (Metal; b12192 for Ripple-65B, started by aibench with llama-swap's flags: q8_0 KV cache, flash attention, 4 slots), DwarfStar (`ds4-server --metal --batched-session 4`), sushi 1.4.1 (MLX), oMLX 0.7.3 (MLX, up to 8 requests at once), Splash 1.7.0 (Metal, DFlash2; Nov 19–20) |
| Concurrency | `speed-concurrent-eos`: a 1k-token prompt and 256 generated tokens per request, at 1, 2, 4 and 8 requests in flight (EOS allowed, as in `speed-quick-eos`) |
| Profile | `mac`: `speed-quick`, `humaneval-quick` (40 problems), `livecodebench` (15 medium + 15 hard, 32k tokens), `kernels` (llama-bench). The sushi and ds4 models run `mac-engine` (no llama-bench) and measure speed with `speed-quick-eos`. |
| Config | [`bench-mac.yaml`](bench-mac.yaml): same model keys, GGUFs and sampling as the R9700's `bench.yaml`, so results compare model for model |

What this machine **doesn't** measure, and why:

- **Terminal suites run in OrbStack** (Docker-compatible, linux/arm64 sandbox), not Docker Desktop.
- **No power, energy or memory figures.** aibench reads those from amdgpu sysfs or nvidia-smi only. On macOS they need `sudo powermetrics`.
- **Different speed suite for sushi and ds4.** Both servers reject `ignore_eos`: DwarfStar allows it only at temperature 0, sushi only on `/v1/completions`. `speed-quick-eos` is identical except that the model may stop early. The prompt asks for a long story, so 128 tokens are always reached.

## 1. LiveCodeBench at 64k

Same 30 problems (15 medium, 15 hard) as the 32k run, with `max_tokens` 65,536 and 3 requests in flight. Qwen3.8-Flash-Next ran twice at 64k, as extra samples: only 1 of its answers was cut off at 32k.

| model | engine, quant | 32k | **64k** | cut off 32k → 64k | medium / hard at 64k | avg answer | 64k min |
|---|---|---|---|---|---|---|---|
| ds4-q4 | DwarfStar, Q4_K experts | 76.7 | **93.3** | 7 → **0** | 93.3 / **93.3** | **18.0k** | 174 |
| ds4-q2 | DwarfStar, IQ2_XXS experts | 73.3 | 86.7 | 8 → 2 | 93.3 / 80.0 | 21.8k | 204 |
| deepseek-v4-flash | llama.cpp, UD-Q2_K_XL | 60.0 | 83.3 | 10 → **0** | 93.3 / 73.3 | 22.3k | 230 |
| flint | llama.cpp, UD-Q4_K_XL | 66.7 | 80.0 | 7 → 2 | 93.3 / 66.7 | 23.0k | 79 |
| flint | oMLX, oQ4e | 66.7 | 76.7 | 7 → 1 | 86.7 / 66.7 | 19.3k | **48** |
| qwen3.8-27b | llama.cpp, UD-Q4_K_XL | 56.7 | 70.0 | 12 → 8 | 93.3 / 46.7 | 33.1k | 224 |
| qwen3.8-27b | oMLX, oQ4e + MTP | 53.3 | 66.7 | 13 → 8 | 86.7 / 46.7 | 30.7k | 177 |
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
| qwen3.8-27b on oMLX | 53.3 | 66.7 | 83.3 | 3 | 86.7 / 80.0 | 39.6k | 288 |
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

**Yes.** oMLX 0.7.3 gave llama.cpp's quality on all three models tried, and was faster on every one: most for the MoE models, least for the dense 27B. Each ran as oMLX's own oQ4e quant (about 4.6–4.8 bits per weight) against Unsloth's UD-Q4_K_XL GGUF on llama.cpp, with the same sampling. qwen3.8-27b used MTP on both engines (embedded head on oMLX, drafter on llama.cpp); flint and Flash-Next ran without it on both, for the speed tables.

**LiveCodeBench** (oMLX / llama.cpp; minutes for the 64k run):

| model | 32k | 64k | 128k | cut off at 64k | 64k min |
|---|---|---|---|---|---|
| flint (MoE, ~2.5B active, 23 GB) | 66.7 / 66.7 | 76.7 / 80.0 | — | 1 / 2 | **48** / 79 |
| qwen3.8-27b (dense, 17.5 GB) | 53.3 / 56.7 | 66.7 / 70.0 | 83.3 / 86.7 | 8 / 8 | **177** / 224 |
| Qwen3.8-Flash-Next (MoE, 108 GB) | 50.0 / 53.3 | 73.3 / 76.7 | — | 7 / 5 | **100** / 208 |

**One request at a time** (tok/s, oMLX / llama.cpp):

| model | gen @512 | gen @8k | prompt @8k | first token @8k |
|---|---|---|---|---|
| flint | 177 / 100 | **161** / 99 | 5,245 / 4,335 | 1.6 / 1.9 s |
| qwen3.8-27b (MTP on both) | 102 / 94 | **112** / 58 | 1,868 / 1,029 | 4.4 / 8.0 s |
| Qwen3.8-Flash-Next | 111 / 50 | **102** / 47 | 4,164 / 1,400 | 2.0 / 5.9 s |

**Total generation with several requests in flight** (tok/s, `speed-concurrent-eos`, oMLX / llama.cpp):

| requests in flight | 1 | 2 | 4 | 8 |
|---|---|---|---|---|
| flint | 127 / 87 | 172 / 112 | 265 / 224 | **351** / 220 |
| qwen3.8-27b | 90 / 62 | 94 / 77 | 109 / 89 | 121 / 93 |
| Qwen3.8-Flash-Next | 97 / 39 | 143 / 61 | 186 / 99 | **226** / 99 |
| Qwen3.8-Flash-Next on sushi | 92 | 120 | 134 | 135 |

- **Quality is a tie within noise, with a possible small loss.** Cut-off counts and answer lengths match. oMLX scored one problem lower in 6 of 7 pairs and tied in the seventh (flint at 32k, with the same 20 problems solved). Problem by problem, llama.cpp solved 13 that oMLX missed and oMLX 7 that llama.cpp missed: a net 6 of 210, about 3 points, but a split that uneven happens by chance about 1 time in 4. If the loss were real, the likelier cause would be the quant, so qwen3.8-27b was rerun at 6 bits (`Jundot/Qwen3.8-27B-oQ6e-mtp`, below). **It wasn't the quant, and most likely there is no loss:** the 6-bit build scored 73.3% at 64k and 50.0% at 32k, 37 of 60 in all, against 36 for the 4-bit build and 38 on llama.cpp.
- **The speed gain depends on the model.** The 64k runs finished 1.6× (flint) and 2.1× (Flash-Next) sooner for the MoE models, 1.3× for the dense 27B. With one request at a time oMLX generates 1.6–2.2× faster; prompt processing is faster too, except for short prompts on flint (1,348 vs 4,079 tok/s at 512 tokens, though the first token still arrives in 0.4 s).
- **oMLX batches best,** and keeps gaining at 8 requests in flight, where llama.cpp's 4 slots and sushi level off. flint reaches 351 tok/s in total: the best executor throughput on this machine.
- **MTP is for single requests.** On Flash-Next, two MTP runs gave 96 and 154 tok/s at 8k (oMLX adapts the draft depth and copies tokens from the prompt, so speed depends on the text), against a steady 102 without it. With 2 or more requests in flight MTP gave no gain, and without it the total at 8 in flight was higher (226 vs 211). Turn it off for models serving several agents; keep it for the dense 27B, where it's why oMLX doubles llama.cpp at 8k.
- **sushi keeps prompt processing fastest under load** (about 2,700 tok/s per request at 8 in flight), but it cuts Flash-Next's reasoning short, so oMLX replaces it.
- **Setup notes.** oMLX turns MTP on by default for any checkpoint with MTP weights, saving that in `~/.omlx/model_settings.json` on first load. The first Flash-Next run meant to be without MTP had it on; it was discarded and re-run with `mtp_enabled: false` set explicitly. oMLX also rejects prompts over 32,768 tokens unless a model's config states a context length (raised to 135,168 in `~/.omlx/settings.json`). It picks each model's tool-call parser from its chat template (GLM-4.7 style for flint) and passes earlier reasoning back to templates that use it.
- **Tool calling works.** flint on oMLX scored 96.3% on `terminal-x3` with no malformed calls; see [the terminal suite](#tool-calling-the-terminal-suite).

**6-bit check (qwen3.8-27b, oMLX oQ6e + MTP against oQ4e + MTP and llama.cpp UD-Q4_K_XL + drafter):**

| | 32k | 64k | solved, both budgets | cut off 32k / 64k | gen @8k | first token @8k |
|---|---|---|---|---|---|---|
| oMLX oQ6e (6-bit) | 50.0 | **73.3** | 37 / 60 | 13 / 7 | 83 tok/s | 4.9 s |
| oMLX oQ4e (4-bit) | 53.3 | 66.7 | 36 / 60 | 13 / 8 | **112** tok/s | **4.4** s |
| llama.cpp UD-Q4_K_XL | **56.7** | 70.0 | **38** / 60 | 12 / 8 | 58 tok/s | 8.0 s |

Problem by problem, the 6-bit build solved 4 that the 4-bit missed and missed 3 that it solved. The ranking flips between 32k and 64k, which is what noise looks like on 30 problems. **Keep the 4-bit builds:** 6 bits buys nothing measurable and generates about 25% slower at 8k.

### Tool calling: the terminal suite

`terminal-x3` (18 agentic shell tasks, 3 runs each, in a Docker sandbox on OrbStack) on the two engines the role picks rely on, with the R9700's scores for the same models:

| model | engine | pass | bad tool calls | wall | R9700 |
|---|---|---|---|---|---|
| DeepSeek V4 Flash, Q4 (ds4-q4) | DwarfStar | **100%** (54/54) | 0% | 35 min | 96.3% (UD-Q2_K_XL, llama.cpp) |
| flint, oQ4e | oMLX | 96.3% (52/54) | 0% | **7.3 min** | 94.4% (UD-Q4_K_XL, llama.cpp) |

- **Both engines parse tool calls cleanly.** No malformed calls on either: DwarfStar's native tool calls and oMLX's GLM-4.7 parser for flint both work.
- **flint's only failures were `kill-rogue`** (2 of 3 runs, and its one miss on `terminal-quick` as well). ds4-q4 passed it every time, so the sandbox isn't the cause.
- **Both match or beat their R9700 scores.** DeepSeek's 100% is at 4 bits against 2 on the R9700. The suite is now saturated at the top on both machines (see [TODO.md](TODO.md)), so it confirms tool calling rather than ranking models.
- **flint is about 5× faster through a whole agent episode,** which matters more for executors than the score gap.

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

### Ripple-65B Preview

Ricursive's first open model (released 2026-11-04): 65B dense, Apache-2.0, trained from scratch and post-trained for agentic coding; Ricursive claims 80.5 on Terminal-Bench 2.1. It ran as AtomicChat's imatrix AD-Q4_K_M GGUF (40.4 GB) on llama.cpp b12192 (Ripple support landed in b12167), with the same flags as the other llama.cpp runs. Ricursive publishes no sampling defaults; it ran at temperature 1.0, top_p 0.95.

| | Ripple-65B | flint (oMLX) | ds4-q4 (DwarfStar) |
|---|---|---|---|
| LiveCodeBench 32k | 66.7 (8 cut off) | 66.7 (7) | **76.7** (7) |
| LiveCodeBench 64k | 76.7 (2 cut off) | 76.7 (1) | **93.3** (0) |
| 64k run | 368 min | **48** min | 174 min |
| terminal-quick / terminal-x3 | **100 / 100** | 83.3 / 96.3 | — / **100** |
| terminal-x3 wall | 31 min | **7.3** min | 35 min |
| gen @8k, one request | 21 tok/s | **161** tok/s | — |
| total gen, 3 requests in flight | ~23 tok/s | — | — |
| first token @8k | 19.2 s | **1.6** s | — |
| size | 40 GB | 23 GB | 153 GB |

- **Tool use lives up to the claim:** 54 of 54 on `terminal-x3`, no malformed calls, about 6 turns per episode. It ties ds4-q4 for the top score here, but the suite is saturated, so this says its tool calling is solid more than that it's the best agent.
- **Coding is mid-pack.** 76.7% at 64k (13 of 15 medium, 10 of 15 hard) ties flint and sits with Qwen3.8-Flash-Next, well below ds4-q4. Answers are moderate (median 11.7k tokens at 64k), and only 2 hit the 64k cap.
- **It's slow.** Every token reads all 40 GB of weights, so it generates about 22 tok/s, and parallel requests barely help (about 23 tok/s in total with 3 in flight, against flint's 351 with 8). Its runs took 4–7× as long as flint's for the same scores.
- **Verdict: not a pick here.** flint on oMLX gives the same LiveCodeBench score, nearly the same terminal score, 7× the speed and far better batching from about half the memory. Worth rechecking with a harder terminal suite (where its tool use might separate it) or once there's an MTP head or a usable MLX build. The unofficial MLX 4-bit build needs `--trust-remote-code` with its uploader's `ricursive.py`, which wasn't tried.

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

Updated Nov 22. Done since the first sweep: the 60-problem runs (ds4-q4 86.7% at 64k), `terminal-x3` for flint, ds4-q4 and Ripple, Strata's settings on oMLX ([section 0](#0-tuned-flash-next-splash-and-laguna-nov-1820)), ThinkingCap-Qwen3.8-Flash-Next on llama.cpp, DeepSeek V4.1, Inkling 2 Small (doesn't fit) and the kernels check. In order of value:

1. **Revisit ai-factory's roles.** Its spike notes still put the planner on ds4-q4. Section 4 now has tuned Flash-Next for hard problems and planning, with ds4-q4 as a second opinion.
2. **Arete-27B** (NousResearch's Qwen3.8-27B fine-tune, 16.8 GB, in `~/models-pending/`). It has the same base as ThinkingCap, so LCB-60 at 64k and `terminal-x3` show whether it's a second ThinkingCap. It fits the R9700 too.
3. ~~Splash with several agents~~ *Done Nov 23: Splash keeps its lead at 8 in flight, and ai-swap's flint moved to it ([Nov 23–24](#nov-2324-flint-moves-to-splash-ripples-drafter)).* Next: **Hy4-Flash** on oMLX 0.8.3 (upgrade, recheck Flash-Next's score, then speed, `terminal-x3` and LCB-60 at 64k), mainly as a research and document model.
4. **AesCode-32B** (in `~/models-pending/`). It generates HTML from a prompt and an image, so it's a speed and smoke test rather than a LiveCodeBench run.
5. **GLM-5.3-Flash at 4 bits** (~155 GB), to see whether the 2.4-bit sushi build explains its weak score. Not during an ai-factory run: it pushes other models out of ai-swap.
6. **Smaller checks:** `llama-bench -d 8192` for qwen3.8-27b (the drafter's long-context drop), sushi 1.5.0, and the monthly disk-wear check (`smartctl`; next one about Dec 6).

[TODO.md](TODO.md#mac-studio-future) has the details.

## 4. Which models to use on this machine, and for what

| role | pick | why |
|---|---|---|
| Hard problems | **Qwen3.8-Flash-Next on oMLX, tuned** (greedy + 24,576-token thinking budget, as ai-swap now serves it) | 90.0% on the 30 at 32k in 46 min, 53 of 60 at 32k in 87 min; ties ds4-q4 on the 60 at 64k in 45% of the time; 98.1% on terminal-x3. 108 GB. |
| Second opinion, escalation | **DeepSeek V4 Flash on DwarfStar (ds4-q4)** | 86.7% on the 60 at 64k (93.3% on the 30), 100% on terminal-x3, but 4× slower than tuned Flash-Next. A different model, so it fails on different problems. Give it a 64k output budget. |
| Hard problems, small footprint | **qwen3.8-27b** (oMLX or llama.cpp) | 83–87% at 128k from 17.5 GB, but 39k-token answers; give it a 128k budget. oMLX doubles generation at 8k. The 4-bit oQ4e is enough; 6 bits added nothing. |
| Strong and fast, executors | **flint on Splash** (ai-swap's `flint` since Nov 24) | 70.0% on the 60 at 64k (77–80% on the 30); 263 tok/s alone and 453 tok/s in total with 8 in flight, 0.11 s to first token. 94.4% on terminal-x3 through ai-swap in 3.6 min (oMLX: 96.3% in 7.3). Fallback: `flint-omlx` (161 / 358 tok/s). |
| Second executor | **Inkling 2 Mini on Splash 1.7.2** (ai-swap's `inkling-2-mini`, on demand, since Nov 25) | 70.0% on the 60 at 64k (flint's score), 98.1% terminal-x3 in 5 min; 135 tok/s at 8k and 267 in total with 8 in flight, from ~20 GB. A different model at flint's level. |
| Fastest, interactive | **Qwen3.8-Flash-Next on oMLX** | 102 tok/s at 8k (up to 154 with MTP for single requests), 2.0 s TTFT, and the hard-problem quality above once tuned. MTP off when several agents share it. |
| Worth watching | Splash for Flash-Next | Flash-Next at oMLX's quality with 40% shorter LiveCodeBench runs. flint already runs on Splash in ai-swap. |
| Worth watching | DeepSeek V4.1 Flash (oMLX) | 90.0% on the 60 at 64k, the Mac's top score but a tie within noise; 51 tok/s and ~207 GB resident, so nothing else fits beside it. Needs `--memory-guard aggressive`. |
| Worth watching | Inkling-Small (oMLX) | 70% at 32k and 64k with short answers; below flint. Inkling 2 Small doesn't fit in memory here. |
| Not recommended | Laguna S 2.1 (oMLX) | 50.0% at 64k, 96.3% terminal-x3, 62 tok/s |
| Worth watching | Ripple-65B Preview (llama.cpp) | 100% on terminal-x3 and 76.7% at 64k, but ~22 tok/s (29–41 with its DFlash2 drafter on llama.cpp master) and ~40 tok/s in total however many requests; flint does the same job 5–9× faster. |
| Not recommended | GLM-5.3-Flash, MiMo-V2.6-Flash | 63–70% even at 128k, with 48–55k-token answers |

DeepSeek V4.1 and Inkling 2 Small are now settled (Nov 20), and neither changes the picks.
