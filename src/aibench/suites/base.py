from __future__ import annotations

import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

from ..backends.base import Backend
from ..config import ModelSpec


@dataclass
class Metric:
    value: float | None
    unit: str = ""
    higher_is_better: bool = True
    headline: bool = False      # shown in the cross-suite summary table


@dataclass
class SuiteResult:
    metrics: dict[str, Metric] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    samples: list[dict[str, Any]] = field(default_factory=list)   # written to samples/*.jsonl
    error: str | None = None

    def add(self, key: str, value: float | None, unit: str = "", higher_is_better: bool = True,
            headline: bool = False) -> None:
        self.metrics[key] = Metric(value, unit, higher_is_better, headline)


@dataclass
class RunContext:
    backend: Backend
    model: ModelSpec
    model_info: dict[str, Any]
    out_dir: Path
    console: Console
    limit: int | None = None


class Suite(ABC):
    """A benchmark. Subclass, decorate with @registry.suite("name"), implement run().

    Constructor kwargs are the suite's options from bench.yaml.
    """

    type_name = "base"
    description = ""

    def __init__(self, key: str, **options: Any):
        self.key = key
        self.options = options
        self.base_dir = Path.cwd()   # set to the config's directory; resolve relative paths against it

    @abstractmethod
    async def run(self, ctx: RunContext) -> SuiteResult:
        ...


def median(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None
