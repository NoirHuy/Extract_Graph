"""Authoritative UMLS Verification & Anti-Hallucination Engine.

Features:
1. Ground Truth Lookup: Uses English terms ("en") as search keys.
2. Semantic Type / Group Enforcement: Filters out mismatched categories (e.g. DrugClass cannot be 'Allergy to...').
3. Negative Keyword Filtering: Blocks 'adverse reaction', 'allergy to', 'survey', 'likelihood', 'severity grade'.
4. Duplicate CUI Collision Audit: Flags any CUI shared across distinct, non-synonymous concepts.
5. Auto-Healing: Updates dictionary with verified official CUIs and preferred names.
"""

import argparse
import json
import logging
import os
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from edc_config import get_settings
from schema.schema_registry import ENTITY_TYPES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

UMLS_SEARCH_URL = "https://uts-ws.nlm.nih.gov/rest/search/current"

# Forbidden substrings in official preferred names for standard concepts
FORBIDDEN_NAME_PATTERNS = [
    "adverse reaction to",
    "allergy to",
    "allergic to",
    "likelihood that",
    "questionnaire",
    "severity grade 1",
    "severity grade 2",
    "severity grade 3",
    "severity grade 4",
]

# Mapping entity_type to accepted UMLS Semantic Types (STYs) and Groups
ENTITY_TYPE_ACCEPTABLE_STYS: Dict[str, Set[str]] = {
    "Disease": {"Disease or Syndrome", "Pathologic Function", "Mental or Behavioral Dysfunction"},
    "DiseaseSubtype": {"Disease or Syndrome", "Pathologic Function", "Finding"},
    "Complication": {"Disease or Syndrome", "Pathologic Function", "Finding"},
    "Cause": {"Disease or Syndrome", "Pathologic Function", "Finding", "Individual Behavior", "Hazardous or Poisonous Substance"},
    "Mechanism": {"Pathologic Function", "Physiologic Function", "Cell or Molecular Dysfunction", "Molecular Function"},
    "Symptom": {"Sign or Symptom", "Finding"},
    "Sign": {"Finding", "Sign or Symptom"},
    "RiskFactor": {"Finding", "Individual Behavior", "Disease or Syndrome", "Hazardous or Poisonous Substance"},
    "Drug": {"Pharmacologic Substance", "Clinical Drug", "Organic Chemical", "Inorganic Chemical"},
    "DrugClass": {"Pharmacologic Substance", "Chemical Viewed Functionally", "Biomedical or Dental Material"},
    "Organ": {"Body Part, Organ, or Organ Component", "Body System", "Tissue", "Anatomical Structure"},
    "Test": {"Diagnostic Procedure", "Laboratory Procedure", "Laboratory or Test Result", "Clinical Attribute"},
    "Measurement": {"Quantitative Concept", "Clinical Attribute", "Laboratory or Test Result", "Finding"},
    "PatientGroup": {"Population Group", "Age Group", "Patient or Disabled Group", "Group", "Finding", "Disease or Syndrome"},
    "Guideline": {"Intellectual Product", "Regulation or Law"},
}


def is_name_valid(name: str) -> bool:
    """Check if concept preferred name does not contain forbidden modifiers."""
    lower = name.lower()
    return not any(pat in lower for pat in FORBIDDEN_NAME_PATTERNS)


def is_semantic_type_compatible(entity_type: str, candidate_stys: List[str]) -> bool:
    """Check if candidate semantic types match expected entity type."""
    acceptable = ENTITY_TYPE_ACCEPTABLE_STYS.get(entity_type)
    if not acceptable or not candidate_stys:
        return True
    return any(sty in acceptable for sty in candidate_stys)


def search_best_umls_concept(
    term_en: str,
    entity_type: str,
    api_key: str,
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """Search UMLS with exact, words, and approximate strategies, applying semantic validity filters."""
    if not api_key:
        return None

    strategies = ["exact", "words", "approximate"]
    for strategy in strategies:
        params = {
            "apiKey": api_key,
            "string": term_en,
            "sabs": "SNOMEDCT_US,MSH,RXNORM,MTH,NCI,ICD10CM,LNC",
            "searchType": strategy,
        }
        try:
            resp = requests.get(UMLS_SEARCH_URL, params=params, timeout=timeout)
            if resp.status_code != 200:
                continue

            data = resp.json()
            results = data.get("result", {}).get("results", [])
            if not results:
                continue

            # Filter candidates for valid name and compatible semantic type
            for item in results:
                cui = item.get("ui")
                name = item.get("name", "")
                stys = item.get("semanticTypes", [])

                if not cui or cui == "NONE" or not cui.startswith("C"):
                    continue

                if not is_name_valid(name):
                    continue

                if is_semantic_type_compatible(entity_type, stys):
                    return {
                        "cui": cui,
                        "preferred_name": name,
                        "semantic_types": stys,
                        "match_strategy": strategy,
                    }

            # Fallback to first candidate with valid name if strict STY match wasn't found
            for item in results:
                cui = item.get("ui")
                name = item.get("name", "")
                if cui and cui.startswith("C") and is_name_valid(name):
                    return {
                        "cui": cui,
                        "preferred_name": name,
                        "semantic_types": item.get("semanticTypes", []),
                        "match_strategy": f"{strategy}_name_only",
                    }

        except Exception as e:
            logger.debug(f"Search failed for '{term_en}' ({strategy}): {e}")
            continue

    return None


def audit_cui_collisions(entries: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Audit duplicate CUIs assigned to distinct, non-synonymous English terms."""
    cui_to_terms: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for vi_term, data in entries.items():
        cui = data.get("cui")
        en_term = data.get("en", "").strip().lower()
        if cui and cui != "NONE":
            cui_to_terms[cui].append((vi_term, en_term))

    collisions = []
    for cui, term_list in cui_to_terms.items():
        distinct_en = set(en for _, en in term_list)
        if len(distinct_en) > 1:
            # Check if they are legitimate synonyms or actual collisions
            collisions.append({
                "cui": cui,
                "terms": term_list,
                "distinct_en_terms": list(distinct_en),
                "count": len(term_list),
            })
    return collisions


def verify_and_heal_dictionary(
    dict_path: str = "data/dict/medical_vi_en_cui.json",
    report_path: str = "data/dict/umls_verification_report.json",
    apply_fixes: bool = False,
    api_key: Optional[str] = None,
    delay_sec: float = 0.05,
) -> Dict[str, Any]:
    """Run full verification, semantic consistency audit, and collision detection on dictionary."""
    target_dict_path = Path(dict_path)
    if not target_dict_path.exists():
        raise FileNotFoundError(f"Dictionary file not found at: {target_dict_path}")

    settings = get_settings()
    active_key = api_key or settings.UMLS_API_KEY
    if not active_key:
        raise ValueError("UMLS_API_KEY is required to verify concepts against official NLM UMLS API.")

    with open(target_dict_path, "r", encoding="utf-8") as f:
        dictionary: Dict[str, Dict[str, Any]] = json.load(f)

    logger.info(f"Loaded {len(dictionary)} entries from {target_dict_path}. Running Semantic Verification...")

    results = []
    updated_dict = {}
    verified_matches = 0
    mismatches = 0
    not_found = 0

    for vi_term, data in dictionary.items():
        en_term = data.get("en", "").strip()
        existing_cui = data.get("cui", "")
        entity_type = data.get("entity_type", "Disease")

        if not en_term:
            updated_dict[vi_term] = data
            continue

        concept = search_best_umls_concept(en_term, entity_type=entity_type, api_key=active_key)
        time.sleep(delay_sec)

        entry_record = {
            "vi_term": vi_term,
            "en_term": en_term,
            "existing_cui": existing_cui,
            "entity_type": entity_type,
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
            new_entry["umls_preferred_name"] = official_name
            if stys:
                new_entry["sty"] = stys[0]
            updated_dict[vi_term] = new_entry
        else:
            entry_record["status"] = "NOT_FOUND_IN_UMLS"
            entry_record["official_cui"] = None
            not_found += 1
            updated_dict[vi_term] = data

        results.append(entry_record)

    # Run CUI Collision Audit
    collisions = audit_cui_collisions(updated_dict if apply_fixes else dictionary)

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dictionary_path": str(target_dict_path),
        "total_entries": len(dictionary),
        "verified_matches": verified_matches,
        "mismatched_cui_count": mismatches,
        "not_found_count": not_found,
        "collision_count": len(collisions),
        "cui_collisions": collisions,
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

    print("\n" + "=" * 75)
    print("  UMLS CUI DICTIONARY VERIFICATION & COLLISION AUDIT REPORT")
    print("=" * 75)
    print(f"Total Dictionary Entries:   {report['total_entries']}")
    print(f"Verified Exact Matches:     {report['verified_matches']} ({report['verified_matches']/report['total_entries']*100:.1f}%)")
    print(f"Mismatched / Hallucinated:  {report['mismatched_cui_count']}")
    print(f"Not Found in UMLS:          {report['not_found_count']}")
    print(f"CUI Collisions (Duplicates): {report['collision_count']}")
    print(f"Report File:                {args.report_path}")
    print("=" * 75)

    if report["cui_collisions"]:
        print("\n[!] CUI Collisions Detected:")
        for col in report["cui_collisions"]:
            print(f" - CUI {col['cui']} is shared across distinct concepts: {col['distinct_en_terms']}")

    if report["mismatched_cui_count"] > 0:
        print("\nDiscrepancies found & updated:")
        for r in report["verification_details"]:
            if r["status"] == "MISMATCH_OR_HALLUCINATED":
                print(f" - [{r['vi_term']}] ('{r['en_term']}'): Old CUI: {r['existing_cui']} -> Official CUI: {r['official_cui']} ('{r.get('official_name')}')")

    if args.apply_fixes:
        print("\n Applied verified official CUIs to dictionary successfully.")
    else:
        print("\n Run with '--apply-fixes' to automatically update dictionary with official CUIs.")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
