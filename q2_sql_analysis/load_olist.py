"""校验九份 Olist CSV，分批写入 MySQL，逐值回读验证后发布。"""

from __future__ import annotations

import argparse
from contextlib import suppress
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import logging
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import inspect, select, text

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_database import check_connection, create_database_engine
from download_data import ROOT, load_sources, validate_file
from q1_data_quality.q1_code import table as markdown_table
from q2_sql_analysis.schema import DATE_COLUMNS, FLOAT_COLUMNS, INTEGER_COLUMNS, LOADER_VERSION, MANIFEST_NAME, MONEY_COLUMNS, TABLE_FILES, build_tables

LOGGER = logging.getLogger(__name__)
CHUNK_SIZE = 10_000


def normalize_chunk(raw: pd.DataFrame, offset: int) -> pd.DataFrame:
    """只规范存储类型和空值，不去重、不翻译、不填补缺失类别。"""
    frame = raw.replace("", pd.NA).copy()
    for name in frame:
        if name in INTEGER_COLUMNS:
            numeric = pd.to_numeric(frame[name], errors="raise")
            if not numeric.dropna().mod(1).eq(0).all():
                raise ValueError(f"非整数：{name}")
            frame[name] = numeric.astype("Int64")
        elif name in DATE_COLUMNS:
            frame[name] = pd.to_datetime(frame[name], format="%Y-%m-%d %H:%M:%S", errors="raise")
        elif name in MONEY_COLUMNS:
            mapping = {}
            for value in frame[name].dropna().unique():
                amount = Decimal(value)
                if not amount.is_finite() or amount != amount.quantize(Decimal("0.01")):
                    raise ValueError(f"金额非有限值或超出两位小数：{name}")
                mapping[value] = amount.quantize(Decimal("0.01"))
            frame[name] = frame[name].map(mapping)
        elif name in FLOAT_COLUMNS:
            frame[name] = pd.to_numeric(frame[name], errors="raise").astype("float64")
            if not np.isfinite(frame[name].dropna()).all():
                raise ValueError(f"坐标不是有限数：{name}")
    frame.insert(0, "_source_row", np.arange(offset + 1, offset + len(frame) + 1))
    frame = frame.astype(object).where(frame.notna(), None)
    return frame


def canonical(value):
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat(sep=" ")
    return value


class ContentDigest:
    """按固定列序和原始记录号对规范化值计算摘要，区别于原始文件摘要。"""
    def __init__(self, columns):
        self.columns = list(columns)
        self.hash = hashlib.sha256()
        self.rows = 0
        self.nulls = {name: 0 for name in self.columns}

    def add(self, rows):
        for row in rows:
            values = []
            for name, value in zip(self.columns, row, strict=True):
                self.nulls[name] += value is None
                values.append(canonical(value))
            self.hash.update((json.dumps(values, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8"))
            self.rows += 1

    def result(self):
        return {"row_count": self.rows, "typed_sha256": self.hash.hexdigest(), "null_counts": self.nulls}


def database_digest(connection, table):
    digest = ContentDigest(table.c.keys())
    statement = select(table).order_by(table.c._source_row).execution_options(yield_per=CHUNK_SIZE)
    result = connection.execute(statement)
    try:
        digest.add(result)
    finally:
        result.close()
    return digest.result()


def insert_csv(connection, table, path: Path) -> dict:
    digest = ContentDigest(table.c.keys())
    for raw in pd.read_csv(path, dtype="string", keep_default_na=False, chunksize=CHUNK_SIZE):
        frame = normalize_chunk(raw, digest.rows)
        digest.add(frame.itertuples(index=False, name=None))
        connection.execute(table.insert(), frame.to_dict("records"))
        connection.commit()
        if digest.rows % 100_000 == 0:
            LOGGER.info("%s 已写入 %s 行", path.name, digest.rows)
    expected = digest.result()
    actual = database_digest(connection, table)
    if actual != expected:
        raise AssertionError(f"MySQL 回读与源数据规范化值不一致：{path.name}")
    return expected


def ensure_import(connection, data_dir: Path) -> dict:
    started = perf_counter()
    database = check_connection(connection)
    specs = load_sources()["olist"]["files"]
    for filename in TABLE_FILES.values():
        validate_file(data_dir / specs[filename]["destination"], specs[filename])
    LOGGER.info("九份源文件的表头及 SHA-256 均通过验证")
    lock_name = "olist_import:" + str(database["database"])
    if connection.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": lock_name}).scalar() != 1:
        raise RuntimeError("同一数据库已有 Olist 导入正在运行")
    created = []
    try:
        existing = set(inspect(connection).get_table_names())
        targets = set(TABLE_FILES) | {MANIFEST_NAME}
        records = []
        if existing & targets:
            if not targets <= existing:
                raise RuntimeError("存在不完整或非本程序管理的 Olist 同名表，拒绝覆盖")
            tables, manifest = build_tables(specs)
            records = [dict(row) for row in connection.execute(select(manifest)).mappings()]
            if {row["table_name"] for row in records} != set(TABLE_FILES):
                raise RuntimeError("现有导入清单不完整，拒绝覆盖")
            for row in records:
                name = row["table_name"]
                filename = TABLE_FILES[name]
                if (row["loader_version"] != LOADER_VERSION or row["source_file"] != filename
                        or row["source_sha256"] != specs[filename]["sha256"]):
                    raise RuntimeError(f"{name} 导入版本不匹配，拒绝覆盖")
                if database_digest(connection, tables[name]) != {key: row[key] for key in ("row_count", "typed_sha256", "null_counts")}:
                    raise AssertionError(f"{name} 内容已变化，拒绝将其视为原始导入")
                LOGGER.info("复用 %s：%s 行，逐值摘要与空值计数一致", name, row["row_count"])
            reused = True
        else:
            prefix = "_olist_" + uuid4().hex[:8] + "_"
            tables, manifest = build_tables(specs, prefix)
            for name, table in tables.items():
                filename = TABLE_FILES[name]
                table.create(connection)
                created.append(table)
                connection.commit()
                LOGGER.info("开始导入 %s", name)
                values = insert_csv(connection, table, data_dir / specs[filename]["destination"])
                records.append({"table_name": name, "source_file": filename, "source_sha256": specs[filename]["sha256"], "loader_version": LOADER_VERSION, **values})
                LOGGER.info("%s 已完成写入及逐值回读：%s 行", name, values["row_count"])
            manifest.create(connection)
            created.append(manifest)
            connection.execute(manifest.insert(), records)
            connection.commit()
            # InnoDB 的一条 RENAME TABLE 一起发布九张表及导入清单；不替换现有表。
            pairs = [f"`{table.name}` TO `{name}`" for name, table in tables.items()]
            pairs.append(f"`{manifest.name}` TO `{MANIFEST_NAME}`")
            connection.exec_driver_sql("RENAME TABLE " + ", ".join(pairs))
            connection.commit()
            created.clear()
            reused = False
        return {"database": database, "reused": reused, "tables": sorted(records, key=lambda row: row["table_name"]), "elapsed_seconds": perf_counter() - started}
    except Exception:
        LOGGER.exception("Olist 导入/验证失败；不发布未校验的表")
        with suppress(Exception):
            connection.rollback()
        for table in reversed(created):
            with suppress(Exception):
                table.drop(connection, checkfirst=True)
                connection.commit()
        raise
    finally:
        with suppress(Exception):
            connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name})
            connection.commit()


def write_import_report(report: dict):
    audit = ROOT / ".local" / "q2"
    audit.mkdir(parents=True, exist_ok=True)
    (audit / "import_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Olist MySQL 导入核验", f'MySQL {report["database"]["version"]}；数据库 `{report["database"]["database"]}`；规则 `{LOADER_VERSION}`。',
             f'本次操作：{"复用并重新验证" if report["reused"] else "首次导入并验证"}；耗时 {report["elapsed_seconds"]:.3f} 秒。',
             markdown_table(["表", "记录数", "规范化值 SHA-256"], [[row["table_name"], row["row_count"], row["typed_sha256"]] for row in report["tables"]]),
             "九份 CSV 均先验证固定版本表头和文件摘要。写入后按 `_source_row` 排序逐值回读，行数、空值计数和规范化值摘要全部一致。原始文件摘要与规范化值摘要的计算对象不同，不应互相比对。",
             "空字符串存为 SQL NULL，其他文本不自动修剪或改写；金额使用 DECIMAL(14,2)，日期使用 DATETIME，ID 和邮编前缀使用字符串。经纬度按 DOUBLE 存储，保留浮点表示；CSV 原始文本未修改。",
             "每表追加 `_source_row` 作为主键及来源记录号（不含表头）。商品、订单、客户、卖家和类别字典使用自然唯一键，订单明细/支付使用组合唯一键；reviews 的 review_id 和 geolocation 的邮编都不是唯一键，不去重、不强加唯一约束。",
             "数据表使用 utf8mb4_0900_bin，保留大小写和重音差异；没有为了导入而丢弃孤立记录或添加跨表外键。业务关联质量将在对应题目中检查。",
             "分批写入独立暂存表，全部通过后一起改名发布；再次运行验证并复用已有结果，不追加重复数据。现有表缺少清单、版本不符或内容改变时，报错而不覆盖。进程被强制终止可能留下带随机前缀的暂存表，需核对后清理。",
             "复现：`python -m q2_sql_analysis.load_olist`；仅使用本机 .env 配置，密码不写入代码或报告。",
             "发布语义参考：[MySQL RENAME TABLE](https://dev.mysql.com/doc/refman/8.4/en/rename-table.html)。"]
    (ROOT / "q2_sql_analysis" / "import_report.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def load_olist(data_dir: Path = ROOT / "data") -> dict:
    engine = create_database_engine()
    try:
        with engine.connect() as connection:
            report = ensure_import(connection, data_dir)
        write_import_report(report)
        return report
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        load_olist(args.data_dir.resolve())
    except Exception as exc:
        LOGGER.error("导入未完成：%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
