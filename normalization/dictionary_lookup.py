"""Tier 1: Curated Bilingual Medical Dictionary Cache."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class DictionaryLookup:
    """Provides high-speed local lookup from curated Vietnamese-English medical CUI dictionary."""

    def __init__(self, dict_path: Optional[str] = None):
        if dict_path is None:
            dict_path = str(Path(__file__).parent.parent / "data" / "dict" / "medical_vi_en_cui.json")
        self.dict_path = Path(dict_path)
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if not self.dict_path.exists():
            logger.warning(f"Medical dictionary file not found at {self.dict_path}")
            return
        try:
            with open(self.dict_path, "r", encoding="utf-8") as f:
                raw_dict = json.load(f)
                # Store lowercase normalized keys
                self._entries = {k.strip().lower(): v for k, v in raw_dict.items()}
        except Exception as e:
            logger.error(f"Failed to load dictionary from {self.dict_path}: {e}")

    def lookup(self, term: str) -> Optional[Dict[str, Any]]:
        """Lookup a clinical term (Vietnamese or English)."""
        clean_key = term.strip().lower()
        if clean_key in self._entries:
            return self._entries[clean_key]
        return None

    def add_entry(self, vi_term: str, en_term: str, cui: str, tui: str, entity_type: str):
        """Add and cache a new resolved entry."""
        clean_key = vi_term.strip().lower()
        entry = {"en": en_term, "cui": cui, "tui": tui, "entity_type": entity_type}
        self._entries[clean_key] = entry
        # Save back to file
        try:
            with open(self.dict_path, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Could not persist new dictionary entry: {e}")
