"""llama-swap proxy in front of llama-server instances.

Adds two things over plain `openai`: the exact upstream command line is recorded
with each result, and `exclusive: true` unloads everything else (including
persistent/resident models) first so the model under test has the GPU to itself.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import ModelSpec
from ..registry import backend
from .openai_compat import OpenAIBackend


@backend("llama-swap")
class LlamaSwapBackend(OpenAIBackend):
    def __init__(self, name: str, base_url: str = "http://localhost:8080/v1", exclusive: bool = False, **options):
        super().__init__(name, base_url=base_url, **options)
        self.exclusive = exclusive

    async def running(self) -> list[dict[str, Any]]:
        try:
            r = await self.client.get(f"{self.root_url}/running", timeout=10)
            return r.json().get("running", []) if r.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            return []

    async def free_gpu(self, model: ModelSpec) -> None:
        if self.exclusive and await self.running():
            await self.client.get(f"{self.root_url}/unload", timeout=120)

    async def prepare(self, model: ModelSpec) -> dict[str, Any]:
        await self.free_gpu(model)
        others = [m["model"] for m in await self.running() if m.get("model") != model.id]
        info = await super().prepare(model)
        if others:
            info["other_models_loaded"] = others
        return info

    async def model_info(self, model: ModelSpec) -> dict[str, Any]:
        info = await self._llamacpp_props(f"{self.root_url}/upstream/{model.id}/props")
        for m in await self.running():
            if m.get("model") == model.id and m.get("cmd"):
                info["cmd"] = m["cmd"]
        return info


@backend("ai-swap")
class AiSwapBackend(LlamaSwapBackend):
    """ai-swap (https://github.com/hofftodd/ai-swap): llama-swap's successor here, a proxy that
    swaps models on demand across several machines. It answers llama-swap's /running, /unload
    and /upstream for this machine's models, so everything above works unchanged. A model it
    keeps loaded by default stays unloaded after `exclusive` unloads it, until something uses
    it again, so the model under test keeps the GPU."""

    async def prepare(self, model: ModelSpec) -> dict[str, Any]:
        # ai-swap forwards a model this machine doesn't serve to a peer. A benchmark has to run
        # here, or its results would be labelled with this machine's hardware.
        try:
            r = await self.client.get(f"{self.root_url}/api/node", timeout=10)
            r.raise_for_status()
            node = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise RuntimeError(f"ai-swap at {self.root_url}: {e}") from e
        local = set()
        for m in node.get("models") or []:
            if m.get("runnable"):
                local |= {m["name"], *(m.get("aliases") or [])}
        if model.id not in local:
            raise RuntimeError(
                f"{model.id} isn't served by this machine's ai-swap ({node.get('name')}); "
                "it would run on another machine. Benchmark it there."
            )
        info = await super().prepare(model)
        info["ai_swap_node"] = node.get("name")
        return info
