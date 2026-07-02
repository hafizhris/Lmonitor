# monitoring/urls.py

from django.urls import path

from .views import SensorDataView, DebugInfluxDBView, dashboard, FloorDataAPI

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('sensor/', SensorDataView.as_view()),
    path('debug/influxdb/', DebugInfluxDBView.as_view()),
    path('api/floors/', FloorDataAPI.as_view(), name='floor-data-api'),
]
