# Q2.1 商品类别翻译完整性

MySQL 8.4.13 上实际执行 `q2_1_translation_gap.sql`；结果与独立读取 CSV 的 Counter 统计逐行一致。

| 原始类别 | 商品数 | 缺失类型 |
| --- | --- | --- |
| NULL（类别本身缺失） | 610 | missing_source_category |
| portateis_cozinha_e_preparadores_de_alimentos | 10 | missing_english_translation |
| pc_gamer | 3 | missing_english_translation |

共 **32,951** 个商品：**32,328** 个已有英文对照；**13** 个属于 **2** 个具名但缺少翻译的类别；另有 **610** 个连原始类别都缺失。三组互斥且合计等于全部商品。

## 如何理解这条 SQL

1. 从 products 出发，因为题目问的是实际商品使用了哪些类别。

2. 对每个商品检查翻译表，只有同名类别且英文不是 NULL/空白才算有对照。NOT EXISTS 保留找不到这种对照的商品，也避免重复翻译行放大商品数。

3. 原始类别为 NULL/空白时单列 missing_source_category；其余缺失标记为 missing_english_translation。按原始类别分组后用 COUNT(*) 计商品数。不能用 COUNT(product_category_name)，否则 NULL 组会被计成零。

题目目录提示“3 个未翻译类别”，本次数据确实返回三组，但其中一组是 NULL，不应称为第三个具名类别。缺少类别的商品不能仅靠翻译字典修复。

## 三种处理方案及利弊

| 方案 | 具体处理 | 优点 | 局限 |
| --- | --- | --- | --- |
| 保留缺失并回退展示 | 展示时具名类别用原葡文；无类别用“未分类”，源字段仍保留 NULL | 能立即运行、可追溯，不伪造翻译 | 展示语言不统一，缺失问题尚未修复 |
| 人工维护版本化补充字典 | 核对两个具名类别的业务含义后添加英文映射，记录来源、审核人与版本 | 数量少，审核成本可控，英文命名稳定 | 新类别需要持续维护；610 个无类别商品需另行补分类 |
| 自动生成候选并人工审核 | 翻译工具或语言模型生成具名类别的英文候选，审核通过再写补充字典 | 适合将来大量新类别，减少重复人工操作 | 可能误译或命名不一致，有调用及审核成本；不能从 NULL 推断真实类别 |

本次建议：原始表保持不变，分析展示可采用第一种回退方式；对两个具名缺口优先人工核实并维护补充字典。610 个无类别商品应向数据源补索商品类别，必要时另做有证据的分类流程。没有自动改写原始类别、执行机器翻译或调用付费 API。

## 复现与验证

```bash
python run_all.py --stage q2.1 --offline
# 或
python -m q2_sql_analysis.run_q21
```

首次执行将九表导入 MySQL；后续逐值核验并复用。测试还覆盖空英文、重复映射、大小写不同、NULL 类别、只有无效翻译和同时存在有效/无效翻译的情况。

SQL 语义参考：[MySQL EXISTS / NOT EXISTS](https://dev.mysql.com/doc/refman/8.4/en/exists-and-not-exists-subqueries.html)。
