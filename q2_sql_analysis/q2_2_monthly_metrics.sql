-- 月份按下单时间；cancel_rate 为百分数（0–100），金额为 BRL。
-- 先把商品明细聚合为每订单一行，避免订单数和配送天数被商品件数加权。
WITH item_totals AS (
    SELECT
        order_id,
        SUM(price + freight_value) AS order_gmv,
        SUM(CASE WHEN price IS NULL OR freight_value IS NULL THEN 1 ELSE 0 END)
            AS invalid_amount_rows
    FROM order_items
    GROUP BY order_id
), order_level AS (
    SELECT
        DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS order_month,
        o.order_status,
        i.order_gmv,
        CASE
            WHEN o.order_status = 'delivered'
             AND (i.order_id IS NULL OR i.invalid_amount_rows > 0)
                THEN 1
            ELSE 0
        END AS unknown_delivered_gmv,
        CASE
            WHEN o.order_status = 'delivered'
             AND o.order_delivered_customer_date >= o.order_purchase_timestamp
                THEN TIMESTAMPDIFF(
                    SECOND, o.order_purchase_timestamp, o.order_delivered_customer_date
                )
            ELSE NULL
        END AS delivery_seconds
    FROM orders AS o
    LEFT JOIN item_totals AS i ON i.order_id = o.order_id
)
SELECT
    order_month AS `month`,
    COUNT(*) AS total_orders,
    SUM(CASE WHEN order_status = 'delivered' THEN 1 ELSE 0 END) AS delivered_orders,
    SUM(CASE WHEN order_status = 'canceled' THEN 1 ELSE 0 END) AS canceled_orders,
    ROUND(
        100.0 * SUM(CASE WHEN order_status = 'canceled' THEN 1 ELSE 0 END) / COUNT(*), 2
    ) AS cancel_rate,
    -- 已送达订单若缺金额，整月 GMV 标为未知；不把缺失金额冒充为零。
    CASE
        WHEN SUM(unknown_delivered_gmv) > 0 THEN NULL
        ELSE SUM(CASE WHEN order_status = 'delivered' THEN order_gmv ELSE 0 END)
    END AS delivered_gmv,
    -- AVG 忽略 NULL；没有有效配送时间时返回 NULL。保留秒精度后再换算为天。
    ROUND(AVG(delivery_seconds) / 86400.0, 2) AS avg_delivery_days
FROM order_level
GROUP BY order_month
ORDER BY order_month;
