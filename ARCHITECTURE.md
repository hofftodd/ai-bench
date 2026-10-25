# Architecture

aibench is a small async Python CLI (about 4,000 lines). It runs a matrix of **models × suites** against inference servers, one model at a time, and writes every result to a JSON file. Reporting and the dashboard only read those files, so they never need a model or a GPU.

```
                bench.yaml
                    │  config.py
                    ▼
 aibench run ──► runner.py ──────────────────────────────► results/<run_id>/run.json
                    │  for each model:                        results/<run_id>/samples/*.jsonl
                    │    backend.free_gpu → prepare (load)
                    │    for each suite: suite.run(ctx) ◄── GpuSampler (VRAM, power)
                    │    backend.release
                    ▼
            backends/*  ──HTTP──►  llama-swap :8080 → llama-server (Vulkan)
                                    Strata :8090 / ollama :11434 / any OpenAI API

 aibench report    ──► report.py    ── reads results/ ──► terminal table / md / csv / json
 aibench dashboard ──► dashboard.py ── reads results/ ──► dashboard/data/models.csv ──► dashboard/ (browser)
                                                       └► RESULTS.md (Markdown + Mermaid, for GitHub)
```

## Source layout

```
bench.yaml                  this machine's backends, models, suites and profiles
src/aibench/
  cli.py                    argparse entry point: run, report, dashboard, list, check, selftest, sysinfo
  config.py                 loads bench.yaml into Config / ModelSpec / SuiteSpec
  registry.py               name → class lookup for backends and suites; loads plugins/
  runner.py                 the benchmark loop; writes run.json after every suite
  report.py                 flattens runs into a table: latest result per (hardware, backend, model, suite)
  dashboard.py              flattens runs into the dashboard's CSV and RESULTS.md; serves dashboard/
  sysinfo.py                host and GPU discovery (amdgpu sysfs, nvidia-smi); background GpuSampler
  backends/
    base.py                 Backend ABC, GenRequest, GenResult (tokens, timings)
    openai_compat.py        OpenAI chat completions with streaming; reads llama.cpp server timings
    llama_swap.py           OpenAI backend plus unloading and model info through llama-swap's API
    llama_server.py         ProcessBackend (start/stop any server command) and LlamaServerBackend
    ollama.py               ollama's native /api/chat
  suites/
    base.py                 Suite ABC, SuiteResult, Metric, RunContext
    throughput.py           prefill/decode/TTFT at several prompt lengths and concurrency levels
    llama_bench.py          wraps the llama-bench binary (no server)
    code_eval.py            HumanEval+, MBPP+, LiveCodeBench, code-jsonl: generate, extract code, grade
    _code_runner.py         subprocess grader for HumanEval+/MBPP+ (memory limit, timeout)
    _lcb_runner.py          subprocess grader for LiveCodeBench (stdin/stdout and LeetCode-style)
    terminal.py             agentic bash/write_file loop in Docker, plus selftest
    terminal_tasks/*.yaml   the 18 built-in terminal tasks
plugins/                    user plugins; every *.py is imported at startup
tasks/                      custom code-jsonl tasks
dashboard/                  static dashboard (see below)
RESULTS.md                  generated Markdown version of the dashboard, for GitHub
results/                    one directory per run (git-ignored)
logs/                       console logs from long runs (git-ignored)
```

## Core ideas

**Everything is pluggable by name.** `bench.yaml` refers to backends and suites by `type:`, which `registry.py` resolves to a class. Built-ins register themselves with `@registry.backend(...)` / `@registry.suite(...)` when imported. Plugins in `plugins/` use the same decorators. A dotted `module:Class` path works without registering anything.

**One model at a time, with the whole GPU.** For each model, the runner:

1. Calls `free_gpu` (llama-swap with `exclusive: true` unloads everything else).
2. Waits for VRAM counters to settle.
3. Calls `prepare` to load the model and gather `model_info`: server build, GGUF path, context size, slots and full command line.
4. Runs each suite.
5. Calls `release`.

It warns when VRAM was already in use before the load, or when model memory spilled into system RAM (GTT). That makes results with a contaminated GPU easy to spot.

**Results are append-only and incremental.** `run.json` is rewritten after every suite. A crash keeps finished suites, and a run that is still going is visible because it has no `finished` timestamp yet. Each result stores its metrics (`value`, `unit`, `higher_is_better`, `headline`), suite-specific `details`, the GPU sampler summary, the model's sampling params and the suite options. Generated answers and their verdicts go to `samples/*.jsonl`, so failures can be inspected later.

**Reports pick the latest result per cell.** `report.build` walks runs oldest-first and overwrites, so re-running a single suite for a single model updates just that cell. Errors are tracked per suite and cleared by a later success.

**Backends own the protocol; suites own the scoring.** A suite only calls `ctx.backend.generate(model, GenRequest)`. The result (`GenResult`) carries the text, reasoning, tool calls, token counts and timings. Where the server reports its own timings (llama.cpp's `timings`, ollama's `eval_duration`), those are used instead of client-side measurements.

**Generated code runs out of process.** HumanEval+/MBPP+/LiveCodeBench answers are graded in a separate `python -I` subprocess with resource limits, or in Docker with `sandbox: docker`. Terminal tasks always run in a fresh, network-less Docker container built from `terminal.py`'s image definition.

## Data the suites download

These are cached in `~/.cache/aibench` (override with `AIBENCH_CACHE`):

- EvalPlus HumanEval+ and MBPP+ datasets, from GitHub releases.
- LiveCodeBench `code_generation_lite` releases, from Hugging Face (~135 MB each).

## Dashboard

```
dashboard/
  index.html          local shell: loads theme.css, vendored d3, dash-local.js
  page.html           the dashboard itself: markup, styles and scripts (shared with the hosted copy)
  dash-local.js       small stand-in for the claude.ai Dashboard runtime (dash.data/onData/calc/colors)
  theme.css           design tokens page.html expects (light and dark)
  vendor/d3.v7.9.0.min.js
  data/models.csv     generated by `aibench dashboard` (committed, so a clone can show results)
  data/meta.json      when the data was built
```

`page.html` is written against the claude.ai Dashboard type's small runtime API:

- `dash.data(id)`: rows of a dataset.
- `dash.onData(fn)`: redraw whenever data or width changes.
- `dash.calc(id, …)`: derived values, such as the summary tiles.
- `dash.colors`: series colors.

`dash-local.js` implements that API over the CSV files listed in `window.DASH_DATASETS`, and `theme.css` supplies the CSS variables. That lets the **same `page.html` run unchanged** both locally and in the hosted artifact.

`dashboard.py` builds `models.csv`, one row per model, from `results/`:

- Overnight metrics come from `terminal-x3` and `livecodebench`. Quick-profile metrics come from `speed-quick`, `humaneval-quick` and `terminal-quick`.
- `overnight_order` is the order in which models first ran an overnight suite.
- `terminal_x3_pass_pct` substitutes the re-run of the fixed `backup-rotation` task (suite `terminal-backup-rotation`) when a model has one; `terminal_x3_orig_pct` keeps the score as run.
- RESULTS.md also gets a Vulkan vs ROCm speed table, pairing each model with its `<model>-rocm` twin run under the `-rocm` hardware label.
- `overnight_status` is one of:
  - `done`: both overnight suites finished.
  - `running`: the model is in a run with no `finished` timestamp.
  - `partial`: only one overnight suite finished.
  - `not run`: no overnight results.

To change what the dashboard shows:

1. Add columns to `METRICS`/`DETAILS` in `dashboard.py`.
2. Use them in `page.html`.
3. Add them to `write_markdown` if they belong in RESULTS.md.
4. Run `aibench dashboard --serve` to check.

**RESULTS.md** is written by `dashboard.write_markdown` from the same rows: a summary line, Mermaid `xychart-beta` bar charts (GitHub renders Mermaid inside Markdown), and the two tables with the best value in each column in bold. `results/` itself isn't committed (raw samples are large), so `models.csv` and `RESULTS.md` are what the published repo shows.

**Updating the hosted copy.** The hosted artifact's page is the `files/index.html` document in its store (the text of `page.html`), and its data is an uploaded copy of `models.csv` referenced by the `datasets/models` document. Updating it is done from a Claude Code session, which has the tools for it:

1. Upload the new CSV as an asset.
2. Point `datasets/models` at it (`url`, `name`, `updated`).
3. If `page.html` changed, write its text to `files/index.html`.
4. Delete the old CSV asset.

## External pieces on this machine

These are outside the repo but the benchmark depends on them:

- **llama-swap** (`~/.local/bin/llama-swap`, config `~/.config/llama-swap/config.yaml`, port 8080): loads each model in its own `llama-server` on demand. It currently runs llama.cpp **b11850** (Vulkan) from `~/src/llama.cpp-b11850`.
- **llama-config** (`~/.local/bin/llama-config`): regenerates the llama-swap config from the GGUFs under `~/models`, fitting the context size to VRAM, and repoints local clients. It always restarts llama-swap, so never run it during a benchmark.
- **Strata** (`strata` CLI): a Rust/HIP engine for Qwen3.8-Flash-Next, started and stopped by the `strata` process backend on port 8090.
- **Docker**: needed by the terminal suites and by `sandbox: docker`.
- **Models** live under `~/models/<name>/` and are synced to the NAS with unison (`~/.unison/models.prf`).
