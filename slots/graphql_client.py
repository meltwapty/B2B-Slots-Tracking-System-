"""
GraphQL Client for AIESEC Contracts API
Fetches slot data (total + fulfilled) for B2B tracking.
"""
import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# ── GraphQL endpoint (AIESEC expa API) ─────────────────────────────────────
GRAPHQL_URL = getattr(settings, "GRAPHQL_URL", "https://gis-api.aiesec.org/graphql")
AUTH_URL     = getattr(settings, "AUTH_URL",     "https://auth.aiesec.org/oauth/token")


# ── QUERIES ─────────────────────────────────────────────────────────────────

GET_TOKEN_QUERY = """
mutation Login($email: String!, $password: String!) {
  loginUser(email: $email, password: $password) {
    token
    person { id full_name }
  }
}
"""

# Fetch all B2B opportunities with slot counts for a given LC/MC
GET_OPPORTUNITIES_QUERY = """
query GetOpportunities($filters: OpportunityFilter, $pagination: Pagination) {
  opportunities(filters: $filters, pagination: $pagination) {
    data {
      id
      title
      status
      slots_count
      applications_close_date
      openings
      office { id name }
      programme { id short_name_display }
      organisation { id name }
      home_lc { id name }
      home_mc { id name }
      meta {
        total_applicants
        total_approved_tn_managers
        total_realized
      }
    }
    paging { total_items current_page total_pages }
  }
}
"""

# Fetch individual opportunity detail (for precise slot breakdown)
GET_OPPORTUNITY_DETAIL_QUERY = """
query GetOpportunityDetail($id: ID!) {
  opportunity(id: $id) {
    id
    title
    status
    slots_count
    openings
    organisation { id name }
    programme { id short_name_display }
    office { id name }
    meta {
      total_applicants
      total_approved_tn_managers
      total_realized
      total_remote_realized
    }
    applications(pagination: { per_page: 200, page: 1 }) {
      data {
        id
        status
        person { id full_name }
        created_at
      }
    }
  }
}
"""


class GraphQLClient:
    """Handles authentication + querying against the AIESEC GIS GraphQL API."""

    def __init__(self):
        self.url   = GRAPHQL_URL
        self.token = None
        self.session = requests.Session()

    # ── Auth ─────────────────────────────────────────────────────────────────

    def authenticate(self, email: str, password: str) -> bool:
        """
        Obtain a bearer token via the loginUser mutation.
        Stores token in self.token for subsequent requests.
        """
        payload = {
            "query": GET_TOKEN_QUERY,
            "variables": {"email": email, "password": password},
        }
        try:
            resp = self.session.post(self.url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                logger.error("GraphQL auth error: %s", data["errors"])
                return False
            self.token = data["data"]["loginUser"]["token"]
            logger.info("GraphQL: authenticated successfully.")
            return True
        except requests.RequestException as exc:
            logger.error("GraphQL auth request failed: %s", exc)
            return False

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    # ── Generic query executor ────────────────────────────────────────────────

    def execute(self, query: str, variables: dict = None) -> dict:
        payload = {"query": query, "variables": variables or {}}
        try:
            resp = self.session.post(
                self.url, json=payload, headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            result = resp.json()
            if "errors" in result:
                logger.warning("GraphQL errors: %s", result["errors"])
            return result.get("data", {})
        except requests.RequestException as exc:
            logger.error("GraphQL execute failed: %s", exc)
            return {}

    # ── Domain helpers ────────────────────────────────────────────────────────

    def fetch_opportunities(self, lc_id: int = None, page: int = 1, per_page: int = 50) -> list:
        """Return a list of opportunity dicts with slot info."""
        filters = {"status": ["open", "finished", "realized"]}
        if lc_id:
            filters["home_lc"] = [lc_id]

        data = self.execute(
            GET_OPPORTUNITIES_QUERY,
            {"filters": filters, "pagination": {"page": page, "per_page": per_page}},
        )
        return data.get("opportunities", {}).get("data", [])

    def fetch_opportunity_detail(self, opportunity_id: str) -> dict:
        """Return full detail of a single opportunity including applications."""
        data = self.execute(GET_OPPORTUNITY_DETAIL_QUERY, {"id": opportunity_id})
        return data.get("opportunity", {})

    def fetch_all_opportunities(self, lc_id: int = None) -> list:
        """Paginate through all pages and return a combined list."""
        all_ops = []
        page = 1
        while True:
            ops = self.fetch_opportunities(lc_id=lc_id, page=page, per_page=50)
            if not ops:
                break
            all_ops.extend(ops)
            page += 1
            if len(ops) < 50:   # last page
                break
        logger.info("GraphQL: fetched %d opportunities total.", len(all_ops))
        return all_ops


# ── Slot extraction helpers ──────────────────────────────────────────────────

def extract_slot_counts(opportunity: dict) -> dict:
    """
    Given a raw opportunity dict from GraphQL, return:
      { total_slots, fulfilled_slots, status, product, company, contract_id }
    """
    meta = opportunity.get("meta") or {}
    programme = opportunity.get("programme") or {}
    org = opportunity.get("organisation") or {}
    office = opportunity.get("office") or {}

    total     = opportunity.get("slots_count") or opportunity.get("openings") or 0
    fulfilled = meta.get("total_realized") or 0

    return {
        "contract_id":     str(opportunity.get("id", "")),
        "company_name":    org.get("name", ""),
        "opportunity_id":  str(opportunity.get("id", "")),
        "product":         programme.get("short_name_display", ""),
        "total_slots":     int(total),
        "fulfilled_slots": int(fulfilled),
        "status":          opportunity.get("status", ""),
        "raw_data":        opportunity,
    }
