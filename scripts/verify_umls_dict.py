"""Verification & Anti-Hallucination Script for Bilingual Medical UMLS CUI Dictionary.

Validates and heals CUIs in medical_vi_en_cui.json using official NLM UMLS UTS REST Search API.
Uses English terms ("en") as the ground truth lookup key.
"""

import argparse
import json
import logging
import os
import shutil
import time
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from edc_config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

UMLS_SEARCH_URL = "https://uts-ws.nlm.nih.gov/rest/search/current"
UMLS_CONTENT_URL = "https://uts-ws.nlm.nih.gov/rest/content/current/CUI"


def search_umls_concept(
    term_en: str,
    api_key: str,
    sabs: str = "SNOMEDCT_US,MSH,RXNORM,MTH,NCI,ICD10CM",
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """Search UMLS for a concept using an English medical term with exact, words, and approximate fallback."""
    if not api_key:
        return None

    # 1. Try exact search
    search_strategies = ["exact", "words", "approximate"]
    for strategy in search_strategies:
        params = {
            "apiKey": api_key,
            "string": term_en,
            "sabs": sabs,
            "searchType": strategy,
        }
        try:
            resp = requests.get(UMLS_SEARCH_URL, params=params, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("result", {}).get("results", [])
                for item in results:
                    cui = item.get("ui")
                    if cui and cui != "NONE" and cui.startswith("C"):
                        return {
                            "cui": cui,
                            "preferred_name": item.get("name"),
                            "semantic_types": item.get("semanticTypes", []),
                            "match_strategy": strategy,
                        }
        except Exception as e:
            logger.debug(f"Error querying UMLS for '{term_en}' with strategy '{strategy}': {e}")
            continue

    return None


def fetch_concept_semantic_types(cui: str, api_key: str, timeout: float = 10.0) -> List[str]:
    """Retrieve detailed semantic types for a CUI from NLM UMLS UTS Content API."""
    if not api_key or not cui:
        return []
    url = f"{UMLS_CONTENT_URL}/{cui}"
    try:
        resp = requests.get(url, params={"apiKey": api_key}, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            stys = data.get("result", {}).get("semanticTypes", [])
            return [s.get("name") for s in stys if isinstance(s, dict) and s.get("name")]
    except Exception:
        pass
    return []


def verify_and_heal_dictionary(
    dict_path: str = "data/dict/medical_vi_en_cui.json",
    report_path: str = "data/dict/umls_verification_report.json",
    apply_fixes: bool = False,
    api_key: Optional[str] = None,
    delay_sec: float = 0.05,
) -> Dict[str, Any]:
    """Verify all CUIs in the bilingual dictionary against live NLM UMLS UTS Search API."""
    target_dict_path = Path(dict_path)
    if not target_dict_path.exists():
        raise FileNotFoundError(f"Dictionary file not found at: {target_dict_path}")

    settings = get_settings()
    active_key = api_key or settings.UMLS_API_KEY
    if not active_key:
        raise ValueError("UMLS_API_KEY is required to verify concepts against official NLM UMLS API.")

    with open(target_dict_path, "r", encoding="utf-8") as f:
        dictionary: Dict[str, Dict[str, Any]] = json.load(f)

    logger.info(f"Loaded {len(dictionary)} entries from {target_dict_path}. Starting live UMLS UTS verification...")

    results = []
    updated_dict = {}
    verified_matches = 0
    mismatches = 0
    not_found = 0

    for vi_term, data in dictionary.items():
        en_term = data.get("en", "").strip()
        existing_cui = data.get("cui", "")
        existing_tui = data.get("tui", "")
        entity_type = data.get("entity_type", "")

        if not en_term:
            logger.warning(f"Skipping entry with empty English term: '{vi_term}'")
            updated_dict[vi_term] = data
            continue

        concept = search_umls_concept(en_term, api_key=active_key)
        time.sleep(delay_sec)

        entry_record = {
            "vi_term": vi_term,
            "en_term": en_term,
            "existing_cui": existing_cui,
            "entity_type": entity_type,
            "existing_tui": existing_tui,
        }

        if concept:
            official_cui = concept["cui"]
            official_name = concept["preferred_name"]
            stys = concept["semantic_types"]

            entry_record["official_cui"] = official_cui
            entry_record["official_name"] = official_name
            entry_record["official_stys"] = stys
            entry_record["match_strategy"] = concept["match_strategy"]

            if existing_cui and existing_cui.upper() == official_cui.upper():
                entry_record["status"] = "VERIFIED_MATCH"
                verified_matches += 1
            else:
                entry_record["status"] = "MISMATCH_OR_HALLUCINATED"
                mismatches += 1

            new_entry = dict(data)
            new_entry["cui"] = official_cui
            if official_name:
                new_entry["umls_preferred_name"] = official_name
            updated_dict[vi_term] = new_entry
        else:
            entry_record["status"] = "NOT_FOUND_IN_UMLS"
            entry_record["official_cui"] = None
            not_found += 1
            updated_dict[vi_term] = data

        results.append(entry_record)

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dictionary_path": str(target_dict_path),
        "total_entries": len(dictionary),
        "verified_matches": verified_matches,
        "mismatched_cui_count": mismatches,
        "not_found_count": not_found,
        "verification_details": results,
    }

    # Save detailed JSON report
    report_target = Path(report_path)
    report_target.parent.mkdir(parents=True, exist_ok=True)
    with open(report_target, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved verification report to: {report_target}")

    # Apply fixes if requested
    if apply_fixes and mismatches > 0:
        backup_path = target_dict_path.with_name(f"{target_dict_path.stem}.backup.json")
        shutil.copy2(target_dict_path, backup_path)
        logger.info(f"Created backup of original dictionary at: {backup_path}")

        with open(target_dict_path, "w", encoding="utf-8") as f:
            json.dump(updated_dict, f, ensure_ascii=False, indent=2)
        logger.info(f"Updated dictionary saved to {target_dict_path} with {mismatches} fixed CUIs.")

    return report


def main():
    parser = argparse.ArgumentParser(description="Verify and heal medical dictionary against NLM UMLS UTS Search API")
    parser.add_argument("--dict-path", default="data/dict/medical_vi_en_cui.json", help="Path to dictionary JSON")
    parser.add_argument("--report-path", default="data/dict/umls_verification_report.json", help="Path to output JSON report")
    parser.add_argument("--apply-fixes", action="store_true", help="Apply official verified CUIs directly into dictionary")
    parser.add_argument("--api-key", default=None, help="UMLS API Key override")
    args = parser.parse_args()

    report = verify_and_heal_dictionary(
        dict_path=args.dict_path,
        report_path=args.report_path,
        apply_fixes=args.apply_fixes,
        api_key=args.api_key,
    )

    print("\n" + "=" * 70)
    print("  UMLS CUI DICTIONARY VERIFICATION REPORT")
    print("=" * 70)
    print(f"Total Dictionary Entries:  {report['total_entries']}")
    print(f"Verified Exact Matches:    {report['verified_matches']} ({report['verified_matches']/report['total_entries']*100:.1f}%)")
    print(f"Mismatched / Hallucinated: {report['mismatched_cui_count']}")
    print(f"Not Found in UMLS:         {report['not_found_count']}")
    print(f"Report File:               {args.report_path}")
    print("=" * 70)

    if report["mismatched_cui_count"] > 0:
        print("\nDiscrepancies found:")
        for r in report["verification_details"]:
            if r["status"] == "MISMATCH_OR_HALLUCINATED":
                print(f" - [{r['vi_term']}] ('{r['en_term']}'): Old CUI: {r['existing_cui']} -> Official CUI: {r['official_cui']} ({r.get('official_name')})")

    if args.apply_fixes:
        print("\n Applied verified official CUIs to dictionary successfully.")
    else:
        print("\n Run with '--apply-fixes' to automatically update dictionary with official CUIs.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
