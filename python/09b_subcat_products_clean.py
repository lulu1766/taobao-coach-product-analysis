"""
09b_subcat_products_clean.py — 给 coach_products_clean.csv 加小分类列
====================================================================
背景：coach_products_clean.csv 是手动整理的表，有两行表头（大表头合并单元格 + 子表头）。
目标：在「分类」列后插入「小分类」列，其他一切不变（包括两行表头结构、编码 gbk）。

列结构（插入前）：
  大表头: 商品信息(3列) | 销售表现(6列) | 渠道信息(3列)
  子表头: 产品id 产品名 分类 | 价格 价格区间 销量 销量区间 销量占比 平均销量 | 发货地 渠道 crawl_time

插入后：
  大表头: 商品信息(4列) | 销售表现(6列) | 渠道信息(3列)
  子表头: 产品id 产品名 分类 小分类 | 价格 价格区间 销量 销量区间 销量占比 平均销量 | 发货地 渠道 crawl_time

复用 09 的小分类规则（按大分类分桶 + 关键词优先级）。

运行：
    py python\\09b_subcat_products_clean.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "processed" / "coach_products_clean.csv"

# 复用 09 的规则表
SUB_RULES: dict[str, list[tuple[str, list[str]]]] = {
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
    "钱包卡包": [
        ("钱包", ["钱包", "钱夹"]),
        ("卡包", ["卡包", "证件包"]),
        ("零钱包", ["零钱包"]),
        ("手拿包", ["手拿包", "手挽", "腕包", "wristlet"]),
    ],
    "香水": [
        ("香水礼盒", ["礼盒", "套装"]),
        ("香水小样", ["小样", "q版"]),
        ("男士香水", ["男士", "男香"]),
        ("女士香水", ["女士", "女香"]),
    ],
    "服饰": [
        ("T恤", ["t恤", "短袖"]),
        ("卫衣", ["卫衣", "帽衫"]),
        ("外套夹克", ["外套", "夹克", "茄克"]),
        ("风衣大衣", ["风衣", "大衣", "棉服", "羽绒服"]),
        ("裤装", ["裤", "短裤", "长裤", "牛仔裤"]),
        ("裙装", ["裙", "半身裙", "连衣裙", "miniskirt"]),
        ("针织毛衣", ["毛衣", "针织衫"]),
    ],
    "首饰": [
        ("手链", ["手链"]),
        ("手镯", ["手镯"]),
        ("耳钉", ["耳钉", "耳环", "耳饰"]),
        ("项链", ["项链", "锁骨", "吊坠"]),
        ("戒指", ["戒指"]),
    ],
    "手表": [
        ("男士手表", ["男士", "男表"]),
        ("女士手表", ["女士", "女表"]),
    ],
    "围巾丝巾": [
        ("围巾", ["围巾", "围脖"]),
        ("丝巾", ["丝巾"]),
        ("披肩", ["披肩"]),
    ],
    "腰带": [
        ("男士腰带", ["男士", "男"]),
        ("女士腰带", ["女士", "女"]),
    ],
    "其他配饰": [
        ("墨镜", ["墨镜", "太阳镜"]),
        ("眼镜", ["眼镜", "镜架"]),
    ],
    "鞋靴": [
        ("凉鞋", ["凉鞋"]),
        ("高跟鞋", ["高跟"]),
        ("单鞋", ["单鞋", "玛丽珍", "芭蕾"]),
        ("运动鞋", ["运动", "帆布", "板鞋", "休闲鞋"]),
    ],
}


def classify_sub(title: str, big_cat: str) -> str:
    if pd.isna(title) or not str(title).strip():
        return "未分类"
    t = str(title).lower()
    rules = SUB_RULES.get(big_cat)
    if not rules:
        return str(big_cat)
    for sub, kws in rules:
        if any(k in t for k in kws):
            return sub
    return f"{big_cat}-其他"


def main() -> int:
    print("=" * 60)
    print("09b 给 coach_products_clean.csv 加小分类列（其他不变）")
    print("=" * 60)

    if not CSV.exists():
        print(f"[错误] 找不到 {CSV}")
        return 2

    # 用 header=None 读取全部行（保留两行表头）
    raw = pd.read_csv(CSV, encoding="gbk", header=None, dtype=str)
    print(f"\n[1] 读取 {len(raw)} 行 × {raw.shape[1]} 列（含两行表头）")

    # 自动识别大表头行（含"商品信息"）和子表头行（含"产品id"），
    # 不固定行号，避免上次表头顺序被打乱后定位错误
    big_idx = None
    sub_idx = None
    for i in range(min(5, len(raw))):
        row_vals = raw.iloc[i].fillna("").astype(str).tolist()
        joined = " ".join(row_vals)
        if "商品信息" in joined and big_idx is None:
            big_idx = i
        if "产品id" in joined and sub_idx is None:
            sub_idx = i

    if big_idx is None or sub_idx is None:
        print(f"[错误] 无法识别表头行（big={big_idx}, sub={sub_idx}）")
        return 3

    big_header = raw.iloc[big_idx].fillna("").tolist()
    sub_header = raw.iloc[sub_idx].fillna("").tolist()
    # 数据行 = 子表头之后的所有行
    data_start = max(big_idx, sub_idx) + 1
    data = raw.iloc[data_start:].reset_index(drop=True)
    print(f"    大表头行={big_idx}, 子表头行={sub_idx}")
    print(f"    子表头: {sub_header}")

    # 如果之前误操作已存在「小分类」列，先删除（避免重复列）
    while "小分类" in sub_header:
        dup_idx = sub_header.index("小分类")
        sub_header.pop(dup_idx)
        big_header.pop(dup_idx)
        data = data.drop(columns=data.columns[dup_idx])

    # 定位「分类」列索引，小分类插在它后面
    if "分类" not in sub_header:
        print("[错误] 找不到「分类」列")
        return 3
    cat_idx = sub_header.index("分类")
    name_idx = sub_header.index("产品名")  # 用于打小分类
    insert_idx = cat_idx + 1

    # 计算每行小分类
    print(f"\n[2] 按大分类匹配小分类，共 {len(data)} 条数据")
    sub_cats = []
    for _, row in data.iterrows():
        sub_cats.append(classify_sub(row[name_idx], row[cat_idx]))

    # 组装新表头与新数据（用纯 list，按正确顺序：大表头→子表头→数据）
    # 大表头：在插入位置留空，商品信息合并范围从3列扩到4列
    new_big = big_header[:insert_idx] + [pd.NA] + big_header[insert_idx:]
    # 子表头：插入「小分类」
    new_sub = sub_header[:insert_idx] + ["小分类"] + sub_header[insert_idx:]

    # 数据行：在 insert_idx 位置插入小分类
    new_data = []
    for i, (_, row) in enumerate(data.iterrows()):
        vals = row.tolist()
        vals.insert(insert_idx, sub_cats[i])
        new_data.append(vals)

    # 完整输出行 = 大表头 + 子表头 + 数据行
    all_rows = [new_big, new_sub] + new_data
    out = pd.DataFrame(all_rows)

    # 分布统计
    print("\n[3] 小分类分布：")
    from collections import Counter
    cnt = Counter(sub_cats)
    for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
        print(f"    {k:<12}: {v}")

    # 写回 gbk 编码，保持原格式（header=False，因为大表头和子表头已在数据里）
    try:
        out.to_csv(CSV, index=False, encoding="gbk", header=False)
    except PermissionError:
        print(f"\n[错误] {CSV.name} 被 Excel 占用，请关闭后重跑。")
        return 5

    print(f"\n[4] 已写回 {CSV.name}")
    print(f"    在「分类」后插入「小分类」列，共 {len(out)} 行 × {out.shape[1]} 列")
    print(f"    原有内容保持不变")
    return 0


if __name__ == "__main__":
    sys.exit(main())
