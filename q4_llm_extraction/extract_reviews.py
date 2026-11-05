"""按用户选择执行零外部模型调用的本地规则抽取，完整保留待复核状态。"""

import argparse
from collections import Counter
import csv
import hashlib
import json
import logging
import math
import re
from pathlib import Path
import random
import sys
from time import perf_counter

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from download_data import ROOT, load_sources, validate_file
from q1_data_quality.q1_code import table
from q4_llm_extraction.rules import CATEGORIES, VERSION, extract_text, clause_at
from q4_llm_extraction.io_utils import atomic_write_text

LOGGER = logging.getLogger(__name__)
OUTPUT = ROOT / "q4_llm_extraction"


def holdout_sample(rows):
    """样本划分来自版本化清单，不依赖被 Git 忽略的开发缓存。"""
    design = json.loads((OUTPUT / "evaluation_design.json").read_text())
    development = set(design["development_source_rows"])
    if design.get("sampling_unit") == "unique_nonempty_text":
        hashes = set(design["development_text_sha256"])
        unique = {}
        for row in rows:
            text = row["review_comment_message"]
            if text.strip() and hashlib.sha256(text.encode()).hexdigest() not in hashes:
                unique.setdefault(text, row)
        return random.Random(design["holdout_seed"]).sample(list(unique.values()), design["holdout_size"])
    return random.Random(design["holdout_seed"]).sample(
        [r for r in rows if r["source_row"] not in development], design["holdout_size"])


def read_reviews(data_dir):
    spec = load_sources()["olist"]["files"]["olist_order_reviews_dataset.csv"]
    path = data_dir / spec["destination"]
    validate_file(path, spec)
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for source_row, row in enumerate(csv.DictReader(stream), 1):
            if int(row["review_score"]) <= 3:
                rows.append({"source_row": source_row, **row})
    return rows


def validate_record(record, source):
    """运行时也执行的校验，不依赖可被 python -O 关闭的 assert。"""
    for key in ('review_id', 'order_id', 'source_row'):
        if record.get(key) != source[key]:
            raise ValueError(f'输出与原始记录的 {key} 不一致')
    for key, lower, upper in [('sentiment_score', -1, 1), ('confidence', 0, 1)]:
        value = record.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError(f'{key} 必须是范围内的有限数值')
    if any(type(record.get(key)) is not bool for key in ('actionable_for_seller', 'needs_review')):
        raise ValueError('动作/复核标志必须是布尔值')
    if not isinstance(record.get('issues'), list):
        raise ValueError('issues 必须为列表')
    categories = set()
    for issue in record['issues']:
        if not isinstance(issue, dict) or set(issue) != {'category','severity','evidence_quote','evidence_quote_en'}:
            raise ValueError('问题字段不完整')
        if issue['category'] not in CATEGORIES or issue['category'] in categories:
            raise ValueError('未知或重复问题类别')
        categories.add(issue['category'])
        if issue['severity'] not in {'low','medium','high'}:
            raise ValueError('未知严重程度')
        quote = issue['evidence_quote']
        if not isinstance(quote, str) or not quote.strip() or quote not in source['review_comment_message']:
            raise ValueError('证据不是原文的非空连续片段')
        if not isinstance(issue['evidence_quote_en'], str) or not issue['evidence_quote_en'].strip():
            raise ValueError('英文释义不能为空')


def evidence_contexts(text, issues):
    # 同一短语可能出现多次，全部保留上下文，避免错误地只展示第一个出现位置。
    return {issue['category']: list(dict.fromkeys(
        clause_at(text, match.start(), match.end())
        for match in re.finditer(re.escape(issue['evidence_quote']), text))) for issue in issues}


def run_extraction(data_dir=ROOT / "data"):
    start = perf_counter()
    rows = read_reviews(data_dir)
    records, cached = [], {}
    for row in rows:
        text = row["review_comment_message"]
        if text not in cached:
            cached[text] = extract_text(text)
        payload, route, review = cached[text]
        record = {"review_id": row["review_id"], **payload, "source_row": row["source_row"],
                  "order_id": row["order_id"], "method": VERSION, "extraction_status": route,
                  "needs_review": review, "evidence_scope": "phrase",
                  "evidence_contexts": evidence_contexts(text, payload["issues"])}
        validate_record(record, row)
        records.append(record)
    if len(records) != len(rows) or len({r["source_row"] for r in records}) != len(records):
        raise ValueError("输出行数或来源行号不完整")
    content = json.dumps(records, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    atomic_write_text(OUTPUT / "extracted_issues.json", content)
    audit_dir = ROOT / ".local/q4"
    audit_dir.mkdir(parents=True, exist_ok=True)
    routes = Counter(r["extraction_status"] for r in records)
    categories = Counter(issue["category"] for r in records for issue in r["issues"])
    metrics = {"rows": len(rows), "unique_exact_texts": len(cached), "routes": dict(routes),
               "categories": dict(categories), "needs_review": sum(r["needs_review"] for r in records),
               "seconds": perf_counter() - start, "api_calls": 0, "api_cost_usd": 0,
               "api_input_tokens": 0, "api_output_tokens": 0, "version": VERSION,
               "output_sha256": hashlib.sha256(content.encode()).hexdigest()}
    atomic_write_text(audit_dir / "metrics.json", json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    review_queue = [{"source_row": r["source_row"], "review_id": r["review_id"], "text": source["review_comment_message"],
                     "status": r["extraction_status"], "issues": r["issues"], "evidence_contexts": r["evidence_contexts"]} for r, source in zip(records, rows, strict=True) if r["needs_review"]]
    atomic_write_text(audit_dir / "review_queue.json", json.dumps(review_queue, ensure_ascii=False, indent=2) + "\n")
    # 样本按原文哈希排除全部开发文本；参考标签不参与抽取。
    sample = holdout_sample(rows)
    atomic_write_text(audit_dir / "evaluation_holdout.json", json.dumps([
        {"source_row": r["source_row"], "review_id": r["review_id"], "text": r["review_comment_message"], "score": int(r["review_score"])}
        for r in sample], ensure_ascii=False, indent=2) + "\n")
    atomic_write_text(OUTPUT / "cost_report.md", "\n\n".join([
        "# Q4 成本与处理覆盖", "数据管道采用本地规则，未调用外部模型 API。规则设计和参考标签有 AI 助手参与，工具使用见 TOOLS.md。",
        table(["项目", "结果"], [["低评分原始记录", len(rows)], ["外部 API 调用", 0], ["API 输入/输出 token", "0 / 0"],
              ["外部 API 实际费用（USD）", "0.00"], ["每条外部 API 成本", "0.00"], ["待复核记录", metrics["needs_review"]], ["本地完整运行秒数", f'{metrics["seconds"]:.3f}']]),
        table(["分流状态", "记录数"], sorted(routes.items())),
        "本报告仅统计数据管道的外部模型 API 费用。AI 聊天服务、人工复核时使用的 Google 翻译、人工时间及本机计算成本未纳入；不以 API 零费用代表项目总成本为零。",
        "单条与批处理比较：本地按完全相同原文缓存，减少重复计算；不把大小写不同或含不同上下文的文本强行合并。未来若接 API，成本公式为 N×(输入token×输入单价+输出token×输出单价)/10^6；请求批组可摊薄提示词，但必须用稳定记录键回填，不能假设模型按输入顺序输出。异步折扣批处理可能不满足 40 分钟要求。",
        f"规划示例：假设每条 600 输入、200 输出 token，单价 $2/$8 每百万，则 {len(rows):,} 条全调用约 ${len(rows)*0.0028:.2f}。这是参数假设下的算式，不是实际账单或供应商当前报价。",
        "每个文件先写同目录临时文件再原子替换；读取评估结果前核对输出摘要，拒绝跨文件中断留下的不一致状态。evidence_scope=phrase 明示规则证据是短语，evidence_contexts 附完整原句便于复核；固定英文是短语释义，未宣称是整句人工翻译。",
        f'输出 SHA-256：`{metrics["output_sha256"]}`。运行时间仅指程序执行，不代表完整开发及人工复核耗时。'
    ]) + "\n")
    LOGGER.info("Q4 本地抽取完成：%s 条，待复核 %s 条，外部调用 0", len(rows), metrics["needs_review"])
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_extraction(args.data_dir.resolve())
