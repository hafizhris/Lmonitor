# monitoring/influx.py

from influxdb_client import InfluxDBClient

url = "http://10.231.37.187:8086"
token = "Xq5L6vBhP8X-hbM9JIBlRuDVJFc6nZaVK2FdHNUm5W2VxeRWl7sDk7NntP3ttfRxppkPOkl9Ze9iXz9LRNirCw=="
org = "Magang"
bucket = "Lmonitor"

client = InfluxDBClient(
    url=url,
    token=token,
    org=org
)
