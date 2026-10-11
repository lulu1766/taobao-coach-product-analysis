"""
01_check_data.py — 原始数据质量检查
============================================================
职责：
  对 data/raw/coach_products_raw.xlsx 做采集后数据质量摸底，
  输出数据规模、字段信息、缺失情况、重复情况、销量统计。

输入：data/raw/coach_products_raw.xlsx
输出：打印到控制台（不修改原始文件）

依赖：pandas、openpyxl

运行：
    py python\\01_check_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# ---------- 路径配置（基于脚本位置，任意 cwd 运行都对）----------
ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "coach_products_raw.xlsx"


def load_raw() -> pd.DataFrame:
    """读取原始 xlsx。"""
    if not RAW_PATH.exists():
        raise FileNotFoundError(f"找不到原始文件：{RAW_PATH}\n请先确保影刀导出的 xlsx 已放在 data/raw/")
    return pd.read_excel(RAW_PATH)


def print_basic_info(df: pd.DataFrame) -> None:
    """[1] 数据规模 + 字段 + 类型。"""
    print("\n[1] 数据规模")
    print(f"    {df.shape[0]} 行 × {df.shape[1]} 列")

    print("\n[2] 字段信息")
    print(f"    {'字段名':<15} {'类型':<10} {'非空数'}")
    print(f"    {'-'*15} {'-'*10} {'-'*10}")
    for col in df.columns:
        non_null = df[col].notna().sum()
        print(f"    {col:<15} {str(df[col].dtype):<10} {non_null}")


def check_missing(df: pd.DataFrame) -> None:
    """[3] 每字段缺失数量+缺失比例。"""
    print("\n[3] 缺失情况")
    total = len(df)
    print(f"    {'字段名':<15} {'缺失数':<8} {'缺失比例':<8}")
    print(f"    {'-'*15} {'-'*8} {'-'*8}")
    for col in df.columns:
        n_missing = int(df[col].isna().sum())
        ratio = n_missing / total * 100 if total else 0
        print(f"    {col:<15} {n_missing:<8} {ratio:.1f}%")


def check_duplicates(df: pd.DataFrame) -> None:
    """[4] 完全重复 + title 重复。"""
    print("\n[4] 重复情况")
    n_full_dup = int(df.duplicated().sum())
    print(f"    完全重复行数: {n_full_dup}")

    if "title" in df.columns:
        n_title_dup = int(df["title"].duplicated().sum())
        print(f"    title 重复行数: {n_title_dup}")
        if n_title_dup > 0:
            print("    重复标题示例（前 5 条）：")
            dup_titles = df[df["title"].duplicated(keep=False)]["title"].value_counts().head(5)
            for t, c in dup_titles.items():
                print(f"      [{c}次] {t}")
    else:
        print("    [警告] 无 title 列，跳过标题重复检查")


def stats_sales(df: pd.DataFrame) -> None:
    """[5] sales_count 销量统计（最大/最小/平均/中位数）。"""
    print("\n[5] 销量统计")
    col = None
    for cand in ("sales_count", "sales_raw"):
        if cand in df.columns:
            col = cand
            break

    if col is None:
        print("    [警告] 无 sales_count / sales_raw 列，跳过销量统计")
        return

    print(f"    分析字段: {col}")

    if col == "sales_count":
        s = pd.to_numeric(df[col], errors="coerce")
    else:
        # sales_raw 是文本，无法直接统计；只报非空数和样本
        s = df[col].astype(str)

    if col == "sales_count":
        s_clean = s.dropna()
        if len(s_clean) == 0:
            print("    sales_count 全部为空")
            return
        print(f"    最大值: {int(s_clean.max())}")
        print(f"    最小值: {int(s_clean.min())}")
        print(f"    平均值: {s_clean.mean():.1f}")
        print(f"    中位数: {s_clean.median():.1f}")
    else:
        n_non_empty = int(((s.notna()) & (s != "nan")).sum())
        print(f"    非空条数: {n_non_empty}（文本格式，需 02 脚本转数字后才能算统计量）")
        print(f"    样本前 5 条:")
        for v in s.head(5):
            print(f"      {v}")


def main() -> int:
    print("=" * 60)
    print("01 原始数据质量检查")
    print("=" * 60)

    try:
        df = load_raw()
    except FileNotFoundError as e:
        print(f"[错误] {e}")
        return 2
    except Exception as e:
        print(f"[错误] 读取失败：{type(e).__name__}: {e}")
        return 3

    try:
        print_basic_info(df)
        check_missing(df)
        check_duplicates(df)
        stats_sales(df)
    except Exception as e:
        print(f"[错误] 检查过程异常：{type(e).__name__}: {e}")
        return 4

    print("\n" + "=" * 60)
    print("检查完成。下一步运行 02_clean_data.py 执行清洗")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
