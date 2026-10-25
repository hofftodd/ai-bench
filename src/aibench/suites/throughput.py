"""Prefill / decode throughput and time-to-first-token across prompt lengths.

Prompts are synthetic prose sized to a target token count (calibrated against
the model's own tokenizer via usage.prompt_tokens), with a random nonce up front
so no request ever hits the prefix cache.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid

from ..backends.base import GenRequest, GenResult
from ..registry import suite
from .base import RunContext, Suite, SuiteResult, median

WORDS = """the a of and to in is was for on that with as by at from it his an were are which this be or has had
not but have one they their all its been after new more who other when also into only time can some first
two there than these most may over such would year city river system light market water history between
under during people state small large early later music field power region house court village island
station family school north south east west report design model engine signal memory network process
value method result garden forest mountain storm winter summer harbor bridge tower library letter
journey council theory record season engineer captain painter teacher farmer merchant soldier""".split()


def _filler(n_words: int, rng: random.Random) -> str:
    out, count = [], 0
    while count < n_words:
        k = min(rng.randint(8, 18), n_words - count)
        sent = " ".join(rng.choice(WORDS) for _ in range(k))
        out.append(sent[0].upper() + sent[1:] + ".")
        count += k
    return " ".join(out)


def _label(n: int) -> str:
    return f"{n // 1024}k" if n >= 1024 and n % 1024 == 0 else str(n)


@suite("throughput")
class ThroughputSuite(Suite):
    description = "Prefill & decode tok/s and TTFT at several prompt lengths (optionally concurrent)"

    def __init__(self, key, prompt_tokens=(512, 4096, 16384), gen_tokens=256, repeats=3,
                 concurrency=(1,), ignore_eos=True, **options):
        super().__init__(key, **options)
        self.prompt_tokens = sorted(int(x) for x in prompt_tokens)
        self.gen_tokens = int(gen_tokens)
        self.repeats = int(repeats)
        self.concurrency = sorted(int(c) for c in concurrency)
        self.ignore_eos = ignore_eos
        self.rng = random.Random(1234)
        self.estimated_prompt = False

    def _messages(self, n_words: int) -> list[dict]:
        body = f"Session {uuid.uuid4().hex}.\n\nNotes:\n{_filler(n_words, self.rng)}" if n_words else \
            f"Session {uuid.uuid4().hex}."
        return [{"role": "user", "content": body + "\n\nWrite a long, detailed story inspired by the notes above."}]

    async def _gen(self, ctx: RunContext, n_words: int, max_tokens: int) -> GenResult:
        return await ctx.backend.generate(ctx.model, GenRequest(
            messages=self._messages(n_words), max_tokens=max_tokens, temperature=0.7,
            ignore_eos=self.ignore_eos, no_cache=True))

    async def _calibrate(self, ctx: RunContext) -> tuple[float, float]:
        probe = 2000
        a = await self._gen(ctx, 0, 1)
        b = await self._gen(ctx, probe, 1)
        for r in (a, b):
            if r.error:
                raise RuntimeError(f"calibration request failed: {r.error}")
        if not (a.prompt_tokens and b.prompt_tokens):
            self.estimated_prompt = True   # no usage reported: assume ~1.35 tokens/word
            return 40, 1.35
        return a.prompt_tokens, (b.prompt_tokens - a.prompt_tokens) / probe

    async def run(self, ctx: RunContext) -> SuiteResult:
        res = SuiteResult()
        overhead, tok_per_word = await self._calibrate(ctx)
        n_ctx = ctx.model_info.get("n_ctx")
        res.details.update(tokens_per_word=round(tok_per_word, 3), gen_tokens=self.gen_tokens,
                           repeats=self.repeats, points=[])
        first, last = self.prompt_tokens[0], self.prompt_tokens[-1]
        drafted = accepted = 0

        for n in self.prompt_tokens:
            if n_ctx and n + self.gen_tokens > n_ctx:
                ctx.console.print(f"    [yellow]skip {n} tokens: exceeds n_ctx {n_ctx}[/]")
                continue
            n_words = max(0, round((n - overhead) / tok_per_word))
            lab = _label(n)
            for c in self.concurrency:
                runs: list[GenResult] = []
                agg: list[float] = []
                for _ in range(self.repeats):
                    t0 = time.perf_counter()
                    batch = await asyncio.gather(*[self._gen(ctx, n_words, self.gen_tokens) for _ in range(c)])
                    wall = time.perf_counter() - t0
                    if errs := [r.error for r in batch if r.error]:
                        raise RuntimeError(errs[0])
                    for r in batch:
                        r.prompt_tokens = r.prompt_tokens or n   # estimate when the server reports no usage
                    runs.extend(batch)
                    agg.append(sum(r.completion_tokens or 0 for r in batch) / wall)
                pp, tg, ttft = (median([r.prefill_tps for r in runs]), median([r.decode_tps for r in runs]),
                                median([r.ttft_s for r in runs]))
                point = dict(prompt_tokens=median([r.prompt_tokens for r in runs]), concurrency=c,
                             prefill_tps=pp, decode_tps=tg, ttft_s=ttft, aggregate_tps=median(agg))
                res.details["points"].append(point)
                ctx.console.print(f"    {lab:>5} ctx  c={c}: prefill {pp or 0:8.1f} tok/s  decode {tg or 0:6.1f} tok/s"
                                  f"  ttft {ttft or 0:6.2f}s" + (f"  aggregate {median(agg):6.1f} tok/s" if c > 1 else ""))
                if c == 1:
                    res.add(f"pp{lab}", pp, "tok/s", headline=n in (first, last))
                    res.add(f"tg@{lab}", tg, "tok/s", headline=n in (first, last))
                    res.add(f"ttft@{lab}", ttft, "s", higher_is_better=False, headline=(n == last))
                    for r in runs:
                        if r.draft_n:
                            drafted += r.draft_n
                            accepted += r.draft_accepted or 0
                else:
                    res.add(f"agg@{lab} c{c}", median(agg), "tok/s", headline=(n == first and c == self.concurrency[-1]))
        if self.estimated_prompt:
            res.details["warning"] = "server reported no usage; prompt sizes and prefill speeds are estimates"
            ctx.console.print(f"    [yellow]{res.details['warning']}[/]")
        if drafted:
            res.add("draft accept", 100 * accepted / drafted, "%")
        return res
