"""Raw llama.cpp kernel throughput via `llama-bench` on the model's GGUF.

Independent of any server: no HTTP, sampling or scheduling overhead, so it's
the cleanest way to compare GPUs / drivers / llama.cpp builds. Needs `gguf:` on
the model, and the GPU should be otherwise idle (unload served models first).
"""

from __future__ import annotations

import asyncio
import json
import os

from ..registry import suite
from .base import RunContext, Suite, SuiteResult
from .throughput import _label


@suite("llama-bench")
class LlamaBenchSuite(Suite):
    description = "llama-bench pp/tg on the GGUF directly (no server); needs `gguf:` on the model"

    def __init__(self, key, binary="llama-bench", prompt_tokens=(512, 4096), gen_tokens=(128,), depth=(0,),
                 repeats=3, args=(), timeout_s=3600, **options):
        super().__init__(key, **options)
        self.binary = os.path.expanduser(binary)
        self.prompt_tokens = [int(x) for x in prompt_tokens]
        self.gen_tokens = [int(x) for x in gen_tokens]
        self.depth = [int(x) for x in depth]
        self.repeats = int(repeats)
        self.args = [str(a) for a in args]
        self.timeout_s = timeout_s

    async def run(self, ctx: RunContext) -> SuiteResult:
        if not ctx.model.gguf:
            raise RuntimeError(f"model {ctx.model.key!r} has no `gguf:` path")
        cmd = [self.binary, "-m", ctx.model.gguf, "-o", "json", "-r", str(self.repeats),
               "-p", ",".join(map(str, self.prompt_tokens)), "-n", ",".join(map(str, self.gen_tokens)),
               "-d", ",".join(map(str, self.depth)), *self.args]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), self.timeout_s)
        if proc.returncode != 0:
            raise RuntimeError(f"llama-bench failed ({proc.returncode}): {err.decode(errors='replace')[-800:]}")
        rows = json.loads(out.decode()[out.decode().index("["):])
        res = SuiteResult()
        res.details["cmd"] = cmd
        res.details["rows"] = rows
        if rows:
            r0 = rows[0]
            res.details.update({k: r0.get(k) for k in ("build_commit", "backends", "gpu_info", "model_type",
                                                        "model_size", "n_gpu_layers", "flash_attn", "type_k")})
        for r in rows:
            depth = f"@d{_label(r['n_depth'])}" if r.get("n_depth") else ""
            if r.get("n_prompt") and not r.get("n_gen"):
                key = f"pp{_label(r['n_prompt'])}{depth}"
            elif r.get("n_gen") and not r.get("n_prompt"):
                key = f"tg{_label(r['n_gen'])}{depth}"
            else:
                key = f"pp{_label(r['n_prompt'])}+tg{_label(r['n_gen'])}{depth}"
            res.add(key, r.get("avg_ts"), "tok/s", headline=not depth)
            ctx.console.print(f"    {key:>14}: {r.get('avg_ts', 0):8.1f} ± {r.get('stddev_ts', 0):.1f} tok/s")
        return res
