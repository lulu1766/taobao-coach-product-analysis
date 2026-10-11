from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('price/', views.price, name='price'),
    path('category/', views.category, name='category'),
    path('channel/', views.channel, name='channel'),
    path('wordcloud/', views.wordcloud, name='wordcloud'),
    path('forecast/', views.forecast, name='forecast'),
]
