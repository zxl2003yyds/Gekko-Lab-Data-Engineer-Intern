"""运行数据准备、Q1–Q4 及 Q5/加分题文档检查；不调用外部模型。"""

import argparse
import importlib
import logging
from pathlib import Path

from download_data import ROOT, download_dataset, load_sources
from inspect_data import inspect_data

LOGGER = logging.getLogger(__name__)
RUNNERS = {
    "q1.1": ("q1_data_quality.q1_code", "run_q11"),
    "q1.2": ("q1_data_quality.investigate", "run_q12"),
    "q2.1": ("q2_sql_analysis.run_q21", "run_q21"),
    "q2.2": ("q2_sql_analysis.run_q22", "run_q22"),
    "q2.3": ("q2_sql_analysis.run_q23", "run_q23"),
    "q2.4": ("q2_sql_analysis.run_q24", "run_q24"),
    "q3": ("q3_etl_pipeline.pipeline", "run_pipeline"),
    "q4": ("q4_llm_extraction.extract_reviews", "run_extraction"),
}
RETAIL = {"q1.1", "q1.2", "q3"}
DOCUMENTS = {
    "q1.3": ["q1_data_quality/cleaning_strategy.md"],
    "q5": ["q5_system_design/real_time_pipeline_design.md"],
    "bonus": ["bonus/q6_1_ai_collaboration.md", "bonus/q6_2_business_insights.md"],
}


def check_documents(stage):
    for name in DOCUMENTS[stage]:
        if not (ROOT / name).read_text(encoding="utf-8").strip():
            raise ValueError(f"文档为空：{name}")
    LOGGER.info("%s 文档存在且非空；此检查不代表人工内容验收", stage)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["prepare", *RUNNERS, *DOCUMENTS, "all"], default="all")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--offline", action="store_true", help="不下载数据，只使用本地文件")
    parser.add_argument("--check-db", action="store_true", help="额外验证已启动的 MySQL")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    data_dir = args.data_dir.resolve()
    failed = False
    if not args.offline and args.stage not in DOCUMENTS:
        names = ["retail"] if args.stage in RETAIL else (["olist"] if args.stage in RUNNERS else list(load_sources()))
        for name in names:
            try:
                download_dataset(name, data_dir)
            except Exception as exc:
                LOGGER.error("%s 下载失败：%s", name, exc)
                failed = True
    if args.stage in ("prepare", "all"):
        try:
            report = inspect_data(data_dir, ROOT / ".local" / "data_inventory.json")
            failed |= bool(report["errors"])
        except Exception as exc:
            LOGGER.error("数据盘点失败：%s", exc)
            failed = True
    for stage, (module, function) in RUNNERS.items():
        if args.stage not in (stage, "all"):
            continue
        try:
            argument = data_dir / "online_retail_ii.csv" if stage in RETAIL else data_dir
            getattr(importlib.import_module(module), function)(argument)
            if stage == "q4":
                from q4_llm_extraction.evaluate import evaluate
                evaluate()
                from q4_llm_extraction.build_semantic_review import run_semantic_review
                from q4_llm_extraction.review_campaign import prepare_default_campaign
                prepare_default_campaign(run_semantic_review(data_dir))
        except Exception as exc:
            LOGGER.error("%s 失败：%s", stage, exc)
            failed = True
    for stage in DOCUMENTS:
        if args.stage in (stage, "all"):
            try:
                check_documents(stage)
            except Exception as exc:
                LOGGER.error("%s 失败：%s", stage, exc)
                failed = True
    if args.check_db:
        try:
            from check_database import check_database
            LOGGER.info("MySQL 检查通过：%s", check_database())
        except Exception as exc:
            LOGGER.error("MySQL 检查失败：%s", exc)
            failed = True
    if args.stage in ("q4", "all"):
        LOGGER.warning("Q4 为本地规则基线，复杂语义覆盖及独立人工验收仍有限；退出码仅表示程序执行结果。")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
