# -*- coding: utf-8 -*-
"""
数据构造模块
============
1. 读取清洗后的 352 条 Coach 淘宝商品截面数据，导入 MySQL Product 表；
2. 原始数据为单次采集的截面快照（无真实历史流水），依据各对象近 12 个月
   真实累计销量，结合电商行业月度季节因子（618/双11/春节等）拆解为
   2024-10 ~ 2026-09 共 24 个月度序列，供 LSTM 模型训练。
   接入真实月度销售流水后，替换 build_monthly_series() 即可直接复用模型。
"""
import datetime as dt
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

# 数据集路径：相对本文件定位（coach_web/dashboard/ml/ → 项目根/data/processed/），
# 也可通过环境变量 COACH_CSV 覆盖
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CSV_PATH = Path(os.environ.get(
    'COACH_CSV',
    PROJECT_ROOT / 'data' / 'processed' / 'coach_products_clean_with_category.csv'
))

# 序列起止月份
START_MONTH = dt.date(2024, 10, 1)
END_MONTH = dt.date(2026, 9, 1)

# 电商行业月度季节因子（1.0 = 平销月，11 月双 11、6 月 618 为高峰，2 月春节低谷）
BASE_SEASON = {
    1: 0.90, 2: 0.55, 3: 0.80, 4: 0.85, 5: 1.05, 6: 1.55,
    7: 0.80, 8: 0.85, 9: 0.95, 10: 1.00, 11: 2.60, 12: 1.30,
}
# 品类差异化因子（在基础因子上按月份加权）：香水在 520/七夕/圣诞礼物季更强
PERFUME_FACTOR = {
    1: 1.05, 2: 0.85, 3: 0.95, 4: 1.00, 5: 1.25, 6: 1.20,
    7: 0.90, 8: 1.25, 9: 0.95, 10: 1.05, 11: 1.70, 12: 1.40,
}
YEAR_GROWTH = 1.12      # 同比增长假设
NOISE_LEVEL = 0.04      # ±4% 确定性随机扰动
RNG = np.random.default_rng(42)


def load_products():
    """读取并清洗商品数据，返回 DataFrame（352 条）"""
    df = pd.read_csv(CSV_PATH, header=1).iloc[:352].copy()
    df['销量'] = df['销量'].astype(int)
    df['售价'] = df['售价'].astype(int)
    df['时间'] = pd.to_datetime(df['时间'], errors='coerce')
    df['发货地'] = df['发货地'].fillna('未知')
    df['小分类'] = df['小分类'].fillna('未分类')
    return df


def _month_range(start, end):
    cur = start
    while cur <= end:
        yield cur
        if cur.month == 12:
            cur = dt.date(cur.year + 1, 1, 1)
        else:
            cur = dt.date(cur.year, cur.month + 1, 1)


def _series_for_target(annual_total, months, perfume=False):
    """
    将近 12 个月真实累计销量 annual_total 按季节因子分解到 months（24 个月）：
    - 最后 12 个月之和锚定 annual_total；
    - 前 12 个月按同比增速反推；
    - 叠加固定种子的小扰动保证可复现。
    """
    factors = []
    for m in months:
        f = BASE_SEASON[m.month]
        if perfume:
            f *= PERFUME_FACTOR[m.month]
        factors.append(f)
    factors = np.array(factors, dtype=float)

    # 近 12 个月（序列后 12 项）按因子归一化到真实累计
    last12 = factors[12:]
    last12 = last12 / last12.sum() * annual_total
    # 前 12 个月：同月份按年增长率反推
    first12 = factors[:12] / factors[:12].sum() * (annual_total / YEAR_GROWTH)
    series = np.concatenate([first12, last12])

    noise = 1 + RNG.uniform(-NOISE_LEVEL, NOISE_LEVEL, size=len(series))
    series = np.maximum(series * noise, 0)
    # 再次校准最后一年合计
    series[12:] = series[12:] / series[12:].sum() * annual_total
    return np.round(series).astype(int)


def build_monthly_series(df):
    """
    构造 4 条月度序列：整体 / 包袋 / 香水 / 其他配饰
    返回 [(target, [(month, sales), ...]), ...]
    """
    months = list(_month_range(START_MONTH, END_MONTH))

    total = int(df['销量'].sum())
    bag = int(df.loc[df['分类'] == '包袋', '销量'].sum())
    perfume = int(df.loc[df['分类'] == '香水', '销量'].sum())
    other = total - bag - perfume

    targets = [
        ('整体', total, False),
        ('包袋', bag, False),
        ('香水', perfume, True),
        ('其他配饰', other, False),
    ]
    result = []
    for name, annual, is_perfume in targets:
        vals = _series_for_target(annual, months, perfume=is_perfume)
        result.append((name, list(zip(months, vals))))
    return result


def import_to_db():
    """一键导入商品 + 月度序列（调用前需 Django 环境就绪）"""
    from dashboard.models import Product, MonthlySales

    df = load_products()
    Product.objects.all().delete()
    MonthlySales.objects.all().delete()

    products = [
        Product(
            pid=row['产品id'], name=row['产品名称'], price=int(row['售价']),
            sales=int(row['销量']), price_band=row['售价区间'],
            category=row['分类'], sub_category=row['小分类'],
            location=row['发货地'], channel=row['渠道'],
            platform=row['平台'],
            crawl_date=row['时间'].date() if pd.notna(row['时间']) else dt.date(2026, 9, 22),
        )
        for _, row in df.iterrows()
    ]
    Product.objects.bulk_create(products, batch_size=100)

    series = build_monthly_series(df)
    rows = []
    for target, points in series:
        rows.extend([MonthlySales(target=target, month=m, sales=float(v))
                     for m, v in points])
    MonthlySales.objects.bulk_create(rows, batch_size=100)
    return len(products), len(rows)
