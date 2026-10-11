"""
04_infer_shop_type.py — 从商品标题+发货地推断店铺类型
============================================================
背景：
  未采集 shop_name / url。淘宝商品标题不含真实店铺名，无法还原；
  但标题与发货地中含有充足的「渠道信号词」，可用规则推断店铺类型，
  这正是指导书 Q3（旗舰/代购/奥莱渠道分析）所需字段。

方法：规则匹配（不使用生成式 AI）
  - 可复现、可审计：每条记录命中哪条规则写入 shop_type_rule
  - 优先级从强到弱，先命中先归类
  - 规则覆盖不到的标「未知」，绝不乱猜

输入：data/processed/coach_products_clean.csv（02 脚本输出）
输出：覆盖写回同一 csv，新增两列：
  shop_type       店铺类型（平台自营/官方旗舰/官方奥莱/奥莱店/专柜/海外代购/未知）
  shop_type_rule  命中的判定规则（审计用，面试可讲）
  另外附 brand_match 标记：标题不含 coach/蔻驰 的疑似非 Coach 商品（搜索噪声）

运行：
    py python\\04_infer_shop_type.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

# ---------- 路径 ----------
ROOT = Path(__file__).resolve().parent.parent
CLEAN_CSV = ROOT / "data" / "processed" / "coach_products_clean.csv"

# ---------- 境外发货地集合（location 命中即视为跨境/代购强信号）----------
OVERSEAS_LOCATIONS = {
    "美国", "香港", "澳门", "台湾", "加拿大", "葡萄牙", "日本", "韩国",
    "法国", "英国", "意大利", "德国", "西班牙", "荷兰", "澳大利亚",
    "新西兰", "欧洲", "俄罗斯",
}

# ---------- 各类型关键词（title 判断前统一 lower）----------
KW_PLATFORM = ["自营", "farfetch", "发发奇", "天猫国际", "考拉", "京东国际", "得物"]
# 强官方信号：「官方正品/官方授权」是营销词不算，只有品牌官方/旗舰店/官网才算
KW_OFFICIAL = ["旗舰店", "官网", "官方店", "官方旗舰", "蔻驰官方", "coach官方"]
KW_OUTLET = ["奥莱", "outlet", "奥特莱斯"]
KW_COUNTER = ["专柜"]
KW_DAIGOU = ["代购", "直邮", "直购", "海外", "保税", "免税", "现货美国", "美国现货"]


def infer_shop_type(title, location) -> tuple[str, str]:
    """
    根据标题+发货地推断店铺类型。
    返回 (店铺类型, 命中规则)。
    优先级：平台自营 > 官方奥莱 > 官方旗舰 > 奥莱店 > 专柜 > 海外代购 > 未知
    """
    t = str(title).lower() if pd.notna(title) else ""
    loc = str(location).strip() if pd.notna(location) else ""
    is_overseas = loc in OVERSEAS_LOCATIONS

    # 1. 平台自营（信号最强：【自营】、FARFETCH 等）
    if any(k in t for k in KW_PLATFORM):
        hit = next(k for k in KW_PLATFORM if k in t)
        return "平台自营", f"标题含「{hit}」"

    # 2. 官方 + 奥莱同时出现 → 官方奥莱（如「COACH/蔻驰官方 奥莱款」）
    has_official = any(k in t for k in KW_OFFICIAL)
    has_outlet = any(k in t for k in KW_OUTLET)
    if has_official and has_outlet:
        return "官方奥莱", "标题同时含「官方」和「奥莱」"

    # 3. 官方/旗舰
    if has_official:
        hit = next(k for k in KW_OFFICIAL if k in t)
        return "官方旗舰", f"标题含「{hit}」"

    # 4. 奥莱
    if has_outlet:
        hit = next(k for k in KW_OUTLET if k in t)
        return "奥莱店", f"标题含「{hit}」"

    # 5. 专柜（多为代购声称的专柜货，结合发货地进一步判断）
    if any(k in t for k in KW_COUNTER):
        if is_overseas:
            return "海外代购", f"标题含「专柜」+ 境外发货({loc})"
        return "专柜渠道", "标题含「专柜」"

    # 6. 海外代购：标题代购词 或 境外发货地
    hit_kw = next((k for k in KW_DAIGOU if k in t), None)
    if hit_kw:
        if is_overseas:
            return "海外代购", f"标题含「{hit_kw}」+ 境外发货({loc})"
        return "海外代购", f"标题含「{hit_kw}」"
    if is_overseas:
        return "海外代购", f"境外发货({loc})"

    # 7. 规则覆盖不到
    return "未知", "无明确渠道信号"


# coach 前后非英文字母即算独立（中文紧贴也能匹配），负向断言挡住 coaching
_BRAND_RE = re.compile(r"(?<![a-z])coach(?![a-z])")
_BOOK_NOISE = ["coaching", "coach's", "coach''s", "playbook", "leadership",
               " guide", "karriere", "dich selbst", "asking", "the person"]
_OTHER_BRANDS = ["adidas", "阿迪达斯", "nike", "耐克"]


def check_brand(title) -> bool:
    """标题是否为 Coach 品牌；排除英文教练/书籍与其他品牌蹭词。"""
    if pd.isna(title):
        return False
    t = str(title).lower()
    if "蔻驰" in t:
        return True
    if not _BRAND_RE.search(t):
        return False
    if any(k in t for k in _BOOK_NOISE + _OTHER_BRANDS):
        return False
    return True


def main() -> int:
    print("=" * 60)
    print("04 店铺类型推断（title + location 规则法）")
    print("=" * 60)

    # [1] 读取
    print(f"\n[1] 读取清洗后数据\n    {CLEAN_CSV}")
    if not CLEAN_CSV.exists():
        print("    [错误] 找不到 clean csv，请先运行 02_clean_data.py")
        return 2
    df = pd.read_csv(CLEAN_CSV, encoding="utf-8-sig")
    print(f"    成功读取 {len(df)} 行 × {len(df.columns)} 列")

    # [2] 推断店铺类型
    print("\n[2] 规则推断店铺类型")
    results = df.apply(
        lambda r: infer_shop_type(r.get("title"), r.get("location")), axis=1
    )
    df["shop_type"] = results.apply(lambda x: x[0])
    df["shop_type_rule"] = results.apply(lambda x: x[1])

    # [3] 品牌噪声标记
    df["brand_match"] = df["title"].apply(check_brand)
    n_noise = int((~df["brand_match"]).sum())

    # [4] 覆盖率统计
    print("\n[3] 店铺类型分布")
    counts = df["shop_type"].value_counts()
    total = len(df)
    for st, c in counts.items():
        print(f"    {st:<8}: {c:>4} 条 ({c/total*100:5.1f}%)")
    n_unknown = int((df["shop_type"] == "未知").sum())
    print(f"\n    规则覆盖率：{(total-n_unknown)/total*100:.1f}%（未知 {n_unknown} 条）")

    if n_noise > 0:
        print(f"\n[4] 品牌噪声提醒：{n_noise} 条标题不含 coach/蔻驰（疑似搜索混入），brand_match=False")
        print("    示例：")
        for t in df.loc[~df["brand_match"], "title"].head(5):
            print(f"      - {t}")

    # [5] 各类型抽样核对
    print("\n[5] 各类型抽样核对（每类 2 条）")
    for st in counts.index:
        print(f"\n  【{st}】")
        sub = df[df["shop_type"] == st].head(2)
        for _, r in sub.iterrows():
            print(f"    [{r['shop_type_rule']}]")
            print(f"    {str(r['title'])[:50]} | 发货地:{r['location']}")

    # [6] 写回
    try:
        df.to_csv(CLEAN_CSV, index=False, encoding="utf-8-sig", lineterminator="\n")
    except PermissionError:
        alt = CLEAN_CSV.with_name("coach_products_clean_with_shoptype.csv")
        df.to_csv(alt, index=False, encoding="utf-8-sig", lineterminator="\n")
        print(f"\n[6] [警告] {CLEAN_CSV.name} 正被 Excel 占用，无法覆盖。")
        print(f"    结果已另存为：{alt.name}")
        print(f"    请关闭 Excel 后重跑本脚本，即可正常写回规范文件。")
        print(f"    新增列：shop_type, shop_type_rule, brand_match")
        return 5

    print(f"\n[6] 已写回 {CLEAN_CSV}")
    print(f"    新增列：shop_type, shop_type_rule, brand_match")
    print(f"    最终字段：{list(df.columns)}")

    print("\n" + "=" * 60)
    print("完成。未知类型如需进一步标注，可导出后人工/AI 小批量复核")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
