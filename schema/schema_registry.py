"""Schema Registry for Medical Knowledge Graph Extraction.

Defines Entity Types, Relation Types, Domain/Range constraints,
UMLS Semantic Types (TUI) and Semantic Groups mappings.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import jsonschema

# Mapping of 16 Entity Types to UMLS STY, TUI and Semantic Group
ENTITY_TYPES: Dict[str, Dict[str, str]] = {
    "Disease": {"sty": "Disease or Syndrome", "tui": "T047", "group": "DISO"},
    "DiseaseSubtype": {"sty": "Disease or Syndrome", "tui": "T047", "group": "DISO"},
    "Symptom": {"sty": "Sign or Symptom", "tui": "T184", "group": "DISO"},
    "Sign": {"sty": "Finding", "tui": "T033", "group": "DISO"},
    "RiskFactor": {"sty": "Finding / Individual Behavior", "tui": "T033", "group": "DISO"},
    "Cause": {"sty": "Disease or Syndrome / Pathologic Function", "tui": "T047", "group": "DISO"},
    "Mechanism": {"sty": "Pathologic Function / Physiologic Function", "tui": "T046", "group": "DISO"},
    "Complication": {"sty": "Disease or Syndrome", "tui": "T047", "group": "DISO"},
    "Test": {"sty": "Diagnostic Procedure / Laboratory Procedure", "tui": "T060", "group": "PROC"},
    "Measurement": {"sty": "Laboratory or Test Result / Quantitative Concept", "tui": "T034", "group": "CONC"},
    "Drug": {"sty": "Pharmacologic Substance", "tui": "T121", "group": "CHEM"},
    "DrugClass": {"sty": "Pharmacologic Substance", "tui": "T121", "group": "CHEM"},
    "Treatment": {"sty": "Therapeutic or Preventive Procedure", "tui": "T061", "group": "PROC"},
    "Organ": {"sty": "Body Part, Organ, or Organ Component", "tui": "T023", "group": "ANAT"},
    "PatientGroup": {"sty": "Population Group / Age Group", "tui": "T098", "group": "LIVB"},
    "Guideline": {"sty": "Intellectual Product", "tui": "T170", "group": "CONC"},
}

# Relation Types & Domain/Range constraints
RELATION_TYPES: List[Dict[str, Any]] = [
    {"name": "IS_SUBTYPE_OF", "domain": ["DiseaseSubtype"], "range": ["Disease"]},
    {"name": "CAUSES", "domain": ["Cause"], "range": ["Disease", "DiseaseSubtype"]},
    {"name": "INCREASES_RISK_OF", "domain": ["RiskFactor"], "range": ["Disease", "Complication"]},
    {"name": "HAS_SYMPTOM", "domain": ["Disease", "DiseaseSubtype"], "range": ["Symptom"]},
    {"name": "HAS_SIGN", "domain": ["Disease", "DiseaseSubtype"], "range": ["Sign"]},
    {"name": "UNDERLIES", "domain": ["Mechanism"], "range": ["Disease", "DiseaseSubtype"]},
    {"name": "PART_OF_MECHANISM", "domain": ["Mechanism"], "range": ["Mechanism"]},
    {"name": "LEADS_TO", "domain": ["Disease", "DiseaseSubtype"], "range": ["Complication"]},
    {"name": "AFFECTS_ORGAN", "domain": ["Complication", "Disease"], "range": ["Organ"]},
    {"name": "DIAGNOSES", "domain": ["Test"], "range": ["Disease", "DiseaseSubtype"]},
    {"name": "DETECTS", "domain": ["Test"], "range": ["Sign", "Complication"]},
    {"name": "MEASURES", "domain": ["Test"], "range": ["Measurement"]},
    {"name": "TREATS", "domain": ["Drug", "DrugClass", "Treatment"], "range": ["Disease", "DiseaseSubtype"]},
    {"name": "CONTRAINDICATED_IN", "domain": ["Drug", "DrugClass"], "range": ["Disease", "PatientGroup"]},
    {"name": "PREFERRED_FOR", "domain": ["Drug", "DrugClass"], "range": ["Disease", "PatientGroup"]},
    {"name": "HAS_PREVALENCE", "domain": ["PatientGroup"], "range": ["Disease", "DiseaseSubtype"]},
    {"name": "DEFINES_THRESHOLD_FOR", "domain": ["Measurement"], "range": ["DiseaseSubtype"]},
    {"name": "CLASSIFIES", "domain": ["Guideline"], "range": ["DiseaseSubtype"]},
    {"name": "MODIFIES", "domain": ["Mechanism", "Measurement"], "range": ["Mechanism", "Disease"]},
]

_RELATION_MAP: Dict[str, Dict[str, List[str]]] = {
    rel["name"]: {"domain": rel["domain"], "range": rel["range"]} for rel in RELATION_TYPES
}

_SCHEMA_PATH = Path(__file__).parent / "edc_schema.json"
_EDC_JSON_SCHEMA: Optional[Dict[str, Any]] = None


def get_edc_json_schema() -> Dict[str, Any]:
    """Load and cache the EDC JSON schema."""
    global _EDC_JSON_SCHEMA
    if _EDC_JSON_SCHEMA is None:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            _EDC_JSON_SCHEMA = json.load(f)
    return _EDC_JSON_SCHEMA


def validate_extraction_payload(payload: Dict[str, Any]) -> bool:
    """Validate that the extracted payload conforms to the EDC JSON Schema."""
    schema = get_edc_json_schema()
    try:
        jsonschema.validate(instance=payload, schema=schema)
        return True
    except jsonschema.ValidationError:
        return False


def is_valid_relation(source_type: str, relation_type: str, target_type: str) -> bool:
    """Check if a relation satisfies Domain and Range constraints."""
    if relation_type not in _RELATION_MAP:
        return False
    rule = _RELATION_MAP[relation_type]
    return (source_type in rule["domain"]) and (target_type in rule["range"])


def get_tui_for_entity_type(entity_type: str) -> Optional[str]:
    """Retrieve the primary UMLS TUI for a given entity type."""
    entry = ENTITY_TYPES.get(entity_type)
    return entry["tui"] if entry else None


def get_semantic_group(entity_type: str) -> Optional[str]:
    """Retrieve the Semantic Group for a given entity type."""
    entry = ENTITY_TYPES.get(entity_type)
    return entry["group"] if entry else None
