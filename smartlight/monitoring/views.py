from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from influxdb_client import Point
from datetime import datetime, timedelta
import json

from .influx import client, bucket, org
from .models import ActivityLogEntry
import math
import random


def _format_light_status(value):
    """Convert numeric light status to label and CSS class."""
    if value in (0, "0", False, "False"):
        return {"label": "OFF", "class": "offline"}
    if value in (1, "1", True, "True"):
        return {"label": "ON", "class": "online"}
    return {"label": "Unknown", "class": "unknown"}


def _generate_dummy_trend(base, count=30, interval_seconds=120, amplitude=30, noise=8, phase=0):
    """Return a smooth dummy lux trend for overview cards."""
    now = datetime.now()
    trend = []
    for i in range(count):
        timestamp = now - timedelta(seconds=interval_seconds * (count - 1 - i))
        drift = math.sin((i + phase) * 0.25) * amplitude
        value = int(max(0, base + drift + random.uniform(-noise, noise)))
        trend.append({"time": timestamp.isoformat(), "value": value})
    return trend


def _build_activity_log(floors, previous_log=None):
    """Create a persistent state-change history for floor status updates."""
    previous_log = previous_log or []
    if not floors:
        return previous_log

    now = datetime.now()
    existing_entries = list(ActivityLogEntry.objects.order_by("id"))
    history = []

    if existing_entries:
        history = [
            {
                "floor_id": entry.floor_id,
                "floor_name": entry.floor_name,
                "status": entry.status,
                "timestamp": entry.timestamp,
                "date": entry.date,
                "time_display": entry.time_display,
            }
            for entry in existing_entries
        ]
    elif previous_log:
        history = [dict(entry) for entry in previous_log]
        for entry in history:
            ActivityLogEntry.objects.create(
                floor_id=entry.get("floor_id"),
                floor_name=entry.get("floor_name", entry.get("floor_id")),
                status=entry.get("status", "UNKNOWN"),
                timestamp=entry.get("timestamp", now.strftime("%H:%M:%S")),
                date=entry.get("date", now.strftime("%Y-%m-%d")),
                time_display=entry.get("time_display", now.strftime("%I:%M:%S %p")),
            )
    else:
        history = []

    latest_by_floor = {}
    for entry in reversed(history):
        floor_id = entry.get("floor_id")
        if floor_id and floor_id not in latest_by_floor:
            latest_by_floor[floor_id] = entry

    for floor in floors:
        floor_id = floor.get("id")
        current_status = floor.get("light_status", {}).get("label", "UNKNOWN")
        previous_entry = latest_by_floor.get(floor_id)
        if previous_entry is None:
            if history:
                continue
            new_entry = {
                "floor_id": floor_id,
                "floor_name": floor.get("name", floor_id),
                "status": current_status,
                "timestamp": now.strftime("%H:%M:%S"),
                "date": now.strftime("%Y-%m-%d"),
                "time_display": now.strftime("%I:%M:%S %p"),
                "details": f"{floor.get('name', floor_id)} changed to {current_status} at {now.strftime('%H:%M:%S')} on {now.strftime('%Y-%m-%d')}"
            }
            history.append(new_entry)
            ActivityLogEntry.objects.create(
                floor_id=new_entry["floor_id"],
                floor_name=new_entry["floor_name"],
                status=new_entry["status"],
                timestamp=new_entry["timestamp"],
                date=new_entry["date"],
                time_display=new_entry["time_display"],
            )
            continue
        if previous_entry.get("status") == current_status:
            continue

        new_entry = {
            "floor_id": floor_id,
            "floor_name": floor.get("name", floor_id),
            "status": current_status,
            "timestamp": now.strftime("%H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "time_display": now.strftime("%I:%M:%S %p"),
            "details": f"{floor.get('name', floor_id)} changed to {current_status} at {now.strftime('%H:%M:%S')} on {now.strftime('%Y-%m-%d')}"
        }
        history.append(new_entry)
        ActivityLogEntry.objects.create(
            floor_id=new_entry["floor_id"],
            floor_name=new_entry["floor_name"],
            status=new_entry["status"],
            timestamp=new_entry["timestamp"],
            date=new_entry["date"],
            time_display=new_entry["time_display"],
        )

    return history


def _extract_latest_sensor_snapshot(records):
    """Read the newest available sensor values from a sorted record set."""
    data = {"adc": None, "lux": None, "light_status": None}
    for record in records:
        field_name = record.get_field()
        value = record.get_value()
        if field_name == "adc" and data["adc"] is None:
            data["adc"] = int(value) if value is not None else None
        elif field_name == "lux" and data["lux"] is None:
            data["lux"] = int(value) if value is not None else None
        elif field_name == "light_status" and data["light_status"] is None:
            data["light_status"] = _format_light_status(value)
    if data["light_status"] is None:
        data["light_status"] = _format_light_status(0)
    return data


def _get_influxdb_latest_data():
    """Fetch the latest reading from InfluxDB for Floor 4."""
    try:
        query_api = client.query_api()
        query = f'''
        from(bucket: "{bucket}")
          |> range(start: -1h)
          |> filter(fn: (r) => r["_measurement"] == "Light_Monitoring")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: 10)
        '''
        result = query_api.query(org=org, query=query)

        records = []
        for table in result:
            records.extend(table.records)
        return _extract_latest_sensor_snapshot(records)
    except Exception as e:
        print(f"Error fetching InfluxDB data: {e}")
        return {"adc": 0, "lux": 0, "light_status": _format_light_status(0), "error": True}


def _get_influxdb_trend_data():
    """Fetch lux trend data from InfluxDB for the last hour."""
    try:
        query_api = client.query_api()
        query = f'''
        from(bucket: "{bucket}")
          |> range(start: -1h)
          |> filter(fn: (r) => r["_measurement"] == "Light_Monitoring" and r["_field"] == "lux")
          |> sort(columns: ["_time"])
        '''
        result = query_api.query(org=org, query=query)
        
        trend_data = []
        for table in result:
            for record in table.records:
                trend_data.append({
                    "time": record.get_time().isoformat(),
                    "value": int(record.get_value()) if record.get_value() else 0
                })
        return trend_data[-30:] if len(trend_data) > 30 else trend_data  # Last 30 points
    except Exception as e:
        print(f"Error fetching trend data: {e}")
        return []


def _sync_trend_with_value(trend, lux_value, light_status=None):
    """Keep the trend aligned with the current lux value, flattening to zero when data is missing or the sensor is off."""
    if not trend:
        return []

    should_flatten = (
        light_status is not None and light_status.get("label") == "OFF"
    ) or lux_value in (None, 0, "0", False)

    if should_flatten:
        return [
            {"time": (datetime.now() - timedelta(seconds=(len(trend) - 1 - i) * 120)).isoformat(), "value": 0}
            for i in range(len(trend))
        ]

    updated_trend = [point.copy() for point in trend]
    updated_trend[-1]["value"] = int(lux_value) if lux_value is not None else 0
    updated_trend[-1]["time"] = datetime.now().isoformat()
    return updated_trend


def dashboard(request):
    """Render the main monitoring dashboard."""
    # Fetch Floor 4 data from InfluxDB
    floor4_data = _get_influxdb_latest_data()
    floor4_trend = _get_influxdb_trend_data()
    floor4_light_status = floor4_data.get("light_status", _format_light_status(1))
    floor4_lux = floor4_data.get("lux") if floor4_data.get("lux") is not None else 0
    floor4_adc = floor4_data.get("adc") if floor4_data.get("adc") is not None else 0

    if floor4_data.get("error", False) or floor4_light_status.get("label") == "OFF" or floor4_lux in (None, 0, "0", False):
        floor4_lux = 0
        floor4_adc = 0
        floor4_light_status = _format_light_status(0)
    
    # Floor data - Floors 1-3 simulated, Floor 4 from InfluxDB with fallback
    floors = [
        {
            "id": "F1",
            "name": "Ground Floor",
            "location": "Lobby",
            "model": "ESP32 Dev Module",
            "adc": 1837,
            "lux": 459,
            "light_status": _format_light_status(1),
            "dummy": True,
            "trend": _generate_dummy_trend(base=420, count=24, interval_seconds=150, amplitude=35, noise=8, phase=0)
        },
        {
            "id": "F2",
            "name": "Floor 2",
            "location": "Sales Departement",
            "model": "ESP32 Dev Module",
            "adc": 796,
            "lux": 196,
            "light_status": _format_light_status(0),
            "dummy": True,
            "trend": _generate_dummy_trend(base=200, count=30, interval_seconds=180, amplitude=25, noise=6, phase=5)
        },
        {
            "id": "F3",
            "name": "Floor 3",
            "location": "Finance Departement",
            "model": "ESP32 Dev Module",
            "adc": 2994,
            "lux": 748,
            "light_status": _format_light_status(1),
            "dummy": True,
            "trend": _generate_dummy_trend(base=760, count=30, interval_seconds=180, amplitude=30, noise=7, phase=10)
        },
        {
            "id": "F4",
            "name": "Floor 4",
            "location": "PT.Awan Teknologi Inovasi",
            "model": "ESP32 Dev Module",
            "adc": floor4_adc,
            "lux": floor4_lux,
            "light_status": floor4_light_status,
            "dummy": floor4_data.get("error", False),
            "trend": _sync_trend_with_value(
                floor4_trend if floor4_trend else [{"time": (datetime.now() - timedelta(minutes=i)).isoformat(), "value": 0} for i in range(30)],
                floor4_lux,
                floor4_light_status
            ),
            "error": floor4_data.get("error", False)
        }
    ]
    
    # Calculate summary stats
    total_floors = len(floors)
    lights_on = sum(1 for f in floors if f["light_status"]["label"] == "ON")
    avg_lux = sum(f["lux"] for f in floors) // total_floors if total_floors > 0 else 0
    
    activity_log = _build_activity_log(
        floors,
        previous_log=request.session.get("activity_log", []),
    )
    request.session["activity_log"] = activity_log
    request.session.modified = True

    context = {
        "floors": floors,  # For template iteration
        "floors_json": json.dumps(floors),  # For JavaScript
        "activity_log_json": json.dumps(activity_log),
        "total_floors": total_floors,
        "lights_on": lights_on,
        "avg_lux": avg_lux,
        "timestamp": datetime.now().strftime("%I:%M %p")
    }
    return render(request, "monitoring/dashboard.html", context)


class DebugInfluxDBView(APIView):
    """Debug endpoint to check InfluxDB connection and available data."""
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            query_api = client.query_api()
            # Query ALL data from last 24 hours to see what's available
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: -24h)
              |> limit(n: 20)
            '''
            result = query_api.query(org=org, query=query)
            
            data = []
            for table in result:
                for record in table.records:
                    data.append({
                        "time": record.get_time().isoformat(),
                        "measurement": record.get_measurement(),
                        "field": record.get_field(),
                        "value": record.get_value(),
                        "tags": dict(record.values)
                    })
            
            if not data:
                return Response({
                    "status": "connected",
                    "message": "InfluxDB is connected but NO data found in bucket 'Lmonitor' (last 24h)",
                    "troubleshooting": [
                        "1. Check if your Node-RED is sending data",
                        "2. Verify the payload format matches your configuration",
                        "3. Check InfluxDB for any data in the Lmonitor bucket",
                        "4. Try posting test data to /sensor/ endpoint"
                    ],
                    "data": [],
                    "url": "http://10.231.37.187:8086",
                    "org": "Magang",
                    "bucket": "Lmonitor"
                })
            
            return Response({
                "status": "connected",
                "message": f"Found {len(data)} records in InfluxDB (last 24h)",
                "data": data
            })
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e),
                "url": "http://10.231.37.187:8086",
                "org": "Magang",
                "bucket": "Lmonitor",
                "error_type": type(e).__name__
            }, status=400)


class SensorDataView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        adc_value = request.data.get("adc")
        lux_value = request.data.get("lux")
        light_status = request.data.get("light_status")

        write_api = client.write_api()
        point = (
            Point("light_sensor")
            .field("ldr_value", int(adc_value) if adc_value else 0)
            .field("lux", int(lux_value) if lux_value else 0)
            .field("light_status", int(light_status) if light_status else 0)
        )
        write_api.write(bucket=bucket, record=point)

        return Response({"status": "success"})


class FloorDataAPI(APIView):
    """API endpoint to fetch real-time floor data for live updates."""
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        """Return current floor data for all floors."""
        # Fetch Floor 4 data from InfluxDB
        floor4_data = _get_influxdb_latest_data()
        floor4_trend = _get_influxdb_trend_data()
        floor4_light_status = floor4_data.get("light_status", _format_light_status(1))
        floor4_lux = floor4_data.get("lux") if floor4_data.get("lux") is not None else 0
        floor4_adc = floor4_data.get("adc") if floor4_data.get("adc") is not None else 0

        if floor4_data.get("error", False) or floor4_light_status.get("label") == "OFF" or floor4_lux in (None, 0, "0", False):
            floor4_lux = 0
            floor4_adc = 0
            floor4_light_status = _format_light_status(0)
        
        # Return floor data
        floors = [
            {
                "id": "F1",
                "name": "Ground Floor",
                "location": "Lobby",
                "model": "ESP32 Dev Module",
                "adc": 1837,
                "lux": 459,
                "light_status": _format_light_status(1),
                "dummy": True,
                "trend": _generate_dummy_trend(base=420, count=24, interval_seconds=150, amplitude=35, noise=8, phase=0)
            },
            {
                "id": "F2",
                "name": "Floor 2",
                "location": "Sales Departement",
                "model": "ESP32 Dev Module",
                "adc": 796,
                "lux": 196,
                "light_status": _format_light_status(0),
                "dummy": True,
                "trend": _generate_dummy_trend(base=200, count=30, interval_seconds=180, amplitude=25, noise=6, phase=5)
            },
            {
                "id": "F3",
                "name": "Floor 3",
                "location": "Finance Departement",
                "model": "ESP32 Dev Module",
                "adc": 2994,
                "lux": 748,
                "light_status": _format_light_status(1),
                "dummy": True,
                "trend": _generate_dummy_trend(base=760, count=30, interval_seconds=180, amplitude=30, noise=7, phase=10)
            },
            {
                "id": "F4",
                "name": "Floor 4",
                "location": "PT.Awan Teknologi Inovasi",
                "model": "ESP32 Dev Module",
                "adc": floor4_adc,
                "lux": floor4_lux,
                "light_status": floor4_light_status,
                "dummy": floor4_data.get("error", False),
                "trend": _sync_trend_with_value(
                    floor4_trend if floor4_trend else [{"time": (datetime.now() - timedelta(minutes=i)).isoformat(), "value": 0} for i in range(30)],
                    floor4_lux,
                    floor4_light_status
                ),
                "error": floor4_data.get("error", False)
            }
        ]
        
        # Calculate summary stats
        total_floors = len(floors)
        lights_on = sum(1 for f in floors if f["light_status"]["label"] == "ON")
        avg_lux = sum(f["lux"] for f in floors) // total_floors if total_floors > 0 else 0
        
        activity_log = _build_activity_log(
            floors,
            previous_log=request.session.get("activity_log", []),
        )
        request.session["activity_log"] = activity_log
        request.session.modified = True

        return Response({
            "status": "success",
            "floors": floors,
            "activity_log": activity_log,
            "total_floors": total_floors,
            "lights_on": lights_on,
            "avg_lux": avg_lux,
            "timestamp": datetime.now().isoformat()
        })
