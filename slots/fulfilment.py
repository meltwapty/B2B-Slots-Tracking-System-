"""
Fulfilment Rate Calculation Engine
Core formula: Fulfilment Rate = fulfilled_slots / total_slots
"""
from collections import defaultdict
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def safe_rate(fulfilled: int, total: int) -> float:
    """Return fulfilment rate as a float between 0 and 1. Avoids ZeroDivisionError."""
    if total <= 0:
        return 0.0
    return round(min(fulfilled / total, 1.0), 4)


def compute_fulfilment(total_slots: int, fulfilled_slots: int) -> dict:
    """
    Compute fulfilment metrics for a single record set.
    Returns:
        total_slots      : int
        fulfilled_slots  : int
        fulfilment_rate  : float (0–1)
        fulfilment_pct   : float (0–100)
        gap              : int  (slots still needed to reach 100%)
    """
    rate = safe_rate(fulfilled_slots, total_slots)
    return {
        "total_slots":     total_slots,
        "fulfilled_slots": fulfilled_slots,
        "fulfilment_rate": rate,
        "fulfilment_pct":  round(rate * 100, 2),
        "gap":             max(total_slots - fulfilled_slots, 0),
    }


def aggregate_graphql(contracts: list) -> dict:
    """
    Aggregate slot counts from a list of ContractData ORM objects.
    Returns combined fulfilment dict + per-product breakdown.
    """
    total = fulfilled = 0
    by_product = defaultdict(lambda: {"total": 0, "fulfilled": 0})

    for c in contracts:
        total     += c.total_slots
        fulfilled += c.fulfilled_slots
        prod = c.product or "Unknown"
        by_product[prod]["total"]     += c.total_slots
        by_product[prod]["fulfilled"] += c.fulfilled_slots

    breakdown = {
        prod: {**compute_fulfilment(v["total"], v["fulfilled"]), "product": prod}
        for prod, v in by_product.items()
    }

    return {
        **compute_fulfilment(total, fulfilled),
        "source": "graphql",
        "product_breakdown": breakdown,
    }


def aggregate_sheets(entries: list) -> dict:
    """
    Aggregate slot counts from a list of OOSEntry ORM objects.
    """
    total = fulfilled = 0
    by_product = defaultdict(lambda: {"total": 0, "fulfilled": 0})

    for e in entries:
        total     += e.slots_contracted
        fulfilled += e.slots_fulfilled
        prod = e.product or "Unknown"
        by_product[prod]["total"]     += e.slots_contracted
        by_product[prod]["fulfilled"] += e.slots_fulfilled

    breakdown = {
        prod: {**compute_fulfilment(v["total"], v["fulfilled"]), "product": prod}
        for prod, v in by_product.items()
    }

    return {
        **compute_fulfilment(total, fulfilled),
        "source": "sheets",
        "product_breakdown": breakdown,
    }


def combine_sources(graphql_agg: dict, sheets_agg: dict) -> dict:
    """
    Merge aggregated data from GraphQL + Google Sheets into one combined summary.
    De-duplicates by summing (assumes separate populations; adjust if overlap exists).
    """
    total     = graphql_agg["total_slots"]     + sheets_agg["total_slots"]
    fulfilled = graphql_agg["fulfilled_slots"]  + sheets_agg["fulfilled_slots"]

    # Merge product breakdowns
    all_products = set(graphql_agg["product_breakdown"]) | set(sheets_agg["product_breakdown"])
    combined_breakdown = {}
    for prod in all_products:
        g = graphql_agg["product_breakdown"].get(prod, {"total_slots": 0, "fulfilled_slots": 0})
        s = sheets_agg["product_breakdown"].get(prod,  {"total_slots": 0, "fulfilled_slots": 0})
        t = g["total_slots"]     + s["total_slots"]
        f = g["fulfilled_slots"] + s["fulfilled_slots"]
        combined_breakdown[prod] = {**compute_fulfilment(t, f), "product": prod}

    return {
        **compute_fulfilment(total, fulfilled),
        "source": "combined",
        "graphql_total":     graphql_agg["total_slots"],
        "graphql_fulfilled": graphql_agg["fulfilled_slots"],
        "sheets_total":      sheets_agg["total_slots"],
        "sheets_fulfilled":  sheets_agg["fulfilled_slots"],
        "product_breakdown": combined_breakdown,
    }


def aggregate_lc_breakdown(sheets_entries: list) -> list:
    """
    Aggregate slot counts per LC (Entity) from OOSEntry.
    Returns a sorted list of LC dicts.
    """
    lcs = defaultdict(lambda: {"total_slots": 0, "fulfilled_slots": 0, "products": set()})

    for e in sheets_entries:
        if not e.entity: 
            continue
        entity = e.entity.strip()
        lcs[entity]["total_slots"] += e.slots_contracted
        lcs[entity]["fulfilled_slots"] += e.slots_fulfilled
        if e.product:
            lcs[entity]["products"].add(e.product.upper())
            
    breakdown = []
    for lc_name, stats in lcs.items():
        computed = compute_fulfilment(stats["total_slots"], stats["fulfilled_slots"])
        breakdown.append({
            "lc_name": lc_name,
            "products": sorted(list(stats["products"])),
            **computed
        })

    # Sort by descending total slots
    breakdown.sort(key=lambda x: x["total_slots"], reverse=True)
    return breakdown


def aggregate_lc_breakdown_product(sheets_entries: list, product: str) -> list:
    """
    Aggregate slot counts per LC (Entity) from OOSEntry for a specific product.
    Returns a sorted list of LC dicts.
    """
    from collections import defaultdict
    lcs = defaultdict(lambda: {"total_slots": 0, "fulfilled_slots": 0})
    for e in sheets_entries:
        if not e.entity or not e.product: 
            continue
        if e.product.upper() != product.upper():
            continue
        entity = e.entity.strip()
        lcs[entity]["total_slots"] += e.slots_contracted
        lcs[entity]["fulfilled_slots"] += e.slots_fulfilled
            
    breakdown = []
    for lc_name, stats in lcs.items():
        computed = compute_fulfilment(stats["total_slots"], stats["fulfilled_slots"])
        breakdown.append({
            "lc_name": lc_name,
            **computed
        })

    # Sort by descending total slots
    breakdown.sort(key=lambda x: x["total_slots"], reverse=True)
    return breakdown


def build_dashboard_payload(combined: dict, graphql: dict, sheets: dict, lc_breakdown: list = None) -> dict:
    """
    Assemble the final dashboard JSON payload.
    """
    payload = {
        "summary": {
            "total_slots":      combined["total_slots"],
            "fulfilled_slots":  combined["fulfilled_slots"],
            "fulfilment_rate":  combined["fulfilment_rate"],
            "fulfilment_pct":   combined["fulfilment_pct"],
            "gap":              combined["gap"],
        },
        "by_source": {
            "graphql": {
                "total_slots":     graphql["total_slots"],
                "fulfilled_slots": graphql["fulfilled_slots"],
                "fulfilment_pct":  graphql["fulfilment_pct"],
            },
            "sheets": {
                "total_slots":     sheets["total_slots"],
                "fulfilled_slots": sheets["fulfilled_slots"],
                "fulfilment_pct":  sheets["fulfilment_pct"],
            },
        },
        "by_product": combined["product_breakdown"],
    }
    
    if lc_breakdown is not None:
        payload["lc_breakdown"] = lc_breakdown
        
    return payload
