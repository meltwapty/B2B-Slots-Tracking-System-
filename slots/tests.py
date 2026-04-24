"""
Unit tests for the fulfilment calculation engine and data parsers.
Run with: python manage.py test slots
"""
from django.test import TestCase, Client
from django.urls import reverse
import json

from .models import ContractData, OOSEntry, FulfilmentMetrics
from .fulfilment import (
    safe_rate, compute_fulfilment, aggregate_graphql,
    aggregate_sheets, combine_sources
)
from .sheets_client import GoogleSheetsClient


# ── Fulfilment engine tests ──────────────────────────────────────────────────

class FulfilmentCalcTests(TestCase):

    def test_safe_rate_normal(self):
        self.assertAlmostEqual(safe_rate(75, 100), 0.75)

    def test_safe_rate_zero_total(self):
        self.assertEqual(safe_rate(0, 0), 0.0)

    def test_safe_rate_capped_at_1(self):
        # fulfilled > total should not exceed 100%
        self.assertEqual(safe_rate(120, 100), 1.0)

    def test_compute_fulfilment_gap(self):
        result = compute_fulfilment(100, 60)
        self.assertEqual(result["gap"], 40)
        self.assertEqual(result["fulfilment_pct"], 60.0)

    def test_compute_fulfilment_zero(self):
        result = compute_fulfilment(0, 0)
        self.assertEqual(result["fulfilment_rate"], 0.0)
        self.assertEqual(result["gap"], 0)

    def test_aggregate_graphql(self):
        ContractData.objects.create(contract_id="c1", product="IGT", total_slots=50, fulfilled_slots=30)
        ContractData.objects.create(contract_id="c2", product="OGT", total_slots=40, fulfilled_slots=20)
        agg = aggregate_graphql(list(ContractData.objects.all()))
        self.assertEqual(agg["total_slots"], 90)
        self.assertEqual(agg["fulfilled_slots"], 50)
        self.assertIn("IGT", agg["product_breakdown"])
        self.assertIn("OGT", agg["product_breakdown"])

    def test_aggregate_sheets(self):
        OOSEntry.objects.create(row_index=1, product="IGV", slots_contracted=20, slots_fulfilled=15)
        OOSEntry.objects.create(row_index=2, product="IGV", slots_contracted=10, slots_fulfilled=5)
        agg = aggregate_sheets(list(OOSEntry.objects.all()))
        self.assertEqual(agg["total_slots"], 30)
        self.assertEqual(agg["fulfilled_slots"], 20)

    def test_combine_sources(self):
        gql = {"total_slots": 90, "fulfilled_slots": 50, "fulfilment_pct": 55.56,
               "fulfilment_rate": 0.5556, "gap": 40, "product_breakdown": {
                   "IGT": {"total_slots": 50, "fulfilled_slots": 30, "fulfilment_pct": 60.0,
                           "fulfilment_rate": 0.6, "gap": 20, "product": "IGT"}}}
        sht = {"total_slots": 30, "fulfilled_slots": 20, "fulfilment_pct": 66.67,
               "fulfilment_rate": 0.6667, "gap": 10, "product_breakdown": {
                   "IGV": {"total_slots": 30, "fulfilled_slots": 20, "fulfilment_pct": 66.67,
                           "fulfilment_rate": 0.6667, "gap": 10, "product": "IGV"}}}
        combined = combine_sources(gql, sht)
        self.assertEqual(combined["total_slots"], 120)
        self.assertEqual(combined["fulfilled_slots"], 70)
        self.assertAlmostEqual(combined["fulfilment_rate"], 0.5833, places=3)


# ── Model tests ──────────────────────────────────────────────────────────────

class FulfilmentMetricsModelTests(TestCase):

    def test_rate_auto_computed_on_save(self):
        m = FulfilmentMetrics.objects.create(
            total_slots=200, fulfilled_slots=150, source="combined"
        )
        self.assertAlmostEqual(float(m.fulfilment_rate), 0.75)
        self.assertEqual(m.fulfilment_rate_percent, 75.0)

    def test_rate_zero_when_no_total(self):
        m = FulfilmentMetrics.objects.create(total_slots=0, fulfilled_slots=0)
        self.assertEqual(float(m.fulfilment_rate), 0.0)


# ── Sheets CSV parser tests ───────────────────────────────────────────────────

class SheetParserTests(TestCase):

    def test_parse_rows_skips_header(self):
        client = GoogleSheetsClient()
        rows = [
            ["Entity", "Company", "Product", "Total", "Fulfilled", "Status", "Notes"],
            ["LC Cairo", "Acme Corp", "IGT", "10", "7", "Open", ""],
            ["LC Cairo", "Beta Ltd",  "OGT", "5",  "5", "Closed", "Done"],
        ]
        entries = client.parse_rows(rows)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["slots_contracted"], 10)
        self.assertEqual(entries[1]["slots_fulfilled"], 5)

    def test_parse_rows_handles_empty_rows(self):
        client = GoogleSheetsClient()
        rows = [
            ["Entity", "Company", "Product", "Total", "Fulfilled", "Status", "Notes"],
            [],
            ["LC Cairo", "Acme", "IGT", "10", "6", "Open", ""],
        ]
        entries = client.parse_rows(rows)
        self.assertEqual(len(entries), 1)

    def test_to_int_handles_non_numeric(self):
        self.assertEqual(GoogleSheetsClient._to_int("N/A"), 0)
        self.assertEqual(GoogleSheetsClient._to_int("15 slots"), 15)
        self.assertEqual(GoogleSheetsClient._to_int(""), 0)


# ── API endpoint tests ────────────────────────────────────────────────────────

class APITests(TestCase):

    def setUp(self):
        self.client = Client()
        ContractData.objects.create(contract_id="x1", product="IGT", total_slots=100, fulfilled_slots=70)
        OOSEntry.objects.create(row_index=1, product="IGV", slots_contracted=50, slots_fulfilled=30)

    def test_dashboard_api_returns_200(self):
        resp = self.client.get("/api/dashboard/")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn("summary", data)
        self.assertIn("by_source", data)

    def test_dashboard_summary_keys(self):
        resp = self.client.get("/api/dashboard/")
        data = json.loads(resp.content)
        summary = data["summary"]
        for key in ["total_slots", "fulfilled_slots", "fulfilment_rate", "fulfilment_pct", "gap"]:
            self.assertIn(key, summary)

    def test_contracts_api(self):
        resp = self.client.get("/api/contracts/")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["count"], 1)

    def test_oos_api(self):
        resp = self.client.get("/api/oos/")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["count"], 1)

    def test_sync_status_api(self):
        resp = self.client.get("/api/sync/status/")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn("sync_logs", data)
