"""
05_eda.py — 阶段 4 探索性分析 EDA
============================================================
读取 data/processed/coach_products_clean.csv（已含 shop_type），
围绕指导书第四节 + Q1/Q2 输出 8 张图，每张配一句「我看到了什么」结论。

图清单（保存到 outputs/figures/）：
  01 价格分布直方图            —— 价格集中在哪个区间
  02 销量分布（长尾）          —— 少数爆款拉高均值
  03 店铺类型商品数量占比      —— 渠道结构（Q3）
  04 店铺类型 × 销量贡献       —— 谁的货卖得动（Q3）
  05 价格带商品数量占比        —— 供给结构（Q2）
  06 价格带销量占比+平均销量   —— 黄金价格带（Q2 核心）
  07 发货地 TOP10              —— 货源地结构
  08 价格 vs 销量散点          —— 价格与热度关系

运行：
    py python\\05_eda.py
依赖：pandas、matplotlib
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # 无界面环境也能出图
import matplotlib.pyplot as plt

# ---------- 中文字体（Windows）----------
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

# ---------- 路径 ----------
ROOT = Path(__file__).resolve().parent.parent
CLEAN_CSV = ROOT / "data" / "processed" / "coach_products_clean.csv"
FIG_DIR = ROOT / "outputs" / "figures"

# ---------- 价格带分箱（指导书 5.2）----------
PRICE_BINS = [0, 500, 1000, 2000, 3000, 100000]
PRICE_LABELS = ["<500", "500-1000", "1000-2000", "2000-3000", ">3000"]

# 统一配色
COLOR = "#1f77b4"
COLOR2 = "#ff7f0e"


def save_fig(fig, name: str) -> None:
    """保存图并关闭。"""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    p = FIG_DIR / name
    fig.savefig(p, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"    已保存 {p.relative_to(ROOT)}")


def fig01_price_hist(df: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(df["price"], bins=40, color=COLOR, edgecolor="white")
    ax.set_title("Coach 商品价格分布")
    ax.set_xlabel("价格（元）")
    ax.set_ylabel("商品数量")
    ax.axvline(df["price"].median(), color=COLOR2, linestyle="--", label=f"中位数 {df['price'].median():.0f}")
    ax.legend()
    save_fig(fig, "01_价格分布.png")
    return f"价格中位数 {df['price'].median():.0f} 元，多数商品集中在 500-2500 元区间。"


def fig02_sales_tail(df: pd.DataFrame) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].hist(df["sales_count"], bins=50, color=COLOR, edgecolor="white")
    axes[0].set_title("销量分布（原始）")
    axes[0].set_xlabel("月销量")
    axes[0].set_ylabel("商品数量")
    pos = df[df["sales_count"] > 0]["sales_count"]
    axes[1].hist(pos, bins=50, color=COLOR2, edgecolor="white")
    axes[1].set_title("有销量商品分布（>0）")
    axes[1].set_xlabel("月销量")
    axes[1].set_ylabel("商品数量")
    save_fig(fig, "02_销量长尾.png")
    return (f"呈典型长尾：{int((df['sales_count']==0).sum())} 条销量为 0，"
            f"而最高 {int(df['sales_count'].max())} 件；均值 {df['sales_count'].mean():.0f} 远高于中位数 {df['sales_count'].median():.0f}。")


def fig03_shop_counts(df: pd.DataFrame) -> str:
    order = df["shop_type"].value_counts().index
    counts = df["shop_type"].value_counts()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(order.astype(str), counts.values, color=COLOR)
    ax.set_title("各店铺类型商品数量")
    ax.set_ylabel("商品数量")
    ax.bar_label(bars)
    plt.xticks(rotation=20)
    save_fig(fig, "03_店铺类型数量.png")
    top = counts.index[0]
    return f"渠道以「{top}」为主（{counts.iloc[0]} 条，{counts.iloc[0]/len(df)*100:.0f}%），{int((df['shop_type']=='未知').sum())} 条无明确渠道信号标为未知。"


def fig04_shop_sales(df: pd.DataFrame) -> str:
    g = df.groupby("shop_type")["sales_count"].agg(["sum", "mean", "count"])
    g = g.sort_values("sum", ascending=False)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    axes[0].bar(g.index.astype(str), g["sum"], color=COLOR)
    axes[0].set_title("各店铺类型总销量贡献")
    axes[0].set_ylabel("总销量")
    axes[0].tick_params(axis="x", rotation=20)
    axes[1].bar(g.index.astype(str), g["mean"], color=COLOR2)
    axes[1].set_title("各店铺类型平均单品销量")
    axes[1].set_ylabel("平均销量/件")
    axes[1].tick_params(axis="x", rotation=20)
    save_fig(fig, "04_店铺类型销量.png")
    best_total = g["sum"].idxmax()
    best_avg = g["mean"].idxmax()
    return f"总销量贡献最高的是「{best_total}」；单品动销效率最高的是「{best_avg}」（平均 {g['mean'].max():.0f} 件/款）。"


def fig05_06_price_band(df: pd.DataFrame) -> tuple[str, str]:
    df = df.copy()
    df["price_band"] = pd.cut(df["price"], bins=PRICE_BINS, labels=PRICE_LABELS, right=False)
    band = df.groupby("price_band", observed=False).agg(
        n=("title", "count"),
        sales_sum=("sales_count", "sum"),
        sales_mean=("sales_count", "mean"),
    )
    band["n_pct"] = band["n"] / band["n"].sum() * 100
    band["sales_pct"] = band["sales_sum"] / band["sales_sum"].sum() * 100

    # 图05：商品数量占比
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(band.index.astype(str), band["n_pct"], color=COLOR)
    ax.set_title("各价格带商品数量占比（供给结构）")
    ax.set_ylabel("商品占比 %")
    ax.set_xlabel("价格带（元）")
    ax.bar_label(bars, fmt="%.1f%%")
    save_fig(fig, "05_价格带商品占比.png")
    top_supply = band["n_pct"].idxmax()
    c05 = f"供给最集中的价格带是「{top_supply}」（占商品数 {band['n_pct'].max():.1f}%）。"

    # 图06：销量占比 + 平均单品销量（双轴）
    fig, ax1 = plt.subplots(figsize=(9, 4.8))
    x = range(len(band))
    ax1.bar([i - 0.2 for i in x], band["sales_pct"], width=0.4, color=COLOR, label="销量占比 %")
    ax1.set_ylabel("销量占比 %", color=COLOR)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(band.index.astype(str))
    ax1.set_xlabel("价格带（元）")
    ax2 = ax1.twinx()
    ax2.bar([i + 0.2 for i in x], band["sales_mean"], width=0.4, color=COLOR2, label="平均单品销量")
    ax2.set_ylabel("平均单品销量（件）", color=COLOR2)
    ax1.set_title("各价格带销量占比 vs 平均单品销量（找黄金价格带）")
    save_fig(fig, "06_黄金价格带.png")
    # 黄金带 = 平均单品销量最高（商品未必最多但卖得动）
    golden = band["sales_mean"].idxmax()
    c06 = (f"「{golden}」价格带平均单品销量最高（{band['sales_mean'].max():.0f} 件/款），"
           f"贡献 {band.loc[golden, 'sales_pct']:.1f}% 销量，是候选黄金价格带。")
    return c05, c06


def fig07_location(df: pd.DataFrame) -> str:
    top = df["location"].value_counts().head(10)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(top.index[::-1], top.values[::-1], color=COLOR)
    ax.set_title("发货地 TOP10")
    ax.set_xlabel("商品数量")
    save_fig(fig, "07_发货地TOP10.png")
    overseas = int(df["location"].isin(["美国", "香港", "加拿大", "葡萄牙", "日本", "韩国", "欧洲", "澳门", "台湾"]).sum())
    return f"货源集中在 {top.index[0]}、{top.index[1]}、{top.index[2]}；境外发货约 {overseas} 条（{overseas/len(df)*100:.0f}%），印证代购占比高。"


def fig08_price_sales_scatter(df: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(8, 5))
    sc = ax.scatter(df["price"], df["sales_count"], c=df["shop_type"].astype("str").astype("category").cat.codes,
                    cmap="tab10", alpha=0.6, s=30)
    ax.set_title("价格 vs 月销量（颜色=店铺类型）")
    ax.set_xlabel("价格（元）")
    ax.set_ylabel("月销量")
    save_fig(fig, "08_价格销量散点.png")
    # 简单相关性
    corr = df[["price", "sales_count"]].corr().iloc[0, 1]
    rel = "弱负相关（越贵越难走量）" if corr < -0.1 else ("正相关" if corr > 0.1 else "几乎无线性关系")
    return f"价格与销量相关系数 {corr:.2f}，呈{rel}；爆款集中在中价位而非最低价。"


def main() -> int:
    print("=" * 60)
    print("05 探索性分析 EDA")
    print("=" * 60)

    if not CLEAN_CSV.exists():
        print(f"[错误] 找不到 {CLEAN_CSV}，请先依次运行 02、04 脚本")
        return 2
    df = pd.read_csv(CLEAN_CSV, encoding="utf-8-sig")
    # shop_type 列是 04 生成；若无则提示
    if "shop_type" not in df.columns:
        print("[错误] clean csv 缺少 shop_type 列，请先运行 04_infer_shop_type.py")
        return 3

    print(f"\n分析样本：{len(df)} 条商品，字段含 shop_type")
    print(f"图片输出目录：outputs/figures/\n")

    conclusions = []
    print("[图1/8] 价格分布")
    conclusions.append(("01 价格分布", fig01_price_hist(df)))
    print("[图2/8] 销量长尾")
    conclusions.append(("02 销量长尾", fig02_sales_tail(df)))
    print("[图3/8] 店铺类型数量")
    conclusions.append(("03 店铺数量结构", fig03_shop_counts(df)))
    print("[图4/8] 店铺类型销量")
    conclusions.append(("04 渠道销量表现", fig04_shop_sales(df)))
    print("[图5-6/8] 价格带")
    c5, c6 = fig05_06_price_band(df)
    conclusions.append(("05 供给价格带", c5))
    conclusions.append(("06 黄金价格带", c6))
    print("[图7/8] 发货地")
    conclusions.append(("07 发货地", fig07_location(df)))
    print("[图8/8] 价格销量散点")
    conclusions.append(("08 价量关系", fig08_price_sales_scatter(df)))

    print("\n" + "=" * 60)
    print("每张图「我看到了什么」结论")
    print("=" * 60)
    for name, c in conclusions:
        print(f"  ▶ {name}：{c}")

    print("\nEDA 完成。下一步：阶段 5 深入分析（热门指数 / 关键词 / 情感）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
