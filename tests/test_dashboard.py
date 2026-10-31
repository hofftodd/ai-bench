import csv

from aibench import dashboard

from conftest import metric, result, run

X3 = {"pass": metric(90.0), "wall": metric(20.0, "min", higher_is_better=False)}
LCB = {"pass@1": metric(60.0), "truncated": metric(9.0, "", higher_is_better=False), "wall": metric(180.0, "min")}


def _rows(runs, **kw):
    return {r["model"]: r for r in dashboard.build_rows(runs, **kw)}


def test_status_and_overnight_order():
    runs = [run("r1", [result("b", "terminal-x3", X3), result("b", "livecodebench", LCB)]),
            run("r2", [result("a", "terminal-x3", X3)]),
            run("r3", [result("c", "speed-quick", {"tg@8k": metric(50.0, "tok/s")})])]
    rows = _rows(runs)
    assert [r["model"] for r in dashboard.build_rows(runs)] == ["b", "a", "c"]   # order run, then the rest
    assert (rows["b"]["overnight_status"], rows["b"]["overnight_order"]) == ("done", 1)
    assert (rows["a"]["overnight_status"], rows["a"]["overnight_order"]) == ("partial", 2)
    assert (rows["c"]["overnight_status"], rows["c"]["overnight_order"]) == ("not run", "")
    assert rows["b"]["lcb_pass_pct"] == "60" and rows["b"]["lcb_truncated"] == "9" and rows["c"]["tg8k_tok_s"] == "50"
    assert rows["c"]["lcb_pass_pct"] == ""


def test_running_model_shows_before_its_first_result():
    runs = [run("r1", [], finished=False, live=True, current={"model": "new", "backend": "swap"})]
    row = _rows(runs)["new"]
    assert (row["overnight_status"], row["backend"]) == ("running", "swap")


def test_running_from_last_result_in_older_runs():
    runs = [run("r1", [result("a", "terminal-x3", X3)], finished=False, live=True)]
    assert _rows(runs)["a"]["overnight_status"] == "running"


def test_dead_or_finished_runs_are_not_running():
    dead = run("r1", [result("a", "terminal-x3", X3)], finished=False, pid=1, boot_id="another-boot")
    done = run("r2", [result("b", "terminal-x3", X3)], live=True)
    rows = _rows([dead, done])
    assert rows["a"]["overnight_status"] == rows["b"]["overnight_status"] == "partial"


def test_limit_runs_and_errors_never_replace_a_score():
    full = run("r1", [result("a", "livecodebench", LCB)])
    smoke = run("r2", [result("a", "livecodebench", {"pass@1": metric(100.0)})], limit=2)
    failed = run("r3", [result("a", "livecodebench", error="load: boom")])
    assert _rows([full, smoke, failed])["a"]["lcb_pass_pct"] == "60"


def test_hardware_filter():
    runs = [run("r1", [result("a", "livecodebench", LCB)]),
            run("r2", [result("a", "livecodebench", {"pass@1": metric(10.0)})], hardware="r9700-rocm")]
    assert _rows(runs, hardware="r9700-vulkan")["a"]["lcb_pass_pct"] == "60"


def _x3(per_task):
    passed = sum(int(v.split("/")[0]) for v in per_task.values())
    return result("a", "terminal-x3", {"pass": metric(100 * passed / 6)}, {"per_task": per_task})


def test_terminal_fix_replaces_the_broken_task_only_when_newer():
    old = _x3({"backup-rotation": "0/3", "csv-summary": "3/3"})
    fix = result("a", dashboard.TERMINAL_FIX, {"pass": metric(100.0)}, {"per_task": {"backup-rotation": "3/3"}})
    row = _rows([run("r1", [old]), run("r2", [fix])])["a"]
    assert (row["terminal_x3_pass_pct"], row["terminal_x3_orig_pct"]) == ("100", "50")
    # a terminal-x3 run after the fix already has the fixed task: keep its own score
    new = _x3({"backup-rotation": "1/3", "csv-summary": "3/3"})
    row = _rows([run("r1", [old]), run("r2", [fix]), run("r3", [new])])["a"]
    assert row["terminal_x3_pass_pct"] == row["terminal_x3_orig_pct"] == "66.7"


def test_quant_from_filename():
    assert dashboard.quant("/m/ThinkingCap-Qwen3.8-27B-UD-Q4_K_XL-local.gguf") == "UD-Q4_K_XL"
    assert dashboard.quant("/m/gemma-4-E4B-it-Q4_K_M.gguf") == "Q4_K_M"
    assert dashboard.quant("/m/gpt-oss-20b-mxfp4.gguf") == "MXFP4"
    assert dashboard.quant(None) == ""
    assert dashboard.quant("/does/not/exist.gguf") == ""   # no name match, header unreadable


def test_write_data_and_markdown(tmp_path):
    runs = [run("r1", [result("a", "terminal-x3", X3, model_path="/m/a-Q4_K_M.gguf"),
                       result("a", "livecodebench", LCB)])]
    rows = dashboard.build_rows(runs)
    out = dashboard.write_data(rows, tmp_path / "data")
    with out.open() as f:
        written = list(csv.DictReader(f))
    assert list(written[0]) == dashboard.COLUMNS
    assert (written[0]["model"], written[0]["quant"], written[0]["terminal_x3_pass_pct"]) == ("a", "Q4_K_M", "90")
    assert (tmp_path / "data" / "meta.json").exists()
    md = dashboard.write_markdown(rows, tmp_path / "RESULTS.md", "r9700-vulkan").read_text()
    assert "Best on terminal-x3: **a** at 90%" in md and "1 of 1 models" in md
