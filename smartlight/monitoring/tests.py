from datetime import datetime

from django.test import TestCase
from django.urls import reverse

from .views import _build_activity_log, _extract_latest_sensor_snapshot, _sync_trend_with_value


class DashboardViewTests(TestCase):
    def test_dashboard_page_renders(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lumina Control")
        self.assertContains(response, "Ground Floor")
        self.assertContains(response, "Floor 4")

    def test_dashboard_shows_sensor_metrics(self):
        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "ADC")
        self.assertContains(response, "Sales Departement")
        self.assertContains(response, "Finance Departement")
        self.assertContains(response, "PT.Awan Teknologi Inovasi")

    def test_trend_flattens_to_zero_when_sensor_is_off(self):
        trend = [{"time": "2024-01-01T00:00:00", "value": 320}]

        result = _sync_trend_with_value(trend, 0, {"label": "OFF"})

        self.assertTrue(result)
        self.assertTrue(all(point["value"] == 0 for point in result))

    def test_activity_log_records_status_changes(self):
        previous_log = [
            {
                "floor_id": "F1",
                "floor_name": "Ground Floor",
                "status": "OFF",
                "timestamp": "2024-01-01T00:00:00",
                "date": "2024-01-01",
            }
        ]
        floors = [{"id": "F1", "name": "Ground Floor", "light_status": {"label": "ON"}}]

        result = _build_activity_log(floors, previous_log=previous_log)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[-1]["floor_id"], "F1")
        self.assertEqual(result[-1]["status"], "ON")
        self.assertEqual(result[-1]["date"], datetime.now().strftime("%Y-%m-%d"))

    def test_activity_log_records_initial_state_when_no_history_exists(self):
        floors = [{"id": "F2", "name": "Floor 2", "light_status": {"label": "OFF"}}]

        result = _build_activity_log(floors, previous_log=[])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["floor_id"], "F2")
        self.assertEqual(result[0]["status"], "OFF")

    def test_extract_latest_sensor_snapshot_prefers_newest_values(self):
        class FakeRecord:
            def __init__(self, field, value):
                self._field = field
                self._value = value

            def get_field(self):
                return self._field

            def get_value(self):
                return self._value

        records = [
            FakeRecord("lux", 120),
            FakeRecord("light_status", 0),
            FakeRecord("lux", 90),
        ]

        result = _extract_latest_sensor_snapshot(records)

        self.assertEqual(result["lux"], 120)
        self.assertEqual(result["light_status"]["label"], "OFF")
