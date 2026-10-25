from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

from ..config import ModelSpec

# Keys in ModelSpec.params that are standard sampling knobs; everything else in
# params["extra_body"] is passed to the server verbatim.
SAMPLING_KEYS = ("temperature", "top_p", "top_k", "min_p", "repeat_penalty",
                 "presence_penalty", "frequency_penalty", "seed")


@dataclass
class GenRequest:
    messages: list[dict[str, Any]]
    max_tokens: int
    temperature: float | None = 0.0
    # Hints a backend may honour if it can (llama.cpp / vLLM do):
    ignore_eos: bool = False      # keep generating to max_tokens (throughput tests)
    no_cache: bool = False        # don't reuse cached prompt prefixes
    tools: list[dict[str, Any]] | None = None   # OpenAI-style function tool definitions
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenResult:
    text: str = ""
    reasoning: str = ""
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    ttft_s: float | None = None
    total_s: float = 0.0
    # Server-measured speeds when the server reports them (llama.cpp, ollama).
    server_prefill_tps: float | None = None
    server_decode_tps: float | None = None
    draft_n: int | None = None
    draft_accepted: int | None = None
    error: str | None = None
    # Native tool calls, normalised to {"id", "name", "arguments" (JSON string)}.
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    estimated: bool = False       # token counts approximated (server reported no usage)

    @property
    def prefill_tps(self) -> float | None:
        if self.server_prefill_tps:
            return self.server_prefill_tps
        if self.prompt_tokens and self.ttft_s:
            return self.prompt_tokens / self.ttft_s
        return None

    @property
    def decode_tps(self) -> float | None:
        if self.server_decode_tps:
            return self.server_decode_tps
        if self.completion_tokens and self.completion_tokens > 1 and self.ttft_s is not None:
            dt = self.total_s - self.ttft_s
            return (self.completion_tokens - 1) / dt if dt > 0 else None
        return None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["prefill_tps"] = self.prefill_tps
        d["decode_tps"] = self.decode_tps
        return d


class Backend(ABC):
    """A model runner. Subclass, decorate with @registry.backend("name"), done.

    Lifecycle per model: prepare() -> generate()* -> release().
    """

    type_name = "base"

    def __init__(self, name: str, **options: Any):
        self.name = name
        self.options = options

    async def prepare(self, model: ModelSpec) -> dict[str, Any]:
        """Make sure the model is loaded and warm. Returns info for the result record."""
        return {}

    async def free_gpu(self, model: ModelSpec) -> None:
        """Called before the pre-load VRAM baseline: unload whatever this backend may hold."""

    async def release(self, model: ModelSpec) -> None:
        """Called after all suites ran for a model (stop a managed server, etc.)."""

    async def close(self) -> None:
        pass

    async def list_models(self) -> list[str]:
        return []

    async def model_info(self, model: ModelSpec) -> dict[str, Any]:
        """Server-reported details (build, context size, slots, weights path...)."""
        return {}

    @abstractmethod
    async def generate(self, model: ModelSpec, req: GenRequest) -> GenResult:
        ...

    @staticmethod
    def sampling_params(model: ModelSpec, req: GenRequest) -> dict[str, Any]:
        """Suite request settings overlaid with the model's recommended sampling."""
        out: dict[str, Any] = {}
        if req.temperature is not None:
            out["temperature"] = req.temperature
        for k in SAMPLING_KEYS:
            if k in model.params:
                out[k] = model.params[k]
        return out
