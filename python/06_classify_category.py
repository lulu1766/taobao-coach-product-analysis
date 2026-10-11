"""
06_classify_category.py — 从商品标题打品类标签
============================================================
职责：
  基于清洗后 title 的关键词，按「优先级规则」给每个商品打品类标签，
  新增 category（品类）和 category_rule（命中关键词，审计用）两列，写回 clean csv。

品类体系（10 个正式品类 + 未分类兜底，共 11 类，≤12）：
  香水 / 手表 / 首饰 / 腰带 / 围巾丝巾 / 鞋靴 / 服饰 /
  钱包卡包 / 包袋 / 其他配饰 / 未分类

为什么用优先级而非简单包含：
  - 「钱包」含「包」字，必须先判钱包卡包再判包袋，否则全被包袋吃掉；
  - 手表标题常含「三眼皮带」，手表必须先于腰带判断；
  - 强专属词（香水/手表/首饰）不会与包袋冲突，优先判定最稳。

输入：data/processed/coach_products_clean.csv
输出：覆盖写回同一 csv，新增 category、category_rule

运行：
    py python\\06_classify_category.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CLEAN_CSV = ROOT / "data" / "processed" / "coach_products_clean.csv"

# ---------- 品类规则表（顺序即优先级，从上到下先命中先归类）----------
# 每条：(品类名, [关键词列表])。标题统一 lower 后匹配。
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("香水", ["香水", "淡香", "浓香", "香氛", "parfum", "toilette", "edp", "edt", "cologne"]),
    ("手表", ["手表", "腕表", "三眼表", "boyfriend系列"]),
    ("首饰", ["项链", "手链", "手镯", "耳环", "耳钉", "耳饰", "戒指", "锁骨", "吊坠", "首饰", "饰品"]),
    ("腰带", ["腰带", "皮带", "针扣", "腰带女", "腰带男"]),
    ("围巾丝巾", ["围巾", "丝巾", "披肩"]),
    ("鞋靴", ["凉鞋", "拖鞋", "板鞋", "运动鞋", "高跟鞋", "平底鞋", "单鞋", "靴子", "短靴", "长靴",
              "sneaker", "鞋", "靴"]),
    ("服饰", ["t恤", "卫衣", "外套", "夹克", "茄克", "风衣", "大衣", "棉服", "羽绒服", "衬衫",
              "连衣裙", "半身裙", "半裙", "miniskirt", "skirt", "裙子", "长裤", "短裤",
              "牛仔裤", "运动裤", "毛衣", "针织衫", "帽衫", "polo", "服饰", "上衣"]),
    ("钱包卡包", ["钱包", "卡包", "零钱包", "钱夹", "钥匙包", "wristlet", "手拿包小号", "信封包"]),
    ("包袋", ["托特", "tote", "手袋", "单肩", "斜挎", "斜跨", "手提", "腋下", "手拎", "背包",
             "双肩", "水桶", "流浪", "麻将包", "贝壳包", "马鞍包", "法棍", "月牙", "半月",
             "波士顿", "hobo", "托包", "包包", "女包", "男包", "包袋", "bag", "包"]),
    ("其他配饰", ["挂件", "挂饰", "钥匙扣", "charm", "眼镜", "墨镜", "太阳镜", "帽子", "手套"]),
]


def classify(title) -> tuple[str, str]:
    """按优先级规则返回 (品类, 命中规则)。"""
    if pd.isna(title) or not str(title).strip():
        return "未分类", "标题为空"
    t = str(title).lower()
    for cat, kws in CATEGORY_RULES:
        for kw in kws:
            if kw in t:
                return cat, f"命中「{kw}」"
    return "未分类", "无品类关键词"


def main() -> int:
    print("=" * 60)
    print("06 商品品类分类")
    print("=" * 60)

    if not CLEAN_CSV.exists():
        print(f"[错误] 找不到 {CLEAN_CSV}，请先运行 02/04 脚本")
        return 2
    df = pd.read_csv(CLEAN_CSV, encoding="utf-8-sig")
    print(f"\n[1] 读取 {len(df)} 条商品")

    # [2] 分类
    print("\n[2] 关键词优先级分类")
    res = df["title"].apply(classify)
    df["category"] = res.apply(lambda x: x[0])
    df["category_rule"] = res.apply(lambda x: x[1])

    # [3] 分布
    print("\n[3] 品类分布")
    total = len(df)
    counts = df["category"].value_counts()
    for cat, n in counts.items():
        print(f"    {cat:<8}: {n:>4} 条 ({n/total*100:5.1f}%)")

    # [4] 未分类抽样（检查规则是否需要补词）
    unk = df[df["category"] == "未分类"]
    print(f"\n[4] 未分类 {len(unk)} 条（抽样核对）")
    for t in unk["title"].head(15):
        print(f"    - {t[:60]}")

    # [5] 各品类价格×销量概览（为分品类价格带分析做准备）
    print("\n[5] 各品类价格/销量概览")
    overview = df.groupby("category").agg(
        数量=("title", "count"),
        价格中位=("price", "median"),
        销量中位=("sales_count", "median"),
        销量均值=("sales_count", "mean"),
        总销量=("sales_count", "sum"),
    ).sort_values("总销量", ascending=False)
    print(overview.round(0).to_string())

    # [6] 各类抽样核对
    print("\n[6] 各品类抽样 1 条核对")
    for cat in counts.index:
        sample = df[df["category"] == cat].iloc[0]
        print(f"    【{cat}】{str(sample['title'])[:48]}")

    # [7] 写回（处理 Excel 占用）
    try:
        df.to_csv(CLEAN_CSV, index=False, encoding="utf-8-sig", lineterminator="\n")
        print(f"\n[7] 已写回 {CLEAN_CSV.name}，新增 category、category_rule")
    except PermissionError:
        alt = CLEAN_CSV.with_name("coach_products_clean_with_category.csv")
        df.to_csv(alt, index=False, encoding="utf-8-sig", lineterminator="\n")
        print(f"\n[7] [警告] 原 csv 被 Excel 占用，结果另存为 {alt.name}；请关闭 Excel 后重跑。")
        return 5

    print(f"    最终字段：{list(df.columns)}")
    print("\n完成。分品类后，黄金价格带分析将更准确（香水/配饰不再干扰包袋）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
