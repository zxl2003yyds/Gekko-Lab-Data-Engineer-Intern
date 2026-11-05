"""Q1 入口：Q1.1 统计数据质量，Q1.2 调查业务结构，保留全部原始记录。"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
import pandas as pd

# 同时支持 python -m 和直接执行本文件。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from download_data import ROOT, load_sources, sha256_file, validate_file

LOGGER = logging.getLogger(__name__)
STRING_COLUMNS = ["Invoice", "StockCode", "Description", "Customer ID", "Country"]
NUMERIC_COLUMNS = ["Quantity", "Price"]
ROLES = {
    "Invoice": "发票标识，保留字母前缀",
    "StockCode": "商品或业务代码，保留文本",
    "Description": "原始描述，不裁剪空格或统一大小写",
    "Quantity": "数量",
    "InvoiceDate": "交易时间，不赋予未经确认的时区",
    "Price": "单价或调整金额字段",
    "Customer ID": "客户标识，保留原始文本及 .0 后缀",
    "Country": "国家或地区标签",
}


def typed_view(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """类型转换只用于统计；空值与转换失败分开记录，不修改输入。"""
    frame = raw.mask(raw.eq(""))
    errors = dict.fromkeys(raw.columns, 0)
    for column in NUMERIC_COLUMNS:
        numeric = pd.to_numeric(frame[column], errors="coerce").astype("Float64")
        numeric = numeric.mask(~np.isfinite(numeric))
        errors[column] = int((frame[column].notna() & numeric.isna()).sum())
        if column == "Quantity" and numeric.dropna().mod(1).eq(0).all():
            frame[column] = numeric.astype("Int64")
        else:
            frame[column] = numeric
    dates = pd.to_datetime(frame["InvoiceDate"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    errors["InvoiceDate"] = int((frame["InvoiceDate"].notna() & dates.isna()).sum())
    frame["InvoiceDate"] = dates
    return frame, errors


def number(value) -> float | None:
    return None if pd.isna(value) else float(value)


def top_values(series: pd.Series, limit: int = 10) -> list[dict]:
    """并列频次按原始文本排序，确保多次执行结果一致。"""
    counts = series.dropna().value_counts().rename_axis("value").reset_index(name="count")
    counts = counts.sort_values(["count", "value"], ascending=[False, True], kind="stable")
    return [{"value": str(row.value), "count": int(row.count)} for row in counts.head(limit).itertuples(index=False)]


def sample_rows(raw: pd.DataFrame, mask: pd.Series, limit: int = 3) -> list[dict]:
    sample = raw.loc[mask.fillna(False)].head(limit).copy()
    sample.insert(0, "record_no", sample.index + 1)
    return sample.to_dict(orient="records")


def build_profile(raw: pd.DataFrame) -> dict:
    if raw.empty:
        raise ValueError("输入没有数据记录，不能生成数据质量结论")
    raw = raw.reset_index(drop=True)
    frame, errors = typed_view(raw)
    rows = len(raw)
    profile = {"rows": rows, "columns": [], "numeric": {}, "strings": {}}
    for column in raw.columns:
        missing = int(raw[column].eq("").sum())
        profile["columns"].append({
            "name": column, "dtype": str(frame[column].dtype), "role": ROLES[column],
            "missing": missing, "missing_pct": missing / rows * 100,
            "parse_errors": errors[column],
            "whitespace_only": int(raw[column].str.fullmatch(r"\s+").sum()),
        })
    for column in NUMERIC_COLUMNS:
        values = frame[column]
        profile["numeric"][column] = {
            "count": int(values.count()), "min": number(values.min()),
            "max": number(values.max()), "mean": number(values.mean()),
            "std": number(values.std(ddof=1)), "median": number(values.median()),
            "p01": number(values.quantile(0.01)), "p95": number(values.quantile(0.95)),
            "p99": number(values.quantile(0.99)),
        }
    for column in STRING_COLUMNS:
        profile["strings"][column] = {
            "unique": int(frame[column].nunique(dropna=True)),
            "top10": top_values(frame[column]),
        }

    quantity, price = frame["Quantity"], frame["Price"]
    cancelled = raw["Invoice"].str.startswith("C")
    description_missing = raw["Description"].eq("")
    customer_missing = raw["Customer ID"].eq("")
    duplicate_members = raw.duplicated(keep=False)
    nonstandard_code = ~raw["StockCode"].str.fullmatch(r"\d+[A-Za-z]*")
    masks = {
        "customer_missing": customer_missing,
        "description_missing": description_missing,
        "description_missing_zero_price": description_missing & price.eq(0),
        "description_missing_customer_missing": description_missing & customer_missing,
        "duplicate_excess": raw.duplicated(keep="first"),
        "duplicate_members": duplicate_members,
        "negative_quantity": quantity.lt(0),
        "zero_quantity": quantity.eq(0),
        "c_invoice": cancelled,
        "c_invoice_nonnegative_quantity": cancelled & quantity.ge(0),
        "non_c_negative_quantity": ~cancelled & quantity.lt(0),
        "negative_price": price.lt(0),
        "zero_price": price.eq(0),
        "negative_price_bad_debt_label": price.lt(0) & raw["Description"].eq("Adjust bad debt"),
        "nonnumeric_invoice": ~raw["Invoice"].str.fullmatch(r"\d+"),
        "nonstandard_stock_code": nonstandard_code,
    }
    profile["signals"] = {name: {"count": int(mask.sum()), "pct": float(mask.sum() / rows * 100)} for name, mask in masks.items()}
    dates = frame["InvoiceDate"]
    profile["date_range"] = {
        "min": dates.min().isoformat() if dates.notna().any() else None,
        "max": dates.max().isoformat() if dates.notna().any() else None,
    }
    profile["examples"] = {
        "description_missing": sample_rows(raw, description_missing),
        "c_invoice_nonnegative_quantity": sample_rows(raw, masks["c_invoice_nonnegative_quantity"]),
        "non_c_negative_quantity": sample_rows(raw, masks["non_c_negative_quantity"]),
        "negative_price": sample_rows(raw, price.lt(0), limit=10),
        "max_price": sample_rows(raw, price.eq(price.max())),
        "min_quantity": sample_rows(raw, quantity.eq(quantity.min())),
        "max_quantity": sample_rows(raw, quantity.eq(quantity.max())),
    }
    # 重复组展示同一个原始八字段组合的实际出现次数，避免混淆重复行与重复发票。
    if duplicate_members.any():
        first = raw.loc[duplicate_members].iloc[0]
        same = raw.eq(first).all(axis=1)
        profile["duplicate_example"] = {"occurrences": int(same.sum()), "rows": sample_rows(raw, same)}
    else:
        profile["duplicate_example"] = {"occurrences": 0, "rows": []}
    prefixes = raw.loc[masks["nonnumeric_invoice"], "Invoice"].str.extract(r"^([^0-9]+)", expand=False)
    profile["invoice_prefixes"] = top_values(prefixes)
    profile["nonstandard_code_top10"] = top_values(raw.loc[nonstandard_code, "StockCode"])
    return profile


def cell(value) -> str:
    if value is None:
        return "—"
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("\n", "\\n").replace("\r", "\\r")


def table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def display_number(value) -> str:
    return "—" if value is None else f"{value:,.6f}".rstrip("0").rstrip(".")


def render_report(profile: dict) -> str:
    s, numeric = profile["signals"], profile["numeric"]
    def count(name):
        return f'{s[name]["count"]:,} 条（{s[name]["pct"]:.4f}%）'

    sections = [
        "# Q1.1 数据质量初探报告",
        "本报告由 `q1_data_quality/q1_code.py` 基于全部原始记录生成。统计线索与业务结论分开；当前未删除、去重、补值、裁剪空格或改写任何原始 CSV。",
        "## 1. 数据范围与统计口径",
        f'- 固定来源：`{profile["source"]["handle"]}`。\n'
        f'- SHA-256：`{profile["source"]["sha256"]}`。\n'
        f'- 记录数：**{profile["rows"]:,}**；原始字段数：**{len(profile["columns"])}**。记录是明细行，不等于订单数。\n'
        f'- 时间范围：`{profile["date_range"]["min"]}` 至 `{profile["date_range"]["max"]}`，未擅自指定时区。\n'
        '- CSV 最初全部按字符串读取。统计视图显式转换 Quantity、Price 和 InvoiceDate；ID 即使形似数字也保留文本。\n'
        '- 缺失指原始空字段；空白字符单独检查，文字 NA 不自动视作缺失。类型转换失败另列，不与原始缺失混为一谈。\n'
        '- 所有比例以全部明细行数为分母。数值统计保留负数、零和极端值；标准差为样本标准差（ddof=1）。\n'
        '- 唯一值和 TOP 10 排除空值，按原始文本精确区分；频次并列按文本升序。引号内的尾部空格有意保留。\n'
        '- 题目 InvoiceNo / UnitPrice 分别对应本文件 Invoice / Price。',
        "## 2. 各列类型与缺失值",
        table(["原始字段", "统计视图类型", "用途", "缺失条数", "缺失率", "转换失败", "仅含空白字符"], [
            [x["name"], x["dtype"], x["role"], f'{x["missing"]:,}', f'{x["missing_pct"]:.4f}%', x["parse_errors"], x["whitespace_only"]] for x in profile["columns"]
        ]),
        "Customer ID 中类似 `16446.0` 的值仍是标识符，不计算均值或标准差。以上类型反映程序的统计视图，CSV 文件本身不携带数据库类型。",
        "## 3. 数值字段分布",
        table(["字段", "有效条数", "min", "max", "mean", "std（ddof=1）", "P01", "中位数", "P95", "P99"], [
            [name, f'{x["count"]:,}', *[display_number(x[key]) for key in ["min", "max", "mean", "std", "p01", "median", "p95", "p99"]]] for name, x in numeric.items()
        ]),
        "均值和标准差明显受到长尾与异常业务记录影响；不能直接把这些汇总解释为普通商品的典型购买数量或单价。",
        "## 4. 字符串字段唯一值与 TOP 10",
    ]
    for name, summary in profile["strings"].items():
        sections.extend([
            f'### {name}：{summary["unique"]:,} 个非空唯一值',
            table(["原始值（双引号包围）", "出现条数", "占全部记录"], [
                [json.dumps(x["value"], ensure_ascii=False), f'{x["count"]:,}', f'{x["count"] / profile["rows"] * 100:.4f}%'] for x in summary["top10"]
            ]),
        ])
    sections.extend([
        "## 5. 八项需要进一步核查的现象",
        "### 5.1 客户标识缺失可能改变客户分析样本",
        f'缺少 Customer ID 的记录有 **{count("customer_missing")}**。这些记录无法直接归属到具体客户；如果先统一删掉，再做销售统计，统计范围也会随之改变。下一步需要比较其金额、国家和商品分布，当前不能直接把它们认定为游客订单。',
        "### 5.2 描述缺失与零价格、客户缺失同时出现",
        f'Description 为空的记录有 **{count("description_missing")}**；其中 **{s["description_missing_zero_price"]["count"]:,}** 条价格为零，**{s["description_missing_customer_missing"]["count"]:,}** 条同时缺少客户 ID。这种共同出现的模式值得核查。是否为库存调整等业务，需结合描述、发票及更多上下文，不能仅据此定性。',
        "### 5.3 存在八个原始字段完全一致的重复记录",
        f'按原始八字段逐项比较，重复组共涉及 **{s["duplicate_members"]["count"]:,}** 条记录；每组保留第一条后，其余 **{count("duplicate_excess")}**。这不是“重复发票数”，因为一张发票本来就可能含多个商品明细。数据缺少独立行标识，现阶段不能区分重复导入与真实重复明细，故仅标记，不直接去重。',
        "### 5.4 负数量和 C 前缀并非完全对应",
        f'负数量记录有 **{count("negative_quantity")}**，C 前缀记录有 **{s["c_invoice"]["count"]:,}** 条。其中 **{s["non_c_negative_quantity"]["count"]:,}** 条负数量记录没有 C 前缀；另有 **{s["c_invoice_nonnegative_quantity"]["count"]:,}** 条 C 前缀记录的数量非负。题面将 C 前缀作为取消记录线索，因此不能简单把“Quantity < 0”与“C 前缀”当作同一规则。',
        "### 5.5 零价格与负价格需要不同的调查路径",
        f'Price 为零的记录有 **{count("zero_price")}**；负价格记录有 **{count("negative_price")}**。负价格中 **{s["negative_price_bad_debt_label"]["count"]:,}** 条描述为 `Adjust bad debt`，为核查坏账调整提供了直接文本线索。不能将负价格一律归因于录入错误，也不能在没有业务定义时将零价格自动填成普通商品价格。',
        "### 5.6 数量极值远离主体分布",
        f'Quantity 中位数为 **{display_number(numeric["Quantity"]["median"])}**，P99 为 **{display_number(numeric["Quantity"]["p99"])}**，但范围达到 **{display_number(numeric["Quantity"]["min"])} 至 {display_number(numeric["Quantity"]["max"])}**。正负极值的原始证据见下方；需检查客户、商品及发生时间是否对应，不能仅凭统计距离删除。',
        "### 5.7 最高价格未必是普通商品单价",
        f'Price 中位数为 **{display_number(numeric["Price"]["median"])}**，P99 为 **{display_number(numeric["Price"]["p99"])}**，最高却为 **{display_number(numeric["Price"]["max"])}**。下方最高价格记录展示其业务代码、描述与数量。计算商品价格分布前需要先确认该类记录是否属于商品销售。',
        "### 5.8 发票号与业务代码不能统一转换成数字",
        f'非纯数字 Invoice 有 **{count("nonnumeric_invoice")}**。不符合“数字主体加可选字母后缀”格式的 StockCode 有 **{count("nonstandard_stock_code")}**。这只是格式筛选，并不证明这些代码都是非商品；自动转数值会丢失业务信息。',
        table(["发票非数字前缀", "明细条数"], [[x["value"], x["count"]] for x in profile["invoice_prefixes"]]),
        table(["不符合常见格式的 StockCode（前十）", "明细条数"], [[x["value"], x["count"]] for x in profile["nonstandard_code_top10"]]),
        "## 6. 原始记录证据",
        "记录序号从第一条数据记录开始，以 1 为起点，不包含表头，也不等同于文件的物理行号。每类按原始顺序取少量例子，完整数量以上方统计为准。",
    ])
    labels = {
        "description_missing": "描述缺失的例子", "c_invoice_nonnegative_quantity": "C 前缀且数量非负",
        "non_c_negative_quantity": "非 C 前缀但数量为负", "negative_price": "负价格记录",
        "min_quantity": "数量最小值", "max_quantity": "数量最大值", "max_price": "价格最大值",
    }
    for key, examples in profile["examples"].items():
        sections.append(f"### {labels[key]}")
        sections.append(table(["记录序号", "Invoice", "StockCode", "Description", "Quantity", "Price", "Customer ID", "InvoiceDate", "Country"], [
            [x.get(name, "") for name in ["record_no", "Invoice", "StockCode", "Description", "Quantity", "Price", "Customer ID", "InvoiceDate", "Country"]] for x in examples
        ]) if examples else "本数据中没有匹配记录。")
    duplicate = profile["duplicate_example"]
    sections.extend([
        "### 完全重复组的例子",
        f'首个重复组实际出现 **{duplicate["occurrences"]}** 次，示例记录序号为：' + ", ".join(str(x["record_no"]) for x in duplicate["rows"]) + "。机器报告保存完整八字段示例。",
        "## 7. 复现与下一步",
        "```bash\npython -m q1_data_quality.q1_code\n# 或通过统一入口，仅运行 Q1.1\npython run_all.py --stage q1.1 --offline\n```",
        "Markdown 为提交报告；同一次计算的完整统计写入 `.local/q1_profile.json`，避免手工抄写数值。固定输入和代码重复运行应产生相同报告。后续 Q1.2 将核实这些线索的业务含义，Q1.3 再按不同下游用途确定清洗策略。本阶段不宣称已完成后二者。",
    ])
    return "\n\n".join(sections) + "\n"


def run_q11(input_path: Path = ROOT / "data" / "online_retail_ii.csv", output_path: Path = ROOT / "q1_data_quality" / "data_quality_report.md", metrics_path: Path = ROOT / ".local" / "q1_profile.json") -> dict:
    started = perf_counter()
    dataset = load_sources()["retail"]
    specification = dataset["files"]["online_retail_II.csv"]
    validate_file(input_path, specification)
    raw = pd.read_csv(input_path, dtype="string", keep_default_na=False)
    LOGGER.info("读取 %s 条原始记录，开始 Q1.1 统计", f"{len(raw):,}")
    profile = build_profile(raw)
    profile["source"] = {"handle": dataset["handle"], "sha256": sha256_file(input_path)}
    report = render_report(profile)
    for path in (output_path, metrics_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False 防止生成不符合 JSON 标准的 NaN 或 Infinity。
    metrics_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    output_path.write_text(report, encoding="utf-8")
    LOGGER.info("Q1.1 完成，报告：%s；耗时 %.2f 秒", output_path, perf_counter() - started)
    return profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", choices=["q1.1", "q1.2"], default="q1.1")
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "online_retail_ii.csv")
    parser.add_argument("--output", type=Path, help="默认写入所选题目的 Markdown 报告")
    parser.add_argument("--metrics", type=Path, help="默认写入 .local 下对应的 JSON 报告")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.part == "q1.1":
            runner, filename, metrics_name = run_q11, "data_quality_report.md", "q1_profile.json"
        else:
            from q1_data_quality.investigate import run_q12

            runner, filename, metrics_name = run_q12, "findings.md", "q1_findings.json"
        output = args.output or ROOT / "q1_data_quality" / filename
        metrics = args.metrics or ROOT / ".local" / metrics_name
        runner(args.input.resolve(), output.resolve(), metrics.resolve())
    except Exception as exc:
        LOGGER.error("%s 失败：%s", args.part, exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
