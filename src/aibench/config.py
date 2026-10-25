"""bench.yaml loading.

Models and suites not defined in the config can still be used ad hoc: an
unknown model key is treated as a model id on `default_backend`, and an unknown
suite key is treated as a suite type with default options.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ModelSpec:
    key: str                      # name used on the CLI and in reports
    backend: str                  # backend key
    id: str                       # id the backend knows the model by
    gguf: str | None = None       # local weights path (llama-server / llama-bench)
    args: list[str] = field(default_factory=list)   # extra server args (managed backends)
    params: dict[str, Any] = field(default_factory=dict)  # sampling params + extra_body
    max_tokens: int | None = None  # overrides code-suite max_tokens (reasoning models need room)
    notes: str = ""


@dataclass
class SuiteSpec:
    key: str
    type: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    path: Path | None
    hardware: str
    results_dir: Path
    default_backend: str
    backends: dict[str, dict[str, Any]]
    models: dict[str, ModelSpec]
    suites: dict[str, SuiteSpec]
    profiles: dict[str, list[str]]
    plugins: list[str]
    monitor_gpus: str | list[str]

    @property
    def base_dir(self) -> Path:
        return self.path.parent if self.path else Path.cwd()

    def model(self, key: str) -> ModelSpec:
        if key in self.models:
            return self.models[key]
        return ModelSpec(key=key, backend=self.default_backend, id=key)

    def suite(self, key: str) -> SuiteSpec:
        if key in self.suites:
            return self.suites[key]
        return SuiteSpec(key=key, type=key)

    def expand_suites(self, keys: list[str]) -> list[str]:
        out: list[str] = []
        for k in keys:
            out.extend(self.profiles.get(k, [k]))
        return out


def _expand(p: str | None) -> str | None:
    return os.path.expanduser(os.path.expandvars(p)) if p else p


DEFAULT_BACKENDS = {"local": {"type": "openai", "base_url": "http://localhost:8080/v1"}}


def load_config(path: str | Path | None) -> Config:
    raw: dict[str, Any] = {}
    cfg_path: Path | None = None
    if path:
        cfg_path = Path(path).expanduser().resolve()
        raw = yaml.safe_load(cfg_path.read_text()) or {}
    elif Path("bench.yaml").exists():
        cfg_path = Path("bench.yaml").resolve()
        raw = yaml.safe_load(cfg_path.read_text()) or {}

    base = cfg_path.parent if cfg_path else Path.cwd()
    backends = raw.get("backends") or DEFAULT_BACKENDS
    default_backend = raw.get("default_backend") or next(iter(backends))

    models: dict[str, ModelSpec] = {}
    for key, m in (raw.get("models") or {}).items():
        m = m or {}
        models[key] = ModelSpec(
            key=key,
            backend=m.get("backend", default_backend),
            id=m.get("id", key),
            gguf=_expand(m.get("gguf")),
            args=[_expand(str(a)) for a in m.get("args", [])],
            params=m.get("params") or {},
            max_tokens=m.get("max_tokens"),
            notes=m.get("notes", ""),
        )

    suites: dict[str, SuiteSpec] = {}
    for key, s in (raw.get("suites") or {}).items():
        s = dict(s or {})
        suites[key] = SuiteSpec(key=key, type=s.pop("type", key), options=s)

    results_dir = Path(_expand(raw.get("results_dir", "results")))
    if not results_dir.is_absolute():
        results_dir = base / results_dir

    return Config(
        path=cfg_path,
        hardware=raw.get("hardware", "unlabeled"),
        results_dir=results_dir,
        default_backend=default_backend,
        backends=backends,
        models=models,
        suites=suites,
        profiles=raw.get("profiles") or {},
        plugins=raw.get("plugins") or [],
        monitor_gpus=raw.get("monitor_gpus", "auto"),
    )
