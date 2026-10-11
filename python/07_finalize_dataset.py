"""
07_finalize_dataset.py — 分析数据集定稿（在 02/04/06 基础上补充分析字段 + 三页签报告）
====================================================================================
定位：本脚本不重复 02 的清洗，而是读取已清洗的 coach_products_clean.csv，
      补充 EDA/爆款分析直接需要的派生字段，并产出面试展示用三页签 Excel 报告。

真实数据适配（与通用 Prompt 模板的差异，已按实际字段落地）：
  - brand_match 是独立列（不是 shop_type.brand_match）
  - price / sales_count 在 02 已转数字，这里只校验类型，不重复解析
  - url 未采集（整列为空）→ 跳过 url 去重，仅做标题相似度「标记不删除」
  - 价格异常只「标记」，不二次删除（02 已按 >10000 剔除过一轮）

新增字段：
  title_clean     规范化标题（与 02 一致，再做一次列名固化，供下游引用）
  price_clean     数值价格校验列
  sales_count_clean 数值销量校验列（0 为有效销量，不是缺失）
  brand_valid     是否 Coach 品牌（来自 brand_match）
  category_clean  标准化品类（来自 category）
  duplicate_flag  疑似重复标记（1=标题高度相似；不删除，只标记）
  keyword_tag     标题特征关键词（| 分隔，供 Q3 爆款特征分析）
  price_range     价格带（0-500/500-1000/1000-2000/2000-3000/3000+）

输出：
  data/processed/coach_product_clean.csv   分析就绪最终数据
  logs/cleaning_report.xlsx                Sheet1 数据 / Sheet2 清洗日志 / Sheet3 异常记录

运行：
    py python\\07_finalize_dataset.py
"""

from __future__ import annotations

import sys
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd

# ---------- 路径 ----------
ROOT = Path(__file__).resolve().parent.parent
IN_CSV = ROOT / "data" / "processed" / "coach_products_clean.csv"
OUT_CSV = ROOT / "data" / "processed" / "coach_product_clean.csv"
REPORT_XLSX = ROOT / "logs" / "cleaning_report.xlsx"

# ---------- 价格带（指导书 5.2）----------
PRICE_BINS = [0, 500, 1000, 2000, 3000, np.inf]
PRICE_LABELS = ["0-500", "500-1000", "1000-2000", "2000-3000", "3000+"]

# ---------- 价格异常标记阈值（只标记不删除）----------
PRICE_FLAG_LOW = 0
PRICE_FLAG_HIGH = 50000

# ---------- 标题相似度阈值（>= 判疑似重复）----------
SIM_THRESHOLD = 0.90

# ---------- Q3 爆款特征关键词表（小写匹配；顺序即标签输出顺序）----------
KEYWORD_TAGS: list[tuple[str, list[str]]] = [
    ("Tabby", ["tabby"]),
    ("Rogue", ["rogue"]),
    ("Willow", ["willow"]),
    ("City", ["city"]),
    ("Rowan", ["rowan"]),
    ("Mollie", ["mollie"]),
    ("Laurel", ["laurel"]),
    ("Teri", ["teri"]),
    ("Brooklyn", ["brooklyn"]),
    ("托特", ["托特", "tote"]),
    ("单肩", ["单肩"]),
    ("斜挎", ["斜挎", "斜跨"]),
    ("手提", ["手提", "手拎"]),
    ("腋下", ["腋下"]),
    ("水桶", ["水桶"]),
    ("麻将包", ["麻将"]),
    ("流浪包", ["流浪"]),
    ("山茶花", ["山茶花"]),
    ("链条", ["链条"]),
    ("老花", ["老花"]),
    ("钱包", ["钱包", "钱夹"]),
    ("卡包", ["卡包"]),
    ("波士顿", ["波士顿"]),
    ("牛仔", ["牛仔"]),
    ("真皮", ["真皮", "牛皮", "全皮", "羊皮"]),
]


# ============ 各字段处理函数（每个职责单一，便于扩展/单测）============

def normalize_title(s) -> str:
    """规范化标题：转字符串、压空格、去首尾空白；已是 02 清洗结果，这里只固化。"""
    if pd.isna(s):
        return ""
    return " ".join(str(s).split()).strip()


def to_number(v) -> float:
    """转数值；无法解析返回 NaN（不把 0 当缺失）。"""
    try:
        x = float(str(v).replace("¥", "").replace("￥", "").replace(",", "").strip())
        return x
    except (ValueError, TypeError):
        return np.nan


def extract_keywords(title: str) -> str:
    """从标题提取特征关键词，多标签用 | 连接；无命中返回空串。"""
    t = str(title).lower()
    hits = [tag for tag, kws in KEYWORD_TAGS if any(k in t for k in kws)]
    return "|".join(hits)


def mark_similar_titles(df: pd.DataFrame) -> pd.Series:
    """
    标题相似度去重标记（不删除）：
      - 优先 url：本数据未采集 url，自动跳过；
      - 同品类内两两比对，SequenceMatcher 相似度 >= 阈值则双方标记 1。
    同品类内比对可降低 O(n²) 开销并减少跨品类误判（352 行可接受）。
    返回与 df 等长的 duplicate_flag(int) Series。
    """
    flag = pd.Series(0, index=df.index, dtype=int)

    # 若存在非空 url，则 url 完全相同标 1
    if "url" in df.columns and df["url"].notna().any():
        dup_url = df["url"].duplicated(keep=False) & df["url"].notna()
        flag.loc[dup_url] = 1

    titles = df["title_clean"].tolist()
    cats = df["category_clean"].tolist() if "category_clean" in df.columns else [""] * len(df)
    idxs = df.index.tolist()

    # 按品类分桶，桶内两两比对
    buckets: dict[str, list[int]] = {}
    for i, c in enumerate(cats):
        buckets.setdefault(str(c), []).append(i)

    for _, members in buckets.items():
        for a in range(len(members)):
            i = members[a]
            ti = titles[i]
            if not ti:
                continue
            for b in range(a + 1, len(members)):
                j = members[b]
                tj = titles[j]
                if not tj:
                    continue
                # quick_ratio 先粗筛（快），过了再算精确 ratio
                sm = SequenceMatcher(None, ti, tj)
                if sm.quick_ratio() >= SIM_THRESHOLD and sm.ratio() >= SIM_THRESHOLD:
                    flag.loc[idxs[i]] = 1
                    flag.loc[idxs[j]] = 1
    return flag


def price_range_of(p: float) -> str:
    """价格带分箱（pd.cut 的行级版本，便于对异常/缺失单独处理）。"""
    if pd.isna(p):
        return "未知"
    for (lo, hi), lab in zip(zip(PRICE_BINS[:-1], PRICE_BINS[1:]), PRICE_LABELS):
        if lo <= p < hi:
            return lab
    return "未知"


def main() -> int:
    print("=" * 60)
    print("07 分析数据集定稿")
    print("=" * 60)

    # [0] 读取（支持 csv / xlsx，优先已清洗 csv）
    if IN_CSV.exists():
        df = pd.read_csv(IN_CSV, encoding="utf-8-sig")
        print(f"\n[0] 读取已清洗数据：{IN_CSV.name}（{len(df)} 行）")
    else:
        raw_xlsx = ROOT / "data" / "raw" / "coach_products_raw.xlsx"
        if not raw_xlsx.exists():
            print("[错误] 找不到输入文件，请先运行 02/04/06")
            return 2
        df = pd.read_excel(raw_xlsx)
        print(f"\n[0] 未找到 clean csv，回退读取 raw：{raw_xlsx.name}（{len(df)} 行）")

    n_raw = len(df)

    # [1] title_clean
    df["title_clean"] = df["title"].apply(normalize_title) if "title" in df.columns else ""

    # [2] 数值校验列（已在 02 转好，这里固化类型；0 是有效值）
    df["price_clean"] = df["price"].apply(to_number) if "price" in df.columns else np.nan
    df["sales_count_clean"] = df["sales_count"].apply(to_number) if "sales_count" in df.columns else np.nan
    df["sales_count_clean"] = df["sales_count_clean"].fillna(0).astype(int)

    # [3] 品牌有效性（来自 04 的 brand_match；缺失则按标题兜底重算）
    if "brand_match" in df.columns:
        df["brand_valid"] = df["brand_match"].astype(bool)
    else:
        df["brand_valid"] = df["title_clean"].str.contains("coach|蔻驰", case=False, regex=True)

    # [4] 品类标准化（06 已分 11 类，直接固化；缺失标未分类）
    df["category_clean"] = df["category"].fillna("未分类") if "category" in df.columns else "未分类"

    # [5] 价格异常标记（只标记，不删除）
    df["price_anomaly"] = (
        df["price_clean"].isna()
        | (df["price_clean"] <= PRICE_FLAG_LOW)
        | (df["price_clean"] > PRICE_FLAG_HIGH)
    )

    # [6] 价格带
    df["price_range"] = df["price_clean"].apply(price_range_of)

    # [7] 关键词标签
    df["keyword_tag"] = df["title_clean"].apply(extract_keywords)

    # [8] 疑似重复标记（标题相似度，不删除）
    print("\n[8] 标题相似度比对（同品类内，阈值 %.2f）..." % SIM_THRESHOLD)
    df["duplicate_flag"] = mark_similar_titles(df)

    # ============ 数据质量报告 ============
    print("\n" + "=" * 60)
    print("数据质量报告")
    print("=" * 60)
    report_rows = [
        ("原始数据数量", n_raw),
        ("清洗后数量", len(df)),
        ("缺失 title_clean", int((df["title_clean"] == "").sum())),
        ("价格无法解析", int(df["price_clean"].isna().sum())),
        ("异常价格标记(<=0 或 >50000)", int(df["price_anomaly"].sum())),
        ("销量为0(有效,非缺失)", int((df["sales_count_clean"] == 0).sum())),
        ("疑似重复标记数", int(df["duplicate_flag"].sum())),
        ("非Coach品牌标记数", int((~df["brand_valid"]).sum())),
        ("未分类品类数", int((df["category_clean"] == "未分类").sum())),
        ("有关键词标签数", int((df["keyword_tag"] != "").sum())),
    ]
    for k, v in report_rows:
        print(f"  {k:<28}: {v}")

    # 价格带分布
    print("\n价格带分布：")
    print(df["price_range"].value_counts().reindex(PRICE_LABELS + ["未知"], fill_value=0).to_string())

    # TOP 关键词
    print("\n高频特征词 TOP12：")
    all_tags = df["keyword_tag"].replace("", pd.NA).dropna().str.split("|").explode()
    print(all_tags.value_counts().head(12).to_string())

    # ============ 保存最终 CSV ============
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig", lineterminator="\n")
    print(f"\n已保存分析数据：{OUT_CSV.relative_to(ROOT)}（{len(df)} 行 × {len(df.columns)} 列）")

    # ============ 三页签 Excel 报告 ============
    # Sheet2 清洗日志
    log_df = pd.DataFrame(report_rows, columns=["检查项", "数量"])
    # 补一行价格带分布明细
    band_df = df["price_range"].value_counts().reindex(PRICE_LABELS + ["未知"], fill_value=0).reset_index()
    band_df.columns = ["价格带", "商品数"]

    # Sheet3 异常/需人工复核记录（价格异常 / 非品牌 / 疑似重复 / 未分类）
    suspect_mask = df["price_anomaly"] | (~df["brand_valid"]) | (df["duplicate_flag"] == 1) | (df["category_clean"] == "未分类")
    suspect_cols = ["title_clean", "price_clean", "sales_count_clean", "category_clean",
                    "price_range", "brand_valid", "duplicate_flag", "price_anomaly"]
    suspect_cols = [c for c in suspect_cols if c in df.columns]
    suspect_df = df.loc[suspect_mask, suspect_cols].copy()
    # 异常原因
    def reason(r):
        rs = []
        if r.get("price_anomaly", False):
            rs.append("价格异常")
        if not r.get("brand_valid", True):
            rs.append("非Coach品牌")
        if r.get("duplicate_flag", 0) == 1:
            rs.append("疑似重复")
        if r.get("category_clean") == "未分类":
            rs.append("未分类")
        return "、".join(rs)
    if len(suspect_df):
        suspect_df["异常原因"] = suspect_df.apply(reason, axis=1)

    REPORT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pd.ExcelWriter(REPORT_XLSX, engine="openpyxl") as w:
            df.to_excel(w, sheet_name="清洗后数据", index=False)
            log_df.to_excel(w, sheet_name="清洗日志", index=False, startrow=0)
            # 价格带明细接在日志下方
            band_df.to_excel(w, sheet_name="清洗日志", index=False, startrow=len(log_df) + 2)
            suspect_df.to_excel(w, sheet_name="异常数据记录", index=False)
        print(f"已保存报告：{REPORT_XLSX.relative_to(ROOT)}")
        print(f"  Sheet1 清洗后数据 {len(df)} 行 | Sheet2 清洗日志 | Sheet3 异常记录 {len(suspect_df)} 行")
    except PermissionError:
        print(f"[警告] {REPORT_XLSX.name} 被 Excel 占用，请关闭后重跑。")
        return 5

    print("\n定稿完成，可直接进入 EDA / 爆款分析 / Tableau·PowerBI。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
