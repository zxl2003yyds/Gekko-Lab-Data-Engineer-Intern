"""Q1.2：以原始记录和明确的金额口径调查四个业务问题。"""

from __future__ import annotations

from decimal import Decimal
import json
import logging
from pathlib import Path
from time import perf_counter

import pandas as pd

from download_data import ROOT, load_sources, sha256_file, validate_file
from q1_data_quality.q1_code import table, top_values, typed_view

LOGGER = logging.getLogger(__name__)
UCI_SOURCE = "https://archive.ics.uci.edu/dataset/502/online+retail+ii"
PRODUCT_PATTERN = r"[0-9]+[A-Za-z]*"
KNOWN_CODES = {
    "POST": "描述为 POSTAGE，按邮资条目单列。",
    "DOT": "描述为 DOTCOM POSTAGE，指向网站渠道邮资；不能据此还原独立消费者。",
    "C2": "描述主要为 CARRIAGE，按运输费用单列，零价空描述行仍需核查。",
    "AMAZONFEE": "描述为 AMAZON FEE，指向平台费用；具体结算方向需结合正负号。",
    "BANK CHARGES": "描述为 Bank Charges，指向银行费用；包含 0.001 单价，不能先按分取整。",
    "CRUK": "描述为 CRUK Commission，指向佣金；数据不足以确认缩写对应的具体组织。",
    "D": "描述为 Discount，指向折扣或其冲回；不能计成独立商品销量。",
    "B": "描述为 Adjust bad debt，与 A 前缀关联，指向坏账调整。",
    "ADJUST": "描述明确为人工调整，需保留调整痕迹并与商品交易分开。",
    "ADJUST2": "描述明确为人工调整，不能把调整金额当作普通商品单价。",
    "M": "描述为 Manual，属手工录入条目；仅凭代码不能确认具体商品或调整原因。",
    "m": "描述也为 Manual，是小写变体；原样保留，并标记与 M 的关联。",
    "S": "描述为 SAMPLES，指向样品相关条目，不宜当作普通商品销售。",
    "TEST001": "描述为 This is a test product.，标记为测试条目。",
    "TEST002": "包含测试商品描述及空描述，标记为测试条目。",
}


def percent(part: int, total: int) -> float | None:
    return None if total == 0 else part / total * 100


def prepare_frame(raw: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """用原始价格构建定点整数金额，避免 0.001 被提前舍入或浮点累加。"""
    if raw.empty:
        raise ValueError("没有记录，无法调查业务问题")
    raw = raw.reset_index(drop=True)
    typed, errors = typed_view(raw)
    if any(errors.values()) or typed[["Quantity", "Price", "InvoiceDate"]].isna().any().any():
        raise ValueError("数量、价格或日期缺失/无法解析，不能静默排除后计算金额占比")
    if not typed["Quantity"].mod(1).eq(0).all():
        raise ValueError("数量包含非整数，需要先确认业务单位")
    decimals = {value: Decimal(value) for value in raw["Price"].unique()}
    digits = max(max(0, -value.as_tuple().exponent) for value in decimals.values())
    scale = 10**digits
    price_units = raw["Price"].map({key: int(value * scale) for key, value in decimals.items()}).astype("int64")
    quantity = typed["Quantity"].astype("int64")
    # 保守上界验证逐行乘积及合计不会溢出 int64。
    if int(price_units.abs().max()) * int(quantity.abs().max()) * len(raw) > 2**63 - 1:
        raise ValueError("定点金额可能溢出 int64，应改用更高精度累加")
    frame = raw.copy()
    frame["record_no"] = frame.index + 1
    frame["quantity"] = quantity
    frame["price_units"] = price_units
    frame["amount_units"] = quantity * price_units
    frame["date"] = typed["InvoiceDate"]
    frame["customer_missing"] = raw["Customer ID"].eq("")
    return frame, scale


def amount_summary(frame: pd.DataFrame, totals: dict) -> dict:
    net = int(frame["amount_units"].sum())
    absolute = int(frame["amount_units"].abs().sum())
    return {
        "rows": len(frame), "row_pct": percent(len(frame), totals["rows"]),
        "net_units": net, "net_pct": percent(net, totals["net_units"]),
        "absolute_units": absolute, "absolute_pct": percent(absolute, totals["absolute_units"]),
    }


def evidence(frame: pd.DataFrame) -> list[dict]:
    columns = ["record_no", "Invoice", "StockCode", "Description", "Quantity", "Price", "Customer ID", "InvoiceDate", "Country", "amount_units"]
    return frame[columns].to_dict("records")


def classify_code(code: str, descriptions: list[str]) -> tuple[str, str]:
    """分类只服务于调查；格式异常不自动等价于非商品。"""
    if code in KNOWN_CODES:
        return "非普通商品业务条目", KNOWN_CODES[code]
    if code != code.strip() and pd.Series([code.strip()]).str.fullmatch(PRODUCT_PATTERN).iloc[0]:
        return "商品代码空格变体", f"去除首尾空格后为 {code.strip()}，本次仅标记，不改写原始代码。"
    if code == "PADS":
        return "实物商品候选", "描述指向配套靠垫内芯；极低价格可能是配套定价，不能只因全字母而删除。"
    if code.startswith("gift_"):
        if any("Gift Voucher" in text for text in descriptions):
            return "礼券条目", "描述明确为礼券；应单列礼券交易，避免与兑换商品混合统计。"
        return "礼券条目（推测）", "仅由同系列代码推测为礼券，描述全空，尚不能核实具体交易。"
    if code.startswith("DCGS") or code == "SP1002":
        informative = [text for text in descriptions if text.strip().lower() not in ("", "ebay", "update")]
        if informative:
            return "实物商品候选", "存在具体商品描述，也可能混有零价库存调整；代码前缀不能作为删除理由。"
        return "信息不足", "只有空描述或渠道/更新备注；可能是商品或库存条目，保留待核查。"
    return "信息不足", "缺少可核实业务含义的描述，不依据名称强行归类。"


def analyze_prefixes(frame: pd.DataFrame, totals: dict) -> list[dict]:
    numeric = frame["Invoice"].str.fullmatch(r"[0-9]+")
    prefix = frame["Invoice"].str.extract(r"^([^0-9]+)", expand=False).fillna("非数字位于中间")
    prefix = prefix.mask(numeric, "纯数字")
    result = []
    for name, group in frame.groupby(prefix, sort=True):
        result.append({
            "prefix": str(name), **amount_summary(group, totals),
            "invoices": int(group["Invoice"].nunique()),
            "negative_quantity": int(group["quantity"].lt(0).sum()),
            "positive_quantity": int(group["quantity"].gt(0).sum()),
            "negative_price": int(group["price_units"].lt(0).sum()),
            "zero_price": int(group["price_units"].eq(0).sum()),
            "description_top5": top_values(group["Description"], 5),
            "examples": evidence(group.head(6)),
        })
    return result


def analyze_codes(frame: pd.DataFrame, totals: dict) -> dict:
    mask = ~frame["StockCode"].str.fullmatch(PRODUCT_PATTERN)
    unusual = frame.loc[mask]
    codes = []
    for code, group in unusual.groupby("StockCode", sort=True):
        descriptions = top_values(group["Description"], limit=5)
        category, interpretation = classify_code(str(code), group["Description"].unique().tolist())
        codes.append({
            "code": str(code), "category": category, "interpretation": interpretation,
            **amount_summary(group, totals), "descriptions": descriptions,
            "quantity_min": int(group["quantity"].min()), "quantity_max": int(group["quantity"].max()),
            "price_min_units": int(group["price_units"].min()), "price_max_units": int(group["price_units"].max()),
        })
    category_lookup = {item["code"]: item["category"] for item in codes}
    categories = []
    for category, group in unusual.groupby(unusual["StockCode"].map(category_lookup), sort=True):
        categories.append({"category": category, **amount_summary(group, totals)})
    normalized_mask = ~frame["StockCode"].str.strip().str.fullmatch(PRODUCT_PATTERN)
    return {
        **amount_summary(unusual, totals), "unique_codes": len(codes), "codes": codes,
        "categories": categories, "after_trim": amount_summary(frame.loc[normalized_mask], totals),
    }


def analyze_extremes(frame: pd.DataFrame) -> dict:
    minimum, maximum = frame["quantity"].min(), frame["quantity"].max()
    low, high = frame.loc[frame["quantity"].eq(minimum)], frame.loc[frame["quantity"].eq(maximum)]
    pairs = []
    # 只遍历极值候选，不在全表逐行匹配；这里的关联是待验证线索，不宣称真实订单关系。
    for _, sale in high.iterrows():
        candidates = low.loc[
            low["Customer ID"].eq(sale["Customer ID"]) & low["Customer ID"].ne("")
            & low["StockCode"].eq(sale["StockCode"]) & low["price_units"].eq(sale["price_units"])
            & low["quantity"].eq(-sale["quantity"]) & low["date"].gt(sale["date"])
        ]
        for _, reversal in candidates.iterrows():
            pairs.append({
                "positive_invoice": sale["Invoice"], "negative_invoice": reversal["Invoice"],
                "delay_minutes": (reversal["date"] - sale["date"]).total_seconds() / 60,
                "net_units": int(sale["amount_units"] + reversal["amount_units"]),
            })
    negative = frame.loc[frame["price_units"].lt(0)]
    return {
        "minimum": evidence(low), "maximum": evidence(high), "candidate_pairs": pairs,
        "negative_price": evidence(negative),
        "negative_price_summary": {
            "rows": len(negative), "quantity_values": sorted(negative["quantity"].unique().tolist()),
            "stock_codes": sorted(negative["StockCode"].unique().tolist()),
            "descriptions": sorted(negative["Description"].unique().tolist()),
            "all_customer_missing": bool(negative["customer_missing"].all()),
            "all_a_prefix": bool(negative["Invoice"].str.startswith("A").all()),
        },
        "all_a_records": evidence(frame.loc[frame["Invoice"].str.startswith("A")]),
    }


def candidate_mask(frame: pd.DataFrame) -> pd.Series:
    """比较客单价的显式筛选口径，尚不是最终业务清洗规则。"""
    return (
        frame["Invoice"].str.fullmatch(r"[0-9]+")
        & frame["StockCode"].str.strip().str.fullmatch(PRODUCT_PATTERN)
        & frame["quantity"].gt(0) & frame["price_units"].gt(0)
    )


def invoice_summary(frame: pd.DataFrame, scale: int) -> dict:
    invoices = frame.groupby("Invoice", sort=True).agg(amount_units=("amount_units", "sum"), lines=("Invoice", "size"))
    return {
        "invoices": len(invoices),
        "mean_amount": float(invoices["amount_units"].mean() / scale) if len(invoices) else None,
        "median_amount": float(invoices["amount_units"].median() / scale) if len(invoices) else None,
        "mean_lines": float(invoices["lines"].mean()) if len(invoices) else None,
        "median_lines": float(invoices["lines"].median()) if len(invoices) else None,
        "largest_invoices": invoices.reset_index().sort_values(["lines", "Invoice"], ascending=[False, True]).head(3).to_dict("records"),
    }


def product_top10(frame: pd.DataFrame) -> list[dict]:
    grouped = frame.groupby("StockCode", sort=True).agg(rows=("Invoice", "size"), quantity=("quantity", "sum"), net_units=("amount_units", "sum"))
    top = grouped.reset_index().sort_values(["rows", "StockCode"], ascending=[False, True]).head(10).to_dict("records")
    for item in top:
        item["description"] = top_values(frame.loc[frame["StockCode"].eq(item["StockCode"]), "Description"].replace("", pd.NA), 1)
    return top


def analyze_customers(frame: pd.DataFrame, totals: dict, scale: int) -> dict:
    invoice_flags = frame.groupby("Invoice")["customer_missing"].nunique()
    customer_counts = frame["Customer ID"].replace("", pd.NA).groupby(frame["Invoice"]).nunique()
    ambiguous = set(invoice_flags[invoice_flags.gt(1)].index) | set(customer_counts[customer_counts.gt(1)].index)
    timestamps = frame.groupby("Invoice")["date"].agg(["min", "max", "nunique"])
    result = {
        "ambiguous_invoices_excluded_from_aov": len(ambiguous),
        "multi_timestamp_invoices": int(timestamps["nunique"].gt(1).sum()),
        "max_invoice_time_span_minutes": float((timestamps["max"] - timestamps["min"]).dt.total_seconds().max() / 60),
        "groups": {},
    }
    for missing, key in [(True, "missing"), (False, "identified")]:
        group = frame.loc[frame["customer_missing"].eq(missing)]
        comparable = group.loc[candidate_mask(group)]
        countries = []
        for country, subgroup in group.groupby("Country", sort=True):
            countries.append({"country": str(country), "rows": len(subgroup), "within_group_pct": percent(len(subgroup), len(group)), "net_units": int(subgroup["amount_units"].sum())})
        result["groups"][key] = {
            **amount_summary(group, totals),
            "raw_invoices": invoice_summary(group.loc[~group["Invoice"].isin(ambiguous)], scale),
            "candidate_rows": len(comparable),
            "candidate_invoices": invoice_summary(comparable.loc[~comparable["Invoice"].isin(ambiguous)], scale),
            "countries": sorted(countries, key=lambda x: (-x["rows"], x["country"])),
            "raw_code_top10": top_values(group["StockCode"]), "candidate_product_top10": product_top10(comparable),
            "dot_rows": int(group["StockCode"].eq("DOT").sum()),
            "c_invoice_rows": int(group["Invoice"].str.startswith("C").sum()),
            "zero_price_rows": int(group["price_units"].eq(0).sum()),
        }
    return result


def build_findings(raw: pd.DataFrame) -> dict:
    frame, scale = prepare_frame(raw)
    totals = {"rows": len(frame), "net_units": int(frame["amount_units"].sum()), "absolute_units": int(frame["amount_units"].abs().sum())}
    return {
        "scale": scale, "totals": totals,
        "prefixes": analyze_prefixes(frame, totals), "special_codes": analyze_codes(frame, totals),
        "extremes": analyze_extremes(frame), "customers": analyze_customers(frame, totals, scale),
    }


def money(units: int, scale: int) -> str:
    return f"{Decimal(units) / scale:,.3f}"


def pct(value: float | None) -> str:
    return "不适用（分母为零）" if value is None else f"{value:.4f}%"


def display(value: float | None) -> str:
    return "不适用" if value is None else f"{value:,.3f}"


def records_table(records: list[dict], scale: int) -> str:
    return table(["记录序号", "Invoice", "StockCode", "Description", "Quantity", "Price", "Customer ID", "InvoiceDate", "Country", "金额（£）"], [
        [r[key] for key in ["record_no", "Invoice", "StockCode", "Description", "Quantity", "Price", "Customer ID", "InvoiceDate", "Country"]] + [money(r["amount_units"], scale)] for r in records
    ])


def render_findings(result: dict) -> str:
    scale, totals = result["scale"], result["totals"]
    codes, extremes, customers = result["special_codes"], result["extremes"], result["customers"]
    missing, known = customers["groups"]["missing"], customers["groups"]["identified"]
    prefixes = {row["prefix"]: row for row in result["prefixes"]}
    sections = [
        "# Q1.2 数据真实结构调查",
        "## 范围、依据与金额口径",
        f'输入：`{result["source"]["handle"]}`，**{totals["rows"]:,}** 条原始明细；SHA-256：`{result["source"]["sha256"]}`。不删除重复、零值、负值或缺失记录。',
        f'本文的行金额定义为 Quantity × Price。按原始价格精度使用 **1/{scale} 英镑**的整数单位累加，原始有符号合计为 **£{money(totals["net_units"], scale)}**，绝对金额合计为 **£{money(totals["absolute_units"], scale)}**。前者包含取消、费用与调整，**不是已经清洗好的销售收入**。金额展示保留三位小数；不先把 0.001 四舍五入为零。',
        f'[UCI 数据说明]({UCI_SOURCE})将 C 前缀定义为取消记录、价格单位定义为英镑，并说明存在批发客户。其他业务解释主要依据本文件的原始 Description、正负号和关联特征；推测不能等同于来源方确认。',
        "## 问题 1：非数字发票前缀",
        "支持代码：`analyze_prefixes()` 提取开头连续非数字字符，并同时统计明细数与独立发票数。以下列出全部前缀，纯数字组作为对照。",
        table(["前缀", "明细数", "独立发票数", "负数量", "正数量", "负价格", "零价格", "有符号金额（£）"], [
            [r["prefix"], r["rows"], r["invoices"], r["negative_quantity"], r["positive_quantity"], r["negative_price"], r["zero_price"], money(r["net_units"], scale)] for r in result["prefixes"]
        ]),
        f'**C：取消/冲回类记录。** 共 {prefixes.get("C", {}).get("rows", 0):,} 条。来源方明确其取消含义，但 C496350 的 Quantity=1、Description=Manual 是正数量例外。计算正向商品销售时应排除 C；计算商品净销售时，应按商品归属将取消金额单列或冲减，并保留例外核查。不能只用数量是否为负替代发票前缀判断。',
        f'**A：当前数据中的坏账调整。** 本数据全部 A 前缀记录见下方，StockCode=B，Description=Adjust bad debt，Quantity=1；共 {prefixes.get("A", {}).get("rows", 0)} 条。这个解释来自当前数据，并非宣称 A 在所有系统里都有同一含义。应从商品销量/商品销售额中分离，进入单独的调整对账表；原始层保留。',
        "**销售总额的选择：** 正向商品销售、扣除取消后的商品净销售、包含费用和调整的交易合计是不同指标。邮资、折扣、平台费、坏账需要各自定义；本题先展示完整分解，不把不同指标用同一名称混用。",
        records_table(extremes["all_a_records"], scale),
        "## 问题 2：StockCode 的格式和业务含义",
        "支持代码：`analyze_codes()` 使用完整匹配 `[0-9]+[A-Za-z]*`，接受纯数字或数字后接字母。原始代码不先 strip、不统一大小写，以免掩盖格式问题；业务解释由 `classify_code()` 给出。",
        f'原样筛出 **{codes["unique_codes"]} 种代码、{codes["rows"]:,} 条记录**，占全部行 **{pct(codes["row_pct"])}**；有符号金额 **£{money(codes["net_units"], scale)}**，占原始有符号合计 **{pct(codes["net_pct"])}**。负占比表示该组净额为负，不是计算错误。其绝对金额 **£{money(codes["absolute_units"], scale)}**，占全表绝对金额 **{pct(codes["absolute_pct"])}**，说明正负抵消后的净额会低估条目规模。',
        f'若只在比较时去除首尾空格，则剩 **{codes["after_trim"]["rows"]:,}** 条格式异常记录；差异来自 `"47503J "`。该条描述为实物园艺工具，不能被当作费用条目删除。',
        "### 全部格式异常代码的金额及描述证据",
        "以下逐一列出全部代码；展示最常见的非空描述，全部为空时明确标记。完整描述频次、数量和价格范围见 `.local/q1_findings.json`。",
        table(["原始代码（引号内保留空格）", "行数", "占全表行", "有符号金额（£）", "占全表净额", "描述证据（优先非空）", "暂定分类"], [
            [json.dumps(r["code"], ensure_ascii=False), r["rows"], pct(r["row_pct"]), money(r["net_units"], scale), pct(r["net_pct"]), next((d["value"] for d in r["descriptions"] if d["value"]), "（空）"), r["category"]] for r in codes["codes"]
        ]),
        "### 逐代码解释与处理建议",
        table(["代码", "基于当前数据的解读"], [[json.dumps(r["code"], ensure_ascii=False), r["interpretation"]] for r in codes["codes"]]),
        "### 分类汇总",
        table(["暂定分类", "行数", "有符号金额（£）", "占全表行", "占全表净额"], [
            [r["category"], r["rows"], money(r["net_units"], scale), pct(r["row_pct"]), pct(r["net_pct"])] for r in codes["categories"]
        ]),
        "**判断边界：** 非数字格式不等于非商品。部分 DCGS、SP1002 和 PADS 的描述明确指向实物商品；没有有效描述的 DCGS、C3、GIFT 则保留为待核查。礼券、样品、手工条目也不能仅凭代码决定最终收入归属。上述分类用于解释和分流，尚未写回原始数据。",
        "## 问题 3：数量极值与负价格",
        "支持代码：`analyze_extremes()` 获取数量最小/最大值的全部行；仅在极值候选之间比较客户、商品、单价、相反数量和先后时间。",
        records_table(extremes["maximum"] + extremes["minimum"], scale),
        table(["正向发票", "负向发票", "间隔（分钟）", "两条合计（£）"], [[p["positive_invoice"], p["negative_invoice"], p["delay_minutes"], money(p["net_units"], scale)] for p in extremes["candidate_pairs"]]),
        "**数量极值判断：** 两行客户、商品和单价相同，数量相反，短时间内出现取消记录且金额抵消。最有依据的解释是一次巨额录入随后被撤销，可能是误录后的纠正，也可能是真实大单取消；缺少原始订单系统记录，无法确认最初是否真实购买。不能把正向极值直接算作已实现销售，也不能只删除负向极值。原始层和取消分析保留两行；商品净额口径成对核查、避免双重扣减；推荐或客户分群是否剔除该已撤销行为，需要明确策略。",
        "### 全部负价格记录",
        records_table(extremes["negative_price"], scale),
        "这些记录共同表现为 A 前缀、B 代码、Quantity=1、Adjust bad debt 描述、英国记录且客户 ID 缺失，指向坏账调整，不是普通负单价商品。上方 A 组还包含一条 +11,062.06，紧接着有两条 −11,062.06；不能只保留负数或因为金额相同就删除一条。当前数据不足以断言重复或调整原因。",
        "**保留标准：** 有可解释业务含义的调整保留在可追溯原始/调整表；面向商品销售或模型训练时按用途排除或单列。只有在证实来源错误、明确修正规则和审计痕迹后才进行更正；异常程度本身不是删除依据。",
        "## 问题 4：缺少 Customer ID 的记录",
        "支持代码：`analyze_customers()` 以原始空字符串分组；记录数和金额先在全量原始数据上计算，再另设可比的正向商品候选口径。",
        table(["分组", "行数", "占全表行", "有符号金额（£）", "占全表净额", "占全表绝对金额"], [
            [label, r["rows"], pct(r["row_pct"]), money(r["net_units"], scale), pct(r["net_pct"]), pct(r["absolute_pct"])] for label, r in [("缺客户 ID", missing), ("有客户 ID", known)]
        ]),
        "缺失组的行数占比与金额占比并不相同，不能用删掉的行数比例估计对销售指标的影响。这里的净额仍包含所有业务类型；绝对金额比例用于补充揭示抵消效应。",
        "### 国家分布（两组各自前十国家/标签的并集）",
    ]
    country_names = set(r["country"] for r in missing["countries"][:10]) | set(r["country"] for r in known["countries"][:10])
    country_maps = [{r["country"]: r for r in group["countries"]} for group in [missing, known]]
    country_rows = []
    for name in sorted(country_names, key=lambda name: (-sum(m.get(name, {}).get("rows", 0) for m in country_maps), name)):
        left, right = [m.get(name, {"rows": 0, "within_group_pct": 0}) for m in country_maps]
        country_rows.append([name, left["rows"], pct(left["within_group_pct"]), right["rows"], pct(right["within_group_pct"])])
    sections.extend([
        table(["国家/标签", "缺失组行数", "占缺失组", "有 ID 组行数", "占有 ID 组"], country_rows),
        "完整国家分布保存在机器报告。Unspecified 是原始未指定标签，不应解释成一个国家。",
        "### 客单价：先定义一单是什么",
        "匿名记录无法还原独立自然人，本节把一单操作性地定义为一个独立 Invoice，不计算“人均消费”。原始单据均额保留取消、调整和零价单据；可比口径只取纯数字 Invoice、去空格后符合商品代码格式、Quantity>0 且 Price>0 的明细，先按 Invoice 求和再比较。此口径排除部分实物候选 DCGS/PADS 等，并非最终商品清洗规则。",
        f'缺失状态混合或含多个非空客户 ID 的发票从两组客单价中都排除，共 **{customers["ambiguous_invoices_excluded_from_aov"]}** 张。另有 **{customers["multi_timestamp_invoices"]}** 张发票含多个时间戳，最大跨度 **{customers["max_invoice_time_span_minutes"]:g} 分钟**；本次仍按来源定义的 Invoice 聚合，保留此限制。',
        table(["指标", "缺客户 ID", "有客户 ID"], [
            ["原始独立单据数", missing["raw_invoices"]["invoices"], known["raw_invoices"]["invoices"]],
            ["原始单据均额（£）", display(missing["raw_invoices"]["mean_amount"]), display(known["raw_invoices"]["mean_amount"])],
            ["原始单据金额中位数（£）", display(missing["raw_invoices"]["median_amount"]), display(known["raw_invoices"]["median_amount"])],
            ["可比正向明细数", missing["candidate_rows"], known["candidate_rows"]],
            ["可比独立单据数", missing["candidate_invoices"]["invoices"], known["candidate_invoices"]["invoices"]],
            ["可比单据均额（£）", display(missing["candidate_invoices"]["mean_amount"]), display(known["candidate_invoices"]["mean_amount"])],
            ["可比单据金额中位数（£）", display(missing["candidate_invoices"]["median_amount"]), display(known["candidate_invoices"]["median_amount"])],
            ["可比单据平均明细行数", display(missing["candidate_invoices"]["mean_lines"]), display(known["candidate_invoices"]["mean_lines"])],
        ]),
        "当前缺失组可比均额更高，中位数却更低，且单据平均明细行数更多。这表明长尾大单或汇总方式可能在抬高均值，不能直接得出“匿名客户更有钱/价值更高”的结论。",
        "### 高频代码与商品候选",
        "原始代码频次可能混入邮资，所以同时给出原始 TOP 10 与上述可比口径的商品 TOP 10；均按明细行出现次数排序，不把它当作独立客户数。商品描述取该组最常见的非空描述。",
    ])
    for label, group in [("缺客户 ID", missing), ("有客户 ID", known)]:
        sections.extend([
            f"#### {label}：原始代码 TOP 10",
            table(["StockCode", "明细行数"], [[r["value"], r["count"]] for r in group["raw_code_top10"]]),
            f"#### {label}：正向商品候选 TOP 10",
            table(["StockCode", "最常见描述", "明细行数", "数量合计", "金额（£）"], [
                [r["StockCode"], r["description"][0]["value"] if r["description"] else "（空）", r["rows"], r["quantity"], money(r["net_units"], scale)] for r in group["candidate_product_top10"]
            ]),
        ])
    sections.extend([
        "### 关于匿名群体的可支持推测",
        f'缺失组包含 **{missing["dot_rows"]:,}** 条 DOT（网站邮资）记录，有 ID 组只有 **{known["dot_rows"]:,}** 条。结合英国占比更高、部分发票包含大量商品明细、均值与中位数方向相反，缺失组可能混合了网站渠道汇总、未采集客户标识的交易，以及没有自然人客户含义的库存/财务调整。',
        "这是渠道或记录形成机制的假设，不是已经识别出的人群身份。数据没有访客登录状态、渠道订单明细或源系统映射，不能据此确定都是游客、线下客户或批发商。下一步需要来源方提供 Invoice 与渠道订单的映射及客户 ID 采集规则。",
        "## 复现与边界",
        "```bash\npython -m q1_data_quality.q1_code --part q1.2\n# 或独立运行统一入口\npython run_all.py --stage q1.2 --offline\n```",
        "支持代码在 `q1_data_quality/investigate.py`，机器结果写入 `.local/q1_findings.json`。所有金额分组均与全表校验对齐；本阶段只调查、定义比较口径，不执行最终清洗。Q1.3 再为报表、客户分群与推荐分别设计处理策略。",
    ])
    return "\n\n".join(sections) + "\n"


def run_q12(input_path: Path = ROOT / "data" / "online_retail_ii.csv", output_path: Path = ROOT / "q1_data_quality" / "findings.md", metrics_path: Path = ROOT / ".local" / "q1_findings.json") -> dict:
    started = perf_counter()
    dataset = load_sources()["retail"]
    validate_file(input_path, dataset["files"]["online_retail_II.csv"])
    raw = pd.read_csv(input_path, dtype="string", keep_default_na=False)
    result = build_findings(raw)
    result["source"] = {"handle": dataset["handle"], "sha256": sha256_file(input_path), "description_url": UCI_SOURCE}
    for field in ("rows", "net_units", "absolute_units"):
        if sum(row[field] for row in result["prefixes"]) != result["totals"][field]:
            raise AssertionError(f"前缀分解未与全表对齐：{field}")
        if sum(row[field] for row in result["customers"]["groups"].values()) != result["totals"][field]:
            raise AssertionError(f"客户分组未与全表对齐：{field}")
        for group in ("codes", "categories"):
            if sum(row[field] for row in result["special_codes"][group]) != result["special_codes"][field]:
                raise AssertionError(f"特殊代码分解未对齐：{group}/{field}")
    for path in (output_path, metrics_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    output_path.write_text(render_findings(result), encoding="utf-8")
    LOGGER.info("Q1.2 完成：%s；耗时 %.2f 秒", output_path, perf_counter() - started)
    return result
