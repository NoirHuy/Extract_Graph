import pytest
from schema.schema_registry import (
    ENTITY_TYPES,
    RELATION_TYPES,
    get_edc_json_schema,
    validate_extraction_payload,
    is_valid_relation,
)

def test_entity_types_count_and_mapping():
    assert len(ENTITY_TYPES) == 16
    assert ENTITY_TYPES["Disease"]["tui"] == "T047"
    assert ENTITY_TYPES["DrugClass"]["tui"] == "T121"
    assert ENTITY_TYPES["Measurement"]["group"] == "CONC"

def test_relation_domain_range_validation():
    assert is_valid_relation("Cause", "CAUSES", "Disease") is True
    assert is_valid_relation("DrugClass", "TREATS", "Disease") is True
    assert is_valid_relation("Measurement", "DEFINES_THRESHOLD_FOR", "DiseaseSubtype") is True
    assert is_valid_relation("Disease", "LEADS_TO", "Complication") is True
    # Invalid combinations
    assert is_valid_relation("Drug", "HAS_SYMPTOM", "Organ") is False
    assert is_valid_relation("Disease", "CAUSES", "Test") is False

def test_validate_extraction_payload():
    valid_payload = {
        "entities": [
            {
                "id": "e1",
                "text": "Tăng huyết áp",
                "normalized_name": "Tăng huyết áp",
                "entity_type": "Disease",
                "evidence_span": "Tăng huyết áp là tình trạng...",
                "umls_cui": None
            }
        ],
        "relations": [
            {
                "source_id": "e1",
                "target_id": "e2",
                "relation_type": "LEADS_TO",
                "evidence_span": "Tăng huyết áp dẫn đến đột quỵ",
                "confidence": 0.95
            }
        ]
    }
    assert validate_extraction_payload(valid_payload) is True

def test_validate_invalid_extraction_payload():
    invalid_payload = {
        "entities": [
            {
                "id": "e1",
                "text": "Tăng huyết áp",
                # missing entity_type and evidence_span
            }
        ],
        "relations": []
    }
    assert validate_extraction_payload(invalid_payload) is False
