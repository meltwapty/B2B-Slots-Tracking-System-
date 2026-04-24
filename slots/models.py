from django.db import models
from django.utils import timezone


class ContractData(models.Model):
    contract_id = models.CharField(max_length=255, unique=True)
    company_name = models.CharField(max_length=255, blank=True, null=True)
    opportunity_id = models.CharField(max_length=255, blank=True, null=True)
    product = models.CharField(max_length=100, blank=True, null=True)
    total_slots = models.IntegerField(default=0)
    fulfilled_slots = models.IntegerField(default=0)
    status = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    raw_data = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Contract Data"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.contract_id} | {self.company_name}"


class OOSEntry(models.Model):
    row_index = models.IntegerField()
    entity = models.CharField(max_length=255, blank=True, null=True)
    company = models.CharField(max_length=255, blank=True, null=True)
    product = models.CharField(max_length=100, blank=True, null=True)
    slots_contracted = models.IntegerField(default=0)
    slots_fulfilled = models.IntegerField(default=0)
    status = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    sheet_id = models.CharField(max_length=255, blank=True, null=True)
    synced_at = models.DateTimeField(auto_now=True)
    raw_row = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "OOS Entry"
        ordering = ["row_index"]

    def __str__(self):
        return f"Row {self.row_index} | {self.company}"


class FulfilmentMetrics(models.Model):
    PERIOD_CHOICES = [("daily","Daily"),("weekly","Weekly"),("monthly","Monthly"),("all_time","All Time")]
    SOURCE_CHOICES = [("graphql","GraphQL API"),("sheets","Google Sheets"),("combined","Combined")]

    period = models.CharField(max_length=20, choices=PERIOD_CHOICES, default="all_time")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="combined")
    total_slots = models.IntegerField(default=0)
    fulfilled_slots = models.IntegerField(default=0)
    fulfilment_rate = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    product_breakdown = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-computed_at"]

    def __str__(self):
        return f"{self.period} | {self.source} | {self.fulfilment_rate_percent}%"

    @property
    def fulfilment_rate_percent(self):
        return round(float(self.fulfilment_rate) * 100, 2)

    def save(self, *args, **kwargs):
        if self.total_slots > 0:
            self.fulfilment_rate = round(self.fulfilled_slots / self.total_slots, 4)
        else:
            self.fulfilment_rate = 0
        super().save(*args, **kwargs)


class SyncLog(models.Model):
    STATUS_CHOICES = [("started","Started"),("success","Success"),("partial","Partial"),("failed","Failed")]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="started")
    source = models.CharField(max_length=50, blank=True)
    records_fetched = models.IntegerField(default=0)
    records_saved = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.source} | {self.status} | {self.started_at.strftime('%Y-%m-%d %H:%M')}"
