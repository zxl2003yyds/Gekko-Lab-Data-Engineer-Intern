"""验证订单粒度、金额口径、月份归属和真实 MySQL 聚合边界。"""

from decimal import Decimal
import os

import pytest
from sqlalchemy import text

from check_database import create_database_engine
from q2_sql_analysis.run_q22 import SQL_PATH, build_reference, verify_results


def order(order_id, status="delivered", purchased="2017-01-01 12:00:00", delivered="2017-01-03 12:00:00"):
    return {"order_id": order_id, "order_status": status, "order_purchase_timestamp": purchased,
            "order_delivered_customer_date": delivered}


def item(order_id, price, freight="0.00"):
    return {"order_id": order_id, "price": price, "freight_value": freight}


def ordinary_fixture():
    orders = [order("a", purchased="2017-01-31 12:00:00", delivered="2017-02-02 12:00:00"),
              order("b", delivered="2017-01-03 00:00:00"), order("c", status="canceled"),
              order("d", delivered=""), order("e", status="shipped", delivered=""),
              order("f", status="canceled", purchased="2017-02-01 12:00:00", delivered=""),
              order("g", status="unavailable", purchased="2017-02-02 12:00:00", delivered="")]
    items = [item("a", "100", "10"), item("a", "20", "2"), item("b", "5", "0.50"),
             item("c", "999", "99"), item("d", "1", "0.10")]
    return orders, items


def exceptional_fixture():
    orders = [order("no_items"), order("missing_price"), order("missing_freight"),
              order("negative", purchased="2017-03-02 12:00:00", delivered="2017-03-01 12:00:00"),
              order("free", purchased="2017-04-01 12:00:00", delivered="2017-04-01 12:00:00")]
    items = [item("missing_price", "", "1"), item("missing_freight", "1", ""),
             item("negative", "20", "2"), item("free", "0", "0"), item("orphan", "9", "9")]
    return orders, items


def test_reference_counts_orders_once_and_uses_purchase_month_and_freight():
    rows, diagnostics = build_reference(*ordinary_fixture())
    assert rows == [
        {"month": "2017-01", "total_orders": 5, "delivered_orders": 3, "canceled_orders": 1,
         "cancel_rate": Decimal("20.00"), "delivered_gmv": Decimal("138.60"), "avg_delivery_days": Decimal("1.75")},
        {"month": "2017-02", "total_orders": 2, "delivered_orders": 0, "canceled_orders": 1,
         "cancel_rate": Decimal("50.00"), "delivered_gmv": Decimal("0.00"), "avg_delivery_days": None},
    ]
    assert diagnostics["valid_delivery_orders"] == 2
    assert diagnostics["delivered_missing_dates"] == [{"order_id": "d", "month": "2017-01"}]
    assert diagnostics["orders_without_items_by_status"] == {"canceled": 1, "shipped": 1, "unavailable": 1}


def test_unknown_gmv_is_not_zero_and_negative_durations_do_not_pollute_mean():
    rows, diagnostics = build_reference(*exceptional_fixture())
    assert rows[0]["delivered_gmv"] is None
    assert rows[1]["avg_delivery_days"] is None
    assert rows[1]["delivered_gmv"] == Decimal("22")
    assert rows[2]["delivered_gmv"] == Decimal(0)
    assert rows[2]["avg_delivery_days"] == Decimal(0)
    assert len(diagnostics["unknown_gmv_orders"]) == 3
    assert diagnostics["orphan_item_rows"] == 1
    assert diagnostics["delivered_negative_durations"] == [{"order_id": "negative", "month": "2017-03"}]


@pytest.mark.parametrize("orders", [[order("a"), order("a")], [order("a", purchased="")]])
def test_missing_month_or_duplicate_order_is_rejected(orders):
    with pytest.raises(ValueError):
        build_reference(orders, [])


@pytest.mark.skipif(os.getenv("OLIST_TEST_MYSQL") != "1", reason="需启用本机 MySQL 临时表集成测试")
@pytest.mark.parametrize("fixture", [ordinary_fixture, exceptional_fixture, lambda: ([], [])])
def test_mysql_monthly_query_against_independent_reference(fixture):
    orders, items = fixture()
    expected, diagnostics = build_reference(orders, items)
    engine = create_database_engine()
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("CREATE TEMPORARY TABLE orders (order_id VARCHAR(32), order_status VARCHAR(20), order_purchase_timestamp DATETIME, order_delivered_customer_date DATETIME)")
            connection.exec_driver_sql("CREATE TEMPORARY TABLE order_items (order_id VARCHAR(32), price DECIMAL(14,2), freight_value DECIMAL(14,2))")
            if orders:
                connection.execute(text("INSERT INTO orders VALUES (:order_id, :order_status, :order_purchase_timestamp, :order_delivered_customer_date)"),
                                   [{key: value or None for key, value in row.items()} for row in orders])
            if items:
                connection.execute(text("INSERT INTO order_items VALUES (:order_id, :price, :freight_value)"),
                                   [{key: value or None for key, value in row.items()} for row in items])
            actual = [dict(row) for row in connection.execute(text(SQL_PATH.read_text())).mappings()]
            verify_results(actual, expected, diagnostics)
    finally:
        engine.dispose()
