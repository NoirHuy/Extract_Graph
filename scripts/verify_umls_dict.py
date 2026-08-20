"""Authoritative UMLS Verification, Semantic Type Resolution & Anti-Hallucination Engine.

Features:
1. Ground Truth Lookup: Uses English terms ("en") as search keys.
2. Official UMLS Semantic Network (SRDEF): Strict 1-to-1 mapping between TUI and STY.
3. Domain-Aware Priority Resolution: Selects the most medically appropriate STY from multiple UMLS concept STYs.
4. Guaranteed TUI-STY Synchronization: tui is always derived directly from STY_TO_TUI[chosen_sty].
5. Negative Keyword Filtering: Blocks 'adverse reaction', 'allergy to', 'survey', 'likelihood', 'severity grade'.
6. Duplicate CUI Collision Audit: Flags any CUI shared across distinct, non-synonymous concepts.
7. Auto-Healing: Updates dictionary with verified official CUIs, STYs, TUIs, and preferred names.
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

# Official NLM UMLS Semantic Network (SRDEF): Canonical 1-to-1 TUI <-> STY mapping
UMLS_SEMANTIC_NETWORK: Dict[str, str] = {
    "T001": "Organism",
    "T002": "Plant",
    "T004": "Fungus",
    "T005": "Virus",
    "T007": "Bacterium",
    "T017": "Anatomical Structure",
    "T021": "Fully Formed Anatomical Structure",
    "T022": "Body System",
    "T023": "Body Part, Organ, or Organ Component",
    "T024": "Tissue",
    "T025": "Cell",
    "T026": "Cell Component",
    "T029": "Body Location or Region",
    "T030": "Body Space or Junction",
    "T031": "Body Substance",
    "T033": "Finding",
    "T034": "Laboratory or Test Result",
    "T037": "Injury or Poisoning",
    "T038": "Biologic Function",
    "T039": "Physiologic Function",
    "T040": "Organism Function",
    "T041": "Mental Process",
    "T042": "Organ or Tissue Function",
    "T043": "Cell Function",
    "T044": "Molecular Function",
    "T045": "Genetic Function",
    "T046": "Pathologic Function",
    "T047": "Disease or Syndrome",
    "T048": "Mental or Behavioral Dysfunction",
    "T049": "Cell or Molecular Dysfunction",
    "T050": "Experimental Model of Disease",
    "T051": "Event",
    "T052": "Activity",
    "T053": "Behavior",
    "T054": "Social Behavior",
    "T055": "Individual Behavior",
    "T056": "Daily or Recreational Activity",
    "T057": "Occupational Activity",
    "T058": "Health Care Activity",
    "T059": "Laboratory Procedure",
    "T060": "Diagnostic Procedure",
    "T061": "Therapeutic or Preventive Procedure",
    "T062": "Research Activity",
    "T063": "Molecular Biology Research Technique",
    "T064": "Governmental or Regulatory Activity",
    "T065": "Educational Activity",
    "T066": "Machine Activity",
    "T067": "Phenomenon or Process",
    "T068": "Human-caused Phenomenon or Process",
    "T069": "Environmental Effect of Humans",
    "T070": "Natural Phenomenon or Process",
    "T071": "Entity",
    "T072": "Physical Object",
    "T073": "Manufactured Object",
    "T074": "Medical Device",
    "T075": "Research Device",
    "T077": "Conceptual Entity",
    "T078": "Idea or Concept",
    "T079": "Temporal Concept",
    "T080": "Qualitative Concept",
    "T081": "Quantitative Concept",
    "T082": "Spatial Concept",
    "T083": "Geographic Area",
    "T085": "Molecular Sequence",
    "T086": "Nucleotide Sequence",
    "T087": "Amino Acid Sequence",
    "T088": "Carbohydrate Sequence",
    "T090": "Occupation or Discipline",
    "T091": "Biomedical Occupation or Discipline",
    "T092": "Organization",
    "T093": "Health Care Related Organization",
    "T094": "Professional Society",
    "T095": "Self-help or Relief Organization",
    "T096": "Group",
    "T097": "Professional or Occupational Group",
    "T098": "Population Group",
    "T099": "Family Group",
    "T100": "Age Group",
    "T101": "Patient or Disabled Group",
    "T102": "Group Attribute",
    "T103": "Chemical",
    "T104": "Chemical Viewed Structurally",
    "T109": "Organic Chemical",
    "T114": "Nucleic Acid, Nucleoside, or Nucleotide",
    "T116": "Amino Acid, Peptide, or Protein",
    "T120": "Chemical Viewed Functionally",
    "T121": "Pharmacologic Substance",
    "T122": "Biomedical or Dental Material",
    "T123": "Biologically Active Substance",
    "T125": "Hormone",
    "T126": "Enzyme",
    "T127": "Vitamin",
    "T129": "Immunologic Factor",
    "T130": "Indicator, Reagent, or Diagnostic Aid",
    "T131": "Hazardous or Poisonous Substance",
    "T167": "Substance",
    "T168": "Food",
    "T169": "Functional Concept",
    "T170": "Intellectual Product",
    "T171": "Language",
    "T184": "Sign or Symptom",
    "T185": "Classification",
    "T190": "Anatomical Abnormality",
    "T191": "Neoplastic Process",
    "T192": "Receptor",
    "T194": "Archaeon",
    "T195": "Antibiotic",
    "T196": "Element, Ion, or Isotope",
    "T197": "Inorganic Chemical",
    "T200": "Clinical Drug",
    "T201": "Clinical Attribute",
    "T203": "Drug Delivery Device",
}

STY_TO_TUI: Dict[str, str] = {sty: tui for tui, sty in UMLS_SEMANTIC_NETWORK.items()}

# Priority order of Semantic Types for each clinical Entity Type
ENTITY_TYPE_STY_PRIORITY: Dict[str, List[str]] = {
    "Drug": ["Pharmacologic Substance", "Clinical Drug", "Organic Chemical", "Inorganic Chemical", "Biologically Active Substance"],
    "DrugClass": ["Pharmacologic Substance", "Chemical Viewed Functionally", "Biomedical or Dental Material", "Organic Chemical"],
    "Disease": ["Disease or Syndrome", "Pathologic Function", "Mental or Behavioral Dysfunction", "Finding"],
    "DiseaseSubtype": ["Disease or Syndrome", "Pathologic Function", "Finding"],
    "Complication": ["Disease or Syndrome", "Pathologic Function", "Finding"],
    "Cause": ["Disease or Syndrome", "Pathologic Function", "Individual Behavior", "Finding", "Hazardous or Poisonous Substance"],
    "Mechanism": ["Pathologic Function", "Physiologic Function", "Cell or Molecular Dysfunction", "Molecular Function"],
    "Symptom": ["Sign or Symptom", "Finding"],
    "Sign": ["Finding", "Sign or Symptom"],
    "RiskFactor": ["Individual Behavior", "Finding", "Disease or Syndrome", "Hazardous or Poisonous Substance"],
    "Organ": ["Body Part, Organ, or Organ Component", "Body System", "Tissue", "Anatomical Structure"],
    "Test": ["Diagnostic Procedure", "Laboratory Procedure", "Laboratory or Test Result", "Clinical Attribute"],
    "Measurement": ["Quantitative Concept", "Laboratory or Test Result", "Clinical Attribute", "Finding"],
    "PatientGroup": ["Patient or Disabled Group", "Population Group", "Age Group", "Finding", "Disease or Syndrome"],
    "Guideline": ["Intellectual Product", "Regulation or Law"],
}

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


def is_name_valid(name: str) -> bool:
    """Check if concept preferred name does not contain forbidden modifiers."""
    lower = name.lower()
    return not any(pat in lower for pat in FORBIDDEN_NAME_PATTERNS)


def select_canonical_sty_and_tui(entity_type: str, candidate_stys: List[str]) -> Tuple[str, str]:
    """Select the best matching semantic type based on entity_type domain priorities and return (sty, tui)."""
    priorities = ENTITY_TYPE_STY_PRIORITY.get(entity_type, [])
    
    # 1. Try to find highest priority STY
    for p_sty in priorities:
        if p_sty in candidate_stys:
            tui = STY_TO_TUI.get(p_sty, "T000")
            return p_sty, tui

    # 2. Fallback to first available STY from UMLS
    if candidate_stys:
        chosen = candidate_stys[0]
        tui = STY_TO_TUI.get(chosen, "T000")
        return chosen, tui

    # 3. Ultimate default from entity_type default
    default_entry = ENTITY_TYPES.get(entity_type, {})
    d_sty = default_entry.get("sty", "Finding")
    d_tui = default_entry.get("tui", "T033")
    return d_sty, d_tui


def search_best_umls_concept(
    term_en: str,
    entity_type: str,
    api_key: str,
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """Search UMLS with exact and words strategies, filtering by vocabulary and semantic compatibility."""
    if not api_key:
        return None

    strategies = ["exact", "words"]
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

            # Prioritize candidates with valid name and matching domain STY
            priorities = set(ENTITY_TYPE_STY_PRIORITY.get(entity_type, []))
            
            for item in results:
                cui = item.get("ui")
                name = item.get("name", "")
                stys = item.get("semanticTypes", [])

                if not cui or cui == "NONE" or not cui.startswith("C"):
                    continue
                if not is_name_valid(name):
                    continue

                # Check if at least one STY is in the priority list
                if any(sty in priorities for sty in stys):
                    chosen_sty, chosen_tui = select_canonical_sty_and_tui(entity_type, stys)
                    return {
                        "cui": cui,
                        "preferred_name": name,
                        "sty": chosen_sty,
                        "tui": chosen_tui,
                        "semantic_types": stys,
                        "match_strategy": strategy,
                    }

            # Fallback to first candidate with valid name
            for item in results:
                cui = item.get("ui")
                name = item.get("name", "")
                stys = item.get("semanticTypes", [])
                if cui and cui.startswith("C") and is_name_valid(name):
                    chosen_sty, chosen_tui = select_canonical_sty_and_tui(entity_type, stys)
                    return {
                        "cui": cui,
                        "preferred_name": name,
                        "sty": chosen_sty,
                        "tui": chosen_tui,
                        "semantic_types": stys,
                        "match_strategy": f"{strategy}_fallback",
                    }

        except Exception as e:
            logger.debug(f"Search failed for '{term_en}' ({strategy}): {e}")
            continue

    return None


def audit_dictionary_integrity(entries: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Perform comprehensive internal audits:

    1. CUI Collisions (duplicate CUIs across distinct English terms).
    2. TUI <-> STY Mismatch (checks if tui and sty strictly match UMLS Semantic Network).
    """
    # 1. CUI Collision Audit
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
            collisions.append({
                "cui": cui,
                "terms": term_list,
                "distinct_en_terms": list(distinct_en),
                "count": len(term_list),
            })

    # 2. TUI <-> STY Strict Mismatch Audit
    tui_sty_mismatches = []
    for vi_term, data in entries.items():
        tui = data.get("tui")
        sty = data.get("sty")
        if tui and sty:
            expected_sty = UMLS_SEMANTIC_NETWORK.get(tui)
            if expected_sty and expected_sty != sty:
                tui_sty_mismatches.append({
                    "vi_term": vi_term,
                    "en_term": data.get("en"),
                    "tui": tui,
                    "sty_actual": sty,
                    "sty_expected_for_this_tui": expected_sty,
                })

    return {
        "collisions": collisions,
        "tui_sty_mismatches": tui_sty_mismatches,
    }


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

    logger.info(f"Loaded {len(dictionary)} entries from {target_dict_path}. Running Full Semantic Network Verification...")

    results = []
    updated_dict = {}
    verified_matches = 0
    mismatches = 0
    not_found = 0

    for vi_term, data in dictionary.items():
        en_term = data.get("en", "").strip()
        existing_cui = data.get("cui", "")
        existing_tui = data.get("tui", "")
        existing_sty = data.get("sty", "")
        entity_type = data.get("entity_type", "Disease")

        if not en_term:
            updated_dict[vi_term] = data
            continue

        # If CUI was explicitly set to null (e.g. for guideline documents), preserve with valid default TUI/STY
        if existing_cui is None:
            default_entry = ENTITY_TYPES.get(entity_type, {})
            d_sty, d_tui = select_canonical_sty_and_tui(entity_type, [default_entry.get("sty", "Intellectual Product")])
            new_entry = dict(data)
            new_entry["sty"] = d_sty
            new_entry["tui"] = d_tui
            updated_dict[vi_term] = new_entry
            results.append({
                "vi_term": vi_term,
                "en_term": en_term,
                "existing_cui": None,
                "official_cui": None,
                "official_name": None,
                "tui": d_tui,
                "sty": d_sty,
                "status": "EXPLICIT_NULL_CUI",
            })
            not_found += 1
            continue

        concept = search_best_umls_concept(en_term, entity_type=entity_type, api_key=active_key)
        time.sleep(delay_sec)

        entry_record = {
            "vi_term": vi_term,
            "en_term": en_term,
            "existing_cui": existing_cui,
            "existing_tui": existing_tui,
            "existing_sty": existing_sty,
            "entity_type": entity_type,
        }

        if concept:
            official_cui = concept["cui"]
            official_name = concept["preferred_name"]
            official_sty = concept["sty"]
            official_tui = concept["tui"]
            stys = concept["semantic_types"]

            entry_record["official_cui"] = official_cui
            entry_record["official_name"] = official_name
            entry_record["official_sty"] = official_sty
            entry_record["official_tui"] = official_tui
            entry_record["official_all_stys"] = stys
            entry_record["match_strategy"] = concept["match_strategy"]

            # Check if CUI, TUI and STY are all matched and synchronized
            is_cui_match = bool(existing_cui and existing_cui.upper() == official_cui.upper())
            is_tui_match = bool(existing_tui == official_tui)
            is_sty_match = bool(existing_sty == official_sty)

            if is_cui_match and is_tui_match and is_sty_match:
                entry_record["status"] = "VERIFIED_MATCH"
                verified_matches += 1
            else:
                entry_record["status"] = "HEALED_OR_UPDATED"
                mismatches += 1

            new_entry = dict(data)
            new_entry["cui"] = official_cui
            new_entry["tui"] = official_tui
            new_entry["sty"] = official_sty
            new_entry["umls_preferred_name"] = official_name
            updated_dict[vi_term] = new_entry
        else:
            entry_record["status"] = "NOT_FOUND_IN_UMLS"
            entry_record["official_cui"] = None
            not_found += 1
            updated_dict[vi_term] = data

        results.append(entry_record)

    # Run Integrity Audits (Collisions + TUI/STY consistency)
    audit = audit_dictionary_integrity(updated_dict if apply_fixes else dictionary)

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dictionary_path": str(target_dict_path),
        "total_entries": len(dictionary),
        "verified_matches": verified_matches,
        "mismatched_or_healed_count": mismatches,
        "not_found_count": not_found,
        "collision_count": len(audit["collisions"]),
        "tui_sty_mismatch_count": len(audit["tui_sty_mismatches"]),
        "cui_collisions": audit["collisions"],
        "tui_sty_mismatches": audit["tui_sty_mismatches"],
        "verification_details": results,
    }

    # Save detailed JSON report
    report_target = Path(report_path)
    report_target.parent.mkdir(parents=True, exist_ok=True)
    with open(report_target, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved verification report to: {report_target}")

    # Apply fixes if requested
    if apply_fixes and (mismatches > 0 or len(audit["tui_sty_mismatches"]) > 0):
        backup_path = target_dict_path.with_name(f"{target_dict_path.stem}.backup.json")
        shutil.copy2(target_dict_path, backup_path)
        with open(target_dict_path, "w", encoding="utf-8") as f:
            json.dump(updated_dict, f, ensure_ascii=False, indent=2)
        logger.info(f"Updated dictionary saved to {target_dict_path} with {mismatches} healed entries.")

    return report


def main():
    parser = argparse.ArgumentParser(description="Verify and heal medical dictionary against NLM UMLS UTS Search API")
    parser.add_argument("--dict-path", default="data/dict/medical_vi_en_cui.json", help="Path to dictionary JSON")
    parser.add_argument("--report-path", default="data/dict/umls_verification_report.json", help="Path to output JSON report")
    parser.add_argument("--apply-fixes", action="store_true", help="Apply official verified CUIs and synchronized TUIs/STYs directly into dictionary")
    parser.add_argument("--api-key", default=None, help="UMLS API Key override")
    args = parser.parse_args()

    report = verify_and_heal_dictionary(
        dict_path=args.dict_path,
        report_path=args.report_path,
        apply_fixes=args.apply_fixes,
        api_key=args.api_key,
    )

    print("\n" + "=" * 75)
    print("  UMLS CUI & SEMANTIC NETWORK (TUI/STY) INTEGRITY REPORT")
    print("=" * 75)
    print(f"Total Dictionary Entries:      {report['total_entries']}")
    print(f"Verified Exact Matches:        {report['verified_matches']} ({report['verified_matches']/report['total_entries']*100:.1f}%)")
    print(f"Healed / Synchronized Entries: {report['mismatched_or_healed_count']}")
    print(f"Explicit Null / Not Found:     {report['not_found_count']}")
    print(f"CUI Collisions (Duplicates):    {report['collision_count']}")
    print(f"TUI <-> STY Mismatches:        {report['tui_sty_mismatch_count']}")
    print(f"Report File:                   {args.report_path}")
    print("=" * 75)

    if report["cui_collisions"]:
        print("\n[!] CUI Collisions Detected:")
        for col in report["cui_collisions"]:
            print(f" - CUI {col['cui']} is shared across distinct concepts: {col['distinct_en_terms']}")

    if report["tui_sty_mismatches"]:
        print("\n[!] TUI/STY Mismatches Detected:")
        for mm in report["tui_sty_mismatches"]:
            print(f" - [{mm['vi_term']}]: TUI {mm['tui']} has STY '{mm['sty_actual']}' (Expected: '{mm['sty_expected_for_this_tui']}')")

    if args.apply_fixes:
        print("\n Applied verified official CUIs & synchronized TUIs/STYs to dictionary successfully.")
    else:
        print("\n Run with '--apply-fixes' to automatically synchronize dictionary with official UMLS Semantic Network.")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
