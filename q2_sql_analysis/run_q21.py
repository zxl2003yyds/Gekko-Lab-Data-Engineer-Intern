"""执行 Q2.1 SQL，用独立 CSV 统计核对结果并生成说明。"""

import argparse
from collections import Counter
import csv
import json
import logging
from pathlib import Path
import sys

from sqlalchemy import text

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_database import create_database_engine
from validation import require
from download_data import ROOT
from q1_data_quality.q1_code import table
from q2_sql_analysis.load_olist import load_olist

SQL_PATH = ROOT / "q2_sql_analysis" / "q2_1_translation_gap.sql"


def csv_reference(data_dir: Path) -> tuple[list[dict], int]:
    with (data_dir / "olist" / "product_category_name_translation.csv").open(encoding="utf-8-sig", newline="") as stream:
        translated = {row["product_category_name"] for row in csv.DictReader(stream)
                      if row["product_category_name_english"].strip()}
    gaps = Counter()
    total = 0
    with (data_dir / "olist" / "olist_products_dataset.csv").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            total += 1
            category = row["product_category_name"] or None
            if category is None or not category.strip() or category not in translated:
                gaps[category] += 1
    rows = [{"product_category_name": category, "product_count": count,
             "gap_type": "missing_source_category" if category is None or not category.strip() else "missing_english_translation"}
            for category, count in gaps.items()]
    return sorted(rows, key=lambda row: (-row["product_count"], row["product_category_name"] or "")), total


def run_q21(data_dir: Path = ROOT / "data") -> dict:
    imported = load_olist(data_dir)
    engine = create_database_engine()
    try:
        with engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(text(SQL_PATH.read_text(encoding="utf-8"))).mappings()]
            product_count = connection.execute(text("SELECT COUNT(*) FROM products")).scalar_one()
    finally:
        engine.dispose()
    expected, source_count = csv_reference(data_dir)
    require(rows == expected, "MySQL 查询与独立 CSV 统计不一致")
    require(product_count == source_count, "商品表记录数与源文件不一致")
    missing_source = sum(row["product_count"] for row in rows if row["gap_type"] == "missing_source_category")
    named_gaps = [row for row in rows if row["gap_type"] == "missing_english_translation"]
    gap_count = sum(row["product_count"] for row in rows)
    result = {"mysql_version": imported["database"]["version"], "product_count": product_count,
              "missing_source_products": missing_source, "named_gap_categories": len(named_gaps),
              "named_gap_products": gap_count - missing_source, "translated_products": product_count - gap_count,
              "rows": rows}
    audit = ROOT / ".local" / "q2"
    audit.mkdir(parents=True, exist_ok=True)
    (audit / "q21_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Q2.1 商品类别翻译完整性",
        f'MySQL {result["mysql_version"]} 上实际执行 `q2_1_translation_gap.sql`；结果与独立读取 CSV 的 Counter 统计逐行一致。',
        table(["原始类别", "商品数", "缺失类型"], [[row["product_category_name"] if row["product_category_name"] is not None else "NULL（类别本身缺失）", row["product_count"], row["gap_type"]] for row in rows]),
        f'共 **{product_count:,}** 个商品：**{result["translated_products"]:,}** 个已有英文对照；**{result["named_gap_products"]}** 个属于 **{len(named_gaps)}** 个具名但缺少翻译的类别；另有 **{missing_source}** 个连原始类别都缺失。三组互斥且合计等于全部商品。',
        "## 如何理解这条 SQL",
        "1. 从 products 出发，因为题目问的是实际商品使用了哪些类别。",
        "2. 对每个商品检查翻译表，只有同名类别且英文不是 NULL/空白才算有对照。NOT EXISTS 保留找不到这种对照的商品，也避免重复翻译行放大商品数。",
        "3. 原始类别为 NULL/空白时单列 missing_source_category；其余缺失标记为 missing_english_translation。按原始类别分组后用 COUNT(*) 计商品数。不能用 COUNT(product_category_name)，否则 NULL 组会被计成零。",
        "题目目录提示“3 个未翻译类别”，本次数据确实返回三组，但其中一组是 NULL，不应称为第三个具名类别。缺少类别的商品不能仅靠翻译字典修复。",
        "## 三种处理方案及利弊",
        table(["方案", "具体处理", "优点", "局限"], [
            ["保留缺失并回退展示", "展示时具名类别用原葡文；无类别用“未分类”，源字段仍保留 NULL", "能立即运行、可追溯，不伪造翻译", "展示语言不统一，缺失问题尚未修复"],
            ["人工维护版本化补充字典", "核对两个具名类别的业务含义后添加英文映射，记录来源、审核人与版本", "数量少，审核成本可控，英文命名稳定", "新类别需要持续维护；610 个无类别商品需另行补分类"],
            ["自动生成候选并人工审核", "翻译工具或语言模型生成具名类别的英文候选，审核通过再写补充字典", "适合将来大量新类别，减少重复人工操作", "可能误译或命名不一致，有调用及审核成本；不能从 NULL 推断真实类别"],
        ]),
        "本次建议：原始表保持不变，分析展示可采用第一种回退方式；对两个具名缺口优先人工核实并维护补充字典。610 个无类别商品应向数据源补索商品类别，必要时另做有证据的分类流程。没有自动改写原始类别、执行机器翻译或调用付费 API。",
        "## 复现与验证",
        "```bash\npython run_all.py --stage q2.1 --offline\n# 或\npython -m q2_sql_analysis.run_q21\n```",
        "首次执行将九表导入 MySQL；后续逐值核验并复用。测试还覆盖空英文、重复映射、大小写不同、NULL 类别、只有无效翻译和同时存在有效/无效翻译的情况。",
        "SQL 语义参考：[MySQL EXISTS / NOT EXISTS](https://dev.mysql.com/doc/refman/8.4/en/exists-and-not-exists-subqueries.html)。",
    ]
    (ROOT / "q2_sql_analysis" / "q2_1_findings.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    logging.getLogger(__name__).info("Q2.1 通过：%s 个具名类别缺翻译，%s 个商品缺原始类别", len(named_gaps), missing_source)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run_q21(args.data_dir.resolve())
    except Exception as exc:
        logging.getLogger(__name__).error("Q2.1 未完成：%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
