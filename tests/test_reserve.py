import asyncio

import httpx

from aibench import reserve
from aibench.backends import openai_compat


def test_api_key_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_SWAP_API_KEY", raising=False)
    monkeypatch.setattr(reserve.Path, "home", lambda: tmp_path)
    assert reserve.auth_headers() == {}
    (tmp_path / ".config/ai-swap").mkdir(parents=True)
    (tmp_path / ".config/ai-swap/env").write_text("# rendered\nAI_SWAP_API_KEY='k1'\n")
    assert reserve.auth_headers() == {"Authorization": "Bearer k1"}
    # Exported, so `pre:` shell steps can use $AI_SWAP_API_KEY.
    import os
    assert os.environ["AI_SWAP_API_KEY"] == "k1"


def test_hook_adds_the_key_unless_the_backend_has_its_own(monkeypatch):
    monkeypatch.setenv("AI_SWAP_API_KEY", "k2")
    req = httpx.Request("GET", "http://swap/v1/models")
    asyncio.run(openai_compat._add_reservation(req))
    assert req.headers["authorization"] == "Bearer k2"
    own = httpx.Request("GET", "http://other/v1/models", headers={"Authorization": "Bearer theirs"})
    asyncio.run(openai_compat._add_reservation(own))
    assert own.headers["authorization"] == "Bearer theirs"
