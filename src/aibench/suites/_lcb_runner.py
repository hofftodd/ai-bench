"""Grades one LiveCodeBench solution. Standalone (stdlib only):
run as `python -I _lcb_runner.py < task.json`, in a subprocess or container.

Task JSON: program, tests ([{input, output, testtype: stdin|functional}]),
func_name (functional tests: method of class Solution), test_timeout (s).
stdin tests run the program as its own process per test (so `open(0)`,
`sys.stdin.buffer` etc. behave); functional tests call the method in-process.
Stops at the first failing test, like LCB. Grading follows LCB: stdin output
compared line by line after stripping, falling back to Decimal comparison of
the tokens; functional results compared with ==, tuples as lists.
Prints one JSON line: {"base": bool, "plus": null, "passed": n, "total": n, "error": str|null}
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
from decimal import Decimal, InvalidOperation

# What LiveCodeBench prepends to every solution.
HEADER = """\
from string import *
from re import *
from datetime import *
from collections import *
from heapq import *
from bisect import *
from copy import *
from math import *
from random import *
from statistics import *
from itertools import *
from functools import *
from operator import *
from io import *
from sys import *
from json import *
from builtins import *
from typing import *
import string
import re
import datetime
import collections
import heapq
import bisect
import copy
import math
import random
import statistics
import itertools
import functools
import operator
import io
import sys
import json
sys.setrecursionlimit(50000)
"""


def fmt(s, n=120):
    s = s if isinstance(s, str) else repr(s)
    return s if len(s) <= n else s[:n] + "..."


def lines_match(exp, got):
    a = [l.strip() for l in exp.strip().splitlines()]
    b = [l.strip() for l in got.strip().splitlines()]
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x == y:
            continue
        try:
            xs, ys = [Decimal(t) for t in x.split()], [Decimal(t) for t in y.split()]
        except InvalidOperation:
            return False
        if xs != ys:
            return False
    return True


def run_stdin(program, tests, timeout):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "solution.py")
        with open(path, "w") as f:
            f.write(HEADER + "\n" + program)
        for i, t in enumerate(tests):
            try:
                p = subprocess.run([sys.executable, "-I", path], input=t["input"].encode(), capture_output=True,
                                   timeout=timeout, cwd=d)
            except subprocess.TimeoutExpired:
                return i, f"test {i + 1}: time limit ({timeout:g}s)"
            if p.returncode != 0:
                err = p.stderr.decode(errors="replace").strip().splitlines()
                return i, f"test {i + 1}: runtime error: {fmt(err[-1] if err else f'exit {p.returncode}')}"
            got = p.stdout.decode(errors="replace")
            if not lines_match(t["output"], got):
                return i, f"test {i + 1}: wrong answer: expected {fmt(t['output'].strip())}, got {fmt(got.strip())}"
    return len(tests), None


class Timeout(Exception):
    pass


def _alarm(*_):
    raise Timeout()


def normalize(x):
    if isinstance(x, tuple):
        x = list(x)
    if isinstance(x, list):
        return [normalize(v) for v in x]
    return x


def run_functional(program, tests, func_name, timeout):
    ns = {"__name__": "solution"}
    sys.stdout = open(os.devnull, "w")   # keep solution prints out of our result
    signal.signal(signal.SIGALRM, _alarm)
    try:
        signal.alarm(int(timeout) + 4)
        exec(compile(HEADER + "\n" + program, "solution.py", "exec"), ns)
        signal.alarm(0)
    except BaseException as e:
        signal.alarm(0)
        return 0, f"load: {type(e).__name__}: {fmt(str(e))}"
    if "Solution" not in ns or not hasattr(ns["Solution"], func_name):
        return 0, f"class Solution with method {func_name!r} not defined"
    for i, t in enumerate(tests):
        try:
            args = [json.loads(line) for line in t["input"].split("\n") if line.strip()]
            expected = json.loads(t["output"])
        except ValueError as e:
            return i, f"test {i + 1}: unparseable test case ({e})"
        try:
            signal.setitimer(signal.ITIMER_REAL, timeout)
            got = getattr(ns["Solution"](), func_name)(*args)
            signal.setitimer(signal.ITIMER_REAL, 0)
        except Timeout:
            return i, f"test {i + 1}: time limit ({timeout:g}s)"
        except BaseException as e:
            signal.setitimer(signal.ITIMER_REAL, 0)
            return i, f"test {i + 1}: runtime error: {type(e).__name__}: {fmt(str(e))}"
        if normalize(got) != normalize(expected):
            return i, f"test {i + 1}: wrong answer: expected {fmt(t['output'])}, got {fmt(got)}"
    return len(tests), None


def main():
    task = json.load(sys.stdin)
    out = os.fdopen(os.dup(1), "w")
    tests, timeout = task["tests"], float(task.get("test_timeout") or 6)
    if tests and tests[0].get("testtype") == "functional":
        passed, error = run_functional(task["program"], tests, task.get("func_name"), timeout)
    else:
        passed, error = run_stdin(task["program"], tests, timeout)
    out.write(json.dumps({"base": error is None, "plus": None, "passed": passed, "total": len(tests),
                          "error": error}) + "\n")
    out.flush()


if __name__ == "__main__":
    try:
        import resource
        limit = int(os.environ.get("AIBENCH_MEM_LIMIT", 4 * 1024 ** 3))
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, ValueError, OSError):
        pass
    main()
