# -*- coding: utf-8 -*-
"""一键初始化：导入 352 条商品 + 构造月度序列 + 训练 LSTM + 预测入库"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '初始化 Coach 分析系统全部数据（商品/月度序列/LSTM预测）'

    def add_arguments(self, parser):
        parser.add_argument('--no-train', action='store_true',
                            help='跳过 LSTM 训练（仅导入商品和月度序列）')

    def handle(self, *args, **opts):
        from dashboard.ml.data_builder import import_to_db
        from dashboard.ml.lstm_forecast import train_and_forecast

        self.stdout.write('1/3 导入商品数据并构造月度销量序列 ...')
        p_cnt, m_cnt = import_to_db()
        self.stdout.write(self.style.SUCCESS(
            f'    商品 {p_cnt} 条，月度序列 {m_cnt} 条'))

        if opts['no_train']:
            self.stdout.write(self.style.WARNING('已跳过 LSTM 训练'))
            return

        self.stdout.write('2/3 训练 LSTM 模型（walk-forward 验证 + 全量重训）...')
        metrics = train_and_forecast()
        self.stdout.write('3/3 完成。各序列验证集指标（MAE / MAPE / RMSE）：')
        for t, (mae, mape, rmse) in metrics.items():
            self.stdout.write(self.style.SUCCESS(
                f'    {t:<6} MAE={mae:>8.1f}  MAPE={mape:>6.2f}%  RMSE={rmse:>8.1f}'))
