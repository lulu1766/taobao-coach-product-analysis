# -*- coding: utf-8 -*-
"""视图层：从 MySQL 取数 -> 组装 JSON 数据契约 -> 渲染 ECharts 页面"""
import json
import re
from collections import Counter

import jieba
from django.db.models import Avg, Count, Sum
from django.shortcuts import render

from .models import Product, MonthlySales, SalesForecast, ModelMetric

BAND_ORDER = ['0-500', '500-1000', '1000-2000', '2000-3000', '3000+']
TARGETS = ['整体', '包袋', '香水', '其他配饰']


def _ctx(**kw):
    """统一把 Python 对象转 JSON 字符串注入模板"""
    return {k: json.dumps(v, ensure_ascii=False) for k, v in kw.items()}


# ------------------------------ 数据总览 ------------------------------
def index(request):
    products = Product.objects.all()
    total_cnt = products.count()
    total_sales = sum(p.sales for p in products)
    prices = sorted(p.price for p in products)
    median_price = prices[len(prices) // 2]
    zero_cnt = sum(1 for p in products if p.sales == 0)
    avg_sales = round(total_sales / total_cnt)

    # TOP10：销量柱 + 售价折线（双轴组合图）
    top10 = products[:10]
    top10_data = json.dumps({
        'names': [p.name[:16] for p in top10],
        'sales': [p.sales for p in top10],
        'prices': [p.price for p in top10],
    }, ensure_ascii=False)

    # 品类销量饼图
    cat = (products.values('category')
           .annotate(value=Sum('sales'))
           .order_by('-value'))
    pie_data = [{'name': c['category'], 'value': c['value']} for c in cat]

    # 渠道漏斗（按销量降序）
    ch = (products.values('channel')
          .annotate(cnt=Count('id'), sales=Sum('sales'))
          .order_by('-sales'))
    funnel = [{'name': c['channel'], 'value': c['sales']} for c in ch]

    kpi = _ctx(total_cnt=total_cnt, total_sales=total_sales,
               median_price=median_price, zero_pct=round(zero_cnt / total_cnt * 100, 1),
               avg_sales=avg_sales, top10_pct=round(
                   sum(p.sales for p in top10) / total_sales * 100, 1))
    return render(request, 'dashboard/index.html', {
        'active': 'index', 'kpi': kpi, 'top10_data': top10_data,
        'pie_data': json.dumps(pie_data, ensure_ascii=False),
        'funnel_data': json.dumps(funnel, ensure_ascii=False),
    })


# ------------------------------ 价格分析 ------------------------------
def price(request):
    products = list(Product.objects.all().values('price', 'sales', 'price_band'))

    # 价格分布直方图（100 元一档）
    bins = list(range(0, 5000, 100)) + [10000]
    labels = [f'{b}-{b + 100}' if b < 4900 else '5000+' for b in bins[:-1]]
    counts = [0] * (len(bins) - 1)
    for p in products:
        for i in range(len(bins) - 1):
            if bins[i] <= p['price'] < bins[i + 1]:
                counts[i] += 1
                break

    # 价格带：款数 / 销量 / 销量占比
    band_cnt = Counter(p['price_band'] for p in products)
    band_sales = Counter()
    for p in products:
        band_sales[p['price_band']] += p['sales']
    total_sales = sum(band_sales.values())
    band_data = _ctx(
        bands=BAND_ORDER,
        counts=[band_cnt.get(b, 0) for b in BAND_ORDER],
        sales=[band_sales.get(b, 0) for b in BAND_ORDER],
        share=[round(band_sales.get(b, 0) / total_sales * 100, 1)
               for b in BAND_ORDER],
    )

    # 价格-销量散点（只取有销量的商品，避免 0 值挤压）
    scatter = [[p['price'], p['sales']] for p in products if p['sales'] > 0]

    return render(request, 'dashboard/price.html', {
        'active': 'price',
        'hist_data': json.dumps({'labels': labels, 'counts': counts},
                                ensure_ascii=False),
        **band_data,
        'scatter_data': json.dumps(scatter, ensure_ascii=False),
    })


# ------------------------------ 品类分析 ------------------------------
def category(request):
    products = Product.objects.all()
    cat = (products.values('category')
           .annotate(cnt=Count('id'), sales=Sum('sales'),
                     avg_price=Avg('price'))
           .order_by('-sales'))
    cats = [c['category'] for c in cat]
    cat_data = _ctx(
        cats=cats,
        counts=[c['cnt'] for c in cat],
        sales=[c['sales'] for c in cat],
        avg=[round(c['sales'] / c['cnt']) for c in cat],
        avg_price=[round(c['avg_price']) for c in cat],
    )

    # 小分类 TOP10 销量
    sub = (products.values('sub_category')
           .annotate(sales=Sum('sales'), cnt=Count('id'))
           .order_by('-sales')[:10])
    sub_data = _ctx(sub_names=[s['sub_category'] for s in sub],
                    sub_sales=[s['sales'] for s in sub],
                    sub_counts=[s['cnt'] for s in sub])
    return render(request, 'dashboard/category.html', {
        'active': 'category', **cat_data, **sub_data})


# ------------------------------ 渠道分析 ------------------------------
def channel(request):
    products = Product.objects.all()
    ch = list(products.values('channel')
              .annotate(cnt=Count('id'), sales=Sum('sales'),
                        avg_price=Avg('price'))
              .order_by('-sales'))
    ch_data = _ctx(
        names=[c['channel'] for c in ch],
        counts=[c['cnt'] for c in ch],
        sales=[c['sales'] for c in ch],
        avg=[round(c['sales'] / c['cnt']) for c in ch],
        avg_price=[round(c['avg_price']) for c in ch],
    )

    # 渠道 × 价格带 堆叠柱
    matrix = {c['channel']: {b: 0 for b in BAND_ORDER} for c in ch}
    for p in products.values('channel', 'price_band'):
        if p['price_band'] in matrix.get(p['channel'], {}):
            matrix[p['channel']][p['price_band']] += 1
    stack = json.dumps({
        'names': [c['channel'] for c in ch],
        'bands': BAND_ORDER,
        'series': [{'name': b, 'data': [matrix[c['channel']][b] for c in ch]}
                   for b in BAND_ORDER],
    }, ensure_ascii=False)
    return render(request, 'dashboard/channel.html', {
        'active': 'channel', **ch_data, 'stack_data': stack})


# ------------------------------ 标题词云 ------------------------------
STOP_WORDS = {
    'COACH', 'Coach', 'coach', '蔻驰', '女士', '女款', '官方', '正品', '新款',
    '代购', '美国', '直邮', '现货', '款', '女', '系列', '旗舰店', '官网',
    'OUTLET', 'outlet', 'Outlet', '同名', '专享', '淘客', '自营', '发货',
    '链接', '商品', 'https', 'http', 'com', '详情', '图片', '品牌',
}


def wordcloud(request):
    names = Product.objects.values_list('name', flat=True)
    freq = Counter()
    for name in names:
        # 英文型号词（CITY/TABBY 等）+ 中文词
        for w in re.findall(r'[A-Za-z]{3,}', name):
            if w not in STOP_WORDS:
                freq[w] += 1
        for w in jieba.cut(name):
            w = w.strip()
            if len(w) >= 2 and w not in STOP_WORDS and not w.isascii():
                freq[w] += 1
    top = freq.most_common(80)
    data = [{'name': w, 'value': c} for w, c in top]
    bar = _ctx(names=[w for w, _ in top[:15][::-1]],
               counts=[c for _, c in top[:15][::-1]])
    return render(request, 'dashboard/wordcloud.html', {
        'active': 'wordcloud',
        'cloud_data': json.dumps(data, ensure_ascii=False), **bar})


# ------------------------------ LSTM 销量预测 ------------------------------
def forecast(request):
    payload = {}
    for t in TARGETS:
        hist = MonthlySales.objects.filter(target=t).order_by('month')
        pred = SalesForecast.objects.filter(target=t).order_by('month')
        payload[t] = {
            'hist_months': [h.month.strftime('%Y-%m') for h in hist],
            'hist_sales': [round(h.sales) for h in hist],
            'pred_months': [p.month.strftime('%Y-%m') for p in pred],
            'pred_sales': [round(p.predicted_sales) for p in pred],
        }
    metrics = list(ModelMetric.objects.all())
    metric_list = [{
        'target': m.target, 'mae': m.mae, 'mape': m.mape,
        'rmse': m.rmse, 'samples': m.sample_count, 'epochs': m.epochs,
    } for m in metrics]
    return render(request, 'dashboard/forecast.html', {
        'active': 'forecast',
        'series_data': json.dumps(payload, ensure_ascii=False),
        'metric_data': json.dumps(metric_list, ensure_ascii=False),
    })
