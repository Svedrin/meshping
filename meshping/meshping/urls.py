from django.urls import path
from . import views


urlpatterns = [
    path('', views.index, name='index'),
    path('api/targets', views.targets, name='targets'),
]
