"""Dashboard data: one row per model, flattened from every run.json in results/.

`aibench dashboard` writes dashboard/data/models.csv (the page's only data) and
RESULTS.md (the same views as Markdown + Mermaid, for GitHub), and can serve the
dashboard/ directory over HTTP. The same CSV is what gets uploaded to the hosted
claude.ai copy of the dashboard.
"""

from __future__ import annotations

import csv
import functools
import json
import re
import shlex
import struct
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .report import _fmt
from .runner import is_alive

OVERNIGHT = ("terminal-x3", "livecodebench")

# speed-quick with ignore_eos off, for servers that reject it (ds4, sushi); same prompts and lengths
SPEED = ("speed-quick", "speed-quick-eos")

# CSV column -> (suite or suites tried in order, metric). Columns the page reads; order is the CSV's.
METRICS: dict[str, tuple[str | tuple[str, ...], str]] = {
    "lcb_truncated": ("livecodebench", "truncated"),
    "terminal_x3_pass_pct": ("terminal-x3", "pass"),
    "lcb_pass_pct": ("livecodebench", "pass@1"),
    "terminal_x3_wall_min": ("terminal-x3", "wall"),
    "lcb_wall_min": ("livecodebench", "wall"),
    "lcb64k_pass_pct": ("livecodebench-64k", "pass@1"),
    "lcb64k_truncated": ("livecodebench-64k", "truncated"),
    "lcb128k_pass_pct": ("livecodebench-128k", "pass@1"),
    "lcb128k_truncated": ("livecodebench-128k", "truncated"),
    "humaneval_quick_pass_pct": ("humaneval-quick", "pass@1"),
    "humaneval_quick_plus_pct": ("humaneval-quick", "plus@1"),
    "terminal_quick_pass_pct": ("terminal-quick", "pass"),
    "pp512_tok_s": (SPEED, "pp512"),
    "tg512_tok_s": (SPEED, "tg@512"),
    "pp8k_tok_s": (SPEED, "pp8k"),
    "tg8k_tok_s": (SPEED, "tg@8k"),
    "ttft8k_s": (SPEED, "ttft@8k"),
    "bench_pp512_tok_s": ("kernels", "pp512"),     # llama-bench, no server
    "bench_tg128_tok_s": ("kernels", "tg128"),
}
DETAILS: dict[str, tuple[str, str]] = {
    "terminal_x3_episodes": ("terminal-x3", "episodes"),
    "lcb_problems": ("livecodebench", "problems"),
}
COLUMNS = ["model", "backend", "quant", "overnight_order", "overnight_status", *METRICS, "terminal_x3_orig_pct",
           *DETAILS]

# Quant names as they appear in GGUF filenames (Unsloth's dynamic quants keep their UD- prefix). ik_llama.cpp's
# IQn_K types (Avalon's "IQ3KS") are matched by name: their header ftype numbers collide with llama.cpp's.
QUANT_RE = re.compile(r"(?<![A-Za-z0-9])((?:UD-)?(?:IQ\d_(?:XXS|XS|NL|S|M)|IQ\d_?K(?:SS|S|T)?|TQ\d_\d"
                      r"|Q\d_K(?:_(?:XL|S|M|L))?|Q\d_\d|MXFP4(?:_MOE)?|NVFP4|BF16|F16|F32))(?![A-Za-z0-9])", re.IGNORECASE)
# llama.cpp's llama_ftype (include/llama.h), for GGUFs whose filename doesn't name the quant.
BPW_RE = re.compile(r"(?<![A-Za-z0-9.])(\d+(?:\.\d+)?bpw)(?![A-Za-z0-9])", re.IGNORECASE)
EXPERTS_RE = re.compile(r"(?<![A-Za-z0-9])(IQ\dXXS|IQ\dXS|Q\dK)(?=-w\d|Experts)")
FILE_TYPES = {0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 7: "Q8_0", 8: "Q5_0", 9: "Q5_1", 10: "Q2_K", 11: "Q3_K_S",
              12: "Q3_K_M", 13: "Q3_K_L", 14: "Q4_K_S", 15: "Q4_K_M", 16: "Q5_K_S", 17: "Q5_K_M", 18: "Q6_K",
              19: "IQ2_XXS", 20: "IQ2_XS", 21: "Q2_K_S", 22: "IQ3_XS", 23: "IQ3_XXS", 24: "IQ1_S", 25: "IQ4_NL",
              26: "IQ3_S", 27: "IQ3_M", 28: "IQ2_S", 29: "IQ2_M", 30: "IQ4_XS", 31: "IQ1_M", 32: "BF16",
              36: "TQ1_0", 37: "TQ2_0", 38: "MXFP4_MOE", 39: "NVFP4", 40: "Q1_0", 41: "Q2_0"}


def _gguf_file_type(path: Path) -> int | None:
    """general.file_type from a GGUF header, or None if it can't be read."""
    scalar = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
    try:
        with path.open("rb") as f:
            if f.read(4) != b"GGUF":
                return None
            _version, _tensors, n_kv = struct.unpack("<IQQ", f.read(20))

            def string() -> str:
                (n,) = struct.unpack("<Q", f.read(8))
                return f.read(n).decode(errors="replace")

            def skip(t: int) -> None:
                if t == 8:
                    string()
                elif t == 9:
                    et, n = struct.unpack("<IQ", f.read(12))
                    for _ in range(n):
                        skip(et)
                else:
                    f.read(struct.calcsize(scalar[t]))

            for _ in range(n_kv):
                key = string()
                (t,) = struct.unpack("<I", f.read(4))
                if key == "general.file_type":
                    return struct.unpack("<" + scalar[t], f.read(struct.calcsize(scalar[t])))[0]
                skip(t)
    except (OSError, KeyError, struct.error):
        return None
    return None


@functools.cache
def quant(model_path: str | None) -> str:
    """The quant a GGUF was made with: from its filename, else from its header."""
    if not model_path:
        return ""
    name = Path(model_path).name
    if m := QUANT_RE.search(name):
        return re.sub(r"^IQ(\d)K", r"IQ\1_K", m.group(1).upper())
    if m := BPW_RE.search(name):          # MLX packs (sushi): "...-Sushi-2.4bpw"
        return m.group(1).lower()
    if m := EXPERTS_RE.search(name):      # DwarfStar: names the routed experts' type ("IQ2XXS-w2Q2K", "Q4KExperts")
        return re.sub(r"^(IQ\d)(XXS|XS|S|M)$|^(Q\d)K$", lambda g: f"{g[1]}_{g[2]}" if g[1] else f"{g[3]}_K", m.group(1))
    return FILE_TYPES.get(_gguf_file_type(Path(model_path)), "")


def _cmd_model(cmd: str | None) -> str | None:
    """The model path from a recorded server command line (`-m X` / `--model X`), for servers whose API doesn't
    report one (DwarfStar, sushi)."""
    parts = shlex.split(cmd or "")
    for flag, value in zip(parts, parts[1:]):
        if flag in ("-m", "--model"):
            return value
    return None

# terminal-x3 shipped with a broken backup-rotation task (it failed any model that tested its script).
# The fixed task was re-run on its own; its per-task result replaces the old one in terminal_x3_pass_pct.
TERMINAL_FIX = "terminal-backup-rotation"


def _rescore(x3: dict, fix: dict) -> float:
    per = {**x3["details"]["per_task"], **fix["details"]["per_task"]}
    passed, total = (sum(int(v.split("/")[i]) for v in per.values()) for i in (0, 1))
    return 100 * passed / total


def _metric(suites: dict[str, dict], suite: str | tuple[str, ...], metric: str) -> Any:
    for s in (suite,) if isinstance(suite, str) else suite:
        v = ((suites.get(s) or {}).get("metrics") or {}).get(metric, {}).get("value")
        if v is not None:
            return v
    return None


def build_rows(runs: list[dict[str, Any]], hardware: str | None = None,
               overnight: tuple[str, ...] | list[str] = OVERNIGHT) -> list[dict[str, Any]]:
    """Latest successful result per (model, suite); overnight order is when a model first ran an overnight suite.

    `overnight` is the set of suites that makes a model "done" (a box without Docker has no terminal-x3).
    Runs made with --limit (smoke tests on a few problems) are skipped so they never replace a full score."""
    latest: dict[str, dict[str, dict]] = {}    # model -> suite -> result
    run_no: dict[tuple[str, str], int] = {}     # (model, suite) -> index of the run its latest result is from
    backend: dict[str, str] = {}
    model_path: dict[str, str] = {}
    order: list[str] = []
    running: set[str] = set()
    for i, run in enumerate(runs):   # oldest first, so later results win
        if hardware and run.get("hardware") != hardware or run.get("limit"):
            continue
        for res in run.get("results", []):
            if res.get("error"):
                continue
            m = res["model"]
            latest.setdefault(m, {})[res["suite"]] = res
            run_no[m, res["suite"]] = i
            backend[m] = res["backend"]
            mi = res.get("model_info") or {}
            if path := mi.get("model_path") or _cmd_model(mi.get("cmd")):
                model_path[m] = path
            if res["suite"] in overnight and m not in order:
                order.append(m)
        if not is_alive(run):
            continue
        if cur := run.get("current"):
            running.add(cur["model"])
            backend.setdefault(cur["model"], cur["backend"])
        elif run.get("results"):   # runs from before the runner recorded `current`
            running.add(run["results"][-1]["model"])

    rows = []
    for m in order + sorted((set(latest) | running) - set(order)):
        suites = latest.get(m, {})
        if all(s in suites for s in overnight):
            status = "done"
        elif m in running:
            status = "running"
        elif any(s in suites for s in overnight):
            status = "partial"
        else:
            status = "not run"
        row: dict[str, Any] = {
            "model": m,
            "backend": backend[m],
            "quant": quant(model_path.get(m)),
            "overnight_order": order.index(m) + 1 if m in order else "",
            "overnight_status": status,
        }
        for col, (suite, metric) in METRICS.items():
            v = _metric(suites, suite, metric)
            row[col] = "" if v is None else _fmt(v)
        for col, (suite, key) in DETAILS.items():
            row[col] = ((suites.get(suite) or {}).get("details") or {}).get(key, "")
        row["terminal_x3_orig_pct"] = row["terminal_x3_pass_pct"]
        # only when the fix ran after terminal-x3; a newer terminal-x3 already has the fixed task
        if "terminal-x3" in suites and TERMINAL_FIX in suites and run_no[m, TERMINAL_FIX] > run_no[m, "terminal-x3"]:
            row["terminal_x3_pass_pct"] = _fmt(_rescore(suites["terminal-x3"], suites[TERMINAL_FIX]))
        rows.append(row)
    return rows


def _latest(runs: list[dict[str, Any]], hardware: str) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for run in runs:
        if run.get("hardware") == hardware:
            for res in run.get("results", []):
                if not res.get("error"):
                    out.setdefault(res["model"], {})[res["suite"]] = res
    return out


# (column, suite on the base hardware, suite on the compared hardware, metric)
COMPARE = [("tg8k", "speed-quick", "speed-quick", "tg@8k"), ("pp8k", "speed-quick", "speed-quick", "pp8k"),
           ("bench_tg128", "kernels", "kernels-rocm", "tg128"), ("bench_pp512", "kernels", "kernels-rocm", "pp512")]


def compare_rows(runs: list[dict[str, Any]], base: str, other: str, suffix: str = "-rocm") -> list[dict[str, Any]]:
    """Speed of each model on `base` next to its `<model><suffix>` twin on `other` (e.g. Vulkan vs ROCm)."""
    a, b = _latest(runs, base), _latest(runs, other)

    def val(suites: dict, suite: str, metric: str) -> float | None:
        return ((suites.get(suite) or {}).get("metrics") or {}).get(metric, {}).get("value")

    rows = []
    for m in sorted(a):
        if m + suffix not in b:
            continue
        row: dict[str, Any] = {"model": m}
        for col, sa, sb, metric in COMPARE:
            va, vb = val(a[m], sa, metric), val(b[m + suffix], sb, metric)
            row[f"{col}_a"] = "" if va is None else _fmt(va)
            row[f"{col}_b"] = "" if vb is None else _fmt(vb)
            row[f"{col}_delta"] = f"{100 * (vb - va) / va:+.0f}%" if va and vb else ""
        rows.append(row)
    return rows


def write_data(rows: list[dict[str, Any]], data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    out = data_dir / "models.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    meta = {"updated": datetime.now().astimezone().isoformat(timespec="seconds"), "models": len(rows)}
    (data_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return out


def _num(v: Any) -> float | None:
    return None if v in ("", None) else float(v)


def _bar_chart(title: str, axis: str, rows: list[dict[str, Any]], col: str, top: float | None = None) -> str:
    """A horizontal Mermaid bar chart (GitHub renders these), best first."""
    rows = sorted((r for r in rows if _num(r[col]) is not None), key=lambda r: -_num(r[col]))
    if not rows:
        return ""
    top = top or max(_num(r[col]) for r in rows) * 1.05
    names = ", ".join(json.dumps(r["model"]) for r in rows)
    values = ", ".join(str(_num(r[col])) for r in rows)
    init = ('%%{init: {"xyChart": {"showDataLabel": true}, '
            '"themeVariables": {"xyChart": {"plotColorPalette": "#3b6fd4"}}}}%%')
    return (f'```mermaid\n{init}\nxychart-beta horizontal\n    title "{title}"\n    x-axis [{names}]\n'
            f'    y-axis "{axis}" 0 --> {top:.0f}\n    bar [{values}]\n```\n')


def _table(rows: list[dict[str, Any]], cols: dict[str, str], higher: dict[str, bool]) -> str:
    """Markdown table; the best value of each column in `higher` is bold."""
    best = {}
    for c, hi in higher.items():
        vals = [_num(r[c]) for r in rows if _num(r[c]) is not None]
        if len(vals) > 1:
            best[c] = max(vals) if hi else min(vals)
    lines = ["| " + " | ".join(cols.values()) + " |",
             "|" + "|".join(":---" if c in ("model", "backend", "quant", "overnight_status") else "---:"
                            for c in cols) + "|"]
    for r in rows:
        cells = []
        for c in cols:
            v = r[c]
            cell = str(v) if v != "" else "—"
            if c in best and _num(v) == best[c]:
                cell = f"**{cell}**"
            cells.append(cell)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _present(rows: list[dict[str, Any]], cols: dict[str, str]) -> dict[str, str]:
    """`cols` minus the columns no row has a value for (a box that never ran a suite)."""
    return {c: h for i, (c, h) in enumerate(cols.items()) if i == 0 or any(r.get(c, "") != "" for r in rows)}


def write_markdown(rows: list[dict[str, Any]], out: Path, hardware: str,
                   compare: list[dict[str, Any]] | None = None, other: str = "",
                   overnight: tuple[str, ...] | list[str] = OVERNIGHT, notes: str = "",
                   data_csv: str = "dashboard/data/models.csv") -> Path:
    """RESULTS.md: the dashboard as Markdown + Mermaid, for reading on GitHub.

    `notes` is Markdown placed under the summary (what this box is, what it can't run)."""
    done = [r for r in rows if r["overnight_status"] == "done"]
    has_terminal = "terminal-x3" in overnight

    def leaders(col: str) -> tuple[str, Any]:
        top = max((_num(r[col]) for r in done if _num(r[col]) is not None), default=None)
        names = [f"**{r['model']}**" for r in done if top is not None and _num(r[col]) == top]
        return " and ".join(names), next((r[col] for r in done if _num(r[col]) == top), None)

    (bt, bt_v), (bl, bl_v) = leaders("terminal_x3_pass_pct"), leaders("lcb_pass_pct")
    speed = [r for r in rows if _num(r["tg8k_tok_s"]) is not None]
    fastest = max(speed, key=lambda r: _num(r["tg8k_tok_s"]), default=None)
    updated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    suites = " + ".join(overnight)

    parts = [
        "# Benchmark results\n\n",
        f"Local LLMs on `{hardware}`, generated by `uv run aibench dashboard` on {updated}. "
        "This is the Markdown version of the interactive dashboard in [`dashboard/`](dashboard/); "
        "serve that with `uv run aibench dashboard --serve`. "
        f"The raw numbers are in [`{data_csv}`]({data_csv}).\n\n",
    ]
    if bl and (bt or not has_terminal):
        lead = (f"Best on terminal-x3: {bt} at {bt_v}%. " if has_terminal else "") + \
            f"Best on LiveCodeBench: {bl} at {bl_v}%."
        parts.append(f"{lead} {len(done)} of {len(rows)} models have finished the overnight profile ({suites}).")
        if fastest:
            parts.append(f" The fastest generator at 8k context is **{fastest['model']}** at "
                         f"{fastest['tg8k_tok_s']} tok/s.")
        parts.append("\n")
    if notes:
        parts.append(f"\n{notes.strip()}\n")

    terminal_text = (
        "**terminal-x3** runs 18 agentic shell tasks three times each (54 episodes) in a Docker sandbox. "
        "Its `backup-rotation` task was broken in the original runs (it failed any model that tested its script). "
        "For runs made before the fix, the fixed task was re-run on its own and its result is used here; "
        "\"as run\" is the original score. ") if has_terminal else ""
    overnight_cols = {"model": "Model", "backend": "Backend", "quant": "Quant", "overnight_status": "Status",
                      "terminal_x3_pass_pct": "terminal-x3 %", "terminal_x3_orig_pct": "as run %",
                      "lcb_pass_pct": "LCB pass@1 %", "lcb_truncated": "LCB cut off", "lcb64k_pass_pct": "LCB 64k %",
                      "lcb64k_truncated": "64k cut off", "lcb128k_pass_pct": "LCB 128k %",
                      "lcb128k_truncated": "128k cut off", "terminal_x3_wall_min": "terminal-x3 min",
                      "lcb_wall_min": "LCB min"}
    if len({r["backend"] for r in rows}) < 2:
        overnight_cols.pop("backend")
    parts += [
        "\n## Overnight profile\n\n",
        terminal_text,
        "**LiveCodeBench** is an evenly spaced sample of 15 medium and 15 hard v6 problems (Jan–Apr 2025), "
        "with a 32k-token budget; **LCB 64k** re-runs the same problems with 64k for models that ran out of room, "
        "and **LCB 128k** with 128k for models still cut off at 64k.\n\n",
        (_bar_chart("terminal-x3 pass rate (%)", "pass %", done, "terminal_x3_pass_pct", 100) + "\n") if has_terminal else "",
        _bar_chart("LiveCodeBench pass@1 (%)", "pass@1 %", done, "lcb_pass_pct", 100), "\n",
        _table(rows, _present(rows, overnight_cols),
               {"terminal_x3_pass_pct": True, "lcb_pass_pct": True, "lcb64k_pass_pct": True,
                "lcb128k_pass_pct": True}),
        "\n\"Cut off\" counts LiveCodeBench answers that hit `max_tokens` before finishing. Those score as "
        "failures, so the cap pulls down models that think at length. \"Quant\" is the GGUF quantization each model "
        "ran at; `UD-` marks Unsloth Dynamic quants, which keep sensitive layers at higher precision. "
        "[TODO.md](TODO.md) has more caveats.\n",
        "\n## Speed and quick profile\n\n",
        "Server-measured speeds from each model's latest `speed-quick` run (the server's own timings where it reports "
        "them, otherwise measured from the stream), the raw llama-bench numbers for llama.cpp models, a 40-problem "
        "HumanEval+ subset" + (" and six terminal tasks" if has_terminal else "") + ".\n\n",
        _bar_chart("Generation speed at 8k context (tok/s)", "tok/s", speed, "tg8k_tok_s"), "\n",
        _table(rows, _present(rows, {
            "model": "Model", "backend": "Backend", "quant": "Quant",
            "humaneval_quick_pass_pct": "HumanEval %", "humaneval_quick_plus_pct": "HumanEval+ %",
            "terminal_quick_pass_pct": "Terminal %", "pp512_tok_s": "Prompt 512 tok/s", "tg512_tok_s": "Gen @512 tok/s",
            "pp8k_tok_s": "Prompt 8k tok/s", "tg8k_tok_s": "Gen @8k tok/s", "ttft8k_s": "TTFT @8k s",
            "bench_pp512_tok_s": "llama-bench pp512", "bench_tg128_tok_s": "llama-bench tg128"}),
               {"humaneval_quick_plus_pct": True, "terminal_quick_pass_pct": True, "pp512_tok_s": True,
                "tg512_tok_s": True, "pp8k_tok_s": True, "tg8k_tok_s": True, "ttft8k_s": False,
                "bench_pp512_tok_s": True, "bench_tg128_tok_s": True}),
        "\nBold marks the best value in a column. — means the model hasn't run that suite yet.\n",
    ]
    if compare:
        parts += [
            f"\n## `{hardware}` vs `{other}`\n\n",
            "The same GGUFs and llama.cpp release (b11850) on both backends. Server speeds come from `speed-quick`; "
            "the llama-bench columns are raw kernel throughput (`kernels` / `kernels-rocm`, no server).\n\n",
            _table(compare, {"model": "Model", "tg8k_a": f"Gen @8k {hardware}", "tg8k_b": other, "tg8k_delta": "Δ",
                             "pp8k_a": f"Prompt 8k {hardware}", "pp8k_b": other, "pp8k_delta": "Δ",
                             "bench_tg128_a": f"llama-bench tg128 {hardware}", "bench_tg128_b": other,
                             "bench_pp512_a": f"llama-bench pp512 {hardware}", "bench_pp512_b": other}, {}),
        ]
    out.write_text("".join(parts))
    return out


def read_rows(path: Path) -> list[dict[str, Any]]:
    """models.csv back into rows (another machine's published results)."""
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


# (column, header, higher is better) for the cross-machine tables
COMPARE_QUALITY = [("humaneval_quick_plus_pct", "HumanEval+ %", True), ("lcb_pass_pct", "LCB pass@1 %", True),
                   ("lcb_truncated", "LCB cut off", False), ("lcb64k_pass_pct", "LCB 64k %", True),
                   ("lcb64k_truncated", "64k cut off", False), ("lcb_wall_min", "LCB min", False)]
COMPARE_SPEED = [("pp512_tok_s", "Prompt 512", True), ("tg512_tok_s", "Gen @512", True),
                 ("pp8k_tok_s", "Prompt 8k", True), ("tg8k_tok_s", "Gen @8k", True), ("ttft8k_s", "TTFT @8k s", False),
                 ("bench_pp512_tok_s", "llama-bench pp512", True), ("bench_tg128_tok_s", "llama-bench tg128", True)]
RATIO = {"lcb_wall_min", "tg8k_tok_s", "pp8k_tok_s", "ttft8k_s", "tg512_tok_s", "pp512_tok_s",
         "bench_pp512_tok_s", "bench_tg128_tok_s"}


def _ratio(a: Any, b: Any, higher: bool) -> str:
    """How many times better b is than a (>1 = b better), for speeds and times alike."""
    a, b = _num(a), _num(b)
    if not a or not b:
        return ""
    r = b / a if higher else a / b
    return f"{r:.2f}×" if r < 10 else f"{r:.0f}×"


def _engine(r: dict[str, Any]) -> str:
    return f"{r['backend']}, {r['quant']}" if r.get("quant") else r["backend"]


def _cross_table(pairs: list[tuple[str, dict, dict]], cols: list[tuple[str, str, bool]], a: str, b: str) -> str:
    cols = [c for c in cols if any(ra.get(c[0], "") != "" or rb.get(c[0], "") != "" for _, ra, rb in pairs)]
    head = ["Model"]
    for c, h, _ in cols:
        head += [f"{h} {a}", b] + (["×"] if c in RATIO else [])
    lines = ["| " + " | ".join(head) + " |", "|:---|" + "---:|" * (len(head) - 1)]
    for name, ra, rb in pairs:
        cells = [name]
        for c, _, hi in cols:
            va, vb = ra.get(c, ""), rb.get(c, "")
            cells += [va or "—", vb or "—"] + ([_ratio(va, vb, hi) or "—"] if c in RATIO else [])
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def write_comparison(base: list[dict[str, Any]], base_label: str, other: list[dict[str, Any]], other_label: str,
                     out: Path, pairs: dict[str, str] | None = None, notes: str = "",
                     sources: tuple[str, str] = ("", "")) -> Path:
    """Two machines side by side, from each one's models.csv.

    Models with the same key ran the same GGUF and settings on both. `pairs` maps a model on `other` to a model
    on `base` that is the same network on a different engine or quant (e.g. DwarfStar vs llama.cpp)."""
    a, b = {r["model"]: r for r in base}, {r["model"]: r for r in other}
    same = [(m, a[m], b[m]) for m in b if m in a]
    paired = [(f"{m} ({_engine(b[m])}) vs {bm} ({_engine(a[bm])})", a[bm], b[m])
              for m, bm in (pairs or {}).items() if m in b and bm in a]
    only_a = sorted(set(a) - set(b) - set((pairs or {}).values()))
    only_b = sorted(set(b) - set(a) - set(pairs or {}))
    updated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    src = " and ".join(f"[`{p}`]({p})" for p in sources if p)
    parts = [
        f"# {base_label} vs {other_label}\n\n",
        f"Generated by `uv run aibench dashboard` on {updated} from each machine's published results"
        + (f" ({src})" if src else "") + f". In every \"×\" column, above 1 means **{other_label}** did better "
        f"(faster, or less time); below 1 means **{base_label}** did.\n",
    ]
    if notes:
        parts.append(f"\n{notes.strip()}\n")
    for title, rows, intro in (
            ("Same GGUF on both machines", same,
             "Same model file, sampling and server settings, so the quality scores should agree within sampling noise "
             "and the speed columns compare the hardware."),
            ("Same model, different engine", paired,
             "The same network on each machine's best available engine or quant, so neither column is a pure "
             "hardware comparison.")):
        if not rows:
            continue
        parts += [f"\n## {title}\n\n{intro}\n\n### Quality\n\n",
                  _cross_table(rows, COMPARE_QUALITY, base_label, other_label),
                  "\n### Speed (tok/s unless noted)\n\n", _cross_table(rows, COMPARE_SPEED, base_label, other_label)]
    if only_a or only_b:
        parts.append("\n## Only on one machine\n\n")
        if only_b:
            parts.append(f"- **{other_label}:** " + ", ".join(f"`{m}` ({_engine(b[m])})" for m in only_b) + "\n")
        if only_a:
            parts.append(f"- **{base_label}:** " + ", ".join(f"`{m}`" for m in only_a) + "\n")
    out.write_text("".join(parts))
    return out


def serve(directory: Path, host: str, port: int) -> None:
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(directory))
    with ThreadingHTTPServer((host, port), handler) as httpd:
        print(f"serving {directory} at http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}/"
              "  (Ctrl-C to stop)")
        httpd.serve_forever()
