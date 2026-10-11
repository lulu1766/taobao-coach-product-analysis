"""
02_clean_data.py — 核心数据清洗
============================================================
职责：
  读取 raw → 标题清洗 → 价格清洗 → 销量清洗 → 去重 → 字段标准化 → 输出 csv
  并把每步处理数量写入 logs/cleaning_stats.json，供 03 脚本生成 xlsx 日志

输入：data/raw/coach_products_raw.xlsx
输出：data/processed/coach_products_clean.csv
      logs/cleaning_stats.json

清洗规则（严格按用户指令）：
  1. 标题：删空、去前后空格、去【xxx】推广词、去装饰符号、去常见推广词
  2. 价格：price_raw → price，转数字，删 price<=0 或 price>10000
  3. 销量：sales_raw → sales_count，正则解析「万 ×10000、+ 和人付款 去掉」
           空值填充 0
  4. 去重：优先按 url，无 url 则按 title，记录删除数量
  5. 标准化字段：title / price / sales_count / location / shop_name / url
                / source / crawl_time；缺失字段不报错，自动跳过

运行：
    py python\\02_clean_data.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

# ---------- 路径 ----------
ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "coach_products_raw.xlsx"
OUT_CSV = ROOT / "data" / "processed" / "coach_products_clean.csv"
STATS_PATH = ROOT / "logs" / "cleaning_stats.json"

# ---------- 默认元数据（raw 缺失时填充）----------
DEFAULT_SOURCE = "淘宝"
DEFAULT_CRAWL_TIME = "2026-09-22"

# ---------- 价格阈值（用户指定）----------
PRICE_MIN = 0        # ≤0 删除
PRICE_MAX = 10000    # >10000 删除

# ---------- 标题清洗规则 ----------
# 【xxx】：营销括号整段删，但「自营」是渠道信号，去括号保留文字
_BRACKET_RE = re.compile(r"[【\[](.*?)[】\]]")
# 括号内出现这些词时，仅去括号、保留内容（供 04 店铺类型推断使用）
_BRACKET_KEEP = ["自营", "官方旗舰", "旗舰", "奥莱"]
# 装饰符号
_DECOR_RE = re.compile(r"[★☆◆◇■□●○▲△▼▽※㊣☀☁☂✦✧❤♥♡]")
# 常见推广词（顺序：长词优先，避免误删）
_PROMO_WORDS = [
    "爆款推荐", "限时秒杀", "限时特惠", "限时促销", "限时",
    "热销爆款", "热卖爆款", "热销", "热卖",
    "新品上市", "新品", "新款", "爆款", "秒杀", "特惠", "促销",
    "包邮赠品", "包邮", "赠品",
    "明星同款", "七夕礼物", "圣诞情人节礼物", "情人节礼物", "生日礼物",
    "送礼物", "520礼物女", "520礼物",
    "官方授权", "官方正品", "正品保障", "正品保证", "正品",
]
_PROMO_RE = re.compile("|".join(_PROMO_WORDS))
# 多余空格
_SPACE_RE = re.compile(r"\s+")

# ---------- 销量解析正则 ----------
_WAN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*万")  # 1万 / 1.5万
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")          # 兜底任意数字


# ============== 清洗函数 ==============

def _bracket_repl(m: re.Match) -> str:
    """括号替换：含渠道信号词（自营/旗舰/奥莱）则去括号保留文字，否则整段删除。"""
    inner = m.group(1)
    if any(k in inner for k in _BRACKET_KEEP):
        return inner
    return ""


def clean_title(title) -> str | None:
    """标题清洗：营销括号删除（渠道括号保留）、去装饰符号/推广词、统一大小写、压缩空格。"""
    if pd.isna(title):
        return None
    s = str(title)
    s = _BRACKET_RE.sub(_bracket_repl, s)  # 【爆款推荐】删；【自营】→自营
    s = _DECOR_RE.sub("", s)               # 去装饰符号
    s = _PROMO_RE.sub("", s)               # 去爆款/正品等推广词
    s = s.upper()                          # 统一大小写（中文不受影响，英文统一）
    s = _SPACE_RE.sub(" ", s).strip()      # 压缩多余空格
    return s if s else None


# 品牌匹配：coach 前后不是英文字母即可（中文/空格/标点都算边界）。
# 不能用 \bcoach\b：Python3 默认把中文当 \w，会导致「邮COACH 女」「COACH山茶花」边界匹配失败。
# 负向断言既能挡住 coaching，又能放行中文紧贴的 COACH。
_BRAND_RE = re.compile(r"(?<![a-z])coach(?![a-z])")
# 搜索 coach 误中的英文书籍/教练语义噪声（这些标题不含「蔻驰」）
_BOOK_NOISE = ["coaching", "coach's", "coach''s", "playbook", "leadership",
               " guide", "karriere", "dich selbst", "asking", "the person"]
# 其他品牌蹭词（标题含这些且不含蔻驰，判为噪声）
_OTHER_BRANDS = ["adidas", "阿迪达斯", "nike", "耐克"]


def is_coach(title) -> bool:
    """清洗后标题是否为 Coach 品牌：
       含独立品牌词 coach（中文/空格/标点为界）或「蔻驰」，
       并排除英文教练/书籍噪声与其他品牌蹭词。"""
    if not title or pd.isna(title):
        return False
    t = str(title).lower()
    if "蔻驰" in t:
        return True
    if not _BRAND_RE.search(t):
        return False
    if any(k in t for k in _BOOK_NOISE):
        return False
    if any(k in t for k in _OTHER_BRANDS):
        return False
    return True


def clean_price(price) -> float | None:
    """价格清洗：转 float；price<=0 或 price>10000 返回 None。"""
    if pd.isna(price):
        return None
    try:
        p = float(price)
    except (ValueError, TypeError):
        return None
    if p <= PRICE_MIN or p > PRICE_MAX:
        return None
    return p


def clean_sales(sales) -> int:
    """销量文本转数字；空填充 0。"""
    if pd.isna(sales):
        return 0
    s = str(sales).strip()
    if not s or s in {"暂无", "无", "-"}:
        return 0
    m = _WAN_RE.search(s)
    if m:
        return int(float(m.group(1)) * 10000)
    m = _NUM_RE.search(s)
    if m:
        return int(float(m.group(0)))
    return 0


def deduplicate(df: pd.DataFrame, stats: dict) -> pd.DataFrame:
    """去重：优先 url，无则 title。同 ID 保留 sales_count 最大那条。"""
    if "url" in df.columns and df["url"].notna().any():
        key = "url"
    elif "title" in df.columns:
        key = "title"
    else:
        stats["重复删除"] = 0
        stats["去重依据"] = "无（缺 url 和 title）"
        return df

    before = len(df)
    # 按 sales_count 降序排，drop_duplicates 保留第一条 = 销量最大那条
    if "sales_count" in df.columns:
        df = df.sort_values("sales_count", ascending=False, na_position="last", kind="stable")
    df = df.drop_duplicates(subset=key, keep="first")
    # 恢复原始顺序
    df = df.sort_index(kind="stable")
    stats["重复删除"] = before - len(df)
    stats["去重依据"] = key
    return df


def standardize(df: pd.DataFrame) -> pd.DataFrame:
    """字段标准化：只保留目标字段，缺失字段补空列。"""
    target = ["title", "price", "sales_count", "location",
              "shop_name", "url", "source", "crawl_time"]
    out = pd.DataFrame(index=df.index)
    for col in target:
        if col in df.columns:
            out[col] = df[col]
        else:
            out[col] = pd.NA
    # 默认元数据填充
    if out["source"].isna().all():
        out["source"] = DEFAULT_SOURCE
    if out["crawl_time"].isna().all():
        out["crawl_time"] = DEFAULT_CRAWL_TIME
    return out


# ============== 主流程 ==============

def main() -> int:
    print("=" * 60)
    print("02 数据清洗")
    print("=" * 60)

    stats: dict = {}

    # [1] 读取
    print(f"\n[1] 读取 raw\n    {RAW_PATH}")
    if not RAW_PATH.exists():
        print(f"    [错误] 找不到原始文件")
        return 2
    try:
        df = pd.read_excel(RAW_PATH)
    except Exception as e:
        print(f"    [错误] 读取失败：{type(e).__name__}: {e}")
        return 3
    stats["原始行数"] = len(df)
    stats["原始字段"] = list(df.columns)
    print(f"    成功读取 {len(df)} 行 × {len(df.columns)} 列")
    print(f"    字段：{list(df.columns)}")

    # [2] 标题清洗
    print("\n[2] 标题清洗")
    if "title" not in df.columns:
        print("    [警告] 无 title 列，跳过")
        stats["删除空标题"] = 0
        stats["非Coach噪声删除"] = 0
    else:
        n_empty_before = int(df["title"].isna().sum())
        df["title"] = df["title"].apply(clean_title)
        n_empty_after = int(df["title"].isna().sum())
        df = df[df["title"].notna()].copy()
        n_deleted = n_empty_before + (n_empty_after - n_empty_before)
        # 删空标题后的行数变化才是真正删除数
        n_deleted = stats["原始行数"] - len(df) if stats["原始行数"] > len(df) else n_empty_after
        stats["删除空标题"] = n_deleted
        print(f"    删除空/清洗后变空标题：{n_deleted} 条")
        print(f"    示例：")
        sample_cols = ["title"] + (["price_raw"] if "price_raw" in df.columns else [])
        print(df[sample_cols].head(3).to_string(index=True))

        # 品牌噪声剔除：标题必须含 coach/蔻驰（搜索会混入蹭型号的其他品牌/无关商品）
        before_brand = len(df)
        noise = df[~df["title"].apply(is_coach)]
        df = df[df["title"].apply(is_coach)].copy()
        stats["非Coach噪声删除"] = before_brand - len(df)
        if stats["非Coach噪声删除"] > 0:
            print(f"    非 Coach 噪声删除：{stats['非Coach噪声删除']} 条（标题不含 coach/蔻驰）")
            for t in noise["title"].head(5):
                print(f"      - {t}")

    # [3] 价格清洗
    print("\n[3] 价格清洗")
    if "price_raw" not in df.columns:
        print("    [警告] 无 price_raw 列，跳过")
        stats["价格异常删除"] = 0
        df["price"] = pd.NA
    else:
        before = len(df)
        df["price"] = df["price_raw"].apply(clean_price)
        n_bad = int(df["price"].isna().sum())
        df = df[df["price"].notna()].copy()
        stats["价格异常删除"] = before - len(df)
        print(f"    删除价格异常（≤0 或 >{PRICE_MAX}）：{before - len(df)} 条")
        print(f"    保留价格区间：{df['price'].min():.0f} ~ {df['price'].max():.0f}")

    # [4] 销量清洗
    print("\n[4] 销量清洗")
    if "sales_raw" not in df.columns and "sales_count" not in df.columns:
        print("    [警告] 无 sales_raw / sales_count 列，跳过")
        stats["销量转换"] = 0
        df["sales_count"] = 0
    else:
        if "sales_count" in df.columns and df["sales_count"].notna().any():
            # 已有 sales_count 列（数字），仅做缺失填充
            df["sales_count"] = pd.to_numeric(df["sales_count"], errors="coerce").fillna(0).astype(int)
            stats["销量转换"] = int((df["sales_count"] != 0).sum())
            print(f"    sales_count 已是数字，填充缺失为 0；非零共 {stats['销量转换']} 条")
        else:
            n_text = int(df["sales_raw"].notna().sum())  # 有文本销量的条数
            n_fill_zero = len(df) - n_text               # 原本缺失、需填 0 的条数
            df["sales_count"] = df["sales_raw"].apply(clean_sales)
            stats["销量转换"] = n_text
            stats["销量缺失填0"] = n_fill_zero
            print(f"    文本转数字：{n_text} 条（如 1.5万人付款 -> 15000）")
            print(f"    原销量缺失填 0：{n_fill_zero} 条")
            print(f"    示例：")
            sample = df[["title", "sales_raw", "sales_count"]].head(3)
            print(sample.to_string(index=True))

    # [5] 去重
    print("\n[5] 去重")
    before = len(df)
    df = deduplicate(df, stats)
    print(f"    去重依据：{stats['去重依据']}")
    print(f"    删除重复：{stats['重复删除']} 条")
    print(f"    保留：{len(df)} 条")

    # [6] 字段标准化
    print("\n[6] 字段标准化")
    out = standardize(df)
    stats["最终行数"] = len(out)
    stats["最终字段"] = list(out.columns)
    print(f"    输出字段：{list(out.columns)}")
    print(f"    最终行数：{len(out)}")

    # [7] 保存 csv
    print("\n[7] 保存")
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig", lineterminator="\n")
    print(f"    已保存到 {OUT_CSV}")

    # [8] 保存 stats json（供 03 读取）
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"    清洗统计已写入 {STATS_PATH}")

    print("\n" + "=" * 60)
    print("清洗完成。下一步运行 03_clean_log.py 生成清洗日志 xlsx")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
