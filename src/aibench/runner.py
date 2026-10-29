"""Runs models x suites, one model at a time, writing results/<run_id>/run.json
incrementally (so a crash or Ctrl-C keeps whatever finished)."""

from __future__ import annotations

import asyncio
import json
import os
import time
import traceback
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from .backends.base import Backend
from .config import Config
from .registry import resolve_backend, resolve_suite
from .suites.base import RunContext
from .sysinfo import GiB, GpuSampler, collect_sysinfo, discover_gpus, primary_gpu_summary, sample_all, select_gpus


def boot_id() -> str | None:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None


def is_alive(run: dict[str, Any]) -> bool:
    """An unfinished run is still going only if its process survives on this boot (not killed, no reboot)."""
    if run.get("finished") or not run.get("pid") or run.get("boot_id") != boot_id():
        return False
    try:
        os.kill(run["pid"], 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def make_backend(cfg: Config, name: str) -> Backend:
    if name not in cfg.backends:
        raise ValueError(f"backend {name!r} not defined; known: {', '.join(cfg.backends)}")
    opts = dict(cfg.backends[name])
    cls = resolve_backend(opts.pop("type", "openai"))
    return cls(name, **opts)


def _vram(gpus) -> dict[str, float]:
    return {gid: s.get("vram", 0) for gid, s in sample_all(gpus).items()}


def _gtt(gpus) -> dict[str, float]:
    """GPU buffers living in system RAM (amdgpu GTT): where the driver parks evicted models."""
    return {gid: s.get("gtt", 0) for gid, s in sample_all(gpus).items()}


async def run_benchmark(cfg: Config, model_keys: list[str], suite_keys: list[str], console: Console,
                        limit: int | None = None, tag: str | None = None, hardware: str | None = None) -> Path:
    gpus = select_gpus(discover_gpus(), cfg.monitor_gpus)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    out_dir = cfg.results_dir / run_id
    (out_dir / "samples").mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "run_id": run_id, "hardware": hardware or cfg.hardware, "tag": tag, "started": datetime.now().isoformat(),
        "config": str(cfg.path) if cfg.path else None, "limit": limit, "sysinfo": collect_sysinfo(), "results": [],
        "pid": os.getpid(), "boot_id": boot_id(),   # lets the dashboard tell a live run from a dead one
    }

    def save():
        (out_dir / "run.json").write_text(json.dumps(record, indent=2, default=str))

    save()
    console.print(f"[bold]run {run_id}[/]  hardware={record['hardware']}  → {out_dir}")
    for g in record["sysinfo"]["gpus"]:
        console.print(f"  gpu {g['id']}: {g['name']} ({g['vram_gib']} GiB)")

    backends: dict[str, Backend] = {}
    try:
        for mkey in model_keys:
            model = cfg.model(mkey)
            if model.backend not in backends:
                backends[model.backend] = make_backend(cfg, model.backend)
            be = backends[model.backend]
            console.rule(f"[bold cyan]{model.key}[/]  ({model.id} via {be.name}/{be.type_name})")

            try:
                await be.free_gpu(model)
            except Exception as e:  # noqa: BLE001
                console.print(f"  [yellow]could not unload other models: {e}[/]")
            before = _vram(gpus)
            for _ in range(20):   # amdgpu's counters lag after an unload; let them settle
                if not before or max(before.values()) < 2 * GiB:
                    break
                await asyncio.sleep(0.5)
                before = _vram(gpus)
            try:
                info = await be.prepare(model)
            except Exception as e:  # noqa: BLE001
                console.print(f"  [red]failed to load model: {e}[/]")
                for skey in suite_keys:
                    record["results"].append({"model": model.key, "model_id": model.id, "backend": be.name,
                                              "backend_type": be.type_name, "suite": skey, "error": f"load: {e}"})
                save()
                continue
            after = _vram(gpus)
            gtt = _gtt(gpus)
            if gtt:
                info["gtt_loaded_gib"] = round(max(gtt.values()) / GiB, 2)
            for gid, g in gtt.items():
                if g > 4 * GiB:
                    console.print(f"  [yellow]⚠ {g / GiB:.1f} GiB of GPU memory sits in system RAM (GTT) on {gid}: "
                                  f"the model spilled out of VRAM, or another model was evicted there[/]")
            if before:
                gid = max(after, key=lambda k: after[k] - before.get(k, 0))
                info["vram_before_gib"] = round(before.get(gid, 0) / GiB, 2)
                info["vram_loaded_gib"] = round(after[gid] / GiB, 2)
                if before.get(gid, 0) > 2 * GiB:
                    console.print(f"  [yellow]⚠ {before[gid] / GiB:.1f} GiB of VRAM was already in use before "
                                  f"loading — another model may be resident and skew results[/]")
            if info.get("other_models_loaded"):
                console.print(f"  [yellow]⚠ also loaded on this backend: {', '.join(info['other_models_loaded'])} "
                              f"(set `exclusive: true` on the llama-swap backend to unload them)[/]")
            console.print("  " + "  ".join(f"{k}={v}" for k, v in info.items() if k not in ("cmd",)))

            for skey in suite_keys:
                spec = cfg.suite(skey)
                entry: dict[str, Any] = {
                    "model": model.key, "model_id": model.id, "backend": be.name, "backend_type": be.type_name,
                    "model_info": info, "model_params": model.params, "suite": spec.key, "suite_type": spec.type,
                    "suite_options": spec.options,
                }
                console.print(f"  [bold]▶ {spec.key}[/] [dim]({spec.type})[/]")
                t0 = time.perf_counter()
                sampler = GpuSampler(gpus)
                try:
                    s = resolve_suite(spec.type)(spec.key, **spec.options)
                    s.base_dir = cfg.base_dir
                    with sampler:
                        result = await s.run(RunContext(backend=be, model=model, model_info=info,
                                                        out_dir=out_dir, console=console, limit=limit))
                    gpu = primary_gpu_summary(sampler.summary())
                    if "peak_vram_gib" in gpu:
                        result.add("peak vram", gpu["peak_vram_gib"], "GiB", higher_is_better=False)
                    if "avg_power_w" in gpu:
                        result.add("avg power", gpu["avg_power_w"], "W", higher_is_better=False)
                        result.add("energy", gpu["energy_kj"], "kJ", higher_is_better=False)
                    entry.update(metrics={k: asdict(m) for k, m in result.metrics.items()}, details=result.details,
                                 gpu=sampler.summary(), error=result.error)
                    if result.samples:
                        f = out_dir / "samples" / f"{model.key}__{spec.key}.jsonl".replace("/", "_")
                        f.write_text("".join(json.dumps(r, default=str) + "\n" for r in result.samples))
                        entry["samples_file"] = str(f.relative_to(out_dir))
                    summary = "  ".join(f"{k}={m.value:.1f}{m.unit}" for k, m in result.metrics.items()
                                        if m.headline and m.value is not None)
                    console.print(f"  [green]✓ {spec.key}[/] {summary}")
                except Exception as e:  # noqa: BLE001
                    entry["error"] = f"{type(e).__name__}: {e}"
                    entry["traceback"] = traceback.format_exc()
                    console.print(f"  [red]✗ {spec.key}: {entry['error']}[/]")
                entry["duration_s"] = round(time.perf_counter() - t0, 1)
                record["results"].append(entry)
                save()
            await be.release(model)
    finally:
        for be in backends.values():
            await be.close()
        record["finished"] = datetime.now().isoformat()
        save()
    return out_dir
