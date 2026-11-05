"""核验数据库存储转换、逐值摘要和可选的 MySQL 集成测试。"""

from datetime import datetime
from decimal import Decimal
import os

import pandas as pd
import pytest
from sqlalchemy import text

from check_database import create_database_engine
from download_data import load_sources
from q2_sql_analysis.load_olist import ContentDigest, normalize_chunk
from q2_sql_analysis.run_q21 import SQL_PATH, csv_reference
from q2_sql_analysis.schema import TABLE_FILES, build_tables


def test_import_types_preserve_text_nulls_money_dates_and_lineage():
    raw = pd.DataFrame({"product_id": ["001", "002"], "product_category_name": ["ação", ""],
                        "product_weight_g": ["1.0", ""], "price": ["0.10", "3.99"],
                        "shipping_limit_date": ["2017-01-01 12:34:56", ""],
                        "review_comment_message": ["NULL\nquoted: \"x\"", " "]}, dtype="string")
    frame = normalize_chunk(raw, 100)
    assert frame["_source_row"].tolist() == [101, 102]
    assert frame["product_id"].tolist() == ["001", "002"]
    assert frame["product_category_name"].tolist() == ["ação", None]
    assert frame["product_weight_g"].tolist() == [1, None]
    assert frame["price"].tolist() == [Decimal("0.10"), Decimal("3.99")]
    assert frame["shipping_limit_date"].tolist() == [datetime(2017, 1, 1, 12, 34, 56), None]
    assert frame["review_comment_message"].tolist() == ["NULL\nquoted: \"x\"", " "]


@pytest.mark.parametrize("field,value", [("price", "0.001"), ("price", "NaN"), ("review_score", "1.5"), ("geolocation_lat", "inf"), ("shipping_limit_date", "bad")])
def test_import_does_not_silently_coerce_invalid_numeric_or_dates(field, value):
    with pytest.raises((ValueError, ArithmeticError)):
        normalize_chunk(pd.DataFrame({field: [value]}, dtype="string"), 0)


def test_digest_handles_typed_values_and_detects_change_and_order():
    first = ContentDigest(["id", "date", "money", "empty"])
    first.add([("001", pd.Timestamp("2017-01-01"), Decimal("1.00"), None)])
    same = ContentDigest(first.columns)
    same.add([("001", datetime(2017, 1, 1), Decimal("1.00"), None)])
    assert first.result() == same.result()
    changed = ContentDigest(first.columns)
    changed.add([("001", datetime(2017, 1, 1), Decimal("2.00"), None)])
    assert first.result()["typed_sha256"] != changed.result()["typed_sha256"]
    assert first.result()["null_counts"]["empty"] == 1


def test_schema_does_not_treat_review_id_or_zip_code_as_unique():
    tables, manifest = build_tables(load_sources()["olist"]["files"])
    assert set(tables) == set(TABLE_FILES)
    for name in ("geolocation", "order_reviews"):
        assert list(tables[name].primary_key.columns.keys()) == ["_source_row"]
        assert all(not index.unique for index in tables[name].indexes)


def test_csv_reference_accepts_bom_in_translation_header(tmp_path):
    target = tmp_path / "olist"
    target.mkdir()
    (target / "product_category_name_translation.csv").write_text(
        "product_category_name,product_category_name_english\na,alpha\n", encoding="utf-8-sig")
    (target / "olist_products_dataset.csv").write_text(
        "product_id,product_category_name\n001,a\n002,b\n003,\n", encoding="utf-8")
    rows, total = csv_reference(tmp_path)
    assert total == 3
    assert rows == [
        {"product_category_name": None, "product_count": 1, "gap_type": "missing_source_category"},
        {"product_category_name": "b", "product_count": 1, "gap_type": "missing_english_translation"},
    ]


@pytest.mark.skipif(os.getenv("OLIST_TEST_MYSQL") != "1", reason="设置 OLIST_TEST_MYSQL=1 在本机 MySQL 执行隔离临时表测试")
def test_q21_sql_on_mysql_handles_missing_blank_duplicate_and_case_sensitive_values():
    engine = create_database_engine()
    try:
        with engine.connect() as connection:
            # 同名临时表只在当前连接遮盖正式表，关闭连接即销毁。
            connection.exec_driver_sql("CREATE TEMPORARY TABLE products (product_category_name VARCHAR(100)) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin")
            connection.exec_driver_sql("CREATE TEMPORARY TABLE product_category_name_translation (product_category_name VARCHAR(100), product_category_name_english VARCHAR(100)) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin")
            categories = [None, None, "", "a", "b", "b", "c", "d", "e", "A"]
            connection.execute(text("INSERT INTO products VALUES (:category)"), [{"category": value} for value in categories])
            connection.execute(text("INSERT INTO product_category_name_translation VALUES (:category, :english)"), [
                {"category": "a", "english": "alpha"}, {"category": "a", "english": "alpha"},
                {"category": "c", "english": " "}, {"category": "d", "english": None},
                {"category": "e", "english": None}, {"category": "e", "english": "valid"},
                {"category": None, "english": "not a category"},
            ])
            rows = list(connection.execute(text(SQL_PATH.read_text())).mappings())
            actual = {row["product_category_name"]: (row["product_count"], row["gap_type"]) for row in rows}
            assert actual == {None: (2, "missing_source_category"), "": (1, "missing_source_category"),
                              "b": (2, "missing_english_translation"), "c": (1, "missing_english_translation"),
                              "d": (1, "missing_english_translation"), "A": (1, "missing_english_translation")}
    finally:
        engine.dispose()
