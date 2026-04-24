"""
Data Sync Engine
Orchestrates: GraphQL fetch → OOS fetch → normalize → compute → persist → push to Sheets
"""
import logging
from django.utils import timezone

from .graphql_client import GraphQLClient, extract_slot_counts
from .sheets_client  import GoogleSheetsClient, read_oos_sheet
from .fulfilment     import aggregate_graphql, aggregate_sheets, combine_sources, build_dashboard_payload
from .models         import ContractData, OOSEntry, FulfilmentMetrics, SyncLog

logger = logging.getLogger(__name__)


class SyncEngine:

    def __init__(self, gql_email: str = None, gql_password: str = None, lc_id: int = None):
        self.gql_email    = gql_email
        self.gql_password = gql_password
        self.lc_id        = lc_id

    # ── Full sync ─────────────────────────────────────────────────────────────

    def run_full_sync(self) -> dict:
        """
        1. Sync GraphQL contracts
        2. Sync Google Sheets OOS entries
        3. Compute combined fulfilment metrics
        4. Persist FulfilmentMetrics record
        5. Push summary back to Sheets
        Returns the final dashboard payload.
        """
        gql_log    = self._sync_graphql()
        sheets_log = self._sync_sheets()
        dashboard  = self._compute_and_persist()
        self._push_to_sheets(dashboard)
        return dashboard

    # ── Step 1: GraphQL sync ──────────────────────────────────────────────────

    def _sync_graphql(self) -> SyncLog:
        log = SyncLog.objects.create(source="graphql")
        try:
            client = GraphQLClient()
            if self.gql_email and self.gql_password:
                ok = client.authenticate(self.gql_email, self.gql_password)
                if not ok:
                    log.status = "failed"
                    log.error_message = "Authentication failed"
                    log.finished_at = timezone.now()
                    log.save()
                    return log

            opportunities = client.fetch_all_opportunities(lc_id=self.lc_id)
            log.records_fetched = len(opportunities)
            saved = 0
            for opp in opportunities:
                slot_data = extract_slot_counts(opp)
                _, created = ContractData.objects.update_or_create(
                    contract_id=slot_data["contract_id"],
                    defaults=slot_data,
                )
                saved += 1

            log.records_saved = saved
            log.status = "success"
            logger.info("GraphQL sync: %d saved", saved)
        except Exception as exc:
            log.status = "failed"
            log.error_message = str(exc)
            logger.error("GraphQL sync error: %s", exc)
        finally:
            log.finished_at = timezone.now()
            log.save()
        return log

    # ── Step 2: Sheets sync ───────────────────────────────────────────────────

    def _sync_sheets(self) -> SyncLog:
        log = SyncLog.objects.create(source="sheets")
        try:
            entries = read_oos_sheet()
            log.records_fetched = len(entries)

            # Clear existing OOS entries before re-inserting
            OOSEntry.objects.all().delete()
            saved = 0
            for entry in entries:
                OOSEntry.objects.create(**entry)
                saved += 1

            log.records_saved = saved
            log.status = "success"
            logger.info("Sheets sync: %d saved", saved)
        except Exception as exc:
            log.status = "failed"
            log.error_message = str(exc)
            logger.error("Sheets sync error: %s", exc)
        finally:
            log.finished_at = timezone.now()
            log.save()
        return log

    # ── Step 3: Compute & persist metrics ─────────────────────────────────────

    def _compute_and_persist(self) -> dict:
        contracts = list(ContractData.objects.all())
        oos       = list(OOSEntry.objects.all())

        graphql_agg = aggregate_graphql(contracts)
        sheets_agg  = aggregate_sheets(oos)
        combined    = combine_sources(graphql_agg, sheets_agg)
        dashboard   = build_dashboard_payload(combined, graphql_agg, sheets_agg)

        # Persist to DB
        FulfilmentMetrics.objects.create(
            period="all_time",
            source="combined",
            total_slots=combined["total_slots"],
            fulfilled_slots=combined["fulfilled_slots"],
            product_breakdown=combined["product_breakdown"],
        )
        FulfilmentMetrics.objects.create(
            period="all_time",
            source="graphql",
            total_slots=graphql_agg["total_slots"],
            fulfilled_slots=graphql_agg["fulfilled_slots"],
            product_breakdown=graphql_agg["product_breakdown"],
        )
        FulfilmentMetrics.objects.create(
            period="all_time",
            source="sheets",
            total_slots=sheets_agg["total_slots"],
            fulfilled_slots=sheets_agg["fulfilled_slots"],
            product_breakdown=sheets_agg["product_breakdown"],
        )
        return dashboard

    # ── Step 4: Push back to Sheets ───────────────────────────────────────────

    def _push_to_sheets(self, dashboard: dict):
        client = GoogleSheetsClient()
        summary = dashboard.get("summary", {})
        payload = {
            "total_slots":     summary.get("total_slots", 0),
            "fulfilled_slots": summary.get("fulfilled_slots", 0),
            "fulfilment_pct":  summary.get("fulfilment_pct", 0),
            "by_product":      dashboard.get("by_product", {}),
            "synced_at":       timezone.now().isoformat(),
        }
        client.push_fulfilment_summary(payload)
