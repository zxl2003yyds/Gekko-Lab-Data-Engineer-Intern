-- 修正业务口径：商品收入每单只累计一次，评分每单只取最新一条。
-- 保留原题 price-only 口径；这里不是 Q2.2 的含运费 GMV。
WITH selected_orders AS (
    SELECT o.order_id, c.customer_state
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
      AND o.order_purchase_timestamp >= '2017-01-01'
      AND LOWER(c.customer_city) LIKE '%sao%'
), items AS (
    SELECT oi.order_id, SUM(oi.price) AS order_revenue
    FROM order_items oi JOIN selected_orders s ON s.order_id = oi.order_id
    GROUP BY oi.order_id
), reviews AS (
    SELECT r.order_id, r.review_score,
           ROW_NUMBER() OVER (PARTITION BY r.order_id ORDER BY
               r.review_answer_timestamp DESC, r.review_creation_date DESC,
               r.review_id DESC, r._source_row DESC) AS choice
    FROM order_reviews r JOIN selected_orders s ON s.order_id = r.order_id
)
SELECT s.customer_state, COUNT(*) AS orders,
       SUM(i.order_revenue) AS revenue, AVG(r.review_score) AS avg_score
FROM selected_orders s
LEFT JOIN items i ON i.order_id = s.order_id
LEFT JOIN reviews r ON r.order_id = s.order_id AND r.choice = 1
GROUP BY s.customer_state
ORDER BY revenue DESC;
