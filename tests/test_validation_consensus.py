import pytest
from validation.consensus import merge_entities, aggregate_relation_consensus
from validation.validate_relations import validate_and_filter_relations

def test_entity_merging_longest_span():
    pass1_entities = [
        {"id": "p1_e1", "text": "Tăng HA", "normalized_name": "Tăng huyết áp", "entity_type": "Disease", "evidence_span": "Tăng HA ngắn", "attributes": {"key1": "val1"}}
    ]
    pass2_entities = [
        {"id": "p2_e2", "text": "Tăng huyết áp", "normalized_name": "Tăng huyết áp", "entity_type": "Disease", "evidence_span": "Tăng huyết áp là câu dài hơn nhiều", "attributes": {"key2": "val2"}}
    ]
    merged, id_mapping = merge_entities([pass1_entities, pass2_entities])
    assert len(merged) == 1
    assert merged[0]["evidence_span"] == "Tăng huyết áp là câu dài hơn nhiều"
    assert "key1" in merged[0]["attributes"] and "key2" in merged[0]["attributes"]
    assert id_mapping["p1_e1"] == merged[0]["id"]
    assert id_mapping["p2_e2"] == merged[0]["id"]

def test_relation_agreement_and_statistical_confidence():
    id_map = {"p1_e1": "canon_e1", "p1_e2": "canon_e2", "p2_e1": "canon_e1", "p2_e2": "canon_e2"}
    rel1 = [{"source_id": "p1_e1", "target_id": "p1_e2", "relation_type": "CAUSES", "evidence_span": "span1", "confidence": 0.8}]
    rel2 = [{"source_id": "p2_e1", "target_id": "p2_e2", "relation_type": "CAUSES", "evidence_span": "span2", "confidence": 0.8}]
    consensus, conflicts = aggregate_relation_consensus([rel1, rel2], id_mapping=id_map, total_passes=2)
    assert len(consensus) == 1
    assert len(conflicts) == 0
    assert consensus[0]["agreement_count"] == 2
    # 1 - (1-0.8)*(1-0.8) = 1 - 0.04 = 0.96
    assert pytest.approx(consensus[0]["confidence"], 0.01) == 0.96

def test_relation_conflict_detection_equal_rank():
    id_map = {"p1_e1": "canon_e1", "p1_e2": "canon_e2", "p2_e1": "canon_e1", "p2_e2": "canon_e2"}
    # TREATS and CONTRAINDICATED_IN both have rank 9 (true contradiction)
    rel1 = [{"source_id": "p1_e1", "target_id": "p1_e2", "relation_type": "TREATS", "evidence_span": "span1", "confidence": 0.8}]
    rel2 = [{"source_id": "p2_e1", "target_id": "p2_e2", "relation_type": "CONTRAINDICATED_IN", "evidence_span": "span2", "confidence": 0.8}]
    consensus, conflicts = aggregate_relation_consensus([rel1, rel2], id_mapping=id_map, total_passes=2)
    assert len(conflicts) == 1
    assert conflicts[0]["status"] == "conflict"
    assert "conflict_variants" in conflicts[0]

def test_relation_tie_breaker_by_specificity():
    id_map = {"p1_e1": "canon_e1", "p1_e2": "canon_e2", "p2_e1": "canon_e1", "p2_e2": "canon_e2"}
    # UNDERLIES (rank 10) vs MODIFIES (rank 4) -> Automatically resolved to UNDERLIES
    rel1 = [{"source_id": "p1_e1", "target_id": "p1_e2", "relation_type": "MODIFIES", "evidence_span": "span1", "confidence": 0.8}]
    rel2 = [{"source_id": "p2_e1", "target_id": "p2_e2", "relation_type": "UNDERLIES", "evidence_span": "span2", "confidence": 0.8}]
    consensus, conflicts = aggregate_relation_consensus([rel1, rel2], id_mapping=id_map, total_passes=2)
    assert len(conflicts) == 0
    assert len(consensus) == 1
    assert consensus[0]["relation_type"] == "UNDERLIES"
    assert consensus[0]["status"] == "resolved_by_specificity"

def test_domain_range_and_confidence_filter():
    entities = [
        {"id": "e1", "normalized_name": "Tăng huyết áp", "entity_type": "Disease"},
        {"id": "e2", "normalized_name": "Đột quỵ", "entity_type": "Complication"},
        {"id": "e3", "normalized_name": "Thuốc A", "entity_type": "Drug"},
    ]
    relations = [
        # Valid: Disease -> LEADS_TO -> Complication
        {"source_id": "e1", "target_id": "e2", "relation_type": "LEADS_TO", "confidence": 0.9, "evidence_span": "..."},
        # Invalid confidence (< 0.7)
        {"source_id": "e1", "target_id": "e2", "relation_type": "LEADS_TO", "confidence": 0.5, "evidence_span": "..."},
        # Invalid domain/range: Drug -> HAS_SYMPTOM -> Complication (even auto-remap cannot convert Drug HAS_SYMPTOM)
        {"source_id": "e3", "target_id": "e2", "relation_type": "HAS_SYMPTOM", "confidence": 0.9, "evidence_span": "..."}
    ]
    valid_rels, invalid_rels = validate_and_filter_relations(relations, entities, min_confidence=0.7)
    assert len(valid_rels) == 1
    assert valid_rels[0]["relation_type"] == "LEADS_TO"
    assert len(invalid_rels) == 2
