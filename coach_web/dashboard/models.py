from django.db import models


class Product(models.Model):
    """Coach 淘宝商品快照（采集于 2026-09-22）"""

    pid = models.CharField('产品ID', max_length=20, unique=True)
    name = models.CharField('商品标题', max_length=300)
    price = models.IntegerField('售价(元)')
    sales = models.IntegerField('销量(件)')
    price_band = models.CharField('价格带', max_length=20)
    category = models.CharField('品类', max_length=30)
    sub_category = models.CharField('小分类', max_length=30)
    location = models.CharField('发货地', max_length=30, blank=True)
    channel = models.CharField('销售渠道', max_length=30)
    platform = models.CharField('平台', max_length=20, default='淘宝')
    crawl_date = models.DateField('采集日期')

    class Meta:
        db_table = 'product'
        verbose_name = '商品'
        verbose_name_plural = verbose_name
        ordering = ['-sales']

    def __str__(self):
        return f'{self.pid} {self.name[:20]}'


class MonthlySales(models.Model):
    """月度销量序列（依据截面总销量与电商季节因子构造，target=整体 或 品类名）"""

    target = models.CharField('预测对象', max_length=30)
    month = models.DateField('月份')
    sales = models.FloatField('月销量(件)')

    class Meta:
        db_table = 'monthly_sales'
        verbose_name = '月度销量'
        verbose_name_plural = verbose_name
        unique_together = ('target', 'month')
        ordering = ['target', 'month']


class SalesForecast(models.Model):
    """LSTM 模型销量预测结果"""

    target = models.CharField('预测对象', max_length=30)
    month = models.DateField('预测月份')
    predicted_sales = models.FloatField('预测销量(件)')
    model_name = models.CharField('模型', max_length=50, default='LSTM')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sales_forecast'
        verbose_name = '销量预测'
        verbose_name_plural = verbose_name
        unique_together = ('target', 'month')
        ordering = ['target', 'month']


class ModelMetric(models.Model):
    """LSTM 模型评估指标"""

    target = models.CharField('预测对象', max_length=30, unique=True)
    mae = models.FloatField('MAE 平均绝对误差')
    mape = models.FloatField('MAPE 平均绝对百分比误差(%)')
    rmse = models.FloatField('RMSE 均方根误差')
    sample_count = models.IntegerField('训练样本数')
    epochs = models.IntegerField('训练轮次')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'model_metric'
        verbose_name = '模型指标'
        verbose_name_plural = verbose_name
