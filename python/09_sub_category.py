"""
09_sub_category.py — 在大分类下打小分类（二级品类）
============================================================
职责：读取 coach_product_clean.csv，仅新增 sub_category / sub_category_rule 两列，
      不修改任何已有字段（其他列原样保留）。

规则：按 category_clean 分桶，每个桶内用关键词优先级匹配，先命中先归类。
      包袋是重点（249 条），先匹配具体包型（托特/波士顿/水桶…），再回退背法（单肩/斜挎/手提/腋下）。

输入：data/processed/coach_product_clean.csv
输出：覆盖写回同一 csv，新增两列；其他列不变。

运行：
    py python\\09_sub_category.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "processed" / "coach_product_clean.csv"

# ---------- 各品类小分类规则表（顺序即优先级，命中即停）----------
# key: 大品类；value: list[(小分类, [关键词])]
SUB_RULES: dict[str, list[tuple[str, list[str]]]] = {
    # —— 包袋（重点）：先具体包型，再背法 ——
    "包袋": [
        ("托特包", ["托特", "tote"]),
        ("波士顿包", ["波士顿", "boston"]),
        ("水桶包", ["水桶"]),
        ("流浪包", ["流浪"]),
        ("麻将包", ["麻将"]),
        ("双肩包", ["双肩", "背包"]),
        ("法棍包", ["法棍"]),
        ("马鞍包", ["马鞍"]),
        ("贝壳包", ["贝壳"]),
        ("腰包", ["腰包", "胸包"]),
        ("信封包", ["信封包"]),
        ("月牙包", ["月牙", "半月"]),
        ("hobo包", ["hobo"]),
        ("腋下包", ["腋下"]),
        ("单肩包", ["单肩"]),
        ("斜挎包", ["斜挎", "斜跨"]),
        ("手提包", ["手提", "手拎"]),
    ],
    # —— 钱包卡包 ——
    "钱包卡包": [
        ("钱包", ["钱包", "钱夹"]),
        ("卡包", ["卡包", "证件包"]),
        ("零钱包", ["零钱包"]),
        ("手拿包", ["手拿包", "手挽", "腕包", "wristlet"]),
    ],
    # —— 香水 ——
    "香水": [
        ("香水礼盒", ["礼盒", "套装"]),
        ("香水小样", ["小样", "q版"]),
        ("男士香水", ["男士", "男香"]),
        ("女士香水", ["女士", "女香"]),
    ],
    # —— 服饰 ——
    "服饰": [
        ("T恤", ["t恤", "短袖"]),
        ("卫衣", ["卫衣", "帽衫"]),
        ("外套夹克", ["外套", "夹克", "茄克"]),
        ("风衣大衣", ["风衣", "大衣", "棉服", "羽绒服"]),
        ("裤装", ["裤", "短裤", "长裤", "牛仔裤"]),
        ("裙装", ["裙", "半身裙", "连衣裙", "miniskirt"]),
        ("针织毛衣", ["毛衣", "针织衫"]),
    ],
    # —— 首饰 ——
    "首饰": [
        ("手链", ["手链"]),
        ("手镯", ["手镯"]),
        ("耳钉", ["耳钉", "耳环", "耳饰"]),
        ("项链", ["项链", "锁骨", "吊坠"]),
        ("戒指", ["戒指"]),
    ],
    # —— 手表 ——
    "手表": [
        ("男士手表", ["男士", "男表"]),
        ("女士手表", ["女士", "女表"]),
    ],
    # —— 围巾丝巾 ——
    "围巾丝巾": [
        ("围巾", ["围巾", "围脖"]),
        ("丝巾", ["丝巾"]),
        ("披肩", ["披肩"]),
    ],
    # —— 腰带 ——
    "腰带": [
        ("男士腰带", ["男士", "男"]),
        ("女士腰带", ["女士", "女"]),
    ],
    # —— 其他配饰 ——
    "其他配饰": [
        ("墨镜", ["墨镜", "太阳镜"]),
        ("眼镜", ["眼镜", "镜架"]),
    ],
    # —— 鞋靴 ——
    "鞋靴": [
        ("凉鞋", ["凉鞋"]),
        ("高跟鞋", ["高跟"]),
        ("单鞋", ["单鞋", "玛丽珍", "芭蕾"]),
        ("运动鞋", ["运动", "帆布", "板鞋", "休闲鞋"]),
    ],
}


def classify_sub(title: str, big_cat: str) -> tuple[str, str]:
    """返回 (小分类, 命中规则)。"""
    if pd.isna(title) or not str(title).strip():
        return ("未分类", "标题为空")
    t = str(title).lower()
    rules = SUB_RULES.get(big_cat)
    if not rules:
        return (str(big_cat), "该大品类无细分规则")
    for sub, kws in rules:
        for kw in kws:
            if kw in t:
                return (sub, f"命中「{kw}」")
    # 该大品类下没匹配到具体小分类 → 用兜底名
    return (f"{big_cat}-其他", "未命中细分关键词")


def main() -> int:
    print("=" * 60)
    print("09 二级小分类打标（仅新增两列，其他不变）")
    print("=" * 60)

    if not CSV.exists():
        print(f"[错误] 找不到 {CSV}，请先运行 07/08")
        return 2
    df = pd.read_csv(CSV, encoding="utf-8-sig")
    n_orig = len(df)
    cols_orig = list(df.columns)
    print(f"\n[1] 读取 {n_orig} 行，原 {len(cols_orig)} 列")

    # [2] 打小分类
    print("\n[2] 按大品类分桶，关键词优先级匹配")
    res = df.apply(lambda r: classify_sub(r.get("title_clean", r.get("title", "")),
                                           r.get("category_clean", "")), axis=1)
    df["sub_category"] = res.apply(lambda x: x[0])
    df["sub_category_rule"] = res.apply(lambda x: x[1])

    # [3] 分布：按大品类→小分类交叉表
    print("\n[3] 小分类分布（按大品类分组）")
    for big, g in df.groupby("category_clean", sort=False):
        print(f"\n  【{big}】共 {len(g)} 条")
        sub_counts = g["sub_category"].value_counts()
        for s, c in sub_counts.items():
            print(f"      {s:<12}: {c:>4}")

    # [4] 抽样核对
    print("\n[4] 各小分类抽样核对（每类 1 条）")
    seen = set()
    for _, r in df.iterrows():
        s = r["sub_category"]
        if s in seen:
            continue
        seen.add(s)
        print(f"    【{s}】{str(r['title_clean'])[:48]}  ({r['category_clean']})")

    # [5] 写回（仅新增两列）
    new_cols = [c for c in df.columns if c not in cols_orig]
    assert new_cols == ["sub_category", "sub_category_rule"], f"意外修改了列: {new_cols}"

    try:
        df.to_csv(CSV, index=False, encoding="utf-8-sig", lineterminator="\n")
    except PermissionError:
        alt = CSV.with_name("coach_product_clean_with_subcat.csv")
        df.to_csv(alt, index=False, encoding="utf-8-sig", lineterminator="\n")
        print(f"\n[5] [警告] {CSV.name} 被 Excel 占用，结果另存为 {alt.name}；请关闭后重跑。")
        return 5

    print(f"\n[5] 已写回 {CSV.name}")
    print(f"    原有 {len(cols_orig)} 列保持不变，仅新增 {new_cols}")
    print(f"    最终 {len(df.columns)} 列，{len(df)} 行")
    print("\n完成。后续分析可按 category_clean × sub_category 下钻。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
