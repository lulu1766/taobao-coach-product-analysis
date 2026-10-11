"""
10_channel_avg_sales.py — 在 coach_products_clean.csv 末尾追加「渠道平均销量」列
====================================================================
公式：渠道平均销量 = 某渠道总销量 ÷ 该渠道商品数量
方法：按「渠道」分组，计算 sum(销量) / count，再广播回每行（同渠道所有行值相同）。

复用 09b 的两行表头自动识别 + 幂等写入逻辑。

运行：
    py python\\10_channel_avg_sales.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "processed" / "coach_products_clean.csv"

NEW_COL = "渠道平均销量"  # 新列名


def main() -> int:
    print("=" * 60)
    print(f"10 追加「{NEW_COL}」列：渠道总销量 ÷ 渠道商品数")
    print("=" * 60)

    if not CSV.exists():
        print(f"[错误] 找不到 {CSV}")
        return 2

    # 读入（保留两行表头）
    raw = pd.read_csv(CSV, encoding="gbk", header=None, dtype=str)
    print(f"\n[1] 读取 {len(raw)} 行 × {raw.shape[1]} 列")

    # 自动识别大表头/子表头行
    big_idx = sub_idx = None
    for i in range(min(5, len(raw))):
        joined = " ".join(raw.iloc[i].fillna("").astype(str).tolist())
        if "商品信息" in joined and big_idx is None:
            big_idx = i
        if "产品id" in joined and sub_idx is None:
            sub_idx = i
    if big_idx is None or sub_idx is None:
        print("[错误] 无法识别表头行")
        return 3

    big_header = raw.iloc[big_idx].fillna("").tolist()
    sub_header = raw.iloc[sub_idx].fillna("").tolist()
    data_start = max(big_idx, sub_idx) + 1
    data = raw.iloc[data_start:].reset_index(drop=True)

    # 如果已存在 NEW_COL，先删除（幂等，避免重复加列）
    while NEW_COL in sub_header:
        dup_idx = sub_header.index(NEW_COL)
        sub_header.pop(dup_idx)
        big_header.pop(dup_idx)
        data = data.drop(columns=data.columns[dup_idx])

    # 定位渠道列和销量列
    if "渠道" not in sub_header or "销量" not in sub_header:
        print(f"[错误] 找不到「渠道」或「销量」列")
        return 4
    channel_idx = sub_header.index("渠道")
    sales_idx = sub_header.index("销量")

    # 计算渠道平均销量
    print(f"\n[2] 按「渠道」分组计算 {NEW_COL} = sum(销量) / count")
    sales_numeric = pd.to_numeric(data.iloc[:, sales_idx], errors="coerce").fillna(0).astype(int)
    channels = data.iloc[:, channel_idx].fillna("未知")
    avg_map = sales_numeric.groupby(channels).mean().to_dict()

    # 打印各渠道计算过程
    ch_grouped = pd.DataFrame({"渠道": channels, "销量": sales_numeric})
    ch_stat = ch_grouped.groupby("渠道")["销量"].agg(["sum", "count", "mean"]).rename(
        columns={"sum": "总销量", "count": "商品数", "mean": NEW_COL}
    )
    ch_stat[NEW_COL] = ch_stat[NEW_COL].round(0).astype(int)
    print(ch_stat.to_string())

    # 组装新列
    new_vals = channels.map(avg_map).round(0).astype(int).tolist()

    # 追加到末尾
    big_header.append("")   # 大表头末尾留空
    sub_header.append(NEW_COL)
    data[len(data.columns)] = new_vals  # 在最后加一列

    # 写回
    all_rows = [big_header, sub_header] + data.values.tolist()
    out = pd.DataFrame(all_rows)

    try:
        out.to_csv(CSV, index=False, encoding="gbk", header=False)
    except PermissionError:
        print(f"\n[错误] {CSV.name} 被 Excel 占用，请关闭后重跑。")
        return 5

    print(f"\n[3] 已写回 {CSV.name}")
    print(f"    追加列「{NEW_COL}」在表格末尾，共 {out.shape[0]} 行 × {out.shape[1]} 列")
    print(f"    其他内容保持不变")
    return 0


if __name__ == "__main__":
    sys.exit(main())
