"""用小型手算案例检查多对多放大、订单粒度、最新评分及排名。"""
from decimal import Decimal
import os
import re
import uuid

import pytest
from sqlalchemy import text

from check_database import create_database_engine
from download_data import ROOT
from q2_sql_analysis.run_q23 import calculate_reference, SQL_PATH


def seller_fixture():
    orders = [
        dict(order_id='a', customer_id='c1', order_status='delivered', order_purchase_timestamp='2017-01-01 00:00:00', order_delivered_customer_date='2017-01-03 00:00:00', order_estimated_delivery_date='2017-01-02 00:00:00'),
        dict(order_id='b', customer_id='c2', order_status='canceled', order_purchase_timestamp='2017-02-01 00:00:00', order_delivered_customer_date='', order_estimated_delivery_date=''),
        dict(order_id='c', customer_id='c3', order_status='delivered', order_purchase_timestamp='2017-12-31 23:59:59', order_delivered_customer_date='', order_estimated_delivery_date=''),
        dict(order_id='d', customer_id='c3', order_status='delivered', order_purchase_timestamp='2018-01-01 00:00:00', order_delivered_customer_date='', order_estimated_delivery_date=''),
    ]
    items = [dict(order_id=o, seller_id=s, price=p, freight_value=f) for o,s,p,f in [
        ('a','s1','10','1'), ('a','s1','20','2'), ('a','s2','30','3'), ('b','s1','999','0'), ('c','s3','10','1'), ('d','s3','9999','0')]]
    reviews = [dict(order_id=o, review_id=r, review_score=v, review_creation_date=t, review_answer_timestamp=t) for o,r,v,t in [
        ('a','r1','1','2017-01-04 00:00:00'), ('a','r2','5','2017-01-05 00:00:00'), ('b','r3','1','2017-02-05 00:00:00')]]
    customers = [dict(customer_id=c, customer_unique_id=u) for c,u in [('c1','u1'),('c2','u1'),('c3','u2')]]
    sellers = [dict(seller_id=s, seller_state='SP') for s in ['s1','s2','s3']]
    return orders, items, reviews, customers, sellers


def assert_sellers(rows):
    assert [r['seller_id'] for r in rows] == ['s1','s2','s3']
    assert [r['gmv_2017'] for r in rows] == [Decimal(33), Decimal(33), Decimal(11)]
    assert [r['state_rank'] for r in rows] == [1,1,3]
    assert [r['order_count'] for r in rows] == [2,1,1]
    assert [r['unique_customers'] for r in rows] == [1,1,1]
    assert [r['avg_review_score'] for r in rows] == [Decimal(3),Decimal(5),None]
    assert [r['late_delivery_rate'] for r in rows] == [Decimal(100),Decimal(100),None]
    assert [r['cancel_rate'] for r in rows] == [Decimal(50),Decimal(0),Decimal(0)]


def test_seller_reference_has_hand_calculated_results():
    rows, audit = calculate_reference(*seller_fixture())
    assert_sellers(rows)
    assert audit['all_seller_gmv'] == 77
    assert audit['seller_order_pairs'] == 4


def insert_rows(conn, table, rows):
    columns = list(rows[0])
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(':'+c for c in columns)})"
    conn.execute(text(sql), [{k: v if v != '' else None for k,v in r.items()} for r in rows])


mysql = pytest.mark.skipif(os.getenv('OLIST_TEST_MYSQL') != '1', reason='需启用本机 MySQL 临时表集成测试')


@mysql
def test_seller_sql_handles_shared_orders_latest_reviews_ties_and_year_boundary():
    engine = create_database_engine()
    try:
        with engine.connect() as c:
            c.exec_driver_sql('CREATE TEMPORARY TABLE orders (order_id VARCHAR(32), customer_id VARCHAR(32), order_status VARCHAR(20), order_purchase_timestamp DATETIME, order_delivered_customer_date DATETIME, order_estimated_delivery_date DATETIME)')
            c.exec_driver_sql('CREATE TEMPORARY TABLE order_items (order_id VARCHAR(32), seller_id VARCHAR(32), price DECIMAL(14,2), freight_value DECIMAL(14,2))')
            c.exec_driver_sql('CREATE TEMPORARY TABLE order_reviews (order_id VARCHAR(32), review_id VARCHAR(32), review_score INT, review_creation_date DATETIME, review_answer_timestamp DATETIME, _source_row INT)')
            c.exec_driver_sql('CREATE TEMPORARY TABLE customers (customer_id VARCHAR(32), customer_unique_id VARCHAR(32))')
            c.exec_driver_sql('CREATE TEMPORARY TABLE sellers (seller_id VARCHAR(32), seller_state CHAR(2))')
            orders, items, reviews, customers, sellers = seller_fixture()
            for name, rows in [('orders',orders),('order_items',items),('order_reviews',[dict(r,_source_row=i) for i,r in enumerate(reviews,1)]),('customers',customers),('sellers',sellers)]:
                insert_rows(c, name, rows)
            rows = [dict(r) for r in c.execute(text(SQL_PATH.read_text())).mappings()]
            assert_sellers(rows)
            assert rows == calculate_reference(*seller_fixture())[0]
    finally:
        engine.dispose()


@mysql
def test_query_rewrite_preserves_original_fanout_but_business_fix_removes_it():
    engine = create_database_engine()
    # 同一临时表经多个 CTE 重开会失败，使用唯一命名、测试后清理的表。
    prefix = '_q24_test_' + uuid.uuid4().hex[:12] + '_'
    names = ['orders', 'customers', 'order_items', 'order_reviews']
    def scoped(sql):
        sql = sql.replace('CREATE TEMPORARY TABLE', 'CREATE TABLE')
        for name in names:
            sql = re.sub(r'\b(FROM|JOIN|TABLE)\s+' + name + r'\b',
                         lambda match: match.group(1) + ' ' + prefix + name, sql, flags=re.I)
        return sql
    try:
        with engine.connect() as c:
            c.exec_driver_sql(scoped('CREATE TEMPORARY TABLE orders (order_id VARCHAR(32), customer_id VARCHAR(32), order_status VARCHAR(20), order_purchase_timestamp DATETIME)'))
            c.exec_driver_sql(scoped('CREATE TEMPORARY TABLE customers (customer_id VARCHAR(32), customer_state CHAR(2), customer_city VARCHAR(100))'))
            c.exec_driver_sql(scoped('CREATE TEMPORARY TABLE order_items (order_id VARCHAR(32), price DECIMAL(14,2))'))
            c.exec_driver_sql(scoped('CREATE TEMPORARY TABLE order_reviews (order_id VARCHAR(32), review_id VARCHAR(32), review_score INT, review_creation_date DATETIME, review_answer_timestamp DATETIME, _source_row INT)'))
            insert_rows(c,prefix+'orders',[dict(order_id=o,customer_id='x',order_status='delivered',order_purchase_timestamp='2017-01-01') for o in 'abcd'])
            insert_rows(c,prefix+'customers',[dict(customer_id='x',customer_state='SP',customer_city='SAO PAULO')])
            insert_rows(c,prefix+'order_items',[dict(order_id=o,price=p) for o,p in [('a',10),('a',20),('b',7)]])
            insert_rows(c,prefix+'order_reviews',[dict(order_id=o,review_id=str(i),review_score=v,review_creation_date=f'2017-01-0{i}',review_answer_timestamp=f'2017-01-0{i}',_source_row=i) for i,(o,v) in enumerate([('a',1),('a',5),('b',None),('c',2)],1)])
            rows = {}
            for name in ['original','equivalent','corrected']:
                sql = (ROOT/f'q2_sql_analysis/q2_4_{name}.sql').read_text()
                rows[name] = [dict(r) for r in c.execute(text(scoped(sql))).mappings()]
            assert rows['original'] == rows['equivalent']
            assert rows['original'][0]['orders'] == rows['corrected'][0]['orders'] == 4
            assert rows['original'][0]['revenue'] == Decimal(67)
            assert rows['corrected'][0]['revenue'] == Decimal(37)
            assert rows['original'][0]['avg_score'] == Decimal('2.8')
            assert rows['corrected'][0]['avg_score'] == Decimal('3.5')
    finally:
        try:
            with engine.begin() as cleanup:
                for name in names:
                    cleanup.exec_driver_sql(f"DROP TABLE IF EXISTS {prefix}{name}")
        finally:
            engine.dispose()
