"""显式 MySQL 类型和表粒度；保留重复地理位置、多次评价和 CSV 来源行号。"""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, JSON, MetaData, Numeric, String, Table, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import DOUBLE

LOADER_VERSION = "olist-v1"
MANIFEST_NAME = "_olist_import_manifest"
OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_bin"}
TABLE_FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "product_category_name_translation": "product_category_name_translation.csv",
}
UNIQUE_KEYS = {
    "customers": ["customer_id"], "orders": ["order_id"], "products": ["product_id"],
    "sellers": ["seller_id"], "product_category_name_translation": ["product_category_name"],
    "order_items": ["order_id", "order_item_id"], "order_payments": ["order_id", "payment_sequential"],
}
INDEXES = {
    "customers": ["customer_unique_id"], "geolocation": ["geolocation_zip_code_prefix"],
    "orders": ["customer_id"], "order_items": ["product_id", "seller_id"],
    "order_reviews": ["order_id", "review_id"], "products": ["product_category_name"],
}
INTEGER_COLUMNS = {
    "order_item_id", "payment_sequential", "payment_installments", "review_score",
    "product_name_lenght", "product_description_lenght", "product_photos_qty",
    "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm",
}
MONEY_COLUMNS = {"price", "freight_value", "payment_value"}
DATE_COLUMNS = {
    "shipping_limit_date", "review_creation_date", "review_answer_timestamp", "order_purchase_timestamp",
    "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date",
}
FLOAT_COLUMNS = {"geolocation_lat", "geolocation_lng"}


def column_type(name):
    if name in INTEGER_COLUMNS:
        return Integer()
    if name in MONEY_COLUMNS:
        return Numeric(14, 2, asdecimal=True)
    if name in DATE_COLUMNS:
        return DateTime()
    if name in FLOAT_COLUMNS:
        return DOUBLE(asdecimal=False)
    if name.endswith("_id"):
        return String(32)
    if name.endswith("_zip_code_prefix"):
        return String(5)
    if name.endswith("_state"):
        return String(2)
    if name.endswith("_city"):
        return String(100)
    if name.startswith("review_comment_"):
        return Text()
    return String(100)


def build_tables(specifications: dict, prefix: str = "") -> tuple[dict, Table]:
    metadata = MetaData()
    tables = {}
    for name, filename in TABLE_FILES.items():
        unique = UNIQUE_KEYS.get(name, [])
        columns = [Column("_source_row", BigInteger, primary_key=True, autoincrement=False)]
        columns += [Column(field, column_type(field), nullable=field not in unique)
                    for field in specifications[filename]["columns"]]
        constraints = [UniqueConstraint(*unique)] if unique else []
        table = Table(prefix + name, metadata, *columns, *constraints, **OPTIONS)
        for field in INDEXES.get(name, []):
            Index("ix_" + field, table.c[field])
        tables[name] = table
    manifest = Table(prefix + MANIFEST_NAME, metadata,
                     Column("table_name", String(64), primary_key=True),
                     Column("source_file", String(128), nullable=False),
                     Column("source_sha256", String(64), nullable=False),
                     Column("typed_sha256", String(64), nullable=False),
                     Column("row_count", BigInteger, nullable=False),
                     Column("null_counts", JSON, nullable=False),
                     Column("loader_version", String(32), nullable=False), **OPTIONS)
    return tables, manifest
