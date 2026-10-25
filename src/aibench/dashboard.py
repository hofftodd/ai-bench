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
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .report import _fmt

OVERNIGHT = ("terminal-x3", "livecodebench")

# CSV column -> (suite, metric). Columns the page reads; order is the CSV's.
METRICS: dict[str, tuple[str, str]] = {
    "lcb_truncated": ("livecodebench", "truncated"),
    "terminal_x3_pass_pct": ("terminal-x3", "pass"),
    "lcb_pass_pct": ("livecodebench", "pass@1"),
    "terminal_x3_wall_min": ("terminal-x3", "wall"),
    "lcb_wall_min": ("livecodebench", "wall"),
    "humaneval_quick_pass_pct": ("humaneval-quick", "pass@1"),
    "humaneval_quick_plus_pct": ("humaneval-quick", "plus@1"),
    "terminal_quick_pass_pct": ("terminal-quick", "pass"),
    "pp512_tok_s": ("speed-quick", "pp512"),
    "tg512_tok_s": ("speed-quick", "tg@512"),
    "pp8k_tok_s": ("speed-quick", "pp8k"),
    "tg8k_tok_s": ("speed-quick", "tg@8k"),
    "ttft8k_s": ("speed-quick", "ttft@8k"),
}
DETAILS: dict[str, tuple[str, str]] = {
    "terminal_x3_episodes": ("terminal-x3", "episodes"),
    "lcb_problems": ("livecodebench", "problems"),
}
COLUMNS = ["model", "backend", "overnight_order", "overnight_status", *METRICS, *DETAILS]


def build_rows(runs: list[dict[str, Any]], hardware: str | None = None) -> list[dict[str, Any]]:
    """Latest successful result per (model, suite); overnight order is when a model first ran an overnight suite."""
    latest: dict[str, dict[str, dict]] = {}    # model -> suite -> result
    backend: dict[str, str] = {}
    order: list[str] = []
    running: set[str] = set()
    for run in runs:   # oldest first, so later results win
        if hardware and run.get("hardware") != hardware:
            continue
        for res in run.get("results", []):
            if res.get("error"):
                continue
            m = res["model"]
            latest.setdefault(m, {})[res["suite"]] = res
            backend[m] = res["backend"]
            if res["suite"] in OVERNIGHT and m not in order:
                order.append(m)
        if not run.get("finished") and run.get("results"):
            running.add(run["results"][-1]["model"])

    rows = []
    for m in order + sorted(set(latest) - set(order)):
        suites = latest[m]
        if all(s in suites for s in OVERNIGHT):
            status = "done"
        elif m in running:
            status = "running"
        elif any(s in suites for s in OVERNIGHT):
            status = "partial"
        else:
            status = "not run"
        row: dict[str, Any] = {
            "model": m,
            "backend": backend[m],
            "overnight_order": order.index(m) + 1 if m in order else "",
            "overnight_status": status,
        }
        for col, (suite, metric) in METRICS.items():
            v = ((suites.get(suite) or {}).get("metrics") or {}).get(metric, {}).get("value")
            row[col] = "" if v is None else _fmt(v)
        for col, (suite, key) in DETAILS.items():
            row[col] = ((suites.get(suite) or {}).get("details") or {}).get(key, "")
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
    return (f'```mermaid\nxychart-beta horizontal\n    title "{title}"\n    x-axis [{names}]\n'
            f'    y-axis "{axis}" 0 --> {top:.0f}\n    bar [{values}]\n```\n')


def _table(rows: list[dict[str, Any]], cols: dict[str, str], higher: dict[str, bool]) -> str:
    """Markdown table; the best value of each column in `higher` is bold."""
    best = {}
    for c, hi in higher.items():
        vals = [_num(r[c]) for r in rows if _num(r[c]) is not None]
        if len(vals) > 1:
            best[c] = max(vals) if hi else min(vals)
    lines = ["| " + " | ".join(cols.values()) + " |",
             "|" + "|".join(":---" if c in ("model", "backend", "overnight_status") else "---:" for c in cols) + "|"]
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


def write_markdown(rows: list[dict[str, Any]], out: Path, hardware: str) -> Path:
    """RESULTS.md: the dashboard as Markdown + Mermaid, for reading on GitHub."""
    done = [r for r in rows if r["overnight_status"] == "done"]

    def leaders(col: str) -> tuple[str, Any]:
        top = max((_num(r[col]) for r in done if _num(r[col]) is not None), default=None)
        names = [f"**{r['model']}**" for r in done if top is not None and _num(r[col]) == top]
        return " and ".join(names), next((r[col] for r in done if _num(r[col]) == top), None)

    (bt, bt_v), (bl, bl_v) = leaders("terminal_x3_pass_pct"), leaders("lcb_pass_pct")
    speed = [r for r in rows if _num(r["tg8k_tok_s"]) is not None]
    fastest = max(speed, key=lambda r: _num(r["tg8k_tok_s"]), default=None)
    updated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")

    parts = [
        "# Benchmark results\n\n",
        f"Local LLMs on `{hardware}`, generated by `uv run aibench dashboard` on {updated}. "
        "This is the Markdown version of the interactive dashboard in [`dashboard/`](dashboard/); "
        "serve that with `uv run aibench dashboard --serve`. "
        "The raw numbers are in [`dashboard/data/models.csv`](dashboard/data/models.csv).\n\n",
    ]
    if bt and bl:
        lead = f"Best on terminal-x3: {bt} at {bt_v}%. Best on LiveCodeBench: {bl} at {bl_v}%."
        parts.append(f"{lead} {len(done)} of {len(rows)} models have finished the overnight profile.")
        if fastest:
            parts.append(f" The fastest generator at 8k context is **{fastest['model']}** at "
                         f"{fastest['tg8k_tok_s']} tok/s.")
        parts.append("\n")

    parts += [
        "\n## Overnight profile\n\n",
        "**terminal-x3** runs 18 agentic shell tasks three times each (54 episodes) in a Docker sandbox. "
        "**LiveCodeBench** is an evenly spaced sample of 15 medium and 15 hard v6 problems (Jan–Apr 2025).\n\n",
        _bar_chart("terminal-x3 pass rate (%)", "pass %", done, "terminal_x3_pass_pct", 100), "\n",
        _bar_chart("LiveCodeBench pass@1 (%)", "pass@1 %", done, "lcb_pass_pct", 100), "\n",
        _table(rows, {"model": "Model", "overnight_status": "Status", "terminal_x3_pass_pct": "terminal-x3 %",
                      "lcb_pass_pct": "LCB pass@1 %", "lcb_truncated": "LCB cut off", "lcb_problems": "LCB problems",
                      "terminal_x3_wall_min": "terminal-x3 min", "lcb_wall_min": "LCB min"},
               {"terminal_x3_pass_pct": True, "lcb_pass_pct": True}),
        "\n\"Cut off\" counts LiveCodeBench answers that hit `max_tokens` (32,768) before finishing. Those score as "
        "failures, so the cap pulls down models that think at length. Strata loaded while VRAM from the previous "
        "model was still in use, so read its numbers with care. [TODO.md](TODO.md) has more caveats.\n",
        "\n## Speed and quick profile\n\n",
        "Server-measured speeds from each model's latest `speed-quick` run (llama.cpp timings), plus a 40-problem "
        "HumanEval+ subset and six terminal tasks.\n\n",
        _bar_chart("Generation speed at 8k context (tok/s)", "tok/s", speed, "tg8k_tok_s"), "\n",
        _table(rows, {"model": "Model", "backend": "Backend", "humaneval_quick_pass_pct": "HumanEval %",
                      "humaneval_quick_plus_pct": "HumanEval+ %", "terminal_quick_pass_pct": "Terminal %",
                      "pp512_tok_s": "Prompt 512 tok/s", "tg512_tok_s": "Gen @512 tok/s",
                      "pp8k_tok_s": "Prompt 8k tok/s", "tg8k_tok_s": "Gen @8k tok/s", "ttft8k_s": "TTFT @8k s"},
               {"humaneval_quick_plus_pct": True, "terminal_quick_pass_pct": True, "pp512_tok_s": True,
                "tg512_tok_s": True, "pp8k_tok_s": True, "tg8k_tok_s": True, "ttft8k_s": False}),
        "\nBold marks the best value in a column. — means the model hasn't run that suite yet.\n",
    ]
    out.write_text("".join(parts))
    return out


def serve(directory: Path, host: str, port: int) -> None:
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(directory))
    with ThreadingHTTPServer((host, port), handler) as httpd:
        print(f"serving {directory} at http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}/"
              "  (Ctrl-C to stop)")
        httpd.serve_forever()
