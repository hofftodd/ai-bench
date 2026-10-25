"""Agentic terminal tasks: the model gets `bash` + `write_file` tools inside a
throwaway Docker container and works until it says it's done; a hidden verify
script then decides pass/fail.

Each task is a YAML file (built-ins in terminal_tasks/, add your own with
`tasks_dir:`):

    name: log-error-report
    difficulty: easy            # easy | medium | hard
    instruction: |              # what the model is told
    setup: |                    # bash, runs as root in /work before the agent starts
    verify: |                   # bash, runs as root afterwards; exit 0 = pass
    solution: |                 # reference solution (bash, as the agent) for `aibench selftest`
    max_turns: 30               # optional

Setup can stash expected answers in /root/expected (the agent runs as the
unprivileged user `agent` and can't read it). Verify can call
`python3 /root/check.py lines|json GOT EXPECTED` for tolerant comparisons.

Besides pass rate this records how well the model and server handle tool
calling: malformed calls, tool calls leaked into plain text (usually a chat
template / tool-parser problem in the server), turns and tokens used.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from ..backends.base import GenRequest
from ..registry import suite
from .base import RunContext, Suite, SuiteResult, median

TASKS_DIR = Path(__file__).with_name("terminal_tasks")

DOCKERFILE = """\
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \\
        git jq sqlite3 gcc libc6-dev make procps unzip zip file bc less \\
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 -s /bin/bash agent && mkdir -p /work /root/expected \\
    && chown agent:agent /work && chmod 700 /root \\
    && git config --system user.name agent && git config --system user.email agent@example.com \\
    && git config --system init.defaultBranch main && git config --system safe.directory '*' \\
    && git config --system advice.detachedHead false
WORKDIR /work
"""

CHECK_PY = r'''
import json, sys
def lines(p):
    return [" ".join(l.split()) for l in open(p).read().splitlines() if l.strip()]
def close(a, b, tol):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= tol
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k], tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close(x, y, tol) for x, y in zip(a, b))
    return a == b
mode, got_p, exp_p = sys.argv[1:4]
try:
    if mode == "lines":
        got, exp = lines(got_p), lines(exp_p)
        if "--unordered" in sys.argv:
            got, exp = sorted(got), sorted(exp)
    else:
        got, exp = json.load(open(got_p)), json.load(open(exp_p))
except FileNotFoundError:
    sys.exit(f"{got_p} does not exist")
except ValueError as e:
    sys.exit(f"{got_p} is not valid JSON: {e}")
if not close(got, exp, 0.011):
    sys.exit(f"{got_p} is wrong.\nexpected: {str(exp)[:600]}\ngot:      {str(got)[:600]}")
'''

SYSTEM_TOOLS = """You are an autonomous agent operating a Linux terminal (Debian; bash, coreutils, python3, git, jq, \
sqlite3, gcc, make are installed; there is no internet access). Your working directory is /work.

Use the tools to inspect the environment, carry out the task, and check your work. Each `bash` call runs in a \
fresh shell that starts in /work: `cd` and variables do not carry over between calls. Commands time out after \
{timeout} seconds. Do not ask questions; nobody will answer. When the task is complete, reply with a one-line \
summary and no tool call."""

SYSTEM_TEXT = """You are an autonomous agent operating a Linux terminal (Debian; bash, coreutils, python3, git, jq, \
sqlite3, gcc, make are installed; there is no internet access). Your working directory is /work.

To run a command, reply with exactly one ```bash code block; you will receive its output. Each block runs in a \
fresh shell starting in /work (`cd` and variables do not carry over). Commands time out after {timeout} seconds. \
Write files with heredocs. Do not ask questions; nobody will answer. When the task is complete, reply with a \
one-line summary and no code block."""

TOOLS = [
    {"type": "function", "function": {
        "name": "bash",
        "description": "Run a bash command in /work and return its exit code and combined stdout/stderr.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "The bash command or script to run."}},
            "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or overwrite a text file (parent directories are created).",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path, absolute or relative to /work."},
            "content": {"type": "string", "description": "The complete file content."}},
            "required": ["path", "content"]}}},
]

# Signs that the model tried to call a tool but the server didn't parse it into a tool call.
LEAK = re.compile(r"<tool_call>|<function=|<\|tool_call|\[TOOL_CALLS\]|to=functions\.|"
                  r'"name"\s*:\s*"(bash|write_file)"|^\s*(bash|write_file)\s*\(', re.M)
BASH_BLOCK = re.compile(r"```(?:bash|sh|shell)?[ \t]*\n(.*?)```", re.S)


@dataclass
class Task:
    name: str
    instruction: str
    setup: str
    verify: str
    difficulty: str = "medium"
    solution: str | None = None
    max_turns: int | None = None
    source: str = ""


def load_tasks(dirs: list[Path]) -> list[Task]:
    tasks: dict[str, Task] = {}
    for d in dirs:
        for f in sorted(d.glob("*.yaml")):
            raw = yaml.safe_load(f.read_text())
            t = Task(name=raw.get("name", f.stem), instruction=raw["instruction"].strip(), setup=raw.get("setup", ""),
                     verify=raw["verify"], difficulty=raw.get("difficulty", "medium"), solution=raw.get("solution"),
                     max_turns=raw.get("max_turns"), source=str(f))
            tasks[t.name] = t
    return list(tasks.values())


def truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    head, tail = int(limit * 0.6), int(limit * 0.35)
    return f"{s[:head]}\n... [{len(s) - head - tail} characters omitted] ...\n{s[-tail:]}"


async def _run(*cmd: str, stdin: bytes | None = None, timeout: float = 120) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE if stdin is not None else None,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(stdin), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, f"[timed out after {timeout:.0f}s]"
    return proc.returncode, out.decode(errors="replace")


async def ensure_image(image: str | None, console) -> str:
    if not shutil.which("docker"):
        raise RuntimeError("the terminal suite needs Docker (model commands must not run on the host)")
    if image:
        return image
    tag = "aibench-terminal:" + hashlib.sha256(DOCKERFILE.encode()).hexdigest()[:10]
    rc, _ = await _run("docker", "image", "inspect", tag, timeout=30)
    if rc != 0:
        console.print(f"    building sandbox image {tag} (one time)…")
        rc, out = await _run("docker", "build", "-t", tag, "-", stdin=DOCKERFILE.encode(), timeout=1200)
        if rc != 0:
            raise RuntimeError(f"docker build failed:\n{out[-1500:]}")
    return tag


class Sandbox:
    """One container per task: no network, capped memory/CPU/PIDs, unprivileged `agent` user."""

    def __init__(self, image: str, cmd_timeout: float = 60, memory: str = "2g", cpus: str = "2"):
        self.image, self.cmd_timeout, self.memory, self.cpus = image, cmd_timeout, memory, cpus
        self.name = f"aibench-term-{uuid.uuid4().hex[:10]}"

    async def __aenter__(self):
        rc, out = await _run("docker", "run", "-d", "--rm", "--init", "--network", "none", "--memory", self.memory,
                             "--cpus", self.cpus, "--pids-limit", "512", "--name", self.name, self.image,
                             "sleep", "infinity", timeout=120)
        if rc != 0:
            raise RuntimeError(f"docker run failed: {out[-500:]}")
        return self

    async def __aexit__(self, *exc):
        await _run("docker", "rm", "-f", self.name, timeout=60)

    async def sh(self, script: str, user: str = "agent", timeout: float | None = None) -> tuple[int, str]:
        # bash -c with stdin closed: a command that reads stdin gets EOF instead of hanging.
        t = timeout or self.cmd_timeout
        return await _run("docker", "exec", "-u", user, "-w", "/work", self.name,
                          "timeout", "-k", "5", str(int(t)), "bash", "-c", script, timeout=t + 30)

    async def write(self, path: str, content: str, user: str = "agent") -> tuple[int, str]:
        return await _run("docker", "exec", "-i", "-u", user, "-w", "/work", self.name, "bash", "-c",
                          'mkdir -p "$(dirname "$1")" && cat > "$1"', "_", path, stdin=content.encode(), timeout=60)

    async def prepare(self, task: Task) -> None:
        rc, out = await self.write("/root/check.py", CHECK_PY, user="root")
        if rc == 0:
            rc, out = await self.sh("set -e\n" + task.setup + "\nchown -R agent:agent /work\n", user="root",
                                    timeout=300)
        if rc != 0:
            raise RuntimeError(f"task setup failed ({rc}): {out[-800:]}")

    async def verify(self, task: Task) -> tuple[bool, str]:
        rc, out = await self.sh(task.verify, user="root", timeout=300)
        return rc == 0, out


@dataclass
class Episode:
    turns: int = 0
    tool_calls: int = 0
    invalid_calls: int = 0
    leaked: bool = False
    ended: str = "done"          # done | max_turns | leak | truncated | error
    out_tokens: int = 0
    decode: list[float] = field(default_factory=list)
    transcript: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@suite("terminal")
class TerminalSuite(Suite):
    description = "Agentic terminal tasks: bash/write_file tool calling in a Docker sandbox, verified by hidden checks"

    def __init__(self, key, tasks=None, difficulty=None, tasks_dir=None, builtin=True, limit=None, concurrency=None,
                 max_turns=30, max_tokens=16384, temperature=0.0, cmd_timeout=60, output_limit=6000,
                 tool_mode="native", keep_reasoning=False, image=None, repeats=1, **options):
        super().__init__(key, **options)
        self.task_names = tasks
        self.difficulty = [difficulty] if isinstance(difficulty, str) else difficulty
        self.tasks_dir, self.builtin = tasks_dir, builtin
        self.limit, self.concurrency = limit, concurrency
        self.max_turns, self.max_tokens, self.temperature = int(max_turns), int(max_tokens), temperature
        self.cmd_timeout, self.output_limit = cmd_timeout, int(output_limit)
        if tool_mode not in ("native", "text"):
            raise ValueError("tool_mode must be 'native' (API tool calls) or 'text' (```bash blocks)")
        self.tool_mode, self.keep_reasoning = tool_mode, keep_reasoning
        self.image = image
        self.repeats = int(repeats)   # run every task N times: pass rates over N x tasks episodes

    def tasks(self) -> list[Task]:
        dirs = ([TASKS_DIR] if self.builtin else []) + \
            ([self.base_dir / Path(self.tasks_dir).expanduser()] if self.tasks_dir else [])
        tasks = load_tasks(dirs)
        if self.task_names:
            tasks = [t for t in tasks if t.name in self.task_names]
        if self.difficulty:
            tasks = [t for t in tasks if t.difficulty in self.difficulty]
        return tasks

    async def _tool(self, box: Sandbox, name: str, args: dict[str, Any]) -> str:
        if name == "bash":
            rc, out = await box.sh(str(args["command"]))
            return f"exit code: {rc}\n{truncate(out, self.output_limit)}"
        if name == "write_file":
            path = str(args["path"])
            full = path if path.startswith("/") else f"/work/{path}"   # report what really happened
            rc, out = await box.write(full, str(args["content"]))
            return f"wrote {len(str(args['content']))} characters to {full}" if rc == 0 else f"error: {out[-500:]}"
        raise KeyError(name)

    async def episode(self, ctx: RunContext, box: Sandbox, task: Task) -> Episode:
        ep = Episode()
        system = (SYSTEM_TOOLS if self.tool_mode == "native" else SYSTEM_TEXT).format(timeout=self.cmd_timeout)
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system},
                                      {"role": "user", "content": task.instruction}]
        max_tokens = ctx.model.max_tokens or self.max_tokens
        for _ in range(task.max_turns or self.max_turns):
            g = await ctx.backend.generate(ctx.model, GenRequest(
                messages=msgs, max_tokens=max_tokens, temperature=self.temperature,
                tools=TOOLS if self.tool_mode == "native" else None))
            ep.turns += 1
            ep.out_tokens += g.completion_tokens or 0
            if g.decode_tps:
                ep.decode.append(g.decode_tps)
            if g.error:
                ep.ended, ep.error = "error", g.error
                break
            assistant: dict[str, Any] = {"role": "assistant", "content": g.text or ""}
            if (self.keep_reasoning or ctx.model.params.get("keep_reasoning")) and g.reasoning:
                assistant["reasoning_content"] = g.reasoning
            ep.transcript.append({"role": "assistant", "content": g.text, "reasoning": g.reasoning,
                                  "tool_calls": g.tool_calls, "finish_reason": g.finish_reason})

            if self.tool_mode == "text":
                blocks = BASH_BLOCK.findall(g.text or "")
                msgs.append(assistant)
                if not blocks:
                    ep.ended = "truncated" if g.finish_reason == "length" else "done"
                    break
                ep.tool_calls += 1
                result = await self._tool(box, "bash", {"command": blocks[0]})
                msgs.append({"role": "user", "content": f"Output:\n{result}"})
                ep.transcript.append({"role": "tool", "content": result})
                continue

            if not g.tool_calls:
                msgs.append(assistant)
                if LEAK.search(g.text or ""):
                    ep.leaked, ep.ended = True, "leak"
                elif g.finish_reason == "length":
                    ep.ended = "truncated"
                break
            assistant["tool_calls"] = [{"id": c["id"], "type": "function",
                                        "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                                       for c in g.tool_calls]
            msgs.append(assistant)
            for c in g.tool_calls:
                ep.tool_calls += 1
                try:
                    args = json.loads(c["arguments"] or "{}")
                    if not isinstance(args, dict):
                        raise ValueError("arguments must be a JSON object")
                    result = await self._tool(box, c["name"], args)
                except (ValueError, KeyError, TypeError) as e:
                    ep.invalid_calls += 1
                    known = ", ".join(t["function"]["name"] for t in TOOLS)
                    result = (f"error: unknown tool {c['name']!r} (available: {known})" if isinstance(e, KeyError)
                              and c["name"] not in ("bash", "write_file") else f"error: invalid arguments: {e}")
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": result})
                ep.transcript.append({"role": "tool", "name": c["name"], "content": result})
        else:
            ep.ended = "max_turns"
        return ep

    async def run(self, ctx: RunContext) -> SuiteResult:
        image = await ensure_image(self.image, ctx.console)
        tasks = self.tasks()
        if limit := (ctx.limit or self.limit):
            tasks = tasks[: int(limit)]
        if not tasks:
            raise RuntimeError("no terminal tasks selected")
        conc = int(self.concurrency or min(4, ctx.model_info.get("slots") or 1))
        sem = asyncio.Semaphore(conc)
        rows: list[dict[str, Any]] = []
        t_start = time.perf_counter()
        jobs = [(rep, t) for rep in range(self.repeats) for t in tasks]

        with Progress(TextColumn("    {task.description}"), BarColumn(), MofNCompleteColumn(),
                      TextColumn("pass {task.fields[passed]}"), TimeElapsedColumn(), console=ctx.console) as bar:
            prog = bar.add_task(f"{self.key} (x{conc})", total=len(jobs), passed=0)
            passed = 0

            async def one(idx: int, rep: int, task: Task):
                nonlocal passed
                async with sem:
                    t0 = time.perf_counter()
                    row: dict[str, Any] = {"idx": idx, "task": task.name, "repeat": rep, "difficulty": task.difficulty}
                    try:
                        async with Sandbox(image, self.cmd_timeout) as box:
                            await box.prepare(task)
                            ep = await self.episode(ctx, box, task)
                            ok, vout = await box.verify(task)
                        row.update(passed=ok, verify_output=truncate(vout, 2000), turns=ep.turns,
                                   tool_calls=ep.tool_calls, invalid_calls=ep.invalid_calls, leaked=ep.leaked,
                                   ended=ep.ended, error=ep.error, out_tokens=ep.out_tokens,
                                   decode_tps=median(ep.decode), transcript=ep.transcript)
                    except RuntimeError as e:   # harness problem (docker, setup), not the model's fault
                        row.update(passed=False, ended="harness_error", error=str(e))
                    row["seconds"] = round(time.perf_counter() - t0, 1)
                    passed += bool(row["passed"])
                    bar.update(prog, advance=1, passed=passed)
                    rows.append(row)

            await asyncio.gather(*[one(i, rep, t) for i, (rep, t) in enumerate(jobs)])

        rows.sort(key=lambda r: r.pop("idx"))
        res = SuiteResult()
        harness = [r for r in rows if r["ended"] == "harness_error"]
        scored = [r for r in rows if r["ended"] != "harness_error"]
        for r in harness:
            ctx.console.print(f"    [red]harness error in {r['task']}: {r['error'][:300]}[/]")
        if not scored:
            raise RuntimeError(f"every task failed in the harness: {harness[0]['error'][:300]}")
        n = len(scored)
        res.add("pass", 100 * sum(r["passed"] for r in scored) / n, "%", headline=True)
        if self.repeats > 1:
            # Standard error of the pass rate over episodes; tasks differ in difficulty, so it's a rough guide.
            p = sum(r["passed"] for r in scored) / n
            res.add("pass ±", 100 * (p * (1 - p) / n) ** 0.5, "%", higher_is_better=False)
        for level in ("easy", "medium", "hard"):
            sub = [r for r in scored if r["difficulty"] == level]
            if sub:
                res.add(f"pass {level}", 100 * sum(r["passed"] for r in sub) / len(sub), "%")
        calls = sum(r["tool_calls"] for r in scored)
        res.add("avg turns", sum(r["turns"] for r in scored) / n, "", higher_is_better=False)
        res.add("bad calls", 100 * sum(r["invalid_calls"] for r in scored) / calls if calls else 0, "%",
                higher_is_better=False, headline=True)
        res.add("leaked calls", sum(r["leaked"] for r in scored), "", higher_is_better=False)
        res.add("hit max turns", sum(r["ended"] == "max_turns" for r in scored), "", higher_is_better=False)
        res.add("avg output", sum(r["out_tokens"] for r in scored) / n, "tok", higher_is_better=False)
        res.add("decode", median([r["decode_tps"] for r in scored]), "tok/s")
        res.add("wall", (time.perf_counter() - t_start) / 60, "min", higher_is_better=False, headline=True)
        res.details["per_task"] = {t.name: f"{sum(r['passed'] for r in scored if r['task'] == t.name)}/"
                                           f"{sum(r['task'] == t.name for r in scored)}" for t in tasks}
        res.details.update(tasks=len(tasks), repeats=self.repeats, episodes=len(rows), scored=n, harness_errors=len(harness), concurrency=conc,
                           tool_mode=self.tool_mode, image=image,
                           ended={k: sum(r["ended"] == k for r in rows) for k in {r["ended"] for r in rows}})
        if leaked := sum(r["leaked"] for r in scored):
            ctx.console.print(f"    [yellow]{leaked} task(s) ended with a tool call written as plain text — the "
                              f"server's tool-call parsing may not support this model (try tool_mode: text)[/]")
        res.samples = rows
        return res


async def selftest(tasks: list[Task], image: str | None, console, concurrency: int = 6) -> bool:
    """For each task: verify must fail on the untouched setup and pass after the reference solution."""
    image = await ensure_image(image, console)
    sem = asyncio.Semaphore(concurrency)
    ok_all = True

    async def one(task: Task):
        nonlocal ok_all
        async with sem:
            problems = []
            try:
                async with Sandbox(image) as box:
                    await box.prepare(task)
                    passed, out = await box.verify(task)
                    if passed:
                        problems.append("verify passes before anything was done")
                    if not task.solution:
                        problems.append("no reference solution")
                    else:
                        rc, sout = await box.sh(task.solution, timeout=120)
                        passed, out = await box.verify(task)
                        if not passed:
                            problems.append(f"reference solution fails verify (solution exit {rc}):\n"
                                            f"{truncate(sout, 600)}\n--- verify:\n{truncate(out, 800)}")
            except RuntimeError as e:
                problems.append(str(e))
        if problems:
            ok_all = False
            console.print(f"[red]✗ {task.name}[/]\n  " + "\n  ".join(problems))
        else:
            console.print(f"[green]✓ {task.name}[/] [dim]({task.difficulty})[/]")

    await asyncio.gather(*[one(t) for t in tasks])
    return ok_all
