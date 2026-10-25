"""aibench command line."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import registry, report
from .config import load_config
from .backends.llama_server import LlamaServerBackend, ProcessBackend
from .runner import make_backend, run_benchmark
from .sysinfo import collect_sysinfo

console = Console()


def _cfg(args):
    cfg = load_config(args.config)
    registry.load_builtins()
    registry.load_plugins(cfg.plugins, cfg.base_dir)
    return cfg


def cmd_run(args):
    cfg = _cfg(args)
    models = args.model or list(cfg.models)
    default = next((p for p in ("default", "quick") if p in cfg.profiles), None)
    suites = cfg.expand_suites(args.suite or ([default] if default else []))
    if not models or not suites:
        sys.exit("nothing to run: pass -m MODEL and -s SUITE (or define models/suites in bench.yaml)")
    for s in suites:   # fail fast on typos before loading any model
        registry.resolve_suite(cfg.suite(s).type)
    out = asyncio.run(run_benchmark(cfg, models, suites, console, limit=args.limit, tag=args.tag,
                                    hardware=args.hardware))
    console.print()
    cols, rows = report.build(report.load_runs([out]))
    report.render_table(cols, rows, console)


def cmd_report(args):
    cfg = _cfg(args)
    paths = [Path(p) for p in args.paths] or [cfg.results_dir]
    runs = report.load_runs(paths)
    if args.last:
        runs = runs[-args.last:]
    cols, rows = report.build(runs, models=args.model, suites=args.suite, hardware=args.hardware, tag=args.tag,
                              detail=args.detail, keep_all=args.all)
    if args.format == "table":
        report.render_table(cols, rows, console, wide=args.wide)
    else:
        text = report.render_text(cols, rows, args.format)
        if args.output:
            Path(args.output).write_text(text)
            console.print(f"wrote {args.output}")
        else:
            print(text, end="")


def cmd_list(args):
    cfg = _cfg(args)
    t = Table(title="backends", header_style="bold")
    for c in ("name", "type", "options"):
        t.add_column(c)
    for name, opts in cfg.backends.items():
        t.add_row(name, opts.get("type", "openai"), ", ".join(f"{k}={v}" for k, v in opts.items() if k != "type"))
    console.print(t)
    t = Table(title="models", header_style="bold")
    for c in ("key", "backend", "id", "gguf"):
        t.add_column(c)
    for m in cfg.models.values():
        t.add_row(m.key, m.backend, m.id, m.gguf or "")
    console.print(t)
    t = Table(title="suites (configured)", header_style="bold")
    for c in ("key", "type", "options"):
        t.add_column(c)
    for s in cfg.suites.values():
        t.add_row(s.key, s.type, ", ".join(f"{k}={v}" for k, v in s.options.items()))
    console.print(t)
    t = Table(title="suite types", header_style="bold")
    t.add_column("type")
    t.add_column("description")
    for name, cls in sorted(registry.SUITES.items()):
        t.add_row(name, cls.description)
    console.print(t)
    console.print("backend types: " + ", ".join(sorted(registry.BACKENDS)))
    if cfg.profiles:
        console.print("profiles: " + "; ".join(f"{k} = {', '.join(v)}" for k, v in cfg.profiles.items()))


def cmd_check(args):
    """Ping each backend and show which configured models it can see."""
    cfg = _cfg(args)

    async def go():
        for name in cfg.backends:
            try:
                be = make_backend(cfg, name)
            except Exception as e:  # noqa: BLE001
                console.print(f"[red]{name}: {e}[/]")
                continue
            if isinstance(be, ProcessBackend):   # only runs during a benchmark; check it's installed
                exe = be.binary if isinstance(be, LlamaServerBackend) else \
                    (shlex.split(be.start_cmd)[0] if isinstance(be.start_cmd, str) else str((be.start_cmd or ["?"])[0]))
                found = shutil.which(os.path.expanduser(exe))
                console.print(f"{'[green]' if found else '[red]'}{name}[/] ({be.type_name}, started on demand): "
                              + (found if found else f"{exe} not found — install it or fix the path"))
                await be.close()
                continue
            try:
                available = await be.list_models()
                console.print(f"[green]{name}[/] ({be.type_name}): {len(available)} models")
                for m in cfg.models.values():
                    if m.backend == name:
                        ok = m.id in available or be.type_name == "llama-server"
                        console.print(f"   {'[green]✓' if ok else '[red]✗'}[/] {m.key} → {m.id}")
            except Exception as e:  # noqa: BLE001
                console.print(f"[red]{name}[/] ({be.type_name}): unreachable — {type(e).__name__}: {e}")
            finally:
                await be.close()

    asyncio.run(go())


def cmd_selftest(args):
    """Check terminal tasks: verify fails untouched and passes with the reference solution."""
    from .suites.terminal import selftest

    cfg = _cfg(args)
    spec = cfg.suite(args.suite)
    s = registry.resolve_suite(spec.type)(spec.key, **spec.options)
    s.base_dir = cfg.base_dir
    tasks = s.tasks()
    if args.task:
        tasks = [t for t in tasks if t.name in args.task]
    console.print(f"self-testing {len(tasks)} tasks from suite {spec.key!r}")
    sys.exit(0 if asyncio.run(selftest(tasks, getattr(s, "image", None), console)) else 1)


def cmd_dashboard(args):
    """Rebuild dashboard/data/ from results/, then optionally serve dashboard/ over HTTP."""
    from . import dashboard

    cfg = _cfg(args)
    root = Path(args.dir) if args.dir else cfg.base_dir / "dashboard"
    hardware = args.hardware or cfg.hardware   # one box/backend per dashboard; ROCm runs carry another label
    runs = report.load_runs([cfg.results_dir])
    rows = dashboard.build_rows(runs, hardware=hardware)
    out = dashboard.write_data(rows, root / "data")
    console.print(f"wrote {out} ({len(rows)} models)")
    other = hardware.replace("-vulkan", "-rocm")   # the *-rocm model twins run under this label
    compare = dashboard.compare_rows(runs, hardware, other) if other != hardware else []
    md = dashboard.write_markdown(rows, cfg.base_dir / "RESULTS.md", hardware, compare, other)
    console.print(f"wrote {md}")
    if args.serve:
        dashboard.serve(root, args.host, args.port)


def cmd_sysinfo(args):
    print(json.dumps(collect_sysinfo(), indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(prog="aibench", description="Benchmark local LLMs: throughput + coding quality")
    p.add_argument("-c", "--config", help="bench.yaml (default: ./bench.yaml if present)")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run suites against models")
    r.add_argument("-m", "--model", action="append", help="model key from config, or a raw model id (repeatable)")
    r.add_argument("-s", "--suite", action="append", help="suite key, suite type, or profile name (repeatable)")
    r.add_argument("-n", "--limit", type=int, help="only the first N problems of each coding suite (quick runs)")
    r.add_argument("--hardware", help="override the hardware label for this run")
    r.add_argument("--tag", help="free-form tag stored with the run")
    r.set_defaults(fn=cmd_run)

    rp = sub.add_parser("report", help="compare stored results")
    rp.add_argument("paths", nargs="*", help="run dirs / run.json files (default: results_dir)")
    rp.add_argument("-m", "--model", action="append")
    rp.add_argument("-s", "--suite", action="append")
    rp.add_argument("--hardware", action="append")
    rp.add_argument("--tag", action="append")
    rp.add_argument("--last", type=int, help="only the N most recent runs")
    rp.add_argument("--detail", action="store_true", help="all metrics, not just headline ones")
    rp.add_argument("--all", action="store_true", help="one entry per run instead of latest per model")
    rp.add_argument("--wide", action="store_true", help="one row per model instead of one column per model")
    rp.add_argument("-f", "--format", choices=["table", "md", "csv", "json"], default="table")
    rp.add_argument("-o", "--output")
    rp.set_defaults(fn=cmd_report)

    d = sub.add_parser("dashboard", help="rebuild the dashboard's data from results/ (and serve it with --serve)")
    d.add_argument("--serve", action="store_true", help="serve the dashboard over HTTP after rebuilding")
    d.add_argument("--host", default="127.0.0.1", help="bind address (0.0.0.0 to reach it from the LAN)")
    d.add_argument("--port", type=int, default=8765)
    d.add_argument("--hardware", help="hardware label to show (default: `hardware:` in bench.yaml)")
    d.add_argument("--dir", help="dashboard directory (default: dashboard/ next to bench.yaml)")
    d.set_defaults(fn=cmd_dashboard)

    sub.add_parser("list", help="show configured backends/models/suites and available plugin types") \
        .set_defaults(fn=cmd_list)
    sub.add_parser("check", help="verify backends are reachable and models exist").set_defaults(fn=cmd_check)
    sub.add_parser("sysinfo", help="print detected hardware").set_defaults(fn=cmd_sysinfo)
    st = sub.add_parser("selftest", help="check terminal tasks with their reference solutions (no model needed)")
    st.add_argument("-s", "--suite", default="terminal", help="a terminal-type suite (default: terminal)")
    st.add_argument("-t", "--task", action="append", help="only these task names")
    st.set_defaults(fn=cmd_selftest)

    args = p.parse_args(argv)
    try:
        args.fn(args)
    except KeyboardInterrupt:
        console.print("[yellow]interrupted — partial results were saved[/]")
        sys.exit(130)
    except ValueError as e:
        sys.exit(f"error: {e}")
