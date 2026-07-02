from django.test import SimpleTestCase
from django.urls import reverse


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
        self.assertContains(response, "LUX LEVEL")
        self.assertContains(response, "Sales Departement")
        self.assertContains(response, "Finance Departement")
        self.assertContains(response, "Engineer Departement")
