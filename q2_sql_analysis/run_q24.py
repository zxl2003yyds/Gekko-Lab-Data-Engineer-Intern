"""对比原查询、严格等价改写与业务修正查询，保存真实执行计划。"""

import argparse
import json
import logging
from pathlib import Path
import statistics
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
from q2_sql_analysis.run_q22 import decimal_json


def run_q24(data_dir=ROOT / "data"):
    imported = load_olist(data_dir)
    folder = ROOT / "q2_sql_analysis"
    queries = {name: (folder / f"q2_4_{name}.sql").read_text() for name in ("original", "equivalent", "corrected")}
    results, durations, plans = {}, {}, {}
    engine = create_database_engine()
    try:
        with engine.connect() as connection:
            for name, sql in queries.items():
                connection.execute(text(sql)).all()  # 热身，不计入三次统计。
                durations[name] = []
            for _ in range(3):
                for name, sql in queries.items():
                    started = perf_counter()
                    results[name] = [dict(r) for r in connection.execute(text(sql)).mappings()]
                    durations[name].append(perf_counter() - started)
            for name, sql in queries.items():
                plans[name] = "\n".join(str(r[0]) for r in connection.execute(text("EXPLAIN ANALYZE " + sql)))
    finally:
        engine.dispose()
    original = {r["customer_state"]: r for r in results["original"]}
    equivalent = {r["customer_state"]: r for r in results["equivalent"]}
    require(original == equivalent, "严格等价查询的结果发生变化")
    corrected = {r["customer_state"]: r for r in results["corrected"]}
    require(original.keys() == corrected.keys(), 'run_q24: original.keys() == corrected.keys()')
    require(all(original[state]["orders"] == corrected[state]["orders"] for state in original), 'run_q24: all(original[state]["orders"] == corrected[state]["orders"] for state in original)')
    audit = ROOT / ".local/q2"
    for name, plan in plans.items():
        (folder / f"q2_4_{name}_plan.txt").write_text(plan.rstrip("\n") + "\n")
    record = {"results": results, "durations": durations, "mysql": imported["database"]["version"]}
    (audit / "q24_benchmark.json").write_text(json.dumps(record, indent=2, default=decimal_json) + "\n")
    differences = [[state, original[state]["orders"], original[state]["revenue"], corrected[state]["revenue"],
                    original[state]["revenue"] - corrected[state]["revenue"], original[state]["avg_score"], corrected[state]["avg_score"]]
                   for state in sorted(original)]
    report = ["# Q2.4 慢查询与统计错误分析", "## 统计错误先于性能",
        "一个订单若有 3 条商品明细、2 条评价，连接后形成 6 行：每条商品收入出现两次，评分则按商品条数加权。COUNT(DISTINCT order_id) 只修正订单数，不能修正 SUM 和 AVG。SUM(DISTINCT price) 也不对：不同商品可能同价。",
        "正确做法是先将商品聚合到订单，再为每订单选择一条有定义的评价。本方案使用最近作答记录，并以创建时间、review_id、源行号确定并列。原题收入只含 price，修正版保留这个口径；需要含运费 GMV 时应另加 freight_value。",
        "## 性能问题及原因",
        "1. 两个一对多明细表直接连接，使中间结果膨胀；下游去重、分组和排序处理更多行。先过滤目标订单并预聚合明细可降低规模。",
        "2. LOWER(customer_city) 包裹列，普通原值索引不能直接给该表达式做范围定位。但即使移除 LOWER，LIKE '%sao%' 的前导通配符仍不能作普通 B-tree 前缀范围查找；函数索引本身也不能解决子串检索。",
        "3. 订单以状态等值加购买时间范围过滤，缺合适组合索引时需要更多扫描。建议测量 (order_status, order_purchase_timestamp, customer_id, order_id)，而不是只建低选择性的状态单列索引。",
        "4. COUNT(DISTINCT) 及按聚合值排序有去重/临时结构开销；确认每单一行后可直接 COUNT(*)。预聚合会增加物化开销，原始小数据上不保证更快。",
        "5. WHERE 条件要求客户城市匹配，因此原 LEFT JOIN customers 实际排除了未匹配客户，可明确写 INNER JOIN。城市口径仍保留原表达式，避免将 sao 和 são 等不同业务匹配悄悄合并。",
        "## SQL 与索引建议",
        "- q2_4_equivalent.sql 保持原始重复收入/评分加权语义，用于公平性能比较；q2_4_corrected.sql 修正业务语义，其结果不应与错误原查询完全相同。",
        "- 已有 orders.order_id、customers.customer_id 的唯一索引；order_items 的 (order_id, order_item_id) 唯一索引及 order_reviews.order_id 索引均可支持关联。不要重复创建同用途索引。",
        "```sql\n-- 候选索引，需在真实查询分布和写入成本下评估后部署；本次未添加。\nCREATE INDEX ix_orders_status_purchase_customer\n    ON orders(order_status, order_purchase_timestamp, customer_id, order_id);\n-- 若“sao 城市集合”是固定业务需求，维护已审核的城市维表或可索引标记；\n-- 任意子串检索需单独检索方案，全文检索也不能未经验证就当作子串等价替代。\n```",
        "## 本机实测", f'MySQL {imported["database"]["version"]}，固定原始数据，先热身后交替执行三轮；时长含取回结果，不含连接及数据核验。未构造 100 倍数据，不能据此声称已验证该规模。',
        table(["版本", "三次耗时（秒）", "中位数（秒）"], [[name, ", ".join(f"{x:.4f}" for x in durations[name]), f"{statistics.median(durations[name]):.4f}"] for name in queries]),
        "等价版本全部结果与原查询一致。若预聚合版本在当前数据上更慢，也按实测保留，不虚构优化倍数。未来应在目标规模比较峰值内存、扫描/连接行数、物化量和 P95 时间。",
        "执行计划保存在 q2_4_original_plan.txt、q2_4_equivalent_plan.txt、q2_4_corrected_plan.txt，保留 actual rows/loops。各节点可能重复读取同一批行，因此不把节点行数简单相加冒充唯一的扫描总行数。",
        "## 业务修正前后", table(["州", "订单数", "原商品收入", "修正商品收入", "虚增收入", "原评分", "最新评价每单均分"], differences),
        "复现环境为已导入 Olist 的 MySQL 8.0+，使用 orders、customers、order_items、order_reviews 四张表。order_reviews 的 `_source_row` 表示原 CSV 中从 1 开始的记录序号，用于相同时间和评价编号下的稳定排序。",
        "在准备好的数据库中分别执行三份 SQL，并在查询前加 `EXPLAIN ANALYZE` 查看实际执行计划。SQL 查询本身不修改业务数据或索引。可用 `python -m q2_sql_analysis.run_q24` 自动核验并生成报告；其数据准备步骤会在首次运行时导入数据，后续运行验证并复用已有表。",
        "参考：[MySQL EXPLAIN ANALYZE](https://dev.mysql.com/doc/refman/8.4/en/explain.html)、[范围优化](https://dev.mysql.com/doc/refman/8.4/en/range-optimization.html)。"]
    (folder / "q2_4_query_optimization.md").write_text("\n\n".join(report) + "\n")
    logging.getLogger(__name__).info("Q2.4 完成：等价结果核对及三轮性能测量通过")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_q24(args.data_dir.resolve())
