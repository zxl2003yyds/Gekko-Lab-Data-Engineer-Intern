# Olist MySQL 导入核验

MySQL 8.4.13；数据库 `olist`；规则 `olist-v1`。

本次操作：复用并重新验证；耗时 15.386 秒。

| 表 | 记录数 | 规范化值 SHA-256 |
| --- | --- | --- |
| customers | 99441 | 98a8fbe7637c8ebc4061ef88baa0dbdddb2b0b8d911b7e71a3c65027ccf1c232 |
| geolocation | 1000163 | de721b577c9d7c565b931dfb4e86006ff1654c68ec2a7a5e775b767c02b1f020 |
| order_items | 112650 | cf49778617c908ad27ff1d5e5901041a7eafad943aa838ed6202b3166e556664 |
| order_payments | 103886 | e994d1bf3170b87dd191cb35c64041b3fee096c413344cfcd012654100c34740 |
| order_reviews | 99224 | 86a4219e68e2dc01776003ecb800d7cc7b0f0390ab604846ce4d4ef71944e7c0 |
| orders | 99441 | 8e8f1cca76de16a10e1a747ca86d2e1169b0e0ee35154b72bee86edd49fba175 |
| product_category_name_translation | 71 | 73caf9f99ffe0279921e578a6ca6ad4017da5cf44641923bd0ed1f814a67dd39 |
| products | 32951 | 785ba3ee65357399e77fc26056580665f6435ed3841329fe21cef3349223dbd0 |
| sellers | 3095 | 3362e8797ad96be14ce4c00476c3eaaee1496ffaddacfa52f6d3eca5e0f3466d |

九份 CSV 均先验证固定版本表头和文件摘要。写入后按 `_source_row` 排序逐值回读，行数、空值计数和规范化值摘要全部一致。原始文件摘要与规范化值摘要的计算对象不同，不应互相比对。

空字符串存为 SQL NULL，其他文本不自动修剪或改写；金额使用 DECIMAL(14,2)，日期使用 DATETIME，ID 和邮编前缀使用字符串。经纬度按 DOUBLE 存储，保留浮点表示；CSV 原始文本未修改。

每表追加 `_source_row` 作为主键及来源记录号（不含表头）。商品、订单、客户、卖家和类别字典使用自然唯一键，订单明细/支付使用组合唯一键；reviews 的 review_id 和 geolocation 的邮编都不是唯一键，不去重、不强加唯一约束。

数据表使用 utf8mb4_0900_bin，保留大小写和重音差异；没有为了导入而丢弃孤立记录或添加跨表外键。业务关联质量将在对应题目中检查。

分批写入独立暂存表，全部通过后一起改名发布；再次运行验证并复用已有结果，不追加重复数据。现有表缺少清单、版本不符或内容改变时，报错而不覆盖。进程被强制终止可能留下带随机前缀的暂存表，需核对后清理。

复现：`python -m q2_sql_analysis.load_olist`；仅使用本机 .env 配置，密码不写入代码或报告。

发布语义参考：[MySQL RENAME TABLE](https://dev.mysql.com/doc/refman/8.4/en/rename-table.html)。
