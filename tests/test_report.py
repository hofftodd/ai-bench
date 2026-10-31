import json

from aibench import report

from conftest import metric, result, run


def _value(rows, model, suite, name):
    row = next(r for r in rows if r.model == model)
    return row.values.get((suite, name))


def test_later_run_overwrites_earlier():
    runs = [run("20261001-000000", [result("a", "lcb", {"pass@1": metric(50.0)})]),
            run("20261002-000000", [result("a", "lcb", {"pass@1": metric(60.0)})])]
    cols, rows = report.build(runs)
    assert [(c.suite, c.metric) for c in cols] == [("lcb", "pass@1")]
    assert len(rows) == 1 and _value(rows, "a", "lcb", "pass@1") == 60.0
    assert rows[0].runs == {"20261001-000000", "20261002-000000"}


def test_headline_only_unless_detail():
    runs = [run("r1", [result("a", "t", {"pass": metric(90.0), "avg turns": metric(5.5, "", headline=False)})])]
    assert [c.metric for c in report.build(runs)[0]] == ["pass"]
    assert [c.metric for c in report.build(runs, detail=True)[0]] == ["pass", "avg turns"]


def test_error_is_cleared_by_a_later_success():
    runs = [run("r1", [result("a", "lcb", error="load: boom")])]
    _, rows = report.build(runs)
    assert rows[0].errors == {"lcb": "load: boom"}
    runs.append(run("r2", [result("a", "lcb", {"pass@1": metric(70.0)})]))
    _, rows = report.build(runs)
    assert rows[0].errors == {} and _value(rows, "a", "lcb", "pass@1") == 70.0


def test_filters():
    runs = [run("r1", [result("a", "lcb", {"pass@1": metric(1.0)}), result("b", "t", {"pass": metric(2.0)})]),
            run("r2", [result("a", "lcb", {"pass@1": metric(3.0)})], hardware="r9700-rocm", tag="rocm")]
    assert [r.model for r in report.build(runs, models=["b"])[1]] == ["b"]
    assert [c.suite for c in report.build(runs, suites=["t"])[0]] == ["t"]
    _, rows = report.build(runs, hardware=["r9700-rocm"])
    assert [(r.hardware, r.model) for r in rows] == [("r9700-rocm", "a")]
    assert len(report.build(runs, tag=["rocm"])[1]) == 1


def test_keep_all_gives_one_row_per_run():
    runs = [run(f"r{i}", [result("a", "lcb", {"pass@1": metric(float(i))})]) for i in (1, 2)]
    assert len(report.build(runs)[1]) == 1
    assert len(report.build(runs, keep_all=True)[1]) == 2


def test_load_runs_sorts_by_start_and_skips_bad_files(tmp_path):
    for rid in ("20261002-000000", "20261001-000000"):
        (tmp_path / rid).mkdir()
        (tmp_path / rid / "run.json").write_text(json.dumps(run(rid, [])))
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "run.json").write_text("{not json")
    assert [r["run_id"] for r in report.load_runs([tmp_path])] == ["20261001-000000", "20261002-000000"]


def test_fmt():
    assert report._fmt(None) == "–"
    assert report._fmt(80.0) == "80"
    assert report._fmt(123.4) == "123"
    assert report._fmt(56.666) == "56.7"
    assert report._fmt(9.456) == "9.46"
