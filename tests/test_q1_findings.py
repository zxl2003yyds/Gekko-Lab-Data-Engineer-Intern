"""验证金额精度、比例分母、特殊代码和单据聚合，避免业务统计失真。"""

import pandas as pd
import pytest

from q1_data_quality.investigate import build_findings, classify_code, prepare_frame


def frame(rows):
    defaults = {
        "Invoice": "100001", "StockCode": "12345A", "Description": "PRODUCT",
        "Quantity": "1", "InvoiceDate": "2011-01-01 12:00:00", "Price": "2.0",
        "Customer ID": "12345.0", "Country": "United Kingdom",
    }
    return pd.DataFrame([{**defaults, **row} for row in rows], dtype="string")


def test_exact_thousandth_amounts_and_signed_shares():
    result = build_findings(frame([
        {"Price": "0.001", "Quantity": "3", "StockCode": "PADS"},
        {"Price": "0.1", "Quantity": "-1", "StockCode": "D", "Invoice": "C100002"},
        {"Price": "0.2", "Quantity": "1"},
    ]))
    assert result["scale"] == 1000
    assert result["totals"]["net_units"] == 103
    assert result["totals"]["absolute_units"] == 303
    assert result["special_codes"]["net_units"] == -97
    assert result["special_codes"]["net_pct"] == pytest.approx(-97 / 103 * 100)
    assert result["special_codes"]["absolute_pct"] == pytest.approx(103 / 303 * 100)


def test_zero_net_total_has_undefined_share_not_zero_or_infinity():
    result = build_findings(frame([{"Quantity": "1"}, {"Quantity": "-1", "Invoice": "C100002"}]))
    assert result["totals"]["net_units"] == 0
    assert result["customers"]["groups"]["identified"]["net_pct"] is None


def test_nonstandard_codes_include_real_products_and_whitespace_variants():
    assert classify_code("47503J ", ["GARDEN TOOLS"])[0] == "商品代码空格变体"
    assert classify_code("DCGS0003", ["BOXED GLASS ASHTRAY", "ebay"])[0] == "实物商品候选"
    assert classify_code("DCGS0006", [""])[0] == "信息不足"
    assert classify_code("gift_0001_60", [""])[0] == "礼券条目（推测）"
    assert classify_code("PADS", ["PADS TO MATCH ALL CUSHIONS"])[0] == "实物商品候选"


def test_aov_aggregates_invoice_lines_and_keeps_missing_groups_separate():
    result = build_findings(frame([
        {"Invoice": "100001", "Price": "10", "Customer ID": ""},
        {"Invoice": "100001", "Price": "20", "Customer ID": ""},
        {"Invoice": "100002", "Price": "2", "Customer ID": ""},
        {"Invoice": "100003", "Price": "8", "Customer ID": "12345.0"},
    ]))
    missing = result["customers"]["groups"]["missing"]
    assert missing["rows"] == 3
    assert missing["candidate_invoices"]["invoices"] == 2
    assert missing["candidate_invoices"]["mean_amount"] == 16
    assert missing["candidate_invoices"]["mean_lines"] == 1.5


def test_mixed_identity_invoice_is_excluded_from_aov_not_from_amount_totals():
    result = build_findings(frame([
        {"Invoice": "100001", "Customer ID": "", "Price": "10"},
        {"Invoice": "100001", "Customer ID": "12345.0", "Price": "20"},
    ]))
    assert result["customers"]["ambiguous_invoices_excluded_from_aov"] == 1
    groups = result["customers"]["groups"]
    assert all(group["candidate_invoices"]["invoices"] == 0 for group in groups.values())
    assert sum(group["net_units"] for group in groups.values()) == result["totals"]["net_units"]


def test_extreme_pair_requires_identity_price_opposite_quantity_and_forward_time():
    result = build_findings(frame([
        {"Invoice": "100001", "Quantity": "100", "Price": "2.08"},
        {"Invoice": "C100002", "Quantity": "-100", "Price": "2.08", "InvoiceDate": "2011-01-01 12:12:00"},
        {"Invoice": "C100003", "Quantity": "-100", "Price": "2.08", "Customer ID": "", "InvoiceDate": "2011-01-01 12:12:00"},
        {"Invoice": "C100004", "Quantity": "-100", "Price": "2.09", "InvoiceDate": "2011-01-01 12:12:00"},
    ]))
    assert result["extremes"]["candidate_pairs"] == [{
        "positive_invoice": "100001", "negative_invoice": "C100002", "delay_minutes": 12.0, "net_units": 0,
    }]


def test_invalid_amount_inputs_do_not_silently_disappear_from_totals():
    with pytest.raises(ValueError, match="缺失/无法解析"):
        prepare_frame(frame([{"Price": "bad"}]))
