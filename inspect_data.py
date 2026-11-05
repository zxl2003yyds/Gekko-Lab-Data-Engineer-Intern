"""检查全部原始 CSV 的行数、表头、缺失值和日期范围，生成数据准备报告。"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from download_data import ROOT, load_sources, sha256_file, validate_file

LOGGER = logging.getLogger(__name__)
DATE_COLUMNS = {
    "InvoiceDate",
    "shipping_limit_date",
    "review_creation_date",
    "review_answer_timestamp",
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
}


def inspect_file(path: Path, specification: dict) -> dict:
    validate_file(path, specification)
    columns = specification["columns"]
    missing = dict.fromkeys(columns, 0)
    date_ranges = {column: {"min": None, "max": None, "invalid": 0} for column in columns if column in DATE_COLUMNS}
    rows = 0
    # 以字符串读取，保留 ID 和邮编的前导零；只将空字段视作缺失。
    for chunk in pd.read_csv(path, dtype="string", keep_default_na=False, chunksize=100_000):
        rows += len(chunk)
        for column in columns:
            missing[column] += int(chunk[column].eq("").sum())
        for column, limits in date_ranges.items():
            original = chunk[column].replace("", pd.NA)
            dates = pd.to_datetime(original, format="mixed", errors="coerce")
            limits["invalid"] += int((original.notna() & dates.isna()).sum())
            if dates.notna().any():
                low, high = dates.min().isoformat(), dates.max().isoformat()
                limits["min"] = min(limits["min"], low) if limits["min"] else low
                limits["max"] = max(limits["max"], high) if limits["max"] else high
    if rows == 0:
        raise ValueError(f"文件只有表头，没有数据：{path}")
    return {
        "path": specification["destination"],
        "rows": rows,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "columns": columns,
        "missing": missing,
        "date_ranges": date_ranges,
    }


def inspect_data(data_dir: Path, report_path: Path) -> dict:
    report = {"datasets": {}, "errors": []}
    for name, dataset in load_sources().items():
        entry = {"handle": dataset["handle"], "url": dataset["url"], "license": dataset["license"], "files": []}
        report["datasets"][name] = entry
        for specification in dataset["files"].values():
            try:
                result = inspect_file(data_dir / specification["destination"], specification)
                entry["files"].append(result)
                for column, limits in result["date_ranges"].items():
                    if limits["invalid"]:
                        error = f'{result["path"]}：{column} 有 {limits["invalid"]} 条非空日期无法解析'
                        report["errors"].append(error)
                        LOGGER.error(error)
                LOGGER.info("%s：%s 行，%d 列", result["path"], f'{result["rows"]:,}', len(result["columns"]))
            except Exception as exc:
                report["errors"].append(str(exc))
                LOGGER.error("检查失败：%s", exc)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--report", type=Path, default=ROOT / ".local" / "data_inventory.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return int(bool(inspect_data(args.data_dir.resolve(), args.report.resolve())["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
