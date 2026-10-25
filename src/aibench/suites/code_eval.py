"""Functional-correctness coding suites: HumanEval+, MBPP+ (EvalPlus data) and
your own JSONL tasks. Generated code runs in a subprocess (rlimits, timeout)
or, with `sandbox: docker`, in a throwaway container with no network.

Scores: `pass@1` = original dataset tests, `plus@1` = also passes EvalPlus's
extended inputs (differential vs. the reference solution). Expect small
deviations from the official EvalPlus harness.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import io
import json
import os
import pickle
import re
import shutil
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from ..backends.base import GenRequest
from ..registry import suite
from .base import RunContext, Suite, SuiteResult, median

CACHE = Path(os.environ.get("AIBENCH_CACHE", Path.home() / ".cache" / "aibench"))
RUNNER = Path(__file__).with_name("_code_runner.py")


@dataclass
class Problem:
    task_id: str
    prompt: str
    entry_point: str | None
    base_test: str | None
    canonical: str | None = None
    inputs: list | None = None
    atol: float = 0.0
    extra: dict | None = None


def download(url: str, name: str) -> Path:
    dest = CACHE / "datasets" / name
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        tmp.rename(dest)
    return dest


def read_jsonl(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as f:
        return [json.loads(line) for line in f if line.strip()]


_FENCE = re.compile(r"```[ \t]*([\w+.-]*)[^\n]*\n(.*?)```", re.S)


def strip_thinking(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.split("</think>", 1)[1] if "</think>" in text else text


def extract_code(text: str, entry_point: str | None) -> str:
    text = strip_thinking(text)
    blocks = [body for lang, body in _FENCE.findall(text) if lang.lower() in ("", "python", "py", "python3")]
    if entry_point:
        for b in reversed(blocks):
            if re.search(rf"def\s+{re.escape(entry_point)}\s*\(", b):
                return b
    if blocks:
        return max(blocks, key=len)
    if m := re.search(r"```(?:python|py)?[^\n]*\n(.*)$", text, re.S):   # unterminated (truncated) fence
        return m.group(1)
    return text


def _inputs(r: dict) -> list:
    return [x for k in ("base_input", "plus_input") if isinstance(r.get(k), list) for x in r[k]]


class CodeSuite(Suite):
    """Base for code suites: subclasses provide problems, prompts and program assembly."""
    runner = RUNNER

    def __init__(self, key, concurrency=None, max_tokens=16384, temperature=0.0, timeout_s=60,
                 sandbox="subprocess", docker_image="python:3.12-slim", system_prompt=None, limit=None,
                 **options):
        super().__init__(key, **options)
        self.concurrency = concurrency
        self.max_tokens = int(max_tokens)
        self.temperature = temperature
        self.timeout_s = float(timeout_s)
        self.sandbox = sandbox
        self.docker_image = docker_image
        self.system_prompt = system_prompt
        self.limit = limit

    def load_problems(self) -> list[Problem]:
        raise NotImplementedError

    def user_prompt(self, p: Problem) -> str:
        raise NotImplementedError

    def program(self, p: Problem, code: str) -> str:
        return code

    def messages(self, p: Problem) -> list[dict]:
        msgs = [{"role": "system", "content": self.system_prompt}] if self.system_prompt else []
        return msgs + [{"role": "user", "content": self.user_prompt(p)}]

    def payload(self, p: Problem, program: str) -> dict[str, Any]:
        """What the runner script gets on stdin."""
        return {"program": program, "entry_point": p.entry_point, "base_test": p.base_test,
                "canonical": p.canonical, "inputs": p.inputs, "atol": p.atol}

    def extract(self, p: Problem, text: str) -> str:
        return extract_code(text, p.entry_point)

    async def execute(self, p: Problem, program: str) -> dict[str, Any]:
        task = json.dumps(self.payload(p, program)).encode()
        if self.sandbox == "docker":
            cmd = ["docker", "run", "--rm", "-i", "--network", "none", "--memory", "2g", "--cpus", "1",
                   "--pids-limit", "256", "-v", f"{self.runner}:/runner.py:ro", self.docker_image,
                   "python", "-I", "/runner.py"]
        else:
            cmd = [sys.executable, "-I", str(self.runner)]
        workdir = CACHE / "sandbox"
        workdir.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE, cwd=workdir,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                    start_new_session=True)
        try:
            out, err = await asyncio.wait_for(proc.communicate(task), self.timeout_s)
        except asyncio.TimeoutError:
            try:
                os.killpg(proc.pid, 9)
            except ProcessLookupError:
                pass
            await proc.wait()
            return {"base": False, "plus": False, "error": f"timeout after {self.timeout_s:.0f}s"}
        try:
            return json.loads(out.decode().strip().splitlines()[-1])
        except (IndexError, ValueError):
            return {"base": False, "plus": False,
                    "error": f"runner crashed (exit {proc.returncode}): {err.decode(errors='replace')[-300:]}"}

    async def run(self, ctx: RunContext) -> SuiteResult:
        if self.sandbox == "docker" and not shutil.which("docker"):
            raise RuntimeError("sandbox: docker requested but docker is not installed")
        problems = self.load_problems()
        limit = ctx.limit or self.limit
        if limit:
            problems = problems[: int(limit)]
        conc = int(self.concurrency or min(4, ctx.model_info.get("slots") or 1))
        max_tokens = ctx.model.max_tokens or self.max_tokens
        sem = asyncio.Semaphore(conc)
        res = SuiteResult()
        rows: list[dict[str, Any]] = []
        t_start = time.perf_counter()

        with Progress(TextColumn("    {task.description}"), BarColumn(), MofNCompleteColumn(),
                      TextColumn("pass {task.fields[passed]}"), TimeElapsedColumn(),
                      console=ctx.console, transient=False) as bar:
            task = bar.add_task(f"{self.key} (x{conc})", total=len(problems), passed=0)
            passed = 0

            async def one(idx: int, p: Problem):
                nonlocal passed
                async with sem:
                    g = await ctx.backend.generate(ctx.model, GenRequest(
                        messages=self.messages(p), max_tokens=max_tokens, temperature=self.temperature))
                if g.error:
                    verdict = {"base": False, "plus": False, "error": f"generation: {g.error}"}
                    code = ""
                else:
                    code = self.extract(p, g.text or g.reasoning)
                    verdict = await self.execute(p, self.program(p, code))
                ok_plus = verdict["base"] and verdict.get("plus") is not False
                passed += ok_plus
                bar.update(task, advance=1, passed=passed)
                rows.append({"idx": idx, "task_id": p.task_id, "base": verdict["base"], "plus": verdict.get("plus"),
                             "error": verdict.get("error"), **self.row_extra(p, verdict), "finish_reason": g.finish_reason,
                             "prompt_tokens": g.prompt_tokens, "completion_tokens": g.completion_tokens,
                             "reasoning_chars": len(g.reasoning), "gen_s": round(g.total_s, 2),
                             "decode_tps": g.decode_tps, "code": code, "response": g.text,
                             "reasoning": g.reasoning})

            await asyncio.gather(*[one(i, p) for i, p in enumerate(problems)])

        rows.sort(key=lambda r: r.pop("idx"))
        res.samples = rows
        n = len(rows)
        has_plus = any(p.inputs for p in problems)
        base = sum(r["base"] for r in rows)
        plus = sum(r["base"] and r["plus"] is not False for r in rows)
        res.add("pass@1", 100 * base / n, "%", headline=True)
        if has_plus:
            res.add("plus@1", 100 * plus / n, "%", headline=True)
        toks = [r["completion_tokens"] for r in rows if r["completion_tokens"]]
        res.add("avg output", sum(toks) / len(toks) if toks else None, "tok", higher_is_better=False)
        res.add("decode", median([r["decode_tps"] for r in rows]), "tok/s")
        res.add("wall", (time.perf_counter() - t_start) / 60, "min", higher_is_better=False, headline=True)
        truncated = sum(r["finish_reason"] == "length" for r in rows)
        res.add("truncated", truncated, "", higher_is_better=False)
        res.details.update(problems=n, concurrency=conc, max_tokens=max_tokens, sandbox=self.sandbox,
                           generation_errors=sum(1 for r in rows if (r["error"] or "").startswith("generation")))
        if truncated:
            ctx.console.print(f"    [yellow]{truncated} responses hit max_tokens={max_tokens}; "
                              f"consider raising max_tokens for this model[/]")
        return res

    def row_extra(self, p: Problem, verdict: dict[str, Any]) -> dict[str, Any]:
        """Extra per-problem fields for the samples file."""
        return {}


@suite("humaneval-plus")
class HumanEvalPlus(CodeSuite):
    description = "HumanEval+ (164 problems): function completion, original + EvalPlus extended tests"
    URL = "https://github.com/evalplus/humanevalplus_release/releases/download/v0.1.10/HumanEvalPlus.jsonl.gz"

    def __init__(self, key, plus=True, dataset_path=None, **options):
        super().__init__(key, **options)
        self.plus = plus
        self.dataset_path = dataset_path

    def load_problems(self) -> list[Problem]:
        path = Path(self.dataset_path).expanduser() if self.dataset_path else download(self.URL, "HumanEvalPlus.jsonl.gz")
        return [Problem(task_id=r["task_id"], prompt=r["prompt"], entry_point=r["entry_point"], base_test=r["test"],
                        canonical=r["prompt"] + r["canonical_solution"] if self.plus else None,
                        inputs=_inputs(r) if self.plus else None, atol=r.get("atol") or 0)
                for r in read_jsonl(path)]

    def user_prompt(self, p: Problem) -> str:
        return ("Complete the following Python function. Reply with the complete function, including its "
                "signature and any imports it needs, in a single ```python code block.\n\n"
                f"```python\n{p.prompt.strip()}\n```")

    def program(self, p: Problem, code: str) -> str:
        if re.search(rf"def\s+{re.escape(p.entry_point)}\s*\(", code):
            # Keep the prompt's imports/helpers; the model's definition overrides the stub.
            return p.prompt + "    pass\n\n" + code
        first = next((l for l in code.splitlines() if l.strip()), "")
        body = code if first[:1] in (" ", "\t") else "\n".join("    " + l for l in code.splitlines())
        return p.prompt + body


@suite("mbpp-plus")
class MbppPlus(CodeSuite):
    description = "MBPP+ (378 problems): write a function from a description, original + extended tests"
    URL = "https://github.com/evalplus/mbppplus_release/releases/download/v0.2.0/MbppPlus.jsonl.gz"

    def __init__(self, key, plus=True, dataset_path=None, **options):
        super().__init__(key, **options)
        self.plus = plus
        self.dataset_path = dataset_path

    def load_problems(self) -> list[Problem]:
        path = Path(self.dataset_path).expanduser() if self.dataset_path else download(self.URL, "MbppPlus.jsonl.gz")
        return [Problem(task_id=r["task_id"], prompt=r["prompt"], entry_point=r["entry_point"],
                        base_test=r["assertion"], canonical=r["canonical_solution"] if self.plus else None,
                        inputs=_inputs(r) if self.plus else None, atol=r.get("atol") or 0)
                for r in read_jsonl(path)]

    def user_prompt(self, p: Problem) -> str:
        desc = p.prompt.strip().strip('"').strip()
        return (f"{desc}\n\nWrite the Python function `{p.entry_point}` described above. Reply with the complete "
                "code, including any imports, in a single ```python code block.")


@suite("code-jsonl")
class CodeJsonl(CodeSuite):
    """Your own tasks. One JSON object per line:
    {"id": "...", "prompt": "...", "entry_point": "fn" (optional), "test": "assert fn(1) == 2\\n..."}
    `test` runs after the solution in the same namespace; a defined check(candidate) is called.
    """
    description = "Custom coding tasks from a JSONL file (prompt + assert-based tests)"

    def __init__(self, key, path, **options):
        super().__init__(key, **options)
        self.path = path

    def load_problems(self) -> list[Problem]:
        return [Problem(task_id=str(r.get("id", i)), prompt=r["prompt"], entry_point=r.get("entry_point"),
                        base_test=r["test"])
                for i, r in enumerate(read_jsonl(self.base_dir / Path(self.path).expanduser()))]

    def user_prompt(self, p: Problem) -> str:
        return p.prompt + "\n\nReply with the complete Python code in a single ```python code block."


class _NoGlobals(pickle.Unpickler):
    """LCB stores private tests as pickled JSON strings; refuse anything but plain data."""

    def find_class(self, module, name):
        raise pickle.UnpicklingError(f"refusing to load {module}.{name}")


@suite("livecodebench")
class LiveCodeBench(CodeSuite):
    """LiveCodeBench code generation (Codeforces-style stdin/stdout from AtCoder, LeetCode-style
    `class Solution`), graded on public + hidden tests. `release` picks the slice: v6 = problems from
    Jan-Apr 2025 (175), v5 = Sep 2024-Jan 2025 (167); a list combines them. Newer problems are less
    likely to be in a model's training data. `sample: {medium: 15, hard: 15}` takes evenly spaced
    problems (by date) per difficulty, so a subset stays the same across runs and models.
    """
    description = "LiveCodeBench: competitive programming (AtCoder/LeetCode) with hidden tests"
    runner = RUNNER.with_name("_lcb_runner.py")
    URL = "https://huggingface.co/datasets/livecodebench/code_generation_lite/resolve/main/{file}"
    SYSTEM = ("You are an expert Python programmer. You will be given a question (problem specification) and will "
              "generate a correct Python program that matches the specification and passes all tests.")

    def __init__(self, key, release="v6", difficulty=None, platform=None, since=None, until=None, sample=None,
                 test_timeout=6, timeout_s=300, system_prompt=SYSTEM, **options):
        super().__init__(key, timeout_s=timeout_s, system_prompt=system_prompt, **options)
        self.releases = [release] if isinstance(release, str) else list(release)
        self.difficulty = [difficulty] if isinstance(difficulty, str) else difficulty
        self.platform = [platform] if isinstance(platform, str) else platform
        self.since, self.until = (str(since) if since else None), (str(until) if until else None)
        self.sample = sample
        self.test_timeout = float(test_timeout)

    def load_problems(self) -> list[Problem]:
        rows = []
        for rel in self.releases:
            n = rel.lstrip("v")
            file = "test.jsonl" if n == "1" else f"test{n}.jsonl"
            rows += read_jsonl(download(self.URL.format(file=file), f"lcb_{file}"))
        rows = [r for r in rows if (not self.difficulty or r["difficulty"] in self.difficulty)
                and (not self.platform or r["platform"] in self.platform)
                and (not self.since or r["contest_date"] >= self.since)
                and (not self.until or r["contest_date"] < self.until)]
        rows.sort(key=lambda r: (r["contest_date"], r["question_id"]))
        if self.sample:
            picked = []
            for level, k in self.sample.items():
                pool = [r for r in rows if r["difficulty"] == level]
                k = min(int(k), len(pool))
                picked += [pool[int(i * len(pool) / k)] for i in range(k)]
            rows = sorted(picked, key=lambda r: (r["contest_date"], r["question_id"]))
        problems = []
        for r in rows:
            private = r["private_test_cases"]
            if isinstance(private, str) and not private.lstrip().startswith("["):
                private = _NoGlobals(io.BytesIO(zlib.decompress(base64.b64decode(private)))).load()
            tests = json.loads(r["public_test_cases"]) + (json.loads(private) if isinstance(private, str) else private)
            meta = json.loads(r["metadata"] or "{}")
            problems.append(Problem(
                task_id=f"{r['platform']}/{r['question_id']}", prompt=r["question_content"],
                entry_point=meta.get("func_name"), base_test=None,
                extra={"tests": tests, "starter": r["starter_code"], "difficulty": r["difficulty"],
                       "platform": r["platform"], "date": r["contest_date"][:10], "title": r["question_title"]}))
        return problems

    def user_prompt(self, p: Problem) -> str:
        if p.extra["starter"]:
            fmt = ("You will use the following starter code to write the solution to the problem and enclose "
                   f"your code within delimiters.\n```python\n{p.extra['starter']}\n```")
        else:
            fmt = ("Read the inputs from stdin solve the problem and write the answer to stdout (do not directly "
                   "test on the sample inputs). Enclose your code within delimiters as follows. Ensure that when "
                   "the python program runs, it answers the question correctly and passes all tests.\n"
                   "```python\n# YOUR CODE HERE\n```")
        return f"### Question:\n{p.prompt}\n\n### Format: {fmt}\n\n### Answer: (use the provided format with backticks)\n\n"

    def extract(self, p: Problem, text: str) -> str:
        blocks = [b for lang, b in _FENCE.findall(strip_thinking(text))
                  if lang.lower() in ("", "python", "py", "python3")]
        if p.entry_point:
            blocks = [b for b in blocks if "class Solution" in b] or blocks
        return blocks[-1] if blocks else extract_code(text, p.entry_point)   # LCB grades the last block

    def payload(self, p: Problem, program: str) -> dict[str, Any]:
        return {"program": program, "tests": p.extra["tests"], "func_name": p.entry_point,
                "test_timeout": self.test_timeout}

    def row_extra(self, p: Problem, verdict: dict[str, Any]) -> dict[str, Any]:
        return {"difficulty": p.extra["difficulty"], "platform": p.extra["platform"], "date": p.extra["date"],
                "tests_passed": verdict.get("passed"), "tests_total": verdict.get("total")}

    async def run(self, ctx: RunContext) -> SuiteResult:
        res = await super().run(ctx)
        for level in ("easy", "medium", "hard"):
            sub = [r for r in res.samples if r["difficulty"] == level]
            if sub:
                res.add(f"pass {level}", 100 * sum(r["base"] for r in sub) / len(sub), "%")
        res.details["releases"] = self.releases
        res.details["dates"] = [min(r["date"] for r in res.samples), max(r["date"] for r in res.samples)]
        return res
