"""Q2.3 卖家指标：真实 SQL 与独立逐订单计算对账。"""

import argparse
from collections import defaultdict
import csv
from datetime import datetime
from decimal import Decimal
import json
import logging
from pathlib import Path
import sys
from time import perf_counter

from sqlalchemy import text

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_database import create_database_engine
from validation import require
from download_data import ROOT
from q1_data_quality.q1_code import table
from q2_sql_analysis.load_olist import load_olist
from q2_sql_analysis.run_q22 import decimal_json, rounded

SQL_PATH = ROOT / "q2_sql_analysis" / "q2_3_top_sellers.sql"
COLUMNS = ["seller_id", "seller_state", "gmv_2017", "order_count", "unique_customers", "avg_review_score", "late_delivery_rate", "cancel_rate", "state_rank"]


def read_csv(data_dir, name):
    with (data_dir / "olist" / f"olist_{name}_dataset.csv").open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def calculate_reference(orders, items, reviews, customers, sellers):
    orders = {r["order_id"]: r for r in orders}
    customers = {r["customer_id"]: r["customer_unique_id"] for r in customers}
    states = {r["seller_id"]: r["seller_state"] for r in sellers}
    latest = {}
    for source_row, row in enumerate(reviews, 1):
        key = (row["review_answer_timestamp"], row["review_creation_date"], row["review_id"], source_row)
        if row["order_id"] not in latest or key > latest[row["order_id"]][0]:
            latest[row["order_id"]] = (key, int(row["review_score"]))
    pairs = defaultdict(lambda: Decimal(0))
    for row in items:
        if not row["price"] or not row["freight_value"]:
            raise ValueError("卖家明细金额不完整，不能发布部分 GMV")
        pairs[(row["seller_id"], row["order_id"])] += Decimal(row["price"]) + Decimal(row["freight_value"])
    stats = {}
    for (seller_id, order_id), amount in pairs.items():
        if order_id not in orders:
            raise ValueError("商品明细找不到订单")
        order = orders[order_id]
        if not "2017-01-01" <= order["order_purchase_timestamp"] < "2018-01-01":
            continue
        if seller_id not in states or order["customer_id"] not in customers:
            raise ValueError("卖家或客户维度缺失，需先核查")
        s = stats.setdefault(seller_id, {"seller_id": seller_id, "seller_state": states[seller_id],
            "gmv_2017": Decimal(0), "order_count": 0, "customers": set(), "scores": [],
            "late": 0, "eligible_late": 0, "canceled": 0})
        s["order_count"] += 1
        s["customers"].add(customers[order["customer_id"]])
        s["canceled"] += order["order_status"] == "canceled"
        if order_id in latest:
            s["scores"].append(latest[order_id][1])
        if order["order_status"] == "delivered":
            s["gmv_2017"] += amount
            actual, estimate = order["order_delivered_customer_date"], order["order_estimated_delivery_date"]
            if actual and estimate:
                s["eligible_late"] += 1
                s["late"] += datetime.fromisoformat(actual) > datetime.fromisoformat(estimate)
    result = []
    for s in stats.values():
        result.append({key: s[key] for key in ["seller_id", "seller_state", "gmv_2017", "order_count"]} | {
            "unique_customers": len(s["customers"]),
            "avg_review_score": rounded(Decimal(sum(s["scores"])) / len(s["scores"])) if s["scores"] else None,
            "late_delivery_rate": rounded(Decimal(100) * s["late"] / s["eligible_late"]) if s["eligible_late"] else None,
            "cancel_rate": rounded(Decimal(100) * s["canceled"] / s["order_count"]),
        })
    for row in result:
        row["state_rank"] = 1 + sum(other["seller_state"] == row["seller_state"] and other["gmv_2017"] > row["gmv_2017"] for other in result)
    result.sort(key=lambda row: (-row["gmv_2017"], row["seller_id"]))
    return result[:20], {"seller_count": len(result), "all_seller_gmv": sum((r["gmv_2017"] for r in result), Decimal(0)),
                        "seller_order_pairs": sum(s["order_count"] for s in stats.values()),
                        "late_denominators": {s["seller_id"]: s["eligible_late"] for s in stats.values()}}


def run_q23(data_dir=ROOT / "data"):
    imported = load_olist(data_dir)
    expected, audit = calculate_reference(*(read_csv(data_dir, name) for name in ["orders", "order_items", "order_reviews", "customers", "sellers"]))
    engine = create_database_engine()
    try:
        with engine.connect() as connection:
            started = perf_counter()
            actual = [dict(row) for row in connection.execute(text(SQL_PATH.read_text())).mappings()]
            seconds = perf_counter() - started
    finally:
        engine.dispose()
    require(actual == expected, "卖家 SQL 与独立计算不一致")
    require(len(actual) == min(20, audit["seller_count"]), 'run_q23: len(actual) == min(20, audit["seller_count"])')
    out = ROOT / "q2_sql_analysis"
    (out / "q2_3_results.json").write_text(json.dumps(actual, indent=2, default=decimal_json) + "\n")
    (ROOT / ".local/q2/q23_diagnostics.json").write_text(json.dumps(audit, indent=2, default=decimal_json) + "\n")
    report = ["# Q2.3 2017 年 GMV 前 20 名卖家", f'MySQL {imported["database"]["version"]} 查询及取回 {seconds:.3f} 秒，全部字段与独立 CSV 计算一致。',
        "## 口径", "- 按下单时间筛选 2017 年，GMV 延续 Q2.2：只计已送达订单，含商品价格和运费；卖家订单数及取消率分母包含所有状态。无法由商品明细归属卖家的订单不硬分配给某个卖家。",
        "- 先聚合到卖家－订单粒度。一个多卖家订单会在每位参与卖家下计一次，但各卖家 GMV 只包含自己的商品明细。",
        "- 客户数按 customer_unique_id 去重；customer_id 是订单关联标识，直接计数会把回购客户重复算入。",
        "- 每订单只取最近作答的评价；依次以作答时间、创建时间、review_id、源行号打破并列。平均评分涵盖有评价的卖家订单，不只看已送达订单。订单级评价被各参与卖家共享，无法证明是对某位卖家的独立评价。",
        "- 延迟率分母为已送达且实际/预计送达时间都存在的订单，分子按题目字面比较 actual > estimated；预计时间常是午夜，若业务按预计日期结束时承诺，需要另行修改口径。两个比率均为百分数，保留两位小数。",
        "- 州内 RANK 在全部合格卖家上计算，然后取全国前 20；同 GMV 同排名且后续跳号。全国并列时用 seller_id 稳定选取。",
        table(COLUMNS, [[row[k] if row[k] is not None else "NULL" for k in COLUMNS] for row in actual]),
        f'2017 年共有 {audit["seller_count"]} 位有商品明细的卖家，{audit["seller_order_pairs"]} 个卖家－订单组合；全部卖家已送达 GMV 合计 {audit["all_seller_gmv"]} BRL。',
        "复现：`python -m q2_sql_analysis.run_q23` 或 `python run_all.py --stage q2.3 --offline`。按订单选择一条评价和对客户真实标识去重，是避免重复连接失真的关键。"]
    (out / "q2_3_findings.md").write_text("\n\n".join(report) + "\n")
    logging.getLogger(__name__).info("Q2.3 完成：%s 位卖家，前 20 名逐字段对账通过", audit["seller_count"])
    return actual


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_q23(args.data_dir.resolve())
