# 项目说明与复现

本项目使用 Online Retail II 完成数据质量调查与 ETL，使用 Olist 完成 MySQL 分析和评价抽取。题目原文保留在 [README.md](README.md)。实现思路、自评与限制见 [REFLECTION.md](REFLECTION.md)，实际工具见 [TOOLS.md](TOOLS.md)，可见对话原文见 [AI_LOG.md](AI_LOG.md)。

## 版本与提交入口

答案位于 [`work/assessment` 分支](https://github.com/zxl2003yyds/Gekko-Lab-Data-Engineer-Intern/tree/work/assessment)。截至本轮文档整理，仓库默认分支仍是 `main`，尚未包含答案；请从工作分支查看或克隆。

2026-11-05 已先行上传 14 笔按模块组织的代码阶段提交，代码基线为 [`19e1db8ee1ad7a470943f8776e44ef712b9afc55`](https://github.com/zxl2003yyds/Gekko-Lab-Data-Engineer-Intern/commit/19e1db8ee1ad7a470943f8776e44ef712b9afc55)。该 hash 不包含本轮四份文档的收尾更新，不能当作完整交付的最终 hash。

正式交付以邮件所列的分支和包含完整文档的 commit hash 为准。交付前应核对远端分支与本地一致；复现指定版本时，使用邮件中的完整 commit hash。以下命令用于核对当前检出的分支与提交号：

```bash
git branch --show-current
git rev-parse HEAD
```

## 环境

- 已验证：macOS Apple Silicon、Python 3.12.5、MySQL 8.4.13。
- 建议使用 Python 3.12；`requirements.txt` 锁定直接及间接依赖，其他 Python 版本和操作系统尚未验证。
- Docker Compose 使用固定摘要的 MySQL 镜像，仅监听本机 `127.0.0.1:3307`，数据库为 `olist`。
- 首次安装和数据下载需要网络；数据齐备后可以离线运行。

## 从新检出的仓库运行

先克隆答案分支并进入项目目录：

```bash
git clone --branch work/assessment --single-branch https://github.com/zxl2003yyds/Gekko-Lab-Data-Engineer-Intern.git gekko-assessment
cd gekko-assessment
```

随后执行以下命令，确保 `python3` 指向 Python 3.12，且 Docker 已启动。GitHub CLI 只用于开发者登录和上传，不是克隆公开仓库或运行本项目的必需依赖。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python setup_local.py
docker compose up -d --wait
python check_database.py
python run_all.py
```

`setup_local.py` 生成本地随机数据库密码并写入权限为 `600` 的 `.env`，不会覆盖已有配置。`.env` 不提交到 Git。数据库卷与本项目隔离；修改 `.env` 不会自动修改已有数据库用户的密码。

`run_all.py` 下载缺失数据、核对表头与 SHA-256、导入 Olist、依次执行 Q1–Q4，并检查 Q1.3、Q5 和加分题文档。某模块失败会记录错误并继续其他独立模块，最终以非零退出码报告失败。文档检查只验证非空，退出码也不代表语义或人工验收结果。

### 固定数据版本

| 数据 | 来源版本 | 本地路径 |
| --- | --- | --- |
| Online Retail II | `mashlyn/online-retail-ii-uci/versions/3` | `data/online_retail_ii.csv` |
| Olist | `olistbr/brazilian-ecommerce/versions/2` | `data/olist/` 下九份 CSV |

文件清单、表头和哈希在 `data_sources.json`。已有文件通过校验时复用；内容不符时报错，不静默覆盖。只规范零售 CSV 的文件名，不改写原始数据。CSV 记录可能含内嵌换行，行数按 CSV 解析统计。

## 独立运行与验证

```bash
python run_all.py --stage prepare
python run_all.py --stage q1.1 --offline
python run_all.py --stage q1.2 --offline
python run_all.py --stage q2.1 --offline
python run_all.py --stage q2.2 --offline
python run_all.py --stage q2.3 --offline
python run_all.py --stage q2.4 --offline
python run_all.py --stage q3 --offline
python run_all.py --stage q4 --offline
python run_all.py --offline --check-db
python -m pytest -q
OLIST_TEST_MYSQL=1 python -m pytest -q
```

Q1 和 Q3 只依赖零售数据，Q4 直接读取评价 CSV；这些模块不需要 MySQL。Q2 使用真实 MySQL，首次调用会检查并导入九表。`q1.3`、`q5`、`bonus` 为文档检查阶段。默认测试跳过 MySQL 集成检查；最后一条命令通过 `OLIST_TEST_MYSQL=1` 启用这些检查，需要上述数据库环境。报告时应区分通过、失败与跳过。

导入使用暂存表，逐值回读比较行数、空值数和规范化内容摘要，全部通过后一起发布。重跑会核验并复用既有数据，不重复追加；对不受程序管理、版本不符或内容改变的同名表拒绝覆盖。

## 模块和主要产物

| 模块 | 实现及交付材料 | 主要口径 |
| --- | --- | --- |
| Q1 | `q1_data_quality/` 下画像、调查、策略及程序 | 保留原始记录；缺失、类型失败与异常分别统计 |
| Q2 | `q2_sql_analysis/` 下 SQL、结果、导入报告和执行计划 | 订单或卖家订单粒度；GMV 口径与配送分母显式定义 |
| Q3 | `pipeline.py`、`rules.py`、`validation_report.md` | 正向商品销售、客户 RFM、全部 C 取消记录 |
| Q4 | 抽取程序、Prompt、JSON、成本与评估报告、语义样本 | 本地规则基线；不发起外部模型 API 调用 |
| Q5 | `q5_system_design/real_time_pipeline_design.md` | 实时架构设计，未部署 Kafka 等组件 |
| 加分题 | `bonus/` 下协作分析与业务建议 | 真实协作过程；收益估计与已测事实区分 |

Q3 本地生成 `sales_facts.parquet`（1,037,021 行）、`customer_features.parquet`（5,852 行）和 `returns_log.parquet`（19,494 行）。RFM 基准日为 2011-12-09，金额为未扣退款的正向商品发生额。6,303 条取消记录匹配成功；未匹配记录保留 NULL 和原因。详细来源、映射与运行清单保存在 `.local/q3/`。

Q4 保留全部 22,754 条低分评价；60 条固定样本的参考标签由同一 AI 助手提供，类别精确率 82.35%、召回率 41.79% 不能解释为独立人工准确率。60 条整句英译和语义草稿另存 `semantic_review/`，不覆盖冻结的自动评估结果。`owner_review_summary.json` 保存 11 条 Google 翻译辅助复核的选择；独立人工验收仍待完成。

## Git 提交范围

提交代码、SQL、测试、依赖与配置模板、分析报告、必填文档，以及复现 Q4 所需的规则、样本划分、标签和语义样本。以下内容由 `.gitignore` 保留在本地：

- 原始 CSV、下载缓存、虚拟环境、数据库密钥。
- Q3 Parquet、运行日志、`.local/` 中的逐行审计与个人审核进度。
- 学习 PDF、临时文件、早期报告与评估历史快照。
- 本人辅助审核网页及对应网页测试；正式评估和盲审工具仍可随仓库复现。

原始数据、Q3 Parquet 与日志按题目规定由运行入口生成，不作为 Git 交付文件。原题 README 保持不变。最终交付以公开 Fork 中的指定分支和提交邮件附带的 commit hash 为准。
