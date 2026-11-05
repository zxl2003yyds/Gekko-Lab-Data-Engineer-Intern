"""确认零售数据模块可独立执行，不会被 Olist 和数据库阻塞。"""

import sys

import pytest

import run_all
from q1_data_quality import q1_code
from q1_data_quality import investigate
from q3_etl_pipeline import pipeline
from q2_sql_analysis import run_q21, run_q22, run_q23, run_q24


@pytest.mark.parametrize("stage,module,runner", [("q1.1", q1_code, "run_q11"), ("q1.2", investigate, "run_q12"), ("q3", pipeline, "run_pipeline")])
def test_retail_stage_skips_full_inventory(monkeypatch, tmp_path, stage, module, runner):
    calls = []
    monkeypatch.setattr(sys, "argv", ["run_all.py", "--stage", stage, "--data-dir", str(tmp_path)])
    monkeypatch.setattr(run_all, "download_dataset", lambda name, path: calls.append(("download", name)))
    monkeypatch.setattr(module, runner, lambda path: calls.append(("profile", path.name)))

    def unexpected_inventory(*args):
        raise AssertionError("零售数据模块不应读取 Olist 或运行全部数据盘点")

    monkeypatch.setattr(run_all, "inspect_data", unexpected_inventory)
    assert run_all.main() == 0
    assert calls == [("download", "retail"), ("profile", "online_retail_ii.csv")]


@pytest.mark.parametrize("stage,module,runner", [("q2.1", run_q21, "run_q21"), ("q2.2", run_q22, "run_q22"), ("q2.3", run_q23, "run_q23"), ("q2.4", run_q24, "run_q24")])
def test_sql_stage_only_requests_olist(monkeypatch, tmp_path, stage, module, runner):
    calls = []
    monkeypatch.setattr(sys, "argv", ["run_all.py", "--stage", stage, "--data-dir", str(tmp_path)])
    monkeypatch.setattr(run_all, "download_dataset", lambda name, path: calls.append(("download", name)))
    monkeypatch.setattr(module, runner, lambda path: calls.append(("query", path)))
    monkeypatch.setattr(run_all, "inspect_data", lambda *args: pytest.fail("SQL 模块不应读取零售数据"))
    assert run_all.main() == 0
    assert calls == [("download", "olist"), ("query", tmp_path)]


def test_q4_runs_evaluation_without_database(monkeypatch, tmp_path):
    from q4_llm_extraction import extract_reviews, evaluate
    from q4_llm_extraction import build_semantic_review, review_campaign
    calls = []
    monkeypatch.setattr(sys, "argv", ["run_all.py", "--stage", "q4", "--data-dir", str(tmp_path)])
    monkeypatch.setattr(run_all, "download_dataset", lambda name, path: calls.append(name))
    monkeypatch.setattr(extract_reviews, "run_extraction", lambda path: calls.append("extract"))
    monkeypatch.setattr(evaluate, "evaluate", lambda: calls.append("evaluate"))
    monkeypatch.setattr(build_semantic_review, "run_semantic_review", lambda path: calls.append("semantic"))
    monkeypatch.setattr(review_campaign, "prepare_default_campaign", lambda cases: calls.append("review"))
    assert run_all.main() == 0
    assert calls == ["olist", "extract", "evaluate", "semantic", "review"]


def test_document_stage_needs_no_download(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_all.py", "--stage", "q5"])
    monkeypatch.setattr(run_all, "download_dataset", lambda *args: pytest.fail("文档不需要数据下载"))
    assert run_all.main() == 0


def test_all_reports_failure_but_continues_independent_work(monkeypatch, tmp_path):
    import importlib
    from q4_llm_extraction import evaluate
    from q4_llm_extraction import build_semantic_review, review_campaign
    calls = []
    monkeypatch.setattr(sys, "argv", ["run_all.py", "--offline", "--data-dir", str(tmp_path)])
    monkeypatch.setattr(run_all, "inspect_data", lambda *args: {"errors": []})
    for stage, (module, function) in run_all.RUNNERS.items():
        def runner(path, name=stage):
            calls.append(name)
            if name == "q2.1":
                raise ConnectionError("synthetic unavailable database")
        monkeypatch.setattr(importlib.import_module(module), function, runner)
    monkeypatch.setattr(evaluate, "evaluate", lambda: None)
    monkeypatch.setattr(build_semantic_review, "run_semantic_review", lambda path: [])
    monkeypatch.setattr(review_campaign, "prepare_default_campaign", lambda cases: None)
    assert run_all.main() == 1
    assert calls == list(run_all.RUNNERS)
