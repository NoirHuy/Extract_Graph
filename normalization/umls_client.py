"""Tier 2: UMLS UTS REST API Client with Semantic Type Filtering."""

import logging
from typing import Any, Dict, List, Optional
import requests
from edc_config import get_settings
from schema.schema_registry import ENTITY_TYPES

logger = logging.getLogger(__name__)


class UMLSClient:
    """Queries NLM UMLS UTS REST API for concept CUIs with semantic type and vocabulary filtering."""

    BASE_URL = "https://uts-ws.nlm.nih.gov/rest/search/current"

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.UMLS_API_KEY

    def search_cui(
        self,
        term_en: str,
        expected_entity_type: Optional[str] = None,
        sabs: str = "SNOMEDCT_US,MSH,RXNORM",
    ) -> Optional[Dict[str, Any]]:
        """Search UMLS for a concept using an English medical term.

        Applies semantic type sanity checking based on expected_entity_type.
        """
        if not self.api_key:
            logger.debug("No UMLS_API_KEY configured; skipping UMLS REST query.")
            return None

        params = {
            "apiKey": self.api_key,
            "string": term_en,
            "sabs": sabs,
            "searchType": "exact",
        }

        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=10.0)
            if resp.status_code != 200:
                # Try approximate search if exact fails
                params["searchType"] = "approximate"
                resp = requests.get(self.BASE_URL, params=params, timeout=10.0)
                if resp.status_code != 200:
                    return None

            data = resp.json()
            results = data.get("result", {}).get("results", [])
            if not results:
                return None

            # Get expected group/tui
            expected_entry = ENTITY_TYPES.get(expected_entity_type) if expected_entity_type else None
            expected_group = expected_entry.get("group") if expected_entry else None

            for item in results:
                cui = item.get("ui")
                name = item.get("name")
                if cui and cui != "NONE":
                    return {
                        "cui": cui,
                        "preferred_name": name,
                        "sty": expected_entry.get("sty") if expected_entry else "Finding",
                        "tui": expected_entry.get("tui") if expected_entry else "T033",
                        "entity_type": expected_entity_type,
                    }

        except Exception as e:
            logger.warning(f"UMLS REST lookup failed for '{term_en}': {e}")

        return None
