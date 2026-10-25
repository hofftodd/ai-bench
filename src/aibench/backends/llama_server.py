"""Managed servers: aibench starts the inference server, benchmarks it, stops it.

`process` runs any engine that serves an OpenAI-compatible API (Strata, vLLM,
SGLang, TabbyAPI, a different llama.cpp build...). `llama-server` is the same
thing with the llama.cpp command line built for you from `gguf:`.

Use these when an engine needs the GPU to itself: `pre:` commands run first
(e.g. tell llama-swap to unload everything), `stop:`/terminate frees the GPU
afterwards so the next model starts clean.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import ModelSpec
from ..registry import backend
from .openai_compat import OpenAIBackend


@backend("process")
class ProcessBackend(OpenAIBackend):
    """Options:
      start: command (string or list). Placeholders: {model_id} {gguf} {port} {host}.
             The model's `args:` are appended.
      stop:  optional command to stop the server (for launchers that daemonize).
      detached: true if `start` returns once the server is up in the background
             (e.g. `strata launch --yes --no-tui`); otherwise the process is the server.
      pre / post: shell commands run before start / after stop.
      health_url: polled until HTTP 200 (default {root}/health, then {base_url}/models).
    """

    def __init__(self, name: str, start: str | list | None = None, stop: str | list | None = None,
                 host: str = "127.0.0.1", port: int = 5899, base_url: str | None = None,
                 health_url: str | None = None, detached: bool = False, pre: list | None = None,
                 post: list | None = None, env: dict | None = None, startup_timeout: float = 900, **options):
        super().__init__(name, base_url=base_url or f"http://{host}:{port}/v1", **options)
        self.start_cmd, self.stop_cmd = start, stop
        self.host, self.port = host, port
        self.health_url = health_url
        self.detached = detached
        self.pre, self.post = pre or [], post or []
        self.env = {k: str(v) for k, v in (env or {}).items()}
        self.startup_timeout = startup_timeout
        self.proc: asyncio.subprocess.Process | None = None
        self.log_path: Path | None = None

    def _fill(self, s: str, model: ModelSpec) -> str:
        return s.format(model_id=model.id, gguf=model.gguf or "", port=self.port, host=self.host)

    def _argv(self, cmd: str | list, model: ModelSpec) -> list[str]:
        parts = shlex.split(cmd) if isinstance(cmd, str) else [str(c) for c in cmd]
        return [os.path.expanduser(self._fill(p, model)) for p in parts]

    def command(self, model: ModelSpec) -> list[str]:
        if not self.start_cmd:
            raise ValueError(f"backend {self.name!r} (process) needs a `start:` command")
        return self._argv(self.start_cmd, model) + model.args

    def _shell(self, cmds: list[str], model: ModelSpec) -> None:
        for c in cmds:
            subprocess.run(self._fill(c, model), shell=True, timeout=300, env={**os.environ, **self.env},
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def _healthy(self) -> bool:
        urls = [self.health_url] if self.health_url else [f"{self.root_url}/health", f"{self.base_url}/models"]
        for u in urls:
            try:
                if (await self.client.get(u, timeout=5)).status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
        return False

    async def prepare(self, model: ModelSpec) -> dict[str, Any]:
        self._shell(self.pre, model)
        if await self._healthy():
            raise RuntimeError(f"something is already serving on {self.base_url}; stop it or change `port:`")
        cmd = self.command(model)
        self.log_path = Path(os.environ.get("TMPDIR", "/tmp")) / f"aibench-{self.name}-{model.key}.log"
        log = open(self.log_path, "wb")
        t0 = time.perf_counter()
        self.proc = await asyncio.create_subprocess_exec(*cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                                         env={**os.environ, **self.env}, start_new_session=True)
        log.close()
        while not await self._healthy():
            if self.proc.returncode not in (None, 0) or (self.proc.returncode == 0 and not self.detached):
                tail = self.log_path.read_text(errors="replace")[-1500:]
                raise RuntimeError(f"{cmd[0]} exited with {self.proc.returncode} (log {self.log_path}):\n{tail}")
            if time.perf_counter() - t0 > self.startup_timeout:
                await self.release(model)
                raise TimeoutError(f"server not healthy after {self.startup_timeout}s (log: {self.log_path})")
            await asyncio.sleep(2)
        info = {"load_s": round(time.perf_counter() - t0, 2), "cmd": shlex.join(cmd)}
        info.update(await super().prepare(model))
        return info

    async def release(self, model: ModelSpec | None) -> None:
        if self.stop_cmd and model is not None:
            subprocess.run(self._argv(self.stop_cmd, model), timeout=120, env={**os.environ, **self.env},
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), 30)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()
        self.proc = None
        if model is not None:
            self._shell(self.post, model)

    async def close(self) -> None:
        if self.proc:
            await self.release(None)
        await super().close()


@backend("llama-server")
class LlamaServerBackend(ProcessBackend):
    """Options: binary (default llama-server), args (common flags), plus everything `process` takes.
    Each model needs `gguf:`; its `args:` are appended."""

    def __init__(self, name: str, binary: str = "llama-server", args: list | None = None, **options):
        super().__init__(name, **options)
        self.binary = os.path.expanduser(binary)
        self.args = [str(a) for a in (args or [])]

    def command(self, model: ModelSpec) -> list[str]:
        if not model.gguf:
            raise ValueError(f"model {model.key!r} needs a `gguf:` path for the llama-server backend")
        return [self.binary, "--host", self.host, "--port", str(self.port), "--model", model.gguf,
                "--alias", model.id, *self.args, *model.args]
