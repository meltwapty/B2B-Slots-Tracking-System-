from django.contrib import admin
from .models import ContractData, OOSEntry, FulfilmentMetrics, SyncLog


@admin.register(ContractData)
class ContractDataAdmin(admin.ModelAdmin):
    list_display = ["contract_id", "company_name", "product", "total_slots", "fulfilled_slots", "status", "updated_at"]
    search_fields = ["contract_id", "company_name"]
    list_filter = ["product", "status"]


@admin.register(OOSEntry)
class OOSEntryAdmin(admin.ModelAdmin):
    list_display = ["row_index", "entity", "company", "product", "slots_contracted", "slots_fulfilled", "status"]
    search_fields = ["company", "entity"]
    list_filter = ["product", "status"]


@admin.register(FulfilmentMetrics)
class FulfilmentMetricsAdmin(admin.ModelAdmin):
    list_display = ["period", "source", "total_slots", "fulfilled_slots", "fulfilment_rate_percent", "computed_at"]
    list_filter = ["source", "period"]
    readonly_fields = ["fulfilment_rate"]


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ["source", "status", "records_fetched", "records_saved", "started_at", "finished_at"]
    list_filter = ["source", "status"]
