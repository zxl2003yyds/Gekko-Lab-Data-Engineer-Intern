-- 先区分原始类别缺失，再查找没有可用英文翻译的具名类别。
-- NOT EXISTS 避免重复的翻译行把商品计数放大；NULL/空白英文均不算有效翻译。
SELECT
    p.product_category_name,
    COUNT(*) AS product_count,
    CASE
        WHEN NULLIF(TRIM(p.product_category_name), '') IS NULL
            THEN 'missing_source_category'
        ELSE 'missing_english_translation'
    END AS gap_type
FROM products AS p
WHERE NULLIF(TRIM(p.product_category_name), '') IS NULL
   OR NOT EXISTS (
        SELECT 1
        FROM product_category_name_translation AS t
        WHERE t.product_category_name = p.product_category_name
          AND NULLIF(TRIM(t.product_category_name_english), '') IS NOT NULL
    )
GROUP BY p.product_category_name
ORDER BY product_count DESC, p.product_category_name;
