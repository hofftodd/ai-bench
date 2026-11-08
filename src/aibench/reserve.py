"""Reserve this machine's ai-swap for the length of a benchmark run.

ai-swap (https://github.com/hofftodd/ai-swap) serves models to agents on several machines. While
a run holds its reservation, that machine's ai-swap serves only requests carrying the run's
token: nobody else can load a model or add load that would skew the numbers, and they're told
the machine is reserved and to retry. With `unload: true` everything ai-swap has loaded is
unloaded first, so a run that starts its own engines (the Mac config) gets the memory. The
reservation is renewed in the background and released at the end, even on errors or Ctrl-C;
if aibench dies, it lapses after `ttl` seconds. Releasing it brings back ai-swap's resident
models.

Config (top level):
    reserve:
      url: http://localhost:8080   # this machine's ai-swap
      unload: true                 # free its models first (default true)
      ttl: 300                     # seconds without renewal before it lapses
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
from typing import Any

import httpx

HEADER = "X-AI-Swap-Lock"
_token: str | None = None


def token_headers() -> dict[str, str]:
    """Headers every request to ai-swap should carry during a reserved run."""
    return {HEADER: _token} if _token else {}


class Reservation:
    def __init__(self, spec: dict[str, Any] | str, reason: str, console: Any = None):
        spec = {"url": spec} if isinstance(spec, str) else dict(spec)
        self.url = str(spec.get("url", "http://localhost:8080")).rstrip("/")
        self.unload = bool(spec.get("unload", True))
        self.ttl = int(spec.get("ttl", 300))
        self.reason = reason
        self.console = console
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5))
        self._renew: asyncio.Task[None] | None = None

    def _say(self, msg: str) -> None:
        if self.console is not None:
            self.console.print(msg)

    async def __aenter__(self) -> Reservation:
        global _token
        body = {"owner": f"ai-bench@{socket.gethostname().split('.')[0]}", "reason": self.reason,
                "ttl_seconds": self.ttl}
        try:
            r = await self.client.post(f"{self.url}/api/lock", json=body)
        except httpx.HTTPError as e:
            self._say(f"  [yellow]no ai-swap at {self.url} ({type(e).__name__}); running unreserved[/]")
            return self
        if r.status_code == 409:
            held = r.json().get("lock") or {}
            await self.client.aclose()
            raise RuntimeError(f"this machine is already reserved by {held.get('owner')} "
                               f"({held.get('reason') or 'no reason given'}); not starting")
        if r.status_code == 404:
            self._say(f"  [yellow]ai-swap at {self.url} has no reservations (too old?); running unreserved[/]")
            return self
        r.raise_for_status()
        _token = r.json()["token"]
        os.environ["AI_SWAP_LOCK"] = _token  # for `pre:` shell steps: curl -H "X-AI-Swap-Lock: $AI_SWAP_LOCK"
        self._say(f"  reserved ai-swap at {self.url} for this run")
        if self.unload:
            u = await self.client.post(f"{self.url}/api/unload", headers=token_headers())
            if u.status_code != 200:
                self._say(f"  [yellow]couldn't unload ai-swap's models: {u.status_code} {u.text[:200]}[/]")
        self._renew = asyncio.create_task(self._keep())
        return self

    async def _keep(self) -> None:
        while True:
            await asyncio.sleep(max(5, self.ttl // 3))
            with contextlib.suppress(httpx.HTTPError):
                await self.client.post(f"{self.url}/api/lock", json={}, headers=token_headers())

    async def __aexit__(self, *exc: object) -> None:
        global _token
        if self._renew is not None:
            self._renew.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._renew
        if _token:
            with contextlib.suppress(httpx.HTTPError):
                await self.client.delete(f"{self.url}/api/lock", headers=token_headers())
            self._say(f"  released ai-swap at {self.url}")
        _token = None
        os.environ.pop("AI_SWAP_LOCK", None)
        await self.client.aclose()
