"""Ollama native API (/api/chat), which reports server-side prompt/eval timings."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ..config import ModelSpec
from ..registry import backend
from .base import Backend, GenRequest, GenResult


@backend("ollama")
class OllamaBackend(Backend):
    def __init__(self, name: str, base_url: str = "http://localhost:11434", timeout: float = 1800,
                 num_ctx: int | None = None, keep_alive: str = "30m", **options):
        super().__init__(name, **options)
        self.base_url = base_url.rstrip("/")
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10))

    async def close(self) -> None:
        await self.client.aclose()

    async def list_models(self) -> list[str]:
        r = await self.client.get(f"{self.base_url}/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    async def model_info(self, model: ModelSpec) -> dict[str, Any]:
        try:
            r = await self.client.post(f"{self.base_url}/api/show", json={"model": model.id})
            d = r.json().get("details", {}) if r.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            return {}
        return {"server": "ollama", **{k: d[k] for k in ("parameter_size", "quantization_level", "family") if k in d}}

    async def prepare(self, model: ModelSpec) -> dict[str, Any]:
        t0 = time.perf_counter()
        r = await self.client.post(f"{self.base_url}/api/generate",
                                   json={"model": model.id, "prompt": "", "keep_alive": self.keep_alive})
        if r.status_code != 200:
            raise RuntimeError(f"ollama load failed: HTTP {r.status_code} {r.text[:300]}")
        return {"load_s": round(time.perf_counter() - t0, 2), **await self.model_info(model)}

    @staticmethod
    def _messages(messages: list[dict]) -> list[dict]:
        """OpenAI-style history -> ollama's (dict tool arguments, tool results by name)."""
        out, names = [], {}
        for m in messages:
            m = dict(m)
            if m.get("tool_calls"):
                calls = []
                for tc in m["tool_calls"]:
                    fn = tc["function"]
                    names[tc.get("id")] = fn["name"]
                    try:
                        args = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                    except ValueError:
                        args = {}
                    calls.append({"function": {"name": fn["name"], "arguments": args}})
                m["tool_calls"] = calls
            if m.get("role") == "tool":
                m = {"role": "tool", "content": m.get("content", ""), "tool_name": names.get(m.get("tool_call_id"), "")}
            out.append(m)
        return out

    async def generate(self, model: ModelSpec, req: GenRequest) -> GenResult:
        opts: dict[str, Any] = {"num_predict": req.max_tokens, **self.sampling_params(model, req)}
        if ctx := model.params.get("num_ctx", self.num_ctx):
            opts["num_ctx"] = ctx
        body = {"model": model.id, "messages": self._messages(req.messages), "stream": True, "options": opts,
                "keep_alive": self.keep_alive, **model.params.get("extra_body", {}), **req.extra}
        if req.tools:
            body["tools"] = req.tools
        res = GenResult()
        text, thinking = [], []
        t0 = time.perf_counter()
        try:
            async with self.client.stream("POST", f"{self.base_url}/api/chat", json=body) as r:
                if r.status_code != 200:
                    res.error = f"HTTP {r.status_code}: {(await r.aread()).decode(errors='replace')[:500]}"
                    return res
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        res.error = str(chunk["error"])[:500]
                        break
                    msg = chunk.get("message") or {}
                    if (msg.get("content") or msg.get("thinking")) and res.ttft_s is None:
                        res.ttft_s = time.perf_counter() - t0
                    for i, tc in enumerate(msg.get("tool_calls") or []):
                        fn = tc.get("function") or {}
                        args = fn.get("arguments")
                        res.tool_calls.append({"id": f"call_{len(res.tool_calls)}", "name": fn.get("name", ""),
                                               "arguments": args if isinstance(args, str) else json.dumps(args)})
                    text.append(msg.get("content") or "")
                    thinking.append(msg.get("thinking") or "")
                    if chunk.get("done"):
                        res.finish_reason = chunk.get("done_reason")
                        res.prompt_tokens = chunk.get("prompt_eval_count")
                        res.completion_tokens = chunk.get("eval_count")
                        if (pd := chunk.get("prompt_eval_duration")) and (res.prompt_tokens or 0) >= 16:
                            res.server_prefill_tps = res.prompt_tokens / (pd / 1e9)
                        if (ed := chunk.get("eval_duration")) and res.completion_tokens:
                            res.server_decode_tps = res.completion_tokens / (ed / 1e9)
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            res.error = f"{type(e).__name__}: {e}"
        res.total_s = time.perf_counter() - t0
        res.text, res.reasoning = "".join(text), "".join(thinking)
        return res
