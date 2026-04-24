from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import json
import logging

from .models import FulfilmentMetrics, ContractData, OOSEntry, SyncLog
from .fulfilment import aggregate_graphql, aggregate_sheets, combine_sources, build_dashboard_payload, aggregate_lc_breakdown, aggregate_lc_breakdown_product
from .sync_engine import SyncEngine
from .sheets_client import fetch_project_data

logger = logging.getLogger(__name__)


def dashboard_ui(request):
    """Serve the HTML dashboard."""
    import os
    template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "dashboard.html")
    with open(template_path, encoding="utf-8") as f:
        html = f.read()
    from django.http import HttpResponse
    return HttpResponse(html)


class DashboardView(View):
    def get(self, request):
        latest    = FulfilmentMetrics.objects.filter(source="combined").first()
        graphql_m = FulfilmentMetrics.objects.filter(source="graphql").first()
        sheets_m  = FulfilmentMetrics.objects.filter(source="sheets").first()

        if not latest:
            gql_agg  = aggregate_graphql(list(ContractData.objects.all()))
            sh_agg   = aggregate_sheets(list(OOSEntry.objects.all()))
            combined = combine_sources(gql_agg, sh_agg)
            lc_bd    = aggregate_lc_breakdown(list(OOSEntry.objects.all()))
            dashboard = build_dashboard_payload(combined, gql_agg, sh_agg, lc_bd)
            dashboard["lc_breakdown_igt"] = aggregate_lc_breakdown_product(list(OOSEntry.objects.all()), "IGT")
            dashboard["lc_breakdown_igv"] = aggregate_lc_breakdown_product(list(OOSEntry.objects.all()), "IGV")
            dashboard["lc_projects_breakdown"] = fetch_project_data()
        else:
            dashboard = {
                "summary": {
                    "total_slots":     latest.total_slots,
                    "fulfilled_slots": latest.fulfilled_slots,
                    "fulfilment_rate": float(latest.fulfilment_rate),
                    "fulfilment_pct":  latest.fulfilment_rate_percent,
                    "gap":             max(latest.total_slots - latest.fulfilled_slots, 0),
                },
                "by_source": {
                    "graphql": {
                        "total_slots":     graphql_m.total_slots if graphql_m else 0,
                        "fulfilled_slots": graphql_m.fulfilled_slots if graphql_m else 0,
                        "fulfilment_pct":  graphql_m.fulfilment_rate_percent if graphql_m else 0,
                    },
                    "sheets": {
                        "total_slots":     sheets_m.total_slots if sheets_m else 0,
                        "fulfilled_slots": sheets_m.fulfilled_slots if sheets_m else 0,
                        "fulfilment_pct":  sheets_m.fulfilment_rate_percent if sheets_m else 0,
                    },
                },
                "by_product":  latest.product_breakdown,
                "lc_breakdown": aggregate_lc_breakdown(list(OOSEntry.objects.all())),
                "lc_breakdown_igt": aggregate_lc_breakdown_product(list(OOSEntry.objects.all()), "IGT"),
                "lc_breakdown_igv": aggregate_lc_breakdown_product(list(OOSEntry.objects.all()), "IGV"),
                "lc_projects_breakdown": fetch_project_data(),
                "computed_at": latest.computed_at.isoformat(),
            }

        dashboard["record_counts"] = {
            "contracts":   ContractData.objects.count(),
            "oos_entries": OOSEntry.objects.count(),
        }
        return JsonResponse(dashboard)


@method_decorator(csrf_exempt, name="dispatch")
class SyncTriggerView(View):
    def post(self, request):
        try:
            body = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            body = {}

        email    = body.get("email")    or getattr(settings, "GQL_EMAIL", None)
        password = body.get("password") or getattr(settings, "GQL_PASSWORD", None)
        lc_id    = body.get("lc_id")    or getattr(settings, "LC_ID", None)

        engine = SyncEngine(gql_email=email, gql_password=password, lc_id=lc_id)
        try:
            dashboard = engine.run_full_sync()
            return JsonResponse({"status": "success", "dashboard": dashboard})
        except Exception as exc:
            logger.error("Sync failed: %s", exc)
            return JsonResponse({"status": "error", "message": str(exc)}, status=500)


class SyncStatusView(View):
    def get(self, request):
        logs = SyncLog.objects.order_by("-started_at")[:20]
        data = [{
            "id": l.id, "source": l.source, "status": l.status,
            "records_fetched": l.records_fetched, "records_saved": l.records_saved,
            "error_message": l.error_message,
            "started_at": l.started_at.isoformat(),
            "finished_at": l.finished_at.isoformat() if l.finished_at else None,
        } for l in logs]
        return JsonResponse({"sync_logs": data})


class ContractsListView(View):
    def get(self, request):
        qs = ContractData.objects.all()[:100]
        data = [{
            "contract_id": c.contract_id, "company_name": c.company_name,
            "product": c.product, "total_slots": c.total_slots,
            "fulfilled_slots": c.fulfilled_slots, "status": c.status,
            "updated_at": c.updated_at.isoformat(),
        } for c in qs]
        return JsonResponse({"contracts": data, "count": len(data)})


class OOSListView(View):
    def get(self, request):
        qs = OOSEntry.objects.all()[:200]
        data = [{
            "row_index": e.row_index, "entity": e.entity, "company": e.company,
            "product": e.product, "slots_contracted": e.slots_contracted,
            "slots_fulfilled": e.slots_fulfilled, "status": e.status,
        } for e in qs]
        return JsonResponse({"oos_entries": data, "count": len(data)})
