# aibench

aibench measures how well local LLMs work on this machine, a Radeon AI PRO R9700 (32 GB, llama.cpp on Vulkan). It answers two questions about each model:

- **How fast is it?** Prompt processing and generation speed in tokens per second, time to first token, and throughput with several requests at once.
- **How good is it at coding?** HumanEval+, MBPP+, LiveCodeBench, and an agentic shell benchmark where the model uses `bash` in a sandbox to finish real tasks.

Every result also records peak VRAM, average GPU power and energy used, plus the exact server build and command line, so runs can be compared later.

Results go to `results/` as JSON. Read them in the terminal (`aibench report`) or on the [dashboard](#the-dashboard). **The latest results are in [RESULTS.md](RESULTS.md).**

> **See also:** [RESULTS.md](RESULTS.md) has the latest numbers, [ANALYSIS.md](ANALYSIS.md) interprets them and recommends models for each role, [ARCHITECTURE.md](ARCHITECTURE.md) explains how the code fits together, and [TODO.md](TODO.md) lists open work and known caveats.

---

## Quick start

You need [uv](https://docs.astral.sh/uv/) and Python 3.11+. The agentic `terminal` suites also need Docker.

```bash
uv sync                                   # install
uv run aibench check                      # are the backends up, and can they see the models?
uv run aibench run -m flint -s quick      # benchmark one model with the quick profile (~15–30 min)
uv run aibench report                     # compare everything in results/
uv run aibench dashboard --serve          # rebuild the dashboard and open http://localhost:8765/
```

## Everyday tasks

### Benchmark a model

```bash
uv run aibench run -m <model> -s <suite or profile> [--tag <label>]
```

- `-m` takes a model key from `bench.yaml`. Repeat it to run several models one after another. Any other name is tried as a raw model id on `default_backend`.
- `-s` takes a suite key, a suite type, or a profile name (see below). It can also be repeated.
- `-n 20` limits every coding suite to its first 20 problems, for a quick sanity check.
- `--tag` stores a free-form label on the run. This project uses `baseline` for quick-profile runs and `overnight` for the long ones.

Models run **one at a time**, each with the whole GPU. `run.json` is saved after every suite, so a crash or Ctrl-C keeps whatever already finished.

The profiles defined in `bench.yaml`:

| profile | suites | time per model |
|---|---|---|
| `quick` | `speed-quick`, `humaneval-quick` (40 problems), `terminal-quick` (6 tasks) | 15–30 min |
| `overnight` | `terminal-x3` (18 tasks × 3), `livecodebench` (30 medium/hard problems) | 45 min–3.5 h |
| `full` | `speed`, `speed-concurrent`, `humaneval`, `mbpp`, `terminal` | hours |
| `agentic` | `terminal`, `terminal-text` | ~1 h |

### Add a new model

1. Put the GGUF under `~/models/<name>/`.
2. Run `llama-config`, which regenerates the llama-swap config with a fitted context size. **It restarts llama-swap, so never run it while a benchmark is running.**
3. Add an entry under `models:` in `bench.yaml`. Use the vendor's recommended sampling settings, and `max_tokens: 32768` for reasoning models so they have room to think:

   ```yaml
   my-model:
     backend: swap
     id: my-model                 # the name llama-swap knows it by
     gguf: ~/models/my-model/My-Model-Q4_K_M.gguf
     max_tokens: 32768
     params: {temperature: 0.6, top_p: 0.95, top_k: 20}
   ```

4. Run `uv run aibench check`, then the `quick` profile, then `overnight`.

### Compare results

```bash
uv run aibench report                          # one column per model, headline metrics
uv run aibench report --wide                   # one row per model
uv run aibench report --detail -s livecodebench   # every metric for one suite
uv run aibench report -f md -o results.md      # also csv / json
```

The report keeps the **latest** result for each (hardware, backend, model, suite), so re-running a single suite updates just that cell. The best value in each row is highlighted.

### The dashboard

`dashboard/` is a static web page that shows the results as charts and tables: the overnight scores, generation speed at 8k context, and full results tables.

```bash
uv run aibench dashboard                       # rebuild dashboard/data/ and RESULTS.md from results/
uv run aibench dashboard --serve               # ...and serve it at http://localhost:8765/
uv run aibench dashboard --serve --host 0.0.0.0 --port 9000   # reachable from the LAN
```

The same command writes [RESULTS.md](RESULTS.md), the same charts and tables as Markdown with Mermaid charts, which GitHub renders. `dashboard/data/models.csv` and `RESULTS.md` are committed, so the published repo shows the latest results without needing `results/`. Commit both after a run to publish new numbers.

Any static file server works too, once the data has been built: `python3 -m http.server -d dashboard 8765`. Opening `index.html` straight from disk (`file://`) won't work, because the page loads its data with `fetch`. It has no external dependencies (d3 is vendored), so it works offline.

A hosted copy is at [claude.ai/artifact/V73ppxH5G8hiHjJ6yiwdux](https://claude.ai/artifact/V73ppxH5G8hiHjJ6yiwdux). [ARCHITECTURE.md](ARCHITECTURE.md#dashboard) explains how the two copies share code and how to update the hosted one.

---

## Reference

### Concepts

| | what it is | built-in types |
|---|---|---|
| **backend** | something that serves models | `openai` (any OpenAI-compatible server), `llama-swap`, `llama-server` (aibench starts and stops it), `process` (any engine aibench starts and stops, such as Strata, vLLM or SGLang), `ollama` |
| **model** | a model on a backend, with its own sampling params, `max_tokens` and server args | — |
| **suite** | one benchmark with its settings | `throughput`, `llama-bench`, `humaneval-plus`, `mbpp-plus`, `livecodebench`, `code-jsonl`, `terminal` |
| **profile** | a named list of suites | — |
| **hardware** | a label for the box, driver and build a run was made on | — |

Run `uv run aibench list` to see everything configured.

### What the numbers mean

**Speed** (`throughput` suites)
- `ppN`: prompt processing (prefill) speed in tok/s for an N-token prompt.
- `tg@N`: generation (decode) speed in tok/s after an N-token prompt.
- `ttft@N`: time to first token, in seconds.
- `agg@N cK`: total tok/s with K requests at once.
- `draft accept`: the share of speculative-decoding draft tokens accepted.

Speeds come from the server's own timings when it reports them (llama.cpp, ollama); otherwise they're measured from the stream. Every prompt carries a random nonce, so the prompt cache never hits.

**Coding** (`humaneval-plus`, `mbpp-plus`, `code-jsonl`)
- `pass@1`: the share of problems solved on the original tests.
- `plus@1`: the share that also pass EvalPlus's extended tests.
- `avg output`: tokens per answer, which shows how much a reasoning model thinks.
- `truncated`: answers that hit `max_tokens` before finishing. These count as failures, so if the number is high, raise the model's `max_tokens`.

The harness passes all 542 reference solutions, but expect small differences from official EvalPlus numbers.

**LiveCodeBench**
- `pass@1` (overall and per difficulty) on competitive-programming problems (AtCoder stdin/stdout and LeetCode `class Solution`), graded on hidden tests with a 6 s limit per test.
- Unlike HumanEval+, it isn't saturated, which makes it the most useful coding signal here.
- `release: v6` means problems from Jan–Apr 2025. `sample: {medium: 15, hard: 15}` picks a fixed, evenly spaced subset, so runs stay comparable.
- The data (~135 MB per release) downloads from Hugging Face on first use.

**Terminal** (agentic tool use)
- The model gets two tools, `bash` and `write_file`, inside a throwaway Docker container (no network, 2 GB RAM, 2 CPUs, unprivileged user). It works until it replies without a tool call, and then a hidden script checks the result.
- The 18 built-in tasks cover log analysis, CSV/JSON/SQLite wrangling, process management, file organization, refactoring, broken C builds, git recovery and bisecting, merge conflicts, and writing a backup script.
- Most tasks hide a trap that punishes the sloppy approach: quoted commas in a CSV, `ERROR` inside INFO messages, numeric IP sorting, mtime vs. filename ordering.
- Metrics:
  - `pass`: tasks completed, overall and per difficulty.
  - `bad calls`: malformed tool arguments.
  - `leaked calls`: tool calls written as plain text, usually a server-side template or parser problem.
  - `avg turns`, `hit max turns`: how long the model took, and how often it ran out of turns.
- `repeats: 3` (the `terminal-x3` suite) runs each task three times. Sampling makes single runs noisy, and `pass ±` gives the standard error.
- Run `terminal-text` (commands in ```bash blocks instead of tool calls) next to `terminal` to tell a weak model apart from a server that can't parse its tool calls.

**Every suite** also records `peak vram`, `avg power` and `energy`, from amdgpu sysfs or nvidia-smi.

### Reasoning models

Set `max_tokens: 32768` or more, and the vendor's recommended sampling under `params:` (`temperature`, `top_p`, `top_k`, `min_p`…).

- **Passing settings to the server:** `params.extra_body` goes to the server as-is, for example `{chat_template_kwargs: {enable_thinking: false}}`.
- **Comparing thinking on and off:** define two model keys with the same `id`.
- **Multi-turn tasks:** `params.keep_reasoning: true` sends the model's reasoning back in the conversation history, for models whose docs ask for it.

### Fair runs on one GPU

- aibench warns when VRAM is already in use before a model loads, or when llama-swap has other models loaded.
- On the `llama-swap` backend, `exclusive: true` unloads everything else first.
- Managed backends (`process`, `llama-server`) take `pre:`/`post:` shell hooks. `bench.yaml` uses these to empty llama-swap before Strata starts.

### Comparing hardware or builds

Set `hardware:` in `bench.yaml` (or `--hardware` per run), for example `r9700-vulkan`, `r9700-rocm7` or `2x3090`. Copy results directories from different machines into one place and `aibench report` lines them up.

The `llama-bench` suite (`kernels`) measures llama.cpp kernels on the GGUF directly, with no HTTP or scheduling in the way. It's the cleanest number for comparing GPUs or llama.cpp builds.

### Code execution safety

Generated code runs in a separate `python -I` process with a memory limit and a timeout. That is **not** a security boundary. For untrusted models, set `sandbox: docker` on the suite (no network, 2 GB RAM, 1 CPU, `python:3.12-slim`).

### Your own coding tasks

Put tasks in a JSONL file such as `tasks/example.jsonl`, one task per line:

```json
{"id": "lru-cache", "entry_point": "LRUCache", "prompt": "Implement ...", "test": "c = LRUCache(2)\nassert ..."}
```

`test` runs in the solution's namespace. If it defines `check(candidate)`, that function is called with `entry_point`. Point a `code-jsonl` suite at the file.

### Your own terminal tasks

Write tasks as YAML (`instruction`, `setup`, `verify`, `solution`; see the files in `src/aibench/suites/terminal_tasks/`), put them in a directory, and point a terminal suite at it with `tasks_dir:`.

`uv run aibench selftest` checks every task without a model: `verify` must fail on the untouched setup and pass after the reference solution.

### Plugins

Every `*.py` under `plugins/` is imported. Register classes with `@registry.suite("name")` or `@registry.backend("name")`, and use that name as `type:` in `bench.yaml`. Alternatively, skip registration and write `type: mypkg.module:MyClass`. `plugins/example_plugin.py` is a complete minimal suite.

- **Suite:** subclass `aibench.suites.base.Suite` and implement `async run(ctx) -> SuiteResult`. Call `ctx.backend.generate(ctx.model, GenRequest(...))`, then record results with `res.add(name, value, unit, headline=True)`.
- **Backend:** subclass `aibench.backends.base.Backend` and implement `async generate(model, req) -> GenResult` (and optionally `prepare`/`release`/`model_info`). Most engines speak the OpenAI API, so `type: openai` or `type: process` usually works without writing code.
