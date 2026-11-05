# 工具与软件使用清单

以下记录实际参与本项目的工具及用途。Kafka、Debezium、ClickHouse、Redis 仅用于 Q5 设计讨论，不代表已在本项目部署。

| 工具 | 版本或范围 | 使用场景 | 替代方式 |
| --- | --- | --- | --- |
| AI 编程助手（Codex） | 底层模型版本未确认 | 协助代码、SQL、测试、报告、葡语样本分析与学习讲解；对话见 AI_LOG.md | 本人实现、代码审查与独立语言审核 |
| Google 翻译 | 本人确认使用，版本未记录 | 辅助理解 Q4 葡语评价并作出部分复核判断 | 具备葡英能力的审核者直接核对 |
| Python | 3.12.5，macOS Apple Silicon | 数据处理、运行入口与校验 | 其他兼容环境，需重新验证 |
| Git | 本机命令行 | 分支、差异与提交范围管理 | Git 图形客户端 |
| GitHub CLI | 2.103.3，官方 macOS arm64 发布包 | GitHub 设备授权、HTTPS Git 认证、账号核对及代码上传 | Git 凭据管理器，或已授权的 SSH 连接 |
| Chrome 浏览器 | 本机已登录会话，版本未记录 | 打开 GitHub 设备授权页，由本人确认授权；查看仓库与提交页面 | 其他受支持的浏览器 |
| Docker / Compose | 固定 MySQL 镜像摘要 | 隔离数据库及本地持久化卷 | 独立安装 MySQL 8 |
| MySQL | 实测 8.4.13 | 九表导入、SQL、窗口函数、EXPLAIN ANALYZE | 题目指定 MySQL，不以 SQLite 替代 |
| pandas | 3.1.0 | 画像、类型转换、分组、向量筛选、merge_asof | 标准库或其他数据框库 |
| NumPy | 2.5.4 | 数组、非有限值检查、匹配索引及金额核验 | Python 列表与数值函数 |
| PyArrow | 26.0.0 | 明确 schema 的 Parquet 压缩写入与回读 | 其他 Parquet 实现及类型校验 |
| SQLAlchemy / PyMySQL | 2.1.6 / 1.2.3 | DDL、连接、参数化批量写入与读取 | 直接数据库驱动 |
| cryptography | 50.0.2 | MySQL 认证支持 | 正确配置其他受支持的认证连接 |
| KaggleHub | 1.0.3 | 下载固定版本数据并复用缓存 | 手动下载同版本后校验哈希 |
| python-dotenv / PyYAML | 1.2.4 / 6.0.3 | 本机环境和容器配置 | 显式环境变量与标准格式解析 |
| pytest | 9.2.0 | 边界、失败保护、独立参照与数据库检查 | unittest 和明确记录的手工验证 |
| Python 标准库 | 随 Python 环境 | Decimal、CSV、JSON、正则、Unicode 映射、哈希、临时文件和原子替换 | 对应的第三方实现 |
| 官方文档与网页检索 | 下列资料 | 核对数据库、消息系统、分析引擎及词义 | 官方离线文档与本机实验 |

直接与间接运行依赖锁定在 requirements.txt。Q4 数据管道未调用外部模型 API；这与 AI 助手参与开发、本人使用 Google 翻译辅助复核是不同口径。

## GitHub 提交工具的使用边界

GitHub CLI 使用官方发布的 macOS arm64 安装包，下载后核对官方 SHA-256。通过设备授权流程登录，本人已在 GitHub 页面确认授权；登录状态检查显示凭据保存在系统 keyring 中。本清单不记录密码、令牌或设备授权码。

前六步的代码阶段按模块整理为 14 笔提交，推送到 `work/assessment`，并核对远端提交与本地一致。GitHub CLI 和浏览器用于提交与核验，不参与数据处理，也不是运行 `run_all.py` 的依赖。

## Google 翻译的实际使用边界

本人不认识葡萄牙语，在网页中完成了 11 条歧义样本的辅助判断，其中 9 条选择译文忠实、2 条未填写译文判断；工具名称于 2026-11-05 确认。具体翻译方向、逐条输入输出和操作步骤未记录。该过程不作为专业葡英审核、独立真值或总体准确率。

60 条完整英文译文的现有草稿由 AI 助手撰写。Google 翻译用于辅助复核，不表示全部译文均由本人翻译或已独立验收。

## 关键取舍

- Q2 使用真实 MySQL，并区分数学等价改写与业务口径修正。当前预聚合版本更慢，保留实测结果。
- Q3 以定点整数计算金额，输出再转规定的浮点类型；退货只循环较小的取消子集，并用独立算法核验。
- Q4 使用规则、原文证据及显式待复核状态，公开低召回和参考标签偏差。
- 配置与密码、原始数据、下载缓存、逐行审计和学习材料保留在本地。

## 辅助工具

数据准备阶段曾通过 Stripe Directory 检查数据来源入口，实际下载由 KaggleHub 完成，未购买服务或开通云资源。学习 PDF 使用本地 ReportLab 制作，并用 pypdf、pdfplumber、Pillow 和 PDF 渲染工具检查；这些是学习材料工具，不是运行 pipeline 所需依赖。

## 使用过的资料

- [KaggleHub 版本化下载](https://github.com/Kaggle/kagglehub)
- [MySQL 执行计划](https://dev.mysql.com/doc/refman/8.4/en/explain.html)、[范围访问](https://dev.mysql.com/doc/refman/8.4/en/range-optimization.html)、[窗口函数](https://dev.mysql.com/doc/refman/8.4/en/window-functions.html)
- [Debezium Outbox](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [Kafka 交付语义](https://kafka.apache.org/43/design/design/)
- [ClickHouse ReplacingMergeTree](https://clickhouse.com/docs/reference/engines/table-engines/mergetree-family/replacingmergetree)
- [Priberam：mocho](https://dicionario.priberam.org/mocho)，结合 Olist 办公家具类别辅助词义判断
