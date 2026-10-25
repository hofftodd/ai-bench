"""OpenAI-compatible chat completions (llama-server, vLLM, SGLang, LM Studio,
TabbyAPI, ollama's /v1, ...). Picks up llama.cpp's per-request `timings` block
when present so prefill/decode speeds are server-measured rather than estimated.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ..config import ModelSpec
from ..registry import backend
from .base import Backend, GenRequest, GenResult


@backend("openai")
class OpenAIBackend(Backend):
    def __init__(self, name: str, base_url: str = "http://localhost:8080/v1", api_key: str | None = None,
                 timeout: float = 1800, extra_body: dict | None = None, send_hints: bool = True, **options):
        super().__init__(name, **options)
        self.base_url = base_url.rstrip("/")
        self.extra_body = extra_body or {}
        # ignore_eos / cache_prompt are understood by llama.cpp and vLLM; turn off for strict servers.
        self.send_hints = send_hints
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(timeout, connect=10))

    @property
    def root_url(self) -> str:
        return self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url

    async def close(self) -> None:
        await self.client.aclose()

    async def list_models(self) -> list[str]:
        r = await self.client.get(f"{self.base_url}/models")
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]

    async def model_info(self, model: ModelSpec) -> dict[str, Any]:
        return await self._llamacpp_props(f"{self.root_url}/props")

    async def _llamacpp_props(self, url: str) -> dict[str, Any]:
        try:
            r = await self.client.get(url, timeout=10)
            if r.status_code != 200:
                return {}
            p = r.json()
        except (httpx.HTTPError, ValueError):
            return {}
        gen = p.get("default_generation_settings") or {}
        return {k: v for k, v in {
            "server": "llama.cpp",
            "build": p.get("build_info"),
            "model_path": p.get("model_path"),
            "n_ctx": gen.get("n_ctx"),
            "slots": p.get("total_slots"),
        }.items() if v is not None}

    async def prepare(self, model: ModelSpec) -> dict[str, Any]:
        # First request may trigger a model load (llama-swap, ollama, LM Studio JIT...).
        t0 = time.perf_counter()
        res = await self.generate(model, GenRequest(messages=[{"role": "user", "content": "Hi"}], max_tokens=1))
        if res.error:
            raise RuntimeError(f"warmup failed: {res.error}")
        info = {"warmup_s": round(time.perf_counter() - t0, 2)}
        info.update(await self.model_info(model))
        return info

    def build_body(self, model: ModelSpec, req: GenRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model.id,
            "messages": req.messages,
            "max_tokens": req.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            **self.sampling_params(model, req),
        }
        if req.tools:
            body["tools"] = req.tools
        if self.send_hints:
            if req.ignore_eos:
                body["ignore_eos"] = True
            if req.no_cache:
                body["cache_prompt"] = False
        body.update(self.extra_body)
        body.update(model.params.get("extra_body", {}))
        body.update(req.extra)
        return body

    async def generate(self, model: ModelSpec, req: GenRequest) -> GenResult:
        res = GenResult()
        text, reasoning = [], []
        chunks = 0
        calls: dict[int, dict[str, Any]] = {}
        t0 = time.perf_counter()
        try:
            async with self.client.stream("POST", f"{self.base_url}/chat/completions",
                                          json=self.build_body(model, req)) as r:
                if r.status_code != 200:
                    body = (await r.aread()).decode(errors="replace")
                    res.error = f"HTTP {r.status_code}: {body[:500]}"
                    return res
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if "error" in chunk:
                        res.error = str(chunk["error"])[:500]
                        break
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        c = delta.get("content")
                        rc = delta.get("reasoning_content") or delta.get("reasoning")
                        tcs = delta.get("tool_calls") or []
                        if (c or rc or tcs) and res.ttft_s is None:
                            res.ttft_s = time.perf_counter() - t0
                        if c or rc or tcs:
                            chunks += 1
                        for tc in tcs:
                            call = calls.setdefault(tc.get("index", len(calls)), {"id": None, "name": "", "arguments": ""})
                            call["id"] = tc.get("id") or call["id"]
                            fn = tc.get("function") or {}
                            call["name"] = call["name"] or fn.get("name") or ""
                            call["arguments"] += fn.get("arguments") or ""
                        if c:
                            text.append(c)
                        if rc:
                            reasoning.append(rc)
                        if choice.get("finish_reason"):
                            res.finish_reason = choice["finish_reason"]
                    if usage := chunk.get("usage"):
                        res.prompt_tokens = usage.get("prompt_tokens")
                        res.completion_tokens = usage.get("completion_tokens")
                        res.cached_tokens = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
                    if timings := chunk.get("timings"):
                        self._apply_llamacpp_timings(res, timings)
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            res.error = f"{type(e).__name__}: {e}"
        res.total_s = time.perf_counter() - t0
        if res.completion_tokens is None and chunks:
            res.completion_tokens = chunks   # server sent no usage; ~1 token per streamed chunk
            res.estimated = True
        res.text = "".join(text)
        res.reasoning = "".join(reasoning)
        res.tool_calls = [{**c, "id": c["id"] or f"call_{i}"} for i, c in sorted(calls.items())]
        return res

    @staticmethod
    def _apply_llamacpp_timings(res: GenResult, t: dict[str, Any]) -> None:
        # Only trust prompt speed when a meaningful number of tokens were processed.
        if t.get("prompt_n", 0) >= 16:
            res.server_prefill_tps = t.get("prompt_per_second")
        if t.get("predicted_n", 0) > 1:
            res.server_decode_tps = t.get("predicted_per_second")
        res.cached_tokens = t.get("cache_n", res.cached_tokens)
        if "draft_n" in t:
            res.draft_n = t.get("draft_n")
            res.draft_accepted = t.get("draft_n_accepted")
