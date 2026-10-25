"""Compare results across runs: one row per (hardware, backend, model),
columns = each suite's headline metrics (or all metrics with --detail)."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table


@dataclass
class Column:
    suite: str
    metric: str
    unit: str
    higher_is_better: bool

    @property
    def header(self) -> str:
        return f"{self.suite}\n{self.metric}" + (f" ({self.unit})" if self.unit else "")


@dataclass
class Row:
    hardware: str
    backend: str
    model: str
    values: dict[tuple[str, str], float | None] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    runs: set[str] = field(default_factory=set)


def load_runs(paths: list[Path]) -> list[dict[str, Any]]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir() and (p / "run.json").exists():
            files.append(p / "run.json")
        elif p.is_dir():
            files.extend(sorted(p.glob("*/run.json")))
        elif p.exists():
            files.append(p)
    runs = []
    for f in files:
        try:
            runs.append(json.loads(f.read_text()))
        except (OSError, ValueError):
            continue
    return sorted(runs, key=lambda r: r.get("started", ""))


def build(runs: list[dict[str, Any]], models=None, suites=None, hardware=None, tag=None,
          detail=False, keep_all=False) -> tuple[list[Column], list[Row]]:
    columns: dict[tuple[str, str], Column] = {}
    rows: dict[tuple, Row] = {}
    for run in runs:   # oldest first, so later runs overwrite earlier ones
        hw = run.get("hardware", "?")
        if hardware and hw not in hardware or tag and run.get("tag") not in tag:
            continue
        for res in run.get("results", []):
            if models and res["model"] not in models or suites and res["suite"] not in suites:
                continue
            key = (hw, res["backend"], res["model"]) + ((run["run_id"],) if keep_all else ())
            row = rows.setdefault(key, Row(hw, res["backend"], res["model"]))
            row.runs.add(run["run_id"])
            if res.get("error"):
                row.errors[res["suite"]] = res["error"]
                continue
            row.errors.pop(res["suite"], None)
            for name, m in (res.get("metrics") or {}).items():
                if not (detail or m.get("headline")):
                    continue
                ck = (res["suite"], name)
                columns.setdefault(ck, Column(res["suite"], name, m.get("unit", ""), m.get("higher_is_better", True)))
                row.values[ck] = m.get("value")
    return list(columns.values()), list(rows.values())


def _fmt(v: float | None) -> str:
    if v is None:
        return "–"
    if float(v).is_integer() and abs(v) < 1e6:
        return f"{v:.0f}"
    if abs(v) >= 100:
        return f"{v:.0f}"
    if abs(v) >= 10:
        return f"{v:.1f}"
    return f"{v:.2f}"


def _best(cols: list[Column], rows: list[Row]) -> dict[tuple[str, str], float]:
    best = {}
    for c in cols:
        vals = [r.values.get((c.suite, c.metric)) for r in rows]
        vals = [v for v in vals if v is not None]
        if len(vals) > 1:
            best[(c.suite, c.metric)] = max(vals) if c.higher_is_better else min(vals)
    return best


def _cell(r: Row, c: Column, best: dict) -> str:
    ck = (c.suite, c.metric)
    v = r.values.get(ck)
    if v is None and c.suite in r.errors:
        return "[red]err[/]"
    if v is not None and best.get(ck) == v:
        return f"[bold green]{_fmt(v)}[/]"
    return _fmt(v)


def render_table(cols: list[Column], rows: list[Row], console: Console, wide: bool = False) -> None:
    if not rows:
        console.print("[yellow]no results match[/]")
        return
    if not wide:
        _render_tall(cols, rows, console)
    else:
        _render_wide(cols, rows, console)
    for r in rows:
        for s, e in r.errors.items():
            console.print(f"[red]  {r.model} / {s}: {e.splitlines()[0][:160]}[/]")


def _render_tall(cols: list[Column], rows: list[Row], console: Console) -> None:
    """Metrics down the side, one column per model: fits a terminal for a handful of models."""
    multi_hw = len({r.hardware for r in rows}) > 1
    multi_be = len({r.backend for r in rows}) > 1
    t = Table(header_style="bold", show_lines=False)
    t.add_column("suite", style="dim")
    t.add_column("metric")
    for r in rows:
        head = r.model + (f"\n{r.backend}" if multi_be else "") + (f"\n{r.hardware}" if multi_hw else "")
        t.add_column(head, justify="right", style=None, header_style="bold cyan")
    best = _best(cols, rows)
    prev = None
    for c in cols:
        t.add_row(c.suite if c.suite != prev else "", c.metric + (f" [dim]{c.unit}[/]" if c.unit else ""),
                  *[_cell(r, c, best) for r in rows], end_section=False)
        prev = c.suite
    console.print(t)


def _render_wide(cols: list[Column], rows: list[Row], console: Console) -> None:
    t = Table(show_lines=False, header_style="bold")
    multi_hw = len({r.hardware for r in rows}) > 1
    multi_be = len({r.backend for r in rows}) > 1
    if multi_hw:
        t.add_column("hardware")
    if multi_be:
        t.add_column("backend")
    t.add_column("model", style="cyan")
    for c in cols:
        t.add_column(c.header, justify="right")
    best = _best(cols, rows)
    for r in rows:
        cells = ([r.hardware] if multi_hw else []) + ([r.backend] if multi_be else []) + [r.model]
        t.add_row(*cells, *[_cell(r, c, best) for c in cols])
    console.print(t)


def render_text(cols: list[Column], rows: list[Row], fmt: str) -> str:
    head = ["hardware", "backend", "model"] + [c.header.replace("\n", " ") for c in cols]
    body = [[r.hardware, r.backend, r.model] + [_fmt(r.values.get((c.suite, c.metric))) for c in cols] for r in rows]
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(head)
        w.writerows(body)
        return buf.getvalue()
    if fmt == "json":
        return json.dumps([dict(zip(head, b)) for b in body], indent=2)
    best = _best(cols, rows)
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * 3 + "---:|" * len(cols)]
    for r, b in zip(rows, body):
        for i, c in enumerate(cols):
            v = r.values.get((c.suite, c.metric))
            if v is not None and best.get((c.suite, c.metric)) == v:
                b[3 + i] = f"**{b[3 + i]}**"
        lines.append("| " + " | ".join(b) + " |")
    return "\n".join(lines) + "\n"
