"""Q3：正向商品事实、客户 RFM、取消记录及严格数量匹配。"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import logging
from pathlib import Path
import random
import sys
import tempfile
from time import perf_counter

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation import require
from download_data import ROOT, load_sources, sha256_file, validate_file
from q1_data_quality.investigate import prepare_frame
from q1_data_quality.q1_code import table
from q3_etl_pipeline.rules import RULE_VERSION, is_product

LOGGER = logging.getLogger("retail_etl")
SEED = 42
FACT_COLUMNS = ["invoice_no", "stock_code", "description", "quantity", "unit_price", "total_amount", "invoice_datetime", "customer_id", "country"]
FEATURE_COLUMNS = ["customer_id", "recency_days", "frequency", "monetary", "first_purchase_date", "last_purchase_date", "unique_products", "country", "is_one_time_buyer"]
RETURN_COLUMNS = FACT_COLUMNS + ["matched_original_invoice"]
FACT_SCHEMA = pa.schema([
    ("invoice_no", pa.string()), ("stock_code", pa.string()), ("description", pa.string()),
    ("quantity", pa.int64()), ("unit_price", pa.float64()), ("total_amount", pa.float64()),
    ("invoice_datetime", pa.timestamp("us")), ("customer_id", pa.string()), ("country", pa.string()),
])
FEATURE_SCHEMA = pa.schema([
    ("customer_id", pa.string()), ("recency_days", pa.int64()), ("frequency", pa.int64()),
    ("monetary", pa.float64()), ("first_purchase_date", pa.timestamp("us")),
    ("last_purchase_date", pa.timestamp("us")), ("unique_products", pa.int64()),
    ("country", pa.string()), ("is_one_time_buyer", pa.bool_()),
])
RETURN_SCHEMA = FACT_SCHEMA.append(pa.field("matched_original_invoice", pa.string()))


@contextmanager
def step(name: str, timings: dict):
    start = perf_counter()
    LOGGER.info("开始：%s", name)
    try:
        yield
    except Exception:
        LOGGER.exception("失败：%s", name)
        raise
    else:
        timings[name] = perf_counter() - start
        LOGGER.info("完成：%s，%.3f 秒", name, timings[name])


def load_data(path: Path) -> pd.DataFrame:
    specification = load_sources()["retail"]["files"]["online_retail_II.csv"]
    validate_file(path, specification)
    return pd.read_csv(path, dtype="string", keep_default_na=False)


def normalize_data(raw: pd.DataFrame) -> tuple[pd.DataFrame, int, dict]:
    # 复用 Q1 已验证的整数金额及时间解析，不依赖任何 Q1 报告文件。
    source, scale = prepare_frame(raw)
    normalized = pd.DataFrame({
        "invoice_no": source["Invoice"].str.strip().replace("", pd.NA),
        "stock_code": source["StockCode"].str.strip().replace("", pd.NA),
        "description": source["Description"].replace("", pd.NA),
        "quantity": source["quantity"].astype("int64"),
        "unit_price": (source["price_units"] / scale).astype("float64"),
        "total_amount": (source["amount_units"] / scale).astype("float64"),
        "invoice_datetime": source["date"].astype("datetime64[us]"),
        "customer_id": source["Customer ID"].str.strip().str.replace(r"^([0-9]+)\.0+$", r"\1", regex=True).replace("", pd.NA),
        "country": source["Country"].replace("", pd.NA),
        "source_row": source["record_no"].astype("int64"),
        "amount_units": source["amount_units"].astype("int64"),
        "price_units": source["price_units"].astype("int64"),
    })
    for name in ["invoice_no", "stock_code", "description", "customer_id", "country"]:
        normalized[name] = normalized[name].astype("string")
    mappings = []
    for old, new in [("Invoice", "invoice_no"), ("StockCode", "stock_code"), ("Customer ID", "customer_id")]:
        changed = source[old].ne(normalized[new].fillna(""))
        pairs = pd.DataFrame({"original": source.loc[changed, old], "normalized": normalized.loc[changed, new]}).value_counts(dropna=False).reset_index(name="rows")
        pairs = pairs.astype(object).where(pairs.notna(), None)
        mappings.append({"field": new, "changed_rows": int(changed.sum()), "mapping": pairs.to_dict("records")})
    audit = {
        "normalization": mappings,
        "raw_duplicate_excess": int(raw.duplicated().sum()),
        "reference_date": normalized["invoice_datetime"].max().normalize().isoformat(),
    }
    return normalized, scale, audit


def filter_real_sales(source: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """互斥归类保证行数和原始金额可以从输出/排除原因回溯。"""
    cancelled = source["invoice_no"].str.startswith("C").fillna(False)
    numeric_invoice = source["invoice_no"].str.fullmatch(r"[0-9]+").fillna(False)
    product = is_product(source["stock_code"])
    reason = pd.Series("sale", index=source.index, dtype="string")
    # 后赋值者优先，取消记录全部进入 returns，不受其他筛选条件影响。
    reason.loc[source["price_units"].le(0)] = "non_positive_price"
    reason.loc[source["quantity"].le(0)] = "non_positive_quantity"
    reason.loc[~product] = "non_product_or_unresolved_code"
    reason.loc[~numeric_invoice] = "non_sale_invoice"
    reason.loc[cancelled] = "cancellation"
    source["classification_reason"] = reason
    summary = []
    for name, group in source.groupby(reason, sort=True):
        summary.append({"reason": str(name), "rows": len(group), "amount_units": int(group["amount_units"].sum())})
    sales = source.loc[reason.eq("sale")].sort_values(["invoice_datetime", "source_row"], kind="stable").copy()
    returns = source.loc[cancelled].sort_values(["invoice_datetime", "source_row"], kind="stable").copy()
    return sales.reset_index(drop=True), returns.reset_index(drop=True), summary


def compute_rfm(sales: pd.DataFrame, reference_date: pd.Timestamp, scale: int) -> pd.DataFrame:
    known = sales.loc[sales["customer_id"].notna()]
    features = known.groupby("customer_id", sort=True).agg(
        frequency=("invoice_no", "nunique"), amount_units=("amount_units", "sum"),
        first_purchase_date=("invoice_datetime", "min"), last_purchase_date=("invoice_datetime", "max"),
        unique_products=("stock_code", "nunique"),
    ).reset_index()
    features["first_purchase_date"] = features["first_purchase_date"].dt.normalize()
    features["last_purchase_date"] = features["last_purchase_date"].dt.normalize()
    features["recency_days"] = (reference_date.normalize() - features["last_purchase_date"]).dt.days.astype("int64")
    features["monetary"] = (features["amount_units"] / scale).astype("float64")
    features["is_one_time_buyer"] = features["frequency"].eq(1)
    # 每张不同发票为国家投一票，避免大单中同一国家的很多行重复加权。
    votes = known[["customer_id", "invoice_no", "country"]].dropna(subset=["country"]).drop_duplicates()
    votes = votes.groupby(["customer_id", "country"], sort=True).size().reset_index(name="votes")
    primary = votes.sort_values(["customer_id", "votes", "country"], ascending=[True, False, True], kind="stable").drop_duplicates("customer_id")
    features = features.merge(primary[["customer_id", "country"]], on="customer_id", how="left", validate="one_to_one")
    features["customer_id"] = features["customer_id"].astype("string")
    features["country"] = features["country"].astype("string")
    return features[FEATURE_COLUMNS].sort_values("customer_id", kind="stable").reset_index(drop=True)


def match_returns(sales: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    """匹配最近的尚未使用的等量销售行；仅循环取消子集，不遍历百万行原表。"""
    result = returns.copy()
    result["matched_original_invoice"] = pd.Series(pd.NA, index=result.index, dtype="string")
    result["matched_source_row"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    result["match_reason"] = "no_prior_exact_quantity"
    result.loc[result["customer_id"].isna(), "match_reason"] = "missing_customer"
    result.loc[~is_product(result["stock_code"]), "match_reason"] = "non_product_or_unresolved_code"
    result.loc[result["price_units"].le(0), "match_reason"] = "non_positive_return_price"
    result.loc[result["quantity"].ge(0), "match_reason"] = "non_negative_cancellation"
    eligible = result["match_reason"].eq("no_prior_exact_quantity")
    right = sales.loc[sales["customer_id"].notna(), ["customer_id", "stock_code", "quantity", "invoice_datetime", "invoice_no", "source_row"]].copy()
    if not eligible.any() or right.empty:
        return result

    right = right.rename(columns={"quantity": "match_quantity", "invoice_datetime": "sale_time", "invoice_no": "sale_invoice", "source_row": "sale_row"})
    right = right.sort_values(["sale_time", "sale_row"], kind="stable").reset_index(drop=True)
    right["sale_position"] = np.arange(len(right), dtype="int64")
    keys = ["customer_id", "stock_code", "match_quantity"]
    # 同键前驱配合路径压缩，使被占用的销售行可以快速跳过。
    previous = right.groupby(keys, sort=False)["sale_position"].shift().fillna(-1).to_numpy(dtype="int64")
    parent = np.arange(len(right), dtype="int64")

    def available(position: int) -> int:
        path = []
        while position != -1 and parent[position] != position:
            path.append(position)
            position = int(parent[position])
        for old in path:
            parent[old] = position
        return position

    left = result.loc[eligible, ["customer_id", "stock_code", "quantity", "invoice_datetime", "source_row"]].copy()
    left["match_quantity"] = -left.pop("quantity")
    left["return_position"] = left.index
    left = left.sort_values(["invoice_datetime", "source_row"], kind="stable")
    candidates = pd.merge_asof(
        left, right, left_on="invoice_datetime", right_on="sale_time", by=keys,
        direction="backward", allow_exact_matches=False,
    )
    invoices = right["sale_invoice"].to_numpy()
    rows = right["sale_row"].to_numpy()
    positions = candidates["sale_position"].fillna(-1).to_numpy(dtype="int64")
    for return_position, candidate in zip(candidates["return_position"], positions, strict=True):
        if candidate == -1:
            continue
        selected = available(int(candidate))
        if selected == -1:
            result.at[return_position, "match_reason"] = "prior_candidates_used"
            continue
        result.at[return_position, "matched_original_invoice"] = invoices[selected]
        result.at[return_position, "matched_source_row"] = rows[selected]
        result.at[return_position, "match_reason"] = "matched"
        parent[selected] = available(int(previous[selected]))
    return result


def validate_output(source: pd.DataFrame, sales: pd.DataFrame, features: pd.DataFrame, returns: pd.DataFrame, reference_date: pd.Timestamp, scale: int) -> dict:
    require(sales["quantity"].gt(0).all(), "销售数量必须为正")
    require(sales["unit_price"].gt(0).all(), "销售价格必须为正")
    require(sales["total_amount"].ge(0).all(), "销售金额不能为负")
    require(sales["invoice_no"].str.fullmatch(r"[0-9]+").all(), "销售发票必须为纯数字")
    require(is_product(sales["stock_code"]).all(), "销售存在不允许的业务代码")
    require(sales["source_row"].is_unique, "同一输入行不得重复输出")
    for frame in (sales, returns):
        require(frame[["invoice_no", "stock_code", "quantity", "unit_price", "total_amount", "invoice_datetime"]].notna().all().all(), "关键字段不能为空")
        require(np.isfinite(frame[["unit_price", "total_amount"]].to_numpy(dtype=float)).all(), "金额必须为有限数")
        np.testing.assert_allclose(frame["total_amount"], frame["quantity"] * frame["unit_price"], rtol=1e-12, atol=1e-9)
    cancelled = source["invoice_no"].str.startswith("C").fillna(False)
    require(set(returns["source_row"]) == set(source.loc[cancelled, "source_row"]), "必须保留全部 C 记录")
    require(returns["invoice_no"].str.startswith("C").all(), 'pipeline: returns["invoice_no"].str.startswith("C").all()')
    require(features["customer_id"].is_unique and features["customer_id"].notna().all(), 'pipeline: features["customer_id"].is_unique and features["customer_id"].notna().all()')
    require(set(features["customer_id"]) == set(sales["customer_id"].dropna()), "每个已知客户都须输出")
    require(features["recency_days"].ge(0).all(), 'pipeline: features["recency_days"].ge(0).all()')
    require(features["frequency"].ge(1).all() and features["monetary"].ge(0).all(), 'pipeline: features["frequency"].ge(1).all() and features["monetary"].ge(0).all()')
    require(features["first_purchase_date"].le(features["last_purchase_date"]).all(), 'pipeline: features["first_purchase_date"].le(features["last_purchase_date"]).all()')
    require(features["last_purchase_date"].le(reference_date).all(), 'pipeline: features["last_purchase_date"].le(reference_date).all()')
    require(features["is_one_time_buyer"].eq(features["frequency"].eq(1)).all(), 'pipeline: features["is_one_time_buyer"].eq(features["frequency"].eq(1)).all()')
    known = sales.loc[sales["customer_id"].notna()]
    require(int(features["frequency"].sum()) == len(known[["customer_id", "invoice_no"]].drop_duplicates()), 'pipeline: int(features["frequency"].sum()) == len(known[["customer_id", "invoice_no"]].drop_duplicates())')
    np.testing.assert_allclose(features["monetary"].sum(), known["amount_units"].sum() / scale, rtol=1e-12, atol=1e-8)

    matched = returns.loc[returns["matched_source_row"].notna()]
    require(matched["matched_source_row"].is_unique, "同一销售行不能匹配两次")
    require(matched["matched_original_invoice"].notna().all(), 'pipeline: matched["matched_original_invoice"].notna().all()')
    require(returns["matched_source_row"].isna().eq(returns["matched_original_invoice"].isna()).all(), 'pipeline: returns["matched_source_row"].isna().eq(returns["matched_original_invoice"].isna()).all()')
    lookup = sales.set_index("source_row").loc[matched["matched_source_row"].astype("int64")].reset_index()
    aligned = matched.reset_index(drop=True)
    for name in ("customer_id", "stock_code"):
        require(aligned[name].notna().all() and aligned[name].eq(lookup[name]).all(), f"匹配键不一致：{name}")
    require(aligned["quantity"].eq(-lookup["quantity"]).all(), "匹配数量不相等")
    require(lookup["invoice_datetime"].lt(aligned["invoice_datetime"]).all(), "匹配必须严格早于退货")
    require(aligned["matched_original_invoice"].eq(lookup["invoice_no"]).all(), "匹配发票号不一致")
    return {
        "matched_rows": len(matched), "unmatched_rows": len(returns) - len(matched),
        "price_different_matches": int(aligned["price_units"].ne(lookup["price_units"]).sum()),
        "return_reasons": returns["match_reason"].value_counts().sort_index().to_dict(),
        "matched_return_amount_units": int(matched["amount_units"].sum()),
        "positive_c_rows": int(returns["quantity"].ge(0).sum()),
    }


def output_frames(sales, features, returns):
    return {
        "sales_facts": (sales[FACT_COLUMNS].reset_index(drop=True), FACT_SCHEMA),
        "customer_features": (features[FEATURE_COLUMNS].reset_index(drop=True), FEATURE_SCHEMA),
        "returns_log": (returns[RETURN_COLUMNS].reset_index(drop=True), RETURN_SCHEMA),
    }


def write_outputs(frames: dict, output_dir: Path) -> dict:
    """三个临时文件都通过回读验证后再发布；每个文件独立原子替换。"""
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    manifests = {}
    with tempfile.TemporaryDirectory(prefix=".q3-staging-", dir=output_dir.parent) as temporary:
        staging = Path(temporary)
        for name, (frame, schema) in frames.items():
            arrow = pa.Table.from_pandas(frame, schema=schema, preserve_index=False, safe=True).replace_schema_metadata(None)
            path = staging / f"{name}.parquet"
            pq.write_table(arrow, path, compression="zstd", version="2.6", row_group_size=100_000)
            reread = pq.read_table(path)
            require(reread.schema.equals(schema, check_metadata=True), f"Parquet 类型不符：{name}")
            require(reread.equals(arrow, check_metadata=True), f"Parquet 回读数据不符：{name}")
            manifests[name] = {"rows": len(frame), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        output_dir.mkdir(parents=True, exist_ok=True)
        for name in frames:
            (staging / f"{name}.parquet").replace(output_dir / f"{name}.parquet")
    return manifests


def summarize_frame(frame: pd.DataFrame) -> dict:
    summary = {"rows": len(frame), "null_counts": {name: int(value) for name, value in frame.isna().sum().items()}, "numeric": {}, "dates": {}, "booleans": {}}
    for name in frame.select_dtypes(include="number").columns:
        values = frame[name]
        summary["numeric"][name] = {key: None if pd.isna(value) else float(value) for key, value in {
            "min": values.min(), "median": values.median(), "p99": values.quantile(0.99), "max": values.max(),
        }.items()}
    for name in frame.select_dtypes(include="datetime").columns:
        summary["dates"][name] = {label: None if pd.isna(value) else value.isoformat() for label, value in {
            "min": frame[name].min(), "max": frame[name].max(),
        }.items()}
    for name in frame.select_dtypes(include="bool").columns:
        summary["booleans"][name] = {"true": int(frame[name].eq(True).sum()), "false": int(frame[name].eq(False).sum())}
    if "country" in frame:
        summary["country_top5"] = frame["country"].value_counts().head(5).to_dict()
    return summary


def peak_rss_mib() -> float | None:
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak / (1024 * 1024 if sys.platform == "darwin" else 1024)
    except (ImportError, AttributeError):
        return None


def render_validation(metrics: dict) -> str:
    scale = metrics["scale"]
    lines = [
        "# Q3 数据校验与性能报告",
        f'规则版本：`{RULE_VERSION}`；输入 `{metrics["input_rows"]:,}` 行，SHA-256 `{metrics["input_sha256"]}`。',
        f'RFM 基准日为完整原始数据的最后一天 **{metrics["reference_date"][:10]}**。金额内部按 1/{scale} 英镑整数累加，最终按题目要求输出 float64。',
        "## 输出及文件校验",
        table(["文件", "行数", "字节数", "SHA-256"], [[name + ".parquet", item["rows"], item["bytes"], item["sha256"]] for name, item in metrics["outputs"].items()]),
        "三份文件均验证固定 Arrow 字段类型，并完成逐值回读比较。原始文件未更改。",
        "## 互斥行归类与金额对账",
        table(["原因", "行数", "原始有符号金额（£）"], [[item["reason"], item["rows"], f'{item["amount_units"] / scale:,.3f}'] for item in metrics["classification"]]),
        "sale 为正向商品事实；cancellation 全部进入取消表；其余原因保留原始数据并在本地审计中记录源行号，不静默删除。各分类行数、整数金额合计已与原始输入对齐。",
        "## 退货关联",
        table(["匹配状态", "行数"], [[name, value] for name, value in metrics["matching"]["return_reasons"].items()]),
        "上表原因互斥，优先级依次为数量非负、价格非正、非商品、缺客户、历史候选匹配状态。因此 missing_customer 是该原因的独占行数，不等于取消表全部客户空值数。未匹配不等于错误退货，也不能视为零退款。",
        f'成功匹配 **{metrics["matching"]["matched_rows"]:,}** 条，未匹配 **{metrics["matching"]["unmatched_rows"]:,}** 条。其中单价不同的匹配有 **{metrics["matching"]["price_different_matches"]:,}** 条；题目匹配键不含价格，此信息保留为待核查线索。',
        "匹配键为客户、商品、绝对数量；严格向前匹配最近的尚未使用销售明细。同一时间按原始行号确定顺序，相同时间戳的销售不能匹配；同一销售行最多使用一次。缺失客户 ID 不互相匹配。每条未匹配记录的源行号和原因均写入 pipeline_log.txt。",
        f'取消表保留 **{metrics["matching"]["positive_c_rows"]}** 条数量非负的 C 前缀记录，标记异常而非修改符号。因此“金额非负”的断言仅用于销售表，不能错误套用到取消表。',
        "## 各输出字段空值率与分布",
    ]
    for name, summary in metrics["summaries"].items():
        lines.extend([
            f"### {name}",
            table(["字段", "空值数", "空值率"], [[column, value, f'{value / summary["rows"]:.4%}' if summary["rows"] else "不适用"] for column, value in summary["null_counts"].items()]),
            table(["数值字段", "min", "median", "P99", "max"], [[column, *[None if values[key] is None else f'{values[key]:,.6f}'.rstrip("0").rstrip(".") for key in ["min", "median", "p99", "max"]]] for column, values in summary["numeric"].items()]),
            table(["主要国家", "行数"], [[country, count] for country, count in summary.get("country_top5", {}).items()]),
        ])
        if summary["dates"]:
            lines.append(table(["日期字段", "最早", "最晚"], [[column, values["min"], values["max"]] for column, values in summary["dates"].items()]))
        if summary["booleans"]:
            lines.append(table(["布尔字段", "true", "false"], [[column, values["true"], values["false"]] for column, values in summary["booleans"].items()]))
    lines.extend([
        "## 规则与局限",
        "- sales_facts 是正向商品发生额：纯数字发票、正数量、正价格、有效商品代码。它保留后来被取消的原正向明细；计算净额时还须按相同商品口径筛选取消记录，不能直接混入非商品退款，也不能只扣成功匹配的退款。不得将该表或基础 RFM 金额直接解释为最终留存收入。",
        "- 数字加可选字母后缀的商品代码，以及 Q1 描述支持的 18 个例外代码予以保留；运费、折扣、坏账、手工、样品、测试、礼券及未能确认的特殊代码不进入商品事实。例外清单见 rules.py。",
        "- 不补造客户 ID 或商品描述；商品代码仅去首尾空格，不擅自统一大小写。客户 ID 的纯数字 .0 后缀移除并保留映射。",
        f'- 原始重复候选为 **{metrics["raw_duplicate_excess"]:,}** 条；因无独立业务行标识，保留而不自动去重，可能仍存在重复导入造成的偏差。',
        "- RFM 的 F 按独立发票计数，M 按正向商品金额计算；国家按独立发票数最多者确定，同票数按国家名称排序。不把匿名记录合成一个客户。",
        "- 本题主输出使用严格等量匹配：买 10 退 5、分拆或合并退货、历史在数据窗口之外的销售都可能不匹配。多个销售符合时先消耗最近可用行；已使用候选耗尽则不复用。此规则保守且可复现，但不等于已证实的真实原单关系。",
        "- 三份规定输出不额外附加字段；逐行来源、匹配原因、规范化映射保存在 .local/q3/。后续可基于取消表补充客户净消费等指标，本次基础 RFM 不冒充净消费。",
        "- 文件先在临时目录验证后逐个原子替换，最终本地清单记录文件摘要；跨文件发布不是数据库事务，发生中断须对照清单或重跑。",
        "## 性能与复现",
        "运行版本：" + "，".join(f"{name} {version}" for name, version in metrics["versions"].items()) + "。",
        table(["阶段", "秒"], [[name, f"{seconds:.3f}"] for name, seconds in metrics["timings"].items()]),
        f'数据处理总计 **{metrics["elapsed_seconds"]:.3f} 秒**（含读取、校验、审计、写出、回读及统计；不含网络下载和最后的报告/清单文本写入）；进程峰值 RSS **{metrics["peak_rss_mib"]:.2f} MiB**。峰值包含同进程此前的工作，应以独立运行作为基准。' if metrics["peak_rss_mib"] is not None else f'总计 {metrics["elapsed_seconds"]:.3f} 秒；此平台未提供进程峰值 RSS。',
        f'固定随机种子 {SEED}；算法不使用抽样。排序及相同时间的决策均已固定。日志和报告中的运行时间允许变化，数据文件内容与摘要应一致。',
        "```bash\npython -m q3_etl_pipeline.pipeline\n# 或\npython run_all.py --stage q3 --offline\n```",
        "算法参考：[pandas merge_asof](https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html) 的严格向前匹配；[Arrow Parquet](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.write_table.html) 的明确类型写出。",
    ])
    return "\n\n".join(lines) + "\n"


def run_pipeline(input_path: Path = ROOT / "data" / "online_retail_ii.csv", output_dir: Path = ROOT / "q3_etl_pipeline" / "outputs", report_path: Path = ROOT / "q3_etl_pipeline" / "validation_report.md", log_path: Path = ROOT / "q3_etl_pipeline" / "pipeline_log.txt", audit_dir: Path = ROOT / ".local" / "q3") -> dict:
    started = perf_counter()
    timings = {}
    random.seed(SEED)
    np.random.seed(SEED)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.setLevel(logging.DEBUG)
    previous_propagate = LOGGER.propagate
    LOGGER.propagate = False
    stream = logging.StreamHandler()
    stream.setLevel(logging.INFO)
    stream.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    LOGGER.addHandler(stream)
    LOGGER.addHandler(handler)
    try:
        with step("读取与校验输入", timings):
            raw = load_data(input_path)
        with step("类型与标识符规范化", timings):
            source, scale, audit = normalize_data(raw)
            del raw
        reference_date = pd.Timestamp(audit["reference_date"])
        with step("商品筛选与取消分流", timings):
            sales, returns, classification = filter_real_sales(source)
            require(sum(item["rows"] for item in classification) == len(source), 'pipeline: sum(item["rows"] for item in classification) == len(source)')
            require(sum(item["amount_units"] for item in classification) == int(source["amount_units"].sum()), 'pipeline: sum(item["amount_units"] for item in classification) == int(source["amount_units"].sum())')
        with step("客户 RFM", timings):
            features = compute_rfm(sales, reference_date, scale)
        with step("严格等量退货匹配", timings):
            returns = match_returns(sales, returns)
        with step("输出业务校验", timings):
            matching = validate_output(source, sales, features, returns, reference_date, scale)
        with step("审计记录", timings):
            excluded = source.loc[~source["source_row"].isin(sales["source_row"])]
            excluded.to_parquet(audit_dir / "excluded_rows.parquet", index=False)
            returns[["source_row", "invoice_no", "matched_source_row", "matched_original_invoice", "match_reason"]].to_parquet(audit_dir / "return_matches.parquet", index=False)
            sales[["source_row", "invoice_no", "stock_code", "customer_id", "amount_units"]].to_parquet(audit_dir / "sales_lineage.parquet", index=False)
            (audit_dir / "normalization.json").write_text(json.dumps(audit["normalization"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            for row in returns.loc[returns["matched_source_row"].isna()].itertuples(index=False):
                LOGGER.debug("UNMATCHED source_row=%s invoice=%s stock=%s customer=%s quantity=%s reason=%s", row.source_row, row.invoice_no, row.stock_code, row.customer_id, row.quantity, row.match_reason)
            LOGGER.info("退货匹配 %s，未匹配 %s", matching["matched_rows"], matching["unmatched_rows"])
        frames = output_frames(sales, features, returns)
        with step("Parquet 写出及回读", timings):
            outputs = write_outputs(frames, output_dir)
        with step("输出分布统计", timings):
            summaries = {name: summarize_frame(frame) for name, (frame, _) in frames.items()}
        metrics = {
            "rule_version": RULE_VERSION, "seed": SEED, "input_rows": len(source),
            "input_sha256": sha256_file(input_path), "scale": scale,
            "reference_date": audit["reference_date"], "raw_duplicate_excess": audit["raw_duplicate_excess"],
            "classification": classification, "matching": matching, "outputs": outputs,
            "summaries": summaries, "timings": timings, "elapsed_seconds": perf_counter() - started,
            "peak_rss_mib": peak_rss_mib(),
            "versions": {"python": sys.version.split()[0], "pandas": pd.__version__, "numpy": np.__version__, "pyarrow": pa.__version__},
        }
        with step("报告与运行清单", {}):
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(render_validation(metrics), encoding="utf-8")
            (audit_dir / "run_manifest.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        LOGGER.info("流水线完成，%.3f 秒，三份输出均通过验证", metrics["elapsed_seconds"])
        return metrics
    finally:
        LOGGER.removeHandler(handler)
        handler.close()
        LOGGER.removeHandler(stream)
        stream.close()
        LOGGER.propagate = previous_propagate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "online_retail_ii.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "q3_etl_pipeline" / "outputs")
    parser.add_argument("--report", type=Path, default=ROOT / "q3_etl_pipeline" / "validation_report.md")
    parser.add_argument("--log", type=Path, default=ROOT / "q3_etl_pipeline" / "pipeline_log.txt")
    parser.add_argument("--audit-dir", type=Path, default=ROOT / ".local" / "q3")
    args = parser.parse_args()
    try:
        run_pipeline(args.input.resolve(), args.output_dir.resolve(), args.report.resolve(), args.log.resolve(), args.audit_dir.resolve())
    except Exception as exc:
        print(f"Q3 未完成：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
