"""覆盖损坏文件、原子替换及含换行的真实 CSV 等准备阶段边界。"""

import csv

import pytest

from download_data import install_file, sha256_file, validate_file
from inspect_data import inspect_file


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def test_rejects_valid_csv_with_changed_content(tmp_path):
    path = tmp_path / "orders.csv"
    write_csv(path, ["order_id"], [["001"]])
    specification = {"columns": ["order_id"], "sha256": sha256_file(path)}
    write_csv(path, ["order_id"], [["002"]])
    with pytest.raises(ValueError, match="校验值不符"):
        validate_file(path, specification)


def test_failed_replacement_preserves_existing_file(tmp_path):
    source, target = tmp_path / "source.csv", tmp_path / "target.csv"
    write_csv(target, ["order_id"], [["001"]])
    original = target.read_bytes()
    source.write_text("<html>download failed</html>", encoding="utf-8")
    with pytest.raises(ValueError, match="表头"):
        install_file(source, target, {"columns": ["order_id"]})
    assert target.read_bytes() == original
    assert {path.name for path in tmp_path.iterdir()} == {"source.csv", "target.csv"}


def test_inventory_counts_csv_records_not_physical_lines(tmp_path):
    path = tmp_path / "reviews.csv"
    columns = ["review_id", "review_comment_message", "review_creation_date"]
    write_csv(path, columns, [
        ["001", "primeira linha\nsegunda linha", "2017-01-01 00:00:00"],
        ["002", "", "not-a-date"],
        ["003", "NA", ""],
    ])
    result = inspect_file(path, {"columns": columns, "destination": "reviews.csv"})
    assert result["rows"] == 3
    assert result["missing"]["review_comment_message"] == 1
    assert result["date_ranges"]["review_creation_date"] == {
        "min": "2017-01-01T00:00:00", "max": "2017-01-01T00:00:00", "invalid": 1,
    }


def test_header_only_file_cannot_pass_inventory(tmp_path):
    path = tmp_path / "empty.csv"
    write_csv(path, ["order_id"], [])
    with pytest.raises(ValueError, match="没有数据"):
        inspect_file(path, {"columns": ["order_id"], "destination": "empty.csv"})


def test_inventory_reports_invalid_dates_as_failure_without_losing_counts(tmp_path, monkeypatch):
    import inspect_data
    path = tmp_path / "reviews.csv"
    columns = ["review_creation_date"]
    write_csv(path, columns, [["not-a-date"], [""], ["2017-01-01 00:00:00"]])
    spec = {"columns": columns, "destination": path.name}
    monkeypatch.setattr(inspect_data, "load_sources", lambda: {
        "fixture": {"handle": "fixture", "url": "fixture", "license": "fixture", "files": {path.name: spec}},
    })
    report = inspect_data.inspect_data(tmp_path, tmp_path / "inventory.json")
    assert len(report["errors"]) == 1
    assert "1 条非空日期无法解析" in report["errors"][0]
    result = report["datasets"]["fixture"]["files"][0]
    assert result["rows"] == 3 and result["missing"]["review_creation_date"] == 1
