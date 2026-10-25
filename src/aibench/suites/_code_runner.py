"""Executes one generated solution against its tests. Standalone (stdlib only):
run as `python -I _code_runner.py < task.json`, in a subprocess or container.

Task JSON: program, entry_point, base_test (code; a defined check() gets called
with the candidate), and optionally canonical + inputs for EvalPlus-style
differential testing against the reference solution.
Prints one JSON line: {"base": bool, "plus": bool|null, "error": str|null}
"""

import copy
import json
import math
import os
import sys

# EvalPlus special cases (output compared as sets / only for None-ness).
SET_EQ = {"similar_elements", "find_char_long", "common_in_nested_lists", "extract_singly",
          "larg_nnum", "intersection_array", "find_dissimilar", "Diff"}
NOT_NONE = {"check_str", "text_match_three", "text_starta_endb"}


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def close(exp, got, atol):
    if is_num(exp) and is_num(got) and (isinstance(exp, float) or isinstance(got, float)):
        if math.isnan(exp) and math.isnan(got):
            return True
        return math.isclose(exp, got, rel_tol=1e-7, abs_tol=max(atol, 1e-6))
    if type(exp) is not type(got):
        return False
    if isinstance(exp, (list, tuple)):
        return len(exp) == len(got) and all(close(a, b, atol) for a, b in zip(exp, got))
    if isinstance(exp, dict):
        return exp.keys() == got.keys() and all(close(exp[k], got[k], atol) for k in exp)
    return exp == got


def outputs_match(entry, inp, exp, got, atol):
    if entry == "find_zero":   # any root is fine, not just the reference's
        if close(exp, got, atol):
            return True
        try:
            return abs(sum(c * math.pow(got, i) for i, c in enumerate(inp[0]))) <= max(atol, 1e-6)
        except (TypeError, OverflowError, ValueError):
            return False
    if entry in SET_EQ:
        try:
            return set(exp) == set(got)
        except TypeError:
            return False
    if entry in NOT_NONE:
        return (exp is None) == (got is None)
    return close(exp, got, atol)


def fmt(x, n=200):
    s = repr(x)
    return s if len(s) <= n else s[:n] + "..."


def main():
    task = json.load(sys.stdin)
    out = os.fdopen(os.dup(1), "w")
    sys.stdout = open(os.devnull, "w")   # keep solution prints out of our result
    sys.setrecursionlimit(10000)
    entry = task.get("entry_point")
    result = {"base": False, "plus": None, "error": None}

    def finish():
        out.write(json.dumps(result) + "\n")
        out.flush()

    ns = {"__name__": "__main__" if not entry else "solution"}
    try:
        exec(compile(task["program"], "solution.py", "exec"), ns)
    except BaseException as e:
        result["error"] = f"load: {type(e).__name__}: {e}"
        return finish()
    fn = ns.get(entry) if entry else None
    if entry and not callable(fn):
        result["error"] = f"function {entry!r} not defined"
        return finish()

    if task.get("base_test"):
        tns = dict(ns)
        tns.setdefault("math", math)   # some MBPP assertions use math.isclose without importing it
        try:
            exec(compile(task["base_test"], "test.py", "exec"), tns)
            # HumanEval-style: the test defines check(candidate). Don't confuse it with a solution named check.
            if entry and callable(tns.get("check")) and tns.get("check") is not ns.get("check"):
                tns["check"](fn)
        except BaseException as e:
            result["error"] = f"base: {type(e).__name__}: {fmt(e)}"
            return finish()
    result["base"] = True

    inputs = task.get("inputs")
    if not inputs or not task.get("canonical"):
        return finish()
    ref_ns = {"__name__": "reference"}
    exec(compile(task["canonical"], "reference.py", "exec"), ref_ns)
    ref = ref_ns[entry]
    atol = task.get("atol") or 0
    for inp in inputs:
        try:
            exp = ref(*copy.deepcopy(inp))
        except BaseException:
            continue   # input outside the reference's domain
        try:
            got = fn(*copy.deepcopy(inp))
        except BaseException as e:
            result["plus"] = False
            result["error"] = f"plus: {type(e).__name__} on input {fmt(inp)}"
            return finish()
        if not outputs_match(entry, inp, exp, got, atol):
            result["plus"] = False
            result["error"] = f"plus: wrong output on input {fmt(inp)}: expected {fmt(exp, 80)}, got {fmt(got, 80)}"
            return finish()
    result["plus"] = True
    finish()


if __name__ == "__main__":
    try:
        import resource
        limit = int(os.environ.get("AIBENCH_MEM_LIMIT", 4 * 1024 ** 3))
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, ValueError, OSError):
        pass
    main()
