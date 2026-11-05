-- 与 Q2.2 一致：GMV 仅计 delivered，含商品金额及运费；订单数/取消率包含所有状态。
-- 客户按 customer_unique_id 去重；多卖家订单在每位参与卖家下计一次。
WITH review_candidates AS (
    SELECT r.*,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY review_answer_timestamp DESC, review_creation_date DESC,
                     review_id DESC, _source_row DESC
        ) AS review_choice
    FROM order_reviews AS r
), seller_orders AS (
    SELECT order_id, seller_id, SUM(price + freight_value) AS seller_order_gmv
    FROM order_items
    GROUP BY order_id, seller_id
), seller_metrics AS (
    SELECT
        so.seller_id,
        s.seller_state,
        SUM(CASE WHEN o.order_status = 'delivered' THEN so.seller_order_gmv ELSE 0 END) AS gmv_2017,
        COUNT(*) AS order_count,
        COUNT(DISTINCT c.customer_unique_id) AS unique_customers,
        ROUND(AVG(r.review_score), 2) AS avg_review_score,
        ROUND(100.0 * AVG(CASE
            WHEN o.order_status = 'delivered'
             AND o.order_delivered_customer_date IS NOT NULL
             AND o.order_estimated_delivery_date IS NOT NULL
            THEN CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 ELSE 0 END
            ELSE NULL END), 2) AS late_delivery_rate,
        ROUND(100.0 * SUM(CASE WHEN o.order_status = 'canceled' THEN 1 ELSE 0 END) / COUNT(*), 2) AS cancel_rate
    FROM seller_orders AS so
    JOIN orders AS o ON o.order_id = so.order_id
    LEFT JOIN sellers AS s ON s.seller_id = so.seller_id
    LEFT JOIN customers AS c ON c.customer_id = o.customer_id
    LEFT JOIN review_candidates AS r ON r.order_id = so.order_id AND r.review_choice = 1
    WHERE o.order_purchase_timestamp >= '2017-01-01'
      AND o.order_purchase_timestamp < '2018-01-01'
    GROUP BY so.seller_id, s.seller_state
), ranked_sellers AS (
    SELECT *, RANK() OVER (PARTITION BY seller_state ORDER BY gmv_2017 DESC) AS state_rank
    FROM seller_metrics
)
SELECT seller_id, seller_state, gmv_2017, order_count, unique_customers,
       avg_review_score, late_delivery_rate, cancel_rate, state_rank
FROM ranked_sellers
ORDER BY gmv_2017 DESC, seller_id
LIMIT 20;
