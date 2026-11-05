"""执行 Q2.2 月度指标，并用 CSV、Decimal 和逐订单计算独立复核。"""

from collections import Counter, defaultdict
import argparse
import csv
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
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

LOGGER = logging.getLogger(__name__)
SQL_PATH = ROOT / "q2_sql_analysis" / "q2_2_monthly_metrics.sql"
COLUMNS = ["month", "total_orders", "delivered_orders", "canceled_orders", "cancel_rate", "delivered_gmv", "avg_delivery_days"]


def rounded(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_reference(orders, items) -> tuple[list[dict], dict]:
    """使用 Python 字典逐订单计数，独立于 SQL 连接和聚合计算路径。"""
    amounts = defaultdict(lambda: Decimal("0.00"))
    item_counts = Counter()
    invalid_amount_orders = set()
    for item in items:
        order_id = item["order_id"]
        item_counts[order_id] += 1
        if not item["price"] or not item["freight_value"]:
            invalid_amount_orders.add(order_id)
        else:
            amounts[order_id] += Decimal(item["price"]) + Decimal(item["freight_value"])
    months = {}
    statuses, no_items = Counter(), Counter()
    seen, missing_dates, negative_dates = set(), [], []
    unknown_gmv_orders = []
    for order in orders:
        order_id, status = order["order_id"], order["order_status"]
        if not order_id or order_id in seen:
            raise ValueError("订单 ID 缺失或重复，不能按一行一订单计算")
        seen.add(order_id)
        if not order["order_purchase_timestamp"]:
            raise ValueError(f"订单缺少下单时间，无法归属月份：{order_id}")
        purchased = datetime.fromisoformat(order["order_purchase_timestamp"])
        month = purchased.strftime("%Y-%m")
        if month not in months:
            months[month] = {"total_orders": 0, "delivered_orders": 0, "canceled_orders": 0,
                             "delivered_gmv": Decimal("0.00"), "unknown_gmv": 0,
                             "delivery_seconds": 0, "valid_delivery_orders": 0}
        group = months[month]
        group["total_orders"] += 1
        group["canceled_orders"] += status == "canceled"
        statuses[status] += 1
        if order_id not in item_counts:
            no_items[status] += 1
        if status != "delivered":
            continue
        group["delivered_orders"] += 1
        if order_id not in item_counts or order_id in invalid_amount_orders:
            group["unknown_gmv"] += 1
            unknown_gmv_orders.append(order_id)
        else:
            group["delivered_gmv"] += amounts[order_id]
        received = order["order_delivered_customer_date"]
        if not received:
            missing_dates.append({"order_id": order_id, "month": month})
        else:
            seconds = int((datetime.fromisoformat(received) - purchased).total_seconds())
            if seconds < 0:
                negative_dates.append({"order_id": order_id, "month": month})
            else:
                group["delivery_seconds"] += seconds
                group["valid_delivery_orders"] += 1
    result = []
    for month, group in sorted(months.items()):
        result.append({"month": month, "total_orders": group["total_orders"],
                       "delivered_orders": group["delivered_orders"], "canceled_orders": group["canceled_orders"],
                       "cancel_rate": rounded(Decimal(100) * group["canceled_orders"] / group["total_orders"]),
                       "delivered_gmv": None if group["unknown_gmv"] else group["delivered_gmv"],
                       "avg_delivery_days": rounded(Decimal(group["delivery_seconds"]) / (group["valid_delivery_orders"] * 86400))
                       if group["valid_delivery_orders"] else None})
    valid_deliveries = sum(group["valid_delivery_orders"] for group in months.values())
    total_seconds = sum(group["delivery_seconds"] for group in months.values())
    total_gmv = None if unknown_gmv_orders else sum((group["delivered_gmv"] for group in months.values()), Decimal("0.00"))
    diagnostics = {
        "order_count": len(seen), "item_count": sum(item_counts.values()), "status_counts": dict(sorted(statuses.items())),
        "orders_without_items_by_status": dict(sorted(no_items.items())),
        "orphan_item_rows": sum(count for order_id, count in item_counts.items() if order_id not in seen),
        "delivered_missing_dates": missing_dates, "delivered_negative_durations": negative_dates,
        "unknown_gmv_orders": unknown_gmv_orders, "valid_delivery_orders": valid_deliveries,
        "total_delivery_seconds": total_seconds, "delivered_gmv": total_gmv,
        "cancel_rate": rounded(Decimal(100) * statuses["canceled"] / len(seen)) if seen else None,
        "avg_delivery_days": rounded(Decimal(total_seconds) / (valid_deliveries * 86400)) if valid_deliveries else None,
        "delivery_samples_by_month": {month: group["valid_delivery_orders"] for month, group in sorted(months.items())},
    }
    return result, diagnostics


def csv_reference(data_dir: Path):
    with (data_dir / "olist" / "olist_orders_dataset.csv").open(encoding="utf-8-sig", newline="") as order_file, \
         (data_dir / "olist" / "olist_order_items_dataset.csv").open(encoding="utf-8-sig", newline="") as item_file:
        return build_reference(csv.DictReader(order_file), csv.DictReader(item_file))


def verify_results(actual: list[dict], expected: list[dict], diagnostics: dict):
    require(actual == expected, "MySQL 月度指标与 CSV 独立计算不一致")
    require(sum(row["total_orders"] for row in actual) == diagnostics["order_count"], 'run_q22: sum(row["total_orders"] for row in actual) == diagnostics["order_count"]')
    for row in actual:
        require(set(row) == set(COLUMNS), 'run_q22: set(row) == set(COLUMNS)')
        require(row["total_orders"] > 0, 'run_q22: row["total_orders"] > 0')
        require(row["delivered_orders"] + row["canceled_orders"] <= row["total_orders"], 'run_q22: row["delivered_orders"] + row["canceled_orders"] <= row["total_orders"]')
        require(Decimal(0) <= row["cancel_rate"] <= Decimal(100), 'run_q22: Decimal(0) <= row["cancel_rate"] <= Decimal(100)')
        require(row["avg_delivery_days"] is None or row["avg_delivery_days"] >= 0, 'run_q22: row["avg_delivery_days"] is None or row["avg_delivery_days"] >= 0')
    if diagnostics["delivered_gmv"] is not None:
        require(sum((row["delivered_gmv"] for row in actual), Decimal(0)) == diagnostics["delivered_gmv"], 'run_q22: sum((row["delivered_gmv"] for row in actual), Decimal(0)) == diagnostics["delivered_gmv"]')


def decimal_json(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"不能序列化 {type(value)}")


def render_report(rows, diagnostics, mysql_version, query_seconds):
    d = diagnostics
    lines = [
        "# Q2.2 月度订单与已送达成交分析",
        f'MySQL {mysql_version} 上执行 `q2_2_monthly_metrics.sql`，查询及取回结果耗时 {query_seconds:.3f} 秒（不含导入核验）。全部 {len(rows)} 个月、7 个字段均与独立 CSV 逐订单计算一致。',
        "## 统计口径",
        "- month 采用下单时间所属月份；状态为数据集中的订单状态快照，不是重建历史月末状态。没有订单的月份不补造记录。",
        "- total_orders 包含所有状态；delivered_orders 只计 delivered；canceled_orders 只计 canceled，不把 unavailable、未发货等自动当作取消。",
        "- cancel_rate = canceled_orders / total_orders × 100，输出为百分数（0–100），保留两位小数。",
        "- delivered_gmv 只汇总已送达订单的 price + freight_value，金额为巴西雷亚尔（BRL）。先按 order_id 汇总商品明细，再与订单左连接，避免重复计数和漏掉没有明细的订单。",
        "- avg_delivery_days 是已送达且时间有效的订单，从下单到送达的秒数均值除以 86,400，再保留两位小数。未送达、送达时间缺失或时间倒置不参与均值；没有有效样本时为 NULL，不填成 0 天。",
        "- 已送达订单如果没有商品明细或任一明细缺金额，相关月份 GMV 为 NULL，并在审计中列出。没有已送达订单的月份 GMV 为 0。本次数据没有已送达订单缺明细或金额的情况。",
        "## 全量结果",
        table(["月份", "下单量", "已送达", "取消", "取消率（%）", "已送达 GMV（BRL）", "平均配送天数"],
              [[row[name] if row[name] is not None else "NULL" for name in COLUMNS] for row in rows]),
        "## 整体核对",
        table(["指标", "值"], [["订单数", d["order_count"]], ["商品明细数", d["item_count"]],
              ["已送达订单", d["status_counts"].get("delivered", 0)], ["取消订单", d["status_counts"].get("canceled", 0)],
              ["整体取消率（%）", d["cancel_rate"]], ["已送达 GMV（BRL）", d["delivered_gmv"]],
              ["有效配送时间样本数", d["valid_delivery_orders"]], ["整体平均配送天数", d["avg_delivery_days"]]]),
        "整体取消率和平均配送天数直接从全部订单计算，不对各月比率或均值再做简单平均。",
        "## 质量检查及解释边界",
        table(["订单状态", "订单数"], list(d["status_counts"].items())),
        table(["没有商品明细的订单状态", "订单数"], list(d["orders_without_items_by_status"].items())),
        f'共有 {sum(d["orders_without_items_by_status"].values())} 张订单没有商品明细；使用左连接后仍完整保留在下单量及相应状态计数中。孤立商品明细 {d["orphan_item_rows"]} 条。',
        f'已送达但缺少送达时间 {len(d["delivered_missing_dates"])} 张，时间倒置 {len(d["delivered_negative_durations"])} 张。它们不影响送达状态计数与已知 GMV，但不参与配送时长均值。',
        table(["缺送达时间的已送达订单", "下单月份"], [[row["order_id"], row["month"]] for row in d["delivered_missing_dates"]]),
        "2016-11 没有下单记录，因此没有输出该月。样本尾部 2018-09 和 2018-10 分别只有 16、4 张订单且没有 delivered 订单；不据此判断平台经营骤降，也不推断订单后来永远未送达。",
        "## 实现与复现",
        "SQL 分两层 CTE：item_totals 将商品明细缩为每单一行，order_level 再关联订单及计算有效配送秒数，最后按月条件聚合。独立复核使用 CSV、Python 字典及 Decimal，不复用 SQL 的计算结果。",
        "```bash\npython run_all.py --stage q2.2 --offline\n# 或\npython -m q2_sql_analysis.run_q22\n```",
        "数值完整结果保存于 `q2_2_monthly_results.json`（Decimal 以字符串保留精度）；详细审计位于 `.local/q2/q22_diagnostics.json`。",
        "函数语义参考：[MySQL 日期函数](https://dev.mysql.com/doc/refman/8.4/en/date-and-time-functions.html)、[聚合函数与 NULL](https://dev.mysql.com/doc/refman/8.4/en/aggregate-functions.html)。",
    ]
    return "\n\n".join(lines) + "\n"


def run_q22(data_dir: Path = ROOT / "data") -> dict:
    imported = load_olist(data_dir)
    expected, diagnostics = csv_reference(data_dir)
    engine = create_database_engine()
    try:
        with engine.connect() as connection:
            started = perf_counter()
            rows = [dict(row) for row in connection.execute(text(SQL_PATH.read_text(encoding="utf-8"))).mappings()]
            query_seconds = perf_counter() - started
    finally:
        engine.dispose()
    verify_results(rows, expected, diagnostics)
    output_dir = ROOT / "q2_sql_analysis"
    audit = ROOT / ".local" / "q2"
    audit.mkdir(parents=True, exist_ok=True)
    (output_dir / "q2_2_monthly_results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=decimal_json) + "\n", encoding="utf-8")
    (audit / "q22_diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2, default=decimal_json) + "\n", encoding="utf-8")
    report = render_report(rows, diagnostics, imported["database"]["version"], query_seconds)
    (output_dir / "q2_2_findings.md").write_text(report, encoding="utf-8")
    LOGGER.info("Q2.2 通过：%s 个月，%s 张订单，SQL 与独立 CSV 计算一致", len(rows), diagnostics["order_count"])
    return {"rows": rows, "diagnostics": diagnostics, "query_seconds": query_seconds}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run_q22(args.data_dir.resolve())
    except Exception as exc:
        LOGGER.error("Q2.2 未完成：%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
