# -*- coding: utf-8 -*-
"""
LSTM 销量预测模型（TensorFlow + Keras）
=======================================
- 数据：MySQL monthly_sales 表中 4 条 24 个月序列（整体/包袋/香水/其他配饰）
- 建模：6 个月滑动窗口 -> 单变量 LSTM，多序列联合训练增强泛化
- 验证：walk-forward，用前 18 个月训练、预测后 6 个月，计算 MAE/MAPE/RMSE
- 预测：全量 24 个月重训最终模型，递归滚动预测未来 6 个月
"""
import json
import os

os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS', '0')

import numpy as np

from django.conf import settings

WINDOW = 6          # 输入窗口：前 6 个月
HORIZON = 6         # 预测未来 6 个月
EPOCHS = 150
BATCH_SIZE = 8
SEED = 42

TARGETS = ['整体', '包袋', '香水', '其他配饰']


def _set_seed():
    import tensorflow as tf
    tf.keras.utils.set_random_seed(SEED)


def _make_model():
    """双层 LSTM + Dropout，Keras Sequential"""
    from tensorflow.keras import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Input

    model = Sequential([
        Input(shape=(WINDOW, 1)),
        LSTM(64, return_sequences=True),
        Dropout(0.2),
        LSTM(32),
        Dropout(0.2),
        Dense(16, activation='relu'),
        Dense(1),
    ])
    model.compile(optimizer='adam', loss='mse', metrics=['mae'])
    return model


def _build_windows(sequences, train_len=None):
    """多条序列联合构造 (X, y)；train_len 指定每条序列只取前若干点"""
    X, y = [], []
    for vals in sequences:
        vals = np.asarray(vals, dtype=float)
        if train_len is not None:
            vals = vals[:train_len]
        for i in range(len(vals) - WINDOW):
            X.append(vals[i:i + WINDOW])
            y.append(vals[i + WINDOW])
    X = np.asarray(X, dtype=float)[..., None]
    y = np.asarray(y, dtype=float)
    return X, y


class Scaler:
    """每条序列独立 MinMax 归一化，参数持久化为 JSON"""

    def __init__(self):
        self.params = {}

    def fit(self, target, vals):
        vals = np.asarray(vals, dtype=float)
        self.params[target] = [float(vals.min()), float(vals.max())]
        return self.transform(target, vals)

    def transform(self, target, vals):
        lo, hi = self.params[target]
        if hi == lo:
            return np.zeros_like(np.asarray(vals, dtype=float))
        return (np.asarray(vals, dtype=float) - lo) / (hi - lo)

    def inverse(self, target, vals):
        lo, hi = self.params[target]
        return np.asarray(vals, dtype=float) * (hi - lo) + lo

    def save(self, path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.params, f, ensure_ascii=False, indent=2)


def _load_series():
    from dashboard.models import MonthlySales
    series = {}
    for t in TARGETS:
        rows = MonthlySales.objects.filter(target=t).order_by('month')
        series[t] = np.array([r.sales for r in rows], dtype=float)
    return series


def _metrics(true, pred):
    true = np.asarray(true, dtype=float)
    pred = np.asarray(pred, dtype=float)
    mae = float(np.mean(np.abs(true - pred)))
    rmse = float(np.sqrt(np.mean((true - pred) ** 2)))
    mape = float(np.mean(np.abs((true - pred) / np.where(true == 0, 1, true))) * 100)
    return mae, mape, rmse


def train_and_forecast():
    """完整训练流程，结果写入 sales_forecast / model_metric 表，模型落盘"""
    import datetime as dt
    from tensorflow.keras.callbacks import EarlyStopping

    from dashboard.models import SalesForecast, ModelMetric

    _set_seed()
    raw = _load_series()
    scaler = Scaler()
    scaled = {t: scaler.fit(t, v) for t, v in raw.items()}

    es = EarlyStopping(monitor='loss', patience=20, restore_best_weights=True)

    # ---------- 1) walk-forward 验证：前 18 月训练 -> 后 6 月验证 ----------
    Xv, yv = _build_windows([scaled[t] for t in TARGETS], train_len=18)
    val_model = _make_model()
    val_model.fit(Xv, yv, epochs=EPOCHS, batch_size=BATCH_SIZE,
                  verbose=0, shuffle=True, callbacks=[es])

    metric_rows = []
    for t in TARGETS:
        s = scaled[t].tolist()
        history_window = s[:18]
        preds = []
        for _ in range(6):
            x = np.asarray(history_window[-WINDOW:], dtype=float)[None, :, None]
            p = float(val_model.predict(x, verbose=0)[0][0])
            preds.append(p)
            history_window.append(p)
        pred_real = scaler.inverse(t, preds)
        true_real = raw[t][18:24]
        mae, mape, rmse = _metrics(true_real, pred_real)
        metric_rows.append(ModelMetric(
            target=t, mae=round(mae, 1), mape=round(mape, 2), rmse=round(rmse, 1),
            sample_count=len(Xv), epochs=EPOCHS))

    # ---------- 2) 全量 24 月重训最终模型 ----------
    Xf, yf = _build_windows([scaled[t] for t in TARGETS])
    final_model = _make_model()
    final_model.fit(Xf, yf, epochs=EPOCHS, batch_size=BATCH_SIZE,
                    verbose=0, shuffle=True, callbacks=[es])

    MODEL_DIR = settings.MODEL_DIR
    os.makedirs(MODEL_DIR, exist_ok=True)
    final_model.save(os.path.join(MODEL_DIR, 'lstm_sales.keras'))
    scaler.save(os.path.join(MODEL_DIR, 'scaler.json'))

    # ---------- 3) 递归滚动预测未来 6 个月 ----------
    SalesForecast.objects.all().delete()
    ModelMetric.objects.all().delete()
    ModelMetric.objects.bulk_create(metric_rows)

    forecast_rows = []
    last_month = dt.date(2026, 9, 1)
    future_months = []
    for i in range(1, HORIZON + 1):
        y, m = last_month.year, last_month.month + i
        y += (m - 1) // 12
        m = (m - 1) % 12 + 1
        future_months.append(dt.date(y, m, 1))

    for t in TARGETS:
        window = scaled[t].tolist()
        preds = []
        for _ in range(HORIZON):
            x = np.asarray(window[-WINDOW:], dtype=float)[None, :, None]
            p = float(final_model.predict(x, verbose=0)[0][0])
            preds.append(p)
            window.append(p)
        pred_real = np.maximum(scaler.inverse(t, preds), 0)
        forecast_rows.extend([
            SalesForecast(target=t, month=future_months[i],
                          predicted_sales=round(float(v), 1))
            for i, v in enumerate(pred_real)
        ])
    SalesForecast.objects.bulk_create(forecast_rows)

    return {r.target: (r.mae, r.mape, r.rmse) for r in metric_rows}
