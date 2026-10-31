"""Builders for small run.json-shaped dicts, as runner.run_benchmark writes them."""

from __future__ import annotations

import os
from typing import Any

from aibench.runner import boot_id


def metric(value: float, unit: str = "%", headline: bool = True, higher_is_better: bool = True) -> dict[str, Any]:
    return {"value": value, "unit": unit, "higher_is_better": higher_is_better, "headline": headline}


def result(model: str, suite: str, metrics: dict[str, Any] | None = None, details: dict | None = None,
           backend: str = "swap", model_path: str | None = None, error: str | None = None) -> dict[str, Any]:
    res: dict[str, Any] = {"model": model, "model_id": model, "backend": backend, "suite": suite,
                           "metrics": metrics or {}, "details": details or {}, "error": error,
                           "model_info": {"model_path": model_path} if model_path else {}}
    if error:   # a failed suite records no metrics
        del res["metrics"]
    return res


def run(run_id: str, results: list[dict], hardware: str = "r9700-vulkan", tag: str | None = None,
        finished: bool = True, live: bool = False, **extra: Any) -> dict[str, Any]:
    """`live` gives the run this process's pid and boot, so runner.is_alive() sees it as still going."""
    r: dict[str, Any] = {"run_id": run_id, "hardware": hardware, "tag": tag, "started": run_id, "limit": None,
                         "results": results, **extra}
    if finished:
        r["finished"] = run_id + "-end"
    if live:
        r.update(pid=os.getpid(), boot_id=boot_id())
    return r
