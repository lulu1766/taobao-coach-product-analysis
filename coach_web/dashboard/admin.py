from django.contrib import admin

from .models import Product, MonthlySales, SalesForecast, ModelMetric


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('pid', 'name', 'price', 'sales', 'price_band',
                    'category', 'sub_category', 'channel', 'crawl_date')
    list_filter = ('category', 'channel', 'price_band')
    search_fields = ('pid', 'name')
    list_per_page = 30


@admin.register(MonthlySales)
class MonthlySalesAdmin(admin.ModelAdmin):
    list_display = ('target', 'month', 'sales')
    list_filter = ('target',)


@admin.register(SalesForecast)
class SalesForecastAdmin(admin.ModelAdmin):
    list_display = ('target', 'month', 'predicted_sales', 'model_name')
    list_filter = ('target', 'model_name')


@admin.register(ModelMetric)
class ModelMetricAdmin(admin.ModelAdmin):
    list_display = ('target', 'mae', 'mape', 'rmse', 'sample_count', 'epochs')
