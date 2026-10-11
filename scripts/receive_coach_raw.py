"""
Coach 淘宝商品采集数据接收脚本（阶段 2）
================================================
- 输入：八爪鱼采集器导出的 CSV（UTF-8 with BOM、英文表头）
- 输出：
    1) data/raw_normalized/coach_taobao_normalized_YYYYMMDD_HHMM.csv  —— 规整后主表，供阶段 3 清洗使用
    2) logs/crawl_YYYYMMDD_HHMM.log                                  —— 采集日志（条数/失败原因/异常告警）
- 职责边界：
    * 阶段 2 只做：读取 → 字段校验 → 类型规整 → 写日志 → 落盘规整 CSV
    * 不做去重、不做异常价格剔除、不做属性标准化（这些属于阶段 3 清洗）
      —— 但会把可疑情况写入日志，便于阶段 3 定位。

用法：
    # 1) 生成 3 行样例 CSV（首次测试用，跑通流程）
    python receive_coach_raw.py --make-template

    # 2) 处理八爪鱼真实导出
    python receive_coach_raw.py path/to/coach_taobao_raw_20260921_1930.csv

    # 3) 指定输出目录
    python receive_coach_raw.py input.csv --out-dir output/
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# ----------------------------- 字段契约 -----------------------------
# 八爪鱼导出 CSV 必须包含这些列（顺序不强求，但名称必须一致）
EXPECTED_COLUMNS: list[str] = [
    "title",
    "item_id",
    "url",
    "price_original",
    "price_final",
    "sales_monthly",
    "comment_count",
    "qa_count",
    "shop_name",
    "shop_type",
    "attributes",
    "crawl_time",
]

# 必填字段（缺失即判该行失败）
REQUIRED_FIELDS: list[str] = ["title", "item_id", "url", "crawl_time"]

# 数值字段（用于类型规整与异常告警）
NUMERIC_FIELDS: list[str] = ["price_original", "price_final", "comment_count", "qa_count"]

# 异常价格阈值（仅告警，不剔除 —— 剔除是阶段 3 的事）
# 下界 10 元：Coach 真品 ≥ 数百元，1 元引流款需被记录
# 上界 50000 元：抓 99999/9999 之类异常标价
PRICE_WARN_RANGE = (10, 50000)


# ----------------------------- 解析函数 -----------------------------
def parse_sales(text: str | float | None) -> int | None:
    """
    把八爪鱼文本销量解析为整数。
        "1.5万"  -> 15000
        "352"    -> 352
        "1.2万+" -> 12000
        "" / None / "暂无" -> None
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s or s in {"暂无", "无", "-"}:
        return None
    # 去掉「+」「人收货」「付款」等后缀
    s = re.sub(r"[+人收货付款月成交 ]+", "", s)
    try:
        if "万" in s:
            num = float(s.replace("万", ""))
            return int(num * 10000)
        return int(float(s))
    except (ValueError, TypeError):
        return None


def parse_price(text: str | float | None) -> float | None:
    """价格字段：去 ¥ / 空格，转 float。"""
    if text is None:
        return None
    s = str(text).strip()
    if not s or s in {"暂无", "无", "-"}:
        return None
    s = s.replace("¥", "").replace("￥", "").replace(",", "").strip()
    try:
        v = float(s)
        return v
    except (ValueError, TypeError):
        return None


def parse_int(text: str | float | None) -> int | None:
    """评论数 / 问大家数等纯整数字段。"""
    if text is None:
        return None
    s = str(text).strip()
    if not s or s in {"暂无", "无", "-"}:
        return None
    s = re.sub(r"[+条评论问大家 ]+", "", s)
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def parse_attributes(text: str | None) -> dict:
    """
    商品属性字符串 -> dict
        "品类:手提包;款式:tabby;材质:牛皮"  ->  {"品类": "手提包", "款式": "tabby", "材质": "牛皮"}
    """
    if not text or not isinstance(text, str):
        return {}
    out: dict[str, str] = {}
    for kv in text.split(";"):
        kv = kv.strip()
        if not kv:
            continue
        if ":" in kv:
            k, _, v = kv.partition(":")
            out[k.strip()] = v.strip()
    return out


# ----------------------------- 主流程 -----------------------------
def load_raw_csv(path: Path) -> pd.DataFrame:
    """读取八爪鱼 CSV：UTF-8 BOM，全字段 str 以避免 pandas 自动类型推断引入的歧义。"""
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False, na_values=[])
    # 去掉首尾空白
    df.columns = [c.strip() for c in df.columns]
    return df


def validate_schema(df: pd.DataFrame) -> list[str]:
    """校验表头是否齐全，返回缺失列名列表。"""
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    return missing, extra


def normalize(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """类型规整：字符串清洗 + 数值/日期解析。"""
    issues: list[str] = []

    # 字符串字段去空白
    str_cols = ["title", "item_id", "url", "shop_name", "shop_type", "attributes"]
    for c in str_cols:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

    # 销量解析
    if "sales_monthly" in df.columns:
        df["sales_monthly"] = df["sales_monthly"].apply(parse_sales)

    # 价格解析
    for c in ("price_original", "price_final"):
        if c in df.columns:
            df[c] = df[c].apply(parse_price)
            # 异常价格告警
            bad = df[(df[c].notna()) & ((df[c] < PRICE_WARN_RANGE[0]) | (df[c] >= PRICE_WARN_RANGE[1]))]
            for idx, v in bad[c].items():
                issues.append(f"行{idx} {c}={v} 超出预期范围{PRICE_WARN_RANGE}（疑似引流款/异常标价），已保留待阶段3处理")

    # 券后价缺失 -> 用券前价（指导书要求并标注）
    if "price_final" in df.columns and "price_original" in df.columns:
        mask = df["price_final"].isna() & df["price_original"].notna()
        filled = int(mask.sum())
        if filled:
            df.loc[mask, "price_final"] = df.loc[mask, "price_original"]
            df.loc[mask, "price_final_source"] = "from_original"
            issues.append(f"券后价缺失 {filled} 行，已用券前价填充并打标 price_final_source=from_original")
        else:
            df["price_final_source"] = "raw"

    # 整数字段
    for c in ("comment_count", "qa_count"):
        if c in df.columns:
            df[c] = df[c].apply(parse_int)

    # 采集时间
    if "crawl_time" in df.columns:
        df["crawl_time"] = pd.to_datetime(df["crawl_time"], errors="coerce")
        bad_time = int(df["crawl_time"].isna().sum())
        if bad_time:
            issues.append(f"crawl_time 解析失败 {bad_time} 行（已置 NaT）")

    # 必填校验
    for c in REQUIRED_FIELDS:
        if c in df.columns:
            n_missing = int((df[c].isna() | (df[c].astype(str).str.strip() == "")).sum())
            if n_missing:
                issues.append(f"必填字段 {c} 缺失 {n_missing} 行")

    # 写日志
    for line in issues:
        logger.warning(line)

    # 摄入元数据
    df.insert(0, "row_id", range(1, len(df) + 1))
    df["ingestion_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return df


def setup_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("receive_coach_raw")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def make_template(out_path: Path) -> None:
    """生成 3 行样例 CSV，用于跑通流程。"""
    rows = [
        {
            "title": "Coach女包tabby山茶花手提包",
            "item_id": "67890123456",
            "url": "https://item.taobao.com/item.htm?id=67890123456",
            "price_original": "1299.00",
            "price_final": "899.00",
            "sales_monthly": "1.5万",
            "comment_count": "2314",
            "qa_count": "56",
            "shop_name": "coach官方旗舰店",
            "shop_type": "旗舰",
            "attributes": "品类:手提包;款式:tabby;材质:牛皮",
            "crawl_time": "2026-09-21 19:30:00",
        },
        {
            "title": "Coach麻将包小号单肩女",
            "item_id": "67890123457",
            "url": "https://item.taobao.com/item.htm?id=67890123457",
            "price_original": "1599",
            "price_final": "",
            "sales_monthly": "352",
            "comment_count": "暂无",
            "qa_count": "",
            "shop_name": "coach奥莱代购店",
            "shop_type": "奥莱",
            "attributes": "品类:单肩包;款式:麻将包;材质:皮质",
            "crawl_time": "2026-09-21 19:30:00",
        },
        {
            "title": "【引流款】Coach钱包1元",
            "item_id": "67890123458",
            "url": "https://item.taobao.com/item.htm?id=67890123458",
            "price_original": "1.00",
            "price_final": "1.00",
            "sales_monthly": "99999",
            "comment_count": "5",
            "qa_count": "0",
            "shop_name": "杂货铺",
            "shop_type": "个人",
            "attributes": "品类:钱包",
            "crawl_time": "2026-09-21 19:30:00",
        },
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_path, index=False, encoding="utf-8-sig", lineterminator="\r\n")
    print(f"已生成样例 CSV：{out_path}（{len(rows)} 行）")


def main() -> int:
    parser = argparse.ArgumentParser(description="接收八爪鱼采集的 Coach 淘宝 CSV，校验+类型规整+写日志")
    parser.add_argument("input_csv", nargs="?", help="八爪鱼导出的 CSV 路径")
    parser.add_argument("--make-template", action="store_true", help="生成 3 行样例 CSV 用于测试")
    parser.add_argument("--template-path", default="data/coach_taobao_raw_sample.csv", help="样例 CSV 输出路径")
    parser.add_argument("--out-dir", default="data/raw_normalized", help="规整后 CSV 输出目录")
    parser.add_argument("--log-dir", default="logs", help="采集日志输出目录")
    args = parser.parse_args()

    if args.make_template:
        make_template(Path(args.template_path))
        return 0

    if not args.input_csv:
        parser.error("请提供 input_csv，或使用 --make-template 生成样例。")

    in_path = Path(args.input_csv)
    if not in_path.exists():
        print(f"错误：找不到输入文件 {in_path}", file=sys.stderr)
        return 2

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = Path(args.log_dir)
    logger = setup_logger(log_dir / f"crawl_{stamp}.log")

    logger.info(f"开始接收：{in_path}")
    df = load_raw_csv(in_path)
    logger.info(f"原始行数：{len(df)}，原始列：{list(df.columns)}")

    missing, extra = validate_schema(df)
    if missing:
        logger.error(f"表头缺失列：{missing}（八爪鱼字段配置不完整，请按指导书检查）")
        return 3
    if extra:
        logger.warning(f"存在未定义列：{extra}（已保留，但不会被下游使用）")

    df_norm = normalize(df, logger)

    out_path = out_dir / f"coach_taobao_normalized_{stamp}.csv"
    df_norm.to_csv(out_path, index=False, encoding="utf-8-sig", lineterminator="\r\n")
    logger.info(f"规整 CSV 已输出：{out_path}（{len(df_norm)} 行 × {len(df_norm.columns)} 列）")

    # 简要统计
    logger.info("—— 字段质量摘要 ——")
    for c in EXPECTED_COLUMNS:
        if c in df_norm.columns:
            n_na = int(df_norm[c].isna().sum())
            logger.info(f"  {c}: 缺失 {n_na}/{len(df_norm)}")
    logger.info("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
