"""
Google Sheets Integration
- Read OOS data from the provided sheet
- Push processed fulfilment metrics back via Apps Script webhook
"""
import logging
import re
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# ─── Sheet config ────────────────────────────────────────────────────────────
OOS_SHEET_ID  = getattr(settings, "OOS_SHEET_ID",  "1U_Z2MXcZ_vDUKNGbPDNOhnl6nwcPiRdaUZlY3xhbfqw")
OOS_SHEET_GID = getattr(settings, "OOS_SHEET_GID", "2082291020")
OOS_SHEET_NAME = getattr(settings, "OOS_SHEET_NAME", "Sheet1")   # update if tab name differs

# Apps Script Web App URL (deploy your doPost script and paste the URL here)
APPS_SCRIPT_PUSH_URL = getattr(settings, "APPS_SCRIPT_PUSH_URL", "")


# ─── Column mapping (0-indexed) ───────────────────────────────────────────────
# Adjust these indices to match the actual OOS sheet columns
COLUMN_MAP = {
    "entity":            1,   # Column B (LC Name)
    "slots_contracted":  2,   # Column C (Total Slots)
    "slots_fulfilled":   3,   # Column D (Fulfilled Slots)
}


class GoogleSheetsClient:
    """
    Reads the OOS Google Sheet via the public CSV export URL (no auth needed
    for public sheets).  For private sheets, swap to gspread + service account.
    """

    def __init__(self):
        self.sheet_id  = OOS_SHEET_ID
        self.sheet_gid = OOS_SHEET_GID

    # ── Public CSV export (works if sheet is shared as "anyone with link") ───

    def _csv_url(self, sheet_name: str) -> str:
        return (
            f"https://docs.google.com/spreadsheets/d/{self.sheet_id}"
            f"/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        )

    def fetch_raw_rows(self) -> list[tuple[str, list[list[str]]]]:
        """Download multiple sheet tabs as CSV and return list of (tab_name, rows)."""
        import csv, io
        all_data = []
        for tab in ["IGT", "IGV"]:
            url = self._csv_url(tab)
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                reader = csv.reader(io.StringIO(resp.text))
                rows = list(reader)
                all_data.append((tab, rows))
                logger.info("Sheets: fetched %d rows from %s tab.", len(rows), tab)
            except requests.RequestException as exc:
                logger.error("Sheets fetch failed for %s: %s", tab, exc)
        return all_data

    # ── Parse rows into structured dicts ─────────────────────────────────────

    def parse_rows(self, tabs_data: list[tuple[str, list]]) -> list[dict]:
        """
        Skip the header row, convert each data row into a structured dict.
        Returns list of clean entry dicts.
        """
        entries = []
        for tab_name, rows in tabs_data:
            if not rows:
                continue

            # Detect header row (first row) and skip it
            data_rows = rows[1:]

            for idx, row in enumerate(data_rows, start=2):  # 1-indexed, row 1 = header
                if not any(row):   # skip empty rows
                    continue
                entry = self._row_to_dict(idx, row, tab_name)
                if entry:
                    entries.append(entry)

        logger.info("Sheets: parsed %d valid entries.", len(entries))
        return entries

    def _row_to_dict(self, row_index: int, row: list, tab_name: str) -> dict | None:
        def get(col_key):
            idx = COLUMN_MAP.get(col_key, -1)
            if idx < 0 or idx >= len(row):
                return ""
            return row[idx].strip()

        try:
            total_raw     = get("slots_contracted")
            fulfilled_raw = get("slots_fulfilled")
            total     = self._to_int(total_raw)
            fulfilled = self._to_int(fulfilled_raw)
        except Exception:
            total = fulfilled = 0

        entity = get("entity").strip()
        if not entity:
            return None

        return {
            "row_index":        row_index,
            "entity":           entity,
            "company":          "",
            "product":          tab_name,
            "slots_contracted": total,
            "slots_fulfilled":  fulfilled,
            "status":           "",
            "notes":            "",
            "sheet_id":         self.sheet_id,
            "raw_row":          row,
        }

    @staticmethod
    def _to_int(value: str) -> int:
        if not value:
            return 0
        cleaned = re.sub(r"[^\d]", "", str(value))
        return int(cleaned) if cleaned else 0

    # ── Push fulfilment summary back to Google Sheets via Apps Script ─────────

    def push_fulfilment_summary(self, summary: dict) -> bool:
        """
        POST the computed fulfilment summary to the Apps Script Web App.
        The Apps Script will write results into a designated summary tab.
        """
        if not APPS_SCRIPT_PUSH_URL:
            logger.warning("APPS_SCRIPT_PUSH_URL not configured — skipping push.")
            return False
        try:
            resp = requests.post(APPS_SCRIPT_PUSH_URL, json=summary, timeout=30)
            resp.raise_for_status()
            logger.info("Sheets: pushed fulfilment summary successfully.")
            return True
        except requests.RequestException as exc:
            logger.error("Sheets push failed: %s", exc)
            return False


# ─── Convenience function ─────────────────────────────────────────────────────

def read_oos_sheet() -> list[dict]:
    client = GoogleSheetsClient()
    rows   = client.fetch_raw_rows()
    return client.parse_rows(rows)


def fetch_project_data() -> dict:
    """
    Fetch and parse the per-LC project breakdown from the specific Google Sheet.
    Returns a dict keyed by LC Name, containing a list of projects with their slot counts.
    """
    import csv, io
    from collections import defaultdict

    # Hardcoded URL and GID from the user's requirements
    url = "https://docs.google.com/spreadsheets/d/1cWZl4-h9YT5TmhhVkfir1uC9TKbqX4PQFBf28vjg5yU/export?format=csv&gid=211400853"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
    except requests.RequestException as exc:
        logger.error("Failed to fetch project data: %s", exc)
        return {}

    # Structure: { "LC_Name": [ {"name": "SP", "product": "IGTe", "slots": 5}, ... ] }
    lc_data = defaultdict(list)

    # Helper to parse a block
    def parse_block(start_row_idx, end_row_idx, col_start_idx, col_end_idx, product_name):
        if start_row_idx - 1 >= len(rows):
            return
        # Project names are usually in start_row_idx - 1
        project_names = rows[start_row_idx - 1][col_start_idx:col_end_idx]
        
        for r_idx in range(start_row_idx, end_row_idx + 1):
            if r_idx >= len(rows):
                continue
            row = rows[r_idx]
            if not row or len(row) <= col_start_idx:
                continue
            
            lc_name = row[0].strip()
            if not lc_name:
                continue

            # Ensure LC exists in dict even if it has 0 slots
            if lc_name not in lc_data:
                lc_data[lc_name] = []

            for c_idx, p_name in enumerate(project_names):
                if not p_name.strip():
                    continue
                actual_col = col_start_idx + c_idx
                if actual_col < len(row):
                    slots_str = row[actual_col].strip()
                    try:
                        slots = int(slots_str) if slots_str else 0
                    except ValueError:
                        slots = 0
                    
                    if slots > 0:
                        lc_data[lc_name].append({
                            "name": p_name.strip(),
                            "product": product_name,
                            "slots": slots
                        })

    # IGTe: LC names A3:A17 (idx 2-16), Project names C2:I2 (row 1, col 2-8), Slots C3:I17
    parse_block(2, 16, 2, 9, "IGTe")
    
    # IGTa: LC names A22:A36 (idx 21-35), Project names C21:I21 (row 20, col 2-8), Slots C22:I36
    parse_block(21, 35, 2, 9, "IGTa")
    
    # IGV: LC names A41:A55 (idx 40-54), Project names C40:K40 (row 39, col 2-10), Slots C41:K55
    parse_block(40, 54, 2, 11, "IGV")

    return dict(lc_data)
