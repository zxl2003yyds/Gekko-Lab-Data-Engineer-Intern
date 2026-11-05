-- 数学等价的预聚合版本：刻意保留原 SQL 的重复计收入和按明细加权评分。
-- 仅用于公平比较执行时间，不作为业务正确结果。
WITH selected_orders AS (
    SELECT o.order_id, c.customer_state
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
      AND o.order_purchase_timestamp >= '2017-01-01'
      AND LOWER(c.customer_city) LIKE '%sao%'
), items AS (
    SELECT oi.order_id, COUNT(*) AS item_rows, SUM(oi.price) AS item_revenue
    FROM order_items oi JOIN selected_orders s ON s.order_id = oi.order_id
    GROUP BY oi.order_id
), reviews AS (
    SELECT r.order_id, COUNT(*) AS review_rows,
           COUNT(r.review_score) AS valid_scores, SUM(r.review_score) AS score_sum
    FROM order_reviews r JOIN selected_orders s ON s.order_id = r.order_id
    GROUP BY r.order_id
)
SELECT s.customer_state, COUNT(*) AS orders,
       SUM(i.item_revenue * GREATEST(COALESCE(r.review_rows, 0), 1)) AS revenue,
       SUM(r.score_sum * GREATEST(COALESCE(i.item_rows, 0), 1)) /
       NULLIF(SUM(COALESCE(r.valid_scores, 0) * GREATEST(COALESCE(i.item_rows, 0), 1)), 0) AS avg_score
FROM selected_orders s
LEFT JOIN items i ON i.order_id = s.order_id
LEFT JOIN reviews r ON r.order_id = s.order_id
GROUP BY s.customer_state
ORDER BY revenue DESC;
