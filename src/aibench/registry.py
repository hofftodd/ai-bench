"""Plugin registry for backends and suites.

Built-ins register themselves with the decorators below. Anything else can be
referenced from config either by a registered name (after listing the file or
module under `plugins:`) or directly as "package.module:ClassName".
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

BACKENDS: dict[str, type] = {}
SUITES: dict[str, type] = {}


def backend(name: str):
    def deco(cls):
        cls.type_name = name
        BACKENDS[name] = cls
        return cls
    return deco


def suite(name: str):
    def deco(cls):
        cls.type_name = name
        SUITES[name] = cls
        return cls
    return deco


def _resolve(registry: dict[str, type], kind: str, type_name: str) -> type:
    if ":" in type_name:
        mod_name, attr = type_name.split(":", 1)
        return getattr(importlib.import_module(mod_name), attr)
    try:
        return registry[type_name]
    except KeyError:
        known = ", ".join(sorted(registry)) or "(none)"
        raise ValueError(f"unknown {kind} type {type_name!r}; available: {known}") from None


def resolve_backend(type_name: str) -> type:
    return _resolve(BACKENDS, "backend", type_name)


def resolve_suite(type_name: str) -> type:
    return _resolve(SUITES, "suite", type_name)


def load_builtins() -> None:
    from . import backends, suites  # noqa: F401  (import registers them)


def load_plugins(entries: list[str], base_dir: Path) -> None:
    """Import plugin files (*.py, or a directory of them) or dotted module names."""
    for entry in entries:
        path = (base_dir / Path(entry).expanduser()).resolve()
        if path.is_dir():
            files = sorted(path.glob("*.py"))
        elif path.suffix == ".py":
            files = [path]
        else:
            importlib.import_module(entry)
            continue
        for f in files:
            if f.name.startswith("_"):
                continue
            mod_name = f"aibench_plugin_{f.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, f)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
