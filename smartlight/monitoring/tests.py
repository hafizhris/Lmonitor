from django.test import SimpleTestCase
from django.urls import reverse

from .views import _sync_trend_with_value


class DashboardViewTests(SimpleTestCase):
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
