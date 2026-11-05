"""数据质量统计必须保留异常，不把转换失败、缺失、重复口径混在一起。"""

import math

import pandas as pd
import pytest

from q1_data_quality.q1_code import build_profile, top_values


def sample_frame(rows):
    defaults = {
        "Invoice": "000123", "StockCode": "00123A", "Description": "NA",
        "Quantity": "1", "InvoiceDate": "2011-01-01 12:00:00", "Price": "2.0",
        "Customer ID": "001.0", "Country": "United Kingdom",
    }
    return pd.DataFrame([{**defaults, **row} for row in rows], dtype="string")


def test_missing_and_parse_errors_are_distinct_and_ids_are_preserved():
    raw = sample_frame([
        {"Price": "", "Description": "", "Customer ID": ""},
        {"Price": "bad", "InvoiceDate": "bad-date"},
        {"Price": "inf", "Description": " "},
    ])
    original = raw.copy(deep=True)
    profile = build_profile(raw)
    columns = {item["name"]: item for item in profile["columns"]}
    assert columns["Price"]["missing"] == 1
    assert columns["Price"]["parse_errors"] == 2
    assert columns["InvoiceDate"]["parse_errors"] == 1
    assert columns["Description"]["missing"] == 1
    assert columns["Description"]["whitespace_only"] == 1
    assert profile["strings"]["Description"]["unique"] == 2
    assert profile["strings"]["Invoice"]["top10"][0]["value"] == "000123"
    assert profile["strings"]["Customer ID"]["top10"][0]["value"] == "001.0"
    assert "Customer ID" not in profile["numeric"]
    pd.testing.assert_frame_equal(raw, original)


def test_numeric_summary_keeps_zero_negative_and_uses_sample_std():
    profile = build_profile(sample_frame([{"Quantity": "-2"}, {"Quantity": "0"}, {"Quantity": "5"}]))
    summary = profile["numeric"]["Quantity"]
    assert summary["count"] == 3
    assert summary["min"] == -2
    assert summary["max"] == 5
    assert summary["mean"] == pytest.approx(1)
    assert summary["std"] == pytest.approx(math.sqrt(13))
    assert summary["median"] == 0


def test_duplicate_count_uses_all_fields_not_invoice_alone():
    profile = build_profile(sample_frame([{}, {}, {}, {"StockCode": "99999"}]))
    assert profile["signals"]["duplicate_members"]["count"] == 3
    assert profile["signals"]["duplicate_excess"]["count"] == 2
    assert profile["duplicate_example"]["occurrences"] == 3
    assert profile["rows"] == 4


def test_c_prefix_and_quantity_sign_are_independent_signals():
    profile = build_profile(sample_frame([
        {"Invoice": "C1", "Quantity": "1"},
        {"Invoice": "2", "Quantity": "-1"},
        {"Invoice": "C3", "Quantity": "-1"},
    ]))
    assert profile["signals"]["c_invoice"]["count"] == 2
    assert profile["signals"]["negative_quantity"]["count"] == 2
    assert profile["signals"]["c_invoice_nonnegative_quantity"]["count"] == 1
    assert profile["signals"]["non_c_negative_quantity"]["count"] == 1


def test_top_values_exclude_missing_and_ties_are_deterministic():
    values = pd.Series(["B", pd.NA, "A", "A ", "NA"], dtype="string")
    assert top_values(values) == [
        {"value": "A", "count": 1}, {"value": "A ", "count": 1},
        {"value": "B", "count": 1}, {"value": "NA", "count": 1},
    ]
