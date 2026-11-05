"""验证业务边界、独立匹配参照、Parquet 类型与失败时的输出保护。"""

import json
import random

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from q3_etl_pipeline import pipeline as p


def raw_frame(rows):
    defaults = {
        "Invoice": "100001", "StockCode": "12345A", "Description": "PRODUCT",
        "Quantity": "5", "InvoiceDate": "2011-01-01 12:00:00", "Price": "2.0",
        "Customer ID": "00123.0", "Country": "United Kingdom",
    }
    return pd.DataFrame([{**defaults, **row} for row in rows], dtype="string")


def prepare(rows):
    source, scale, audit = p.normalize_data(raw_frame(rows))
    sales, returns, classification = p.filter_real_sales(source)
    reference = pd.Timestamp(audit["reference_date"])
    features = p.compute_rfm(sales, reference, scale)
    matched = p.match_returns(sales, returns)
    return source, sales, features, matched, reference, scale, classification


def test_normalization_preserves_identifier_zeroes_case_precision_and_duplicates():
    original = raw_frame([
        {"StockCode": " 47503j ", "Price": "0.001", "Quantity": "3"},
        {"StockCode": " 47503j ", "Price": "0.001", "Quantity": "3"},
        {"Customer ID": "   "},
    ])
    snapshot = original.copy(deep=True)
    source, scale, audit = p.normalize_data(original)
    pd.testing.assert_frame_equal(original, snapshot)
    assert source["customer_id"].iloc[0] == "00123"
    assert pd.isna(source["customer_id"].iloc[2])
    assert source["stock_code"].iloc[0] == "47503j"
    assert scale == 1000 and source["amount_units"].iloc[0] == 3
    assert audit["raw_duplicate_excess"] == 1
    json.dumps(audit, allow_nan=False)
    sales, _, _ = p.filter_real_sales(source)
    assert len(sales) == 3


def test_classification_keeps_goods_exceptions_and_every_cancellation():
    result = prepare([
        {}, {"StockCode": "DCGS0003"}, {"StockCode": "PADS", "Price": "0.001"},
        {"StockCode": "POST"}, {"StockCode": "DCGS0006"},
        {"Invoice": "A100001", "StockCode": "B", "Price": "-9"},
        {"Invoice": "C100002", "StockCode": "M", "Quantity": "1"},
        {"Invoice": "C100003", "Customer ID": "", "Quantity": "-5"},
        {"Price": "0"}, {"Quantity": "-5"},
    ])
    source, sales, features, returns, reference, scale, classification = result
    assert sales["source_row"].tolist() == [1, 2, 3]
    assert returns["source_row"].tolist() == [7, 8]
    assert returns["match_reason"].tolist() == ["non_negative_cancellation", "missing_customer"]
    assert sum(item["rows"] for item in classification) == len(source)
    assert sum(item["amount_units"] for item in classification) == source["amount_units"].sum()
    assert source["classification_reason"].notna().all()
    p.validate_output(source, sales, features, returns, reference, scale)


def test_rfm_uses_raw_last_day_distinct_invoices_and_country_votes():
    rows = [{"Country": "Z", "Price": "1", "Quantity": "1"}] * 4 + [
        {"Invoice": "100002", "Country": "A", "StockCode": "22222", "InvoiceDate": "2011-01-02 15:00:00", "Price": "3", "Quantity": "2"},
        {"Customer ID": "00456.0", "Country": "B", "Invoice": "100003"},
        {"Customer ID": "", "Invoice": "100004"},
        {"Invoice": "A100005", "InvoiceDate": "2011-01-10 12:00:00"},
    ]
    source, sales, features, returns, reference, scale, _ = prepare(rows)
    customer = features.set_index("customer_id").loc["00123"]
    assert customer["recency_days"] == 8
    assert customer["frequency"] == 2
    assert customer["monetary"] == 10
    assert customer["unique_products"] == 2
    assert customer["country"] == "A"  # 两张发票各一票，不能按五条明细加权。
    assert not customer["is_one_time_buyer"]
    assert features.set_index("customer_id").loc["00456", "is_one_time_buyer"]
    assert len(features) == 2 and len(sales) == 7
    assert customer["first_purchase_date"] == pd.Timestamp("2011-01-01")
    p.validate_output(source, sales, features, returns, reference, scale)


def test_nearest_unused_sale_strict_time_and_tie_break():
    source, sales, features, returns, reference, scale, _ = prepare([
        {"Invoice": "100001"},
        {"Invoice": "100002", "InvoiceDate": "2011-01-02 12:00:00"},
        {"Invoice": "100003", "InvoiceDate": "2011-01-02 12:00:00"},
        {"Invoice": "C200001", "Quantity": "-5", "InvoiceDate": "2011-01-02 12:00:00"},
        {"Invoice": "C200002", "Quantity": "-5", "InvoiceDate": "2011-01-03 12:00:00", "Price": "3"},
        {"Invoice": "C200003", "Quantity": "-5", "InvoiceDate": "2011-01-03 12:00:00"},
        {"Invoice": "C200004", "Quantity": "-5", "InvoiceDate": "2011-01-04 12:00:00"},
        {"Invoice": "100004", "InvoiceDate": "2011-01-05 12:00:00"},
    ])
    assert returns["matched_source_row"].fillna(-1).tolist() == [1, 3, 2, -1]
    assert returns["match_reason"].iloc[-1] == "prior_candidates_used"
    validation = p.validate_output(source, sales, features, returns, reference, scale)
    assert validation["price_different_matches"] == 1


def test_matching_does_not_cross_customers_products_quantities_or_fill_anonymous():
    _, _, _, returns, _, _, _ = prepare([
        {"Quantity": "10"},
        {"Quantity": "5", "Customer ID": "99999.0"},
        {"Quantity": "5", "StockCode": "99999"},
        {"Quantity": "5", "Customer ID": ""},
        {"Invoice": "C200001", "Quantity": "-5", "InvoiceDate": "2011-01-02 12:00:00"},
        {"Invoice": "C200002", "Quantity": "-5", "InvoiceDate": "2011-01-03 12:00:00"},
        {"Invoice": "C200003", "Quantity": "-5", "Customer ID": "", "InvoiceDate": "2011-01-04 12:00:00"},
    ])
    assert returns["matched_original_invoice"].isna().all()
    assert returns["match_reason"].tolist() == ["no_prior_exact_quantity", "no_prior_exact_quantity", "missing_customer"]


def test_duplicate_source_lines_are_separate_available_sales():
    _, _, _, returns, _, _, _ = prepare([
        {}, {},
        {"Invoice": "C200001", "Quantity": "-5", "InvoiceDate": "2011-01-02 12:00:00"},
        {"Invoice": "C200001", "Quantity": "-5", "InvoiceDate": "2011-01-02 12:00:00"},
    ])
    assert returns["matched_source_row"].tolist() == [2, 1]


def test_optimized_matching_agrees_with_independent_small_history_search():
    rng = random.Random(503)
    rows = []
    for number in range(500):
        is_return = rng.random() < 0.48
        rows.append({
            "Invoice": ("C" if is_return else "") + str(100000 + number),
            "Customer ID": rng.choice(["00123", "00456", "00789"]),
            "StockCode": rng.choice(["12345A", "22222"]),
            "Quantity": str(rng.choice([1, 2, 5]) * (-1 if is_return else 1)),
            "InvoiceDate": f"2011-01-{rng.randint(1, 10):02d} 12:00:00",
        })
    source, sales, features, returns, reference, scale, _ = prepare(rows)
    used, expected = set(), []
    sale_records = sales.to_dict("records")
    # 独立、易读的暴力参照仅用于小样本测试，不参与全量流水线。
    for row in returns.to_dict("records"):
        candidates = [sale for sale in sale_records if
                      sale["source_row"] not in used
                      and sale["customer_id"] == row["customer_id"]
                      and sale["stock_code"] == row["stock_code"]
                      and sale["quantity"] == -row["quantity"]
                      and sale["invoice_datetime"] < row["invoice_datetime"]]
        if candidates:
            selected = max(candidates, key=lambda sale: (sale["invoice_datetime"], sale["source_row"]))
            used.add(selected["source_row"])
            expected.append(selected["source_row"])
        else:
            expected.append(-1)
    assert returns["matched_source_row"].fillna(-1).tolist() == expected
    p.validate_output(source, sales, features, returns, reference, scale)


@pytest.mark.parametrize("rows", [[{"StockCode": "POST"}], [{}]])
def test_empty_outputs_keep_explicit_parquet_types(tmp_path, rows):
    source, sales, features, returns, reference, scale, _ = prepare(rows)
    p.validate_output(source, sales, features, returns, reference, scale)
    frames = p.output_frames(sales, features, returns)
    p.write_outputs(frames, tmp_path / "outputs")
    for name, (frame, schema) in frames.items():
        restored = pq.read_table(tmp_path / "outputs" / f"{name}.parquet")
        assert restored.schema.equals(schema, check_metadata=True)
        assert restored.num_rows == len(frame)


def test_invalid_later_file_does_not_replace_existing_outputs(tmp_path):
    destination = tmp_path / "outputs"
    destination.mkdir()
    old = destination / "first.parquet"
    old.write_bytes(b"previous validated output")
    frames = {
        "first": (pd.DataFrame({"n": [1]}), pa.schema([("n", pa.int64())])),
        "second": (pd.DataFrame({"n": ["bad"]}), pa.schema([("n", pa.int64())])),
    }
    with pytest.raises((pa.ArrowInvalid, pa.ArrowTypeError)):
        p.write_outputs(frames, destination)
    assert old.read_bytes() == b"previous validated output"
    assert not (destination / "second.parquet").exists()


def test_validation_rejects_reusing_a_sale():
    source, sales, features, returns, reference, scale, _ = prepare([
        {}, {},
        {"Invoice": "C200001", "Quantity": "-5", "InvoiceDate": "2011-01-02 12:00:00"},
        {"Invoice": "C200002", "Quantity": "-5", "InvoiceDate": "2011-01-03 12:00:00"},
    ])
    returns.loc[:, "matched_source_row"] = 1
    with pytest.raises(AssertionError, match="不能匹配两次"):
        p.validate_output(source, sales, features, returns, reference, scale)


def test_pipeline_repeatability_unmatched_log_and_failure_cleanup(tmp_path, monkeypatch):
    input_path = tmp_path / "source.csv"
    input_path.write_text("fixture\n")
    fixture = raw_frame([
        {},
        {"Invoice": "C200001", "Quantity": "-5", "InvoiceDate": "2011-01-02 12:00:00"},
        {"Invoice": "C200002", "Quantity": "-1", "InvoiceDate": "2011-01-03 12:00:00"},
    ])
    monkeypatch.setattr(p, "load_data", lambda path: fixture.copy(deep=True))
    args = (input_path, tmp_path / "outputs", tmp_path / "report.md", tmp_path / "pipeline.log", tmp_path / "audit")
    before = list(p.LOGGER.handlers)
    first = p.run_pipeline(*args)
    second = p.run_pipeline(*args)
    assert first["outputs"] == second["outputs"]
    assert args[3].read_text().count("UNMATCHED source_row=") == 1
    excluded = pd.read_parquet(args[4] / "excluded_rows.parquet")
    assert excluded["classification_reason"].eq("cancellation").all()
    assert p.LOGGER.handlers == before

    def fail_load(path):
        raise ValueError("fixture checksum mismatch")

    monkeypatch.setattr(p, "load_data", fail_load)
    with pytest.raises(ValueError, match="checksum mismatch"):
        p.run_pipeline(*args)
    assert "失败：读取与校验输入" in args[3].read_text()
    assert p.LOGGER.handlers == before
    assert p.sha256_file(args[1] / "sales_facts.parquet") == first["outputs"]["sales_facts"]["sha256"]
