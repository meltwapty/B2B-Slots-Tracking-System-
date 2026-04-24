"""
Management command: python manage.py sync_slots
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from slots.sync_engine import SyncEngine


class Command(BaseCommand):
    help = "Sync slot data from GraphQL + Google Sheets and recompute fulfilment metrics."

    def add_arguments(self, parser):
        parser.add_argument("--email",        type=str, default=None)
        parser.add_argument("--password",     type=str, default=None)
        parser.add_argument("--lc-id",        type=int, default=None)
        parser.add_argument("--sheets-only",  action="store_true")
        parser.add_argument("--graphql-only", action="store_true")

    def handle(self, *args, **options):
        email    = options["email"]    or getattr(settings, "GQL_EMAIL", None)
        password = options["password"] or getattr(settings, "GQL_PASSWORD", None)
        lc_id    = options["lc_id"]    or getattr(settings, "LC_ID", None)

        self.stdout.write(self.style.MIGRATE_HEADING("Starting B2B Slots Sync..."))
        engine = SyncEngine(gql_email=email, gql_password=password, lc_id=lc_id)

        if options["sheets_only"]:
            engine._sync_sheets()
            dashboard = engine._compute_and_persist()
        elif options["graphql_only"]:
            engine._sync_graphql()
            dashboard = engine._compute_and_persist()
        else:
            dashboard = engine.run_full_sync()

        s = dashboard.get("summary", {})
        self.stdout.write(self.style.SUCCESS("\n── Fulfilment Summary ──────────────────────"))
        self.stdout.write(f"  Total Slots     : {s.get('total_slots', 0)}")
        self.stdout.write(f"  Fulfilled Slots : {s.get('fulfilled_slots', 0)}")
        self.stdout.write(f"  Gap             : {s.get('gap', 0)}")
        self.stdout.write(self.style.SUCCESS(f"  Fulfilment Rate : {s.get('fulfilment_pct', 0)}%"))

        bp = dashboard.get("by_product", {})
        if bp:
            self.stdout.write("\n── By Product ──────────────────────────────")
            for prod, v in bp.items():
                self.stdout.write(f"  {prod:12s}  {v['fulfilled_slots']}/{v['total_slots']}  ({v['fulfilment_pct']}%)")

        self.stdout.write(self.style.SUCCESS("\nSync complete.\n"))
