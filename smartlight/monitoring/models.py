from django.db import models


class ActivityLogEntry(models.Model):
    floor_id = models.CharField(max_length=50)
    floor_name = models.CharField(max_length=100)
    status = models.CharField(max_length=10)
    timestamp = models.CharField(max_length=20)
    date = models.CharField(max_length=20)
    time_display = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
