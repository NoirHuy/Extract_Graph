"""End-to-End Regression Suite for Hypertension Clinical Knowledge Graph Extraction."""

import pytest
from schema.schema_registry import is_valid_relation
from validation.consensus import merge_entities, aggregate_relation_consensus
from validation.validate_relations import validate_and_filter_relations
from normalization.umls_normalize import normalize_entities
from ingestion.neo4j_loader import Neo4jLoader


def test_hypertension_benchmark_triplets(tmp_path):
    """Test full pipeline on clinical hypertension benchmark entities and relations."""
    pass1_entities = [
        {"id": "p1_e1", "text": "Cường aldosteron nguyên phát", "normalized_name": "Cường aldosteron nguyên phát", "entity_type": "Cause", "evidence_span": "Cường aldosteron nguyên phát là một nguyên nhân quan trọng dẫn đến Tăng huyết áp."},
        {"id": "p1_e2", "text": "Tăng huyết áp", "normalized_name": "Tăng huyết áp", "entity_type": "Disease", "evidence_span": "Tăng huyết áp là tình trạng huyết áp động mạch tăng cao mạn tính."},
        {"id": "p1_e3", "text": "ACE inhibitor", "normalized_name": "ACE inhibitor", "entity_type": "DrugClass", "evidence_span": "Thuốc ức chế men chuyển (ACE inhibitor) được chỉ định phổ biến để điều trị Tăng huyết áp."},
        {"id": "p1_e4", "text": "130/80 mmHg", "normalized_name": "130/80 mmHg", "entity_type": "Measurement", "evidence_span": "Tăng huyết áp giai đoạn 1 được xác định khi huyết áp từ 130/80 mmHg.", "attributes": {"systolic": 130, "diastolic": 80, "unit": "mmHg"}},
        {"id": "p1_e5", "text": "Tăng huyết áp giai đoạn 1", "normalized_name": "Tăng huyết áp giai đoạn 1", "entity_type": "DiseaseSubtype", "evidence_span": "Tăng huyết áp giai đoạn 1 được xác định khi huyết áp từ 130/80 mmHg."},
        {"id": "p1_e6", "text": "Đột quỵ", "normalized_name": "Đột quỵ", "entity_type": "Complication", "evidence_span": "Tăng huyết áp là yếu tố nguy cơ chính dẫn đến Đột quỵ."}
    ]

    pass2_entities = [
        {"id": "p2_e1", "text": "Cường aldosteron", "normalized_name": "Cường aldosteron nguyên phát", "entity_type": "Cause", "evidence_span": "Cường aldosteron nguyên phát làm tăng tái hấp thu natri."},
        {"id": "p2_e2", "text": "Tăng huyết áp", "normalized_name": "Tăng huyết áp", "entity_type": "Disease", "evidence_span": "Tăng huyết áp lâu ngày gây tổn thương cơ quan đích."},
        {"id": "p2_e3", "text": "Thuốc ức chế men chuyển", "normalized_name": "ACE inhibitor", "entity_type": "DrugClass", "evidence_span": "Thuốc ức chế men chuyển (ACE inhibitor) điều trị Tăng huyết áp."},
        {"id": "p2_e4", "text": "130/80 mmHg", "normalized_name": "130/80 mmHg", "entity_type": "Measurement", "evidence_span": "ngưỡng 130/80 mmHg", "attributes": {"systolic": 130, "diastolic": 80, "unit": "mmHg"}},
        {"id": "p2_e5", "text": "Tăng huyết áp giai đoạn 1", "normalized_name": "Tăng huyết áp giai đoạn 1", "entity_type": "DiseaseSubtype", "evidence_span": "Tăng huyết áp giai đoạn 1"},
        {"id": "p2_e6", "text": "Đột quỵ não", "normalized_name": "Đột quỵ", "entity_type": "Complication", "evidence_span": "dẫn đến Đột quỵ, Nhồi máu cơ tim"}
    ]

    pass1_relations = [
        {"source_id": "p1_e1", "target_id": "p1_e2", "relation_type": "CAUSES", "evidence_span": "Cường aldosteron dẫn đến Tăng huyết áp", "confidence": 0.9},
        {"source_id": "p1_e3", "target_id": "p1_e2", "relation_type": "TREATS", "evidence_span": "ACE inhibitor điều trị Tăng huyết áp", "confidence": 0.95},
        {"source_id": "p1_e4", "target_id": "p1_e5", "relation_type": "DEFINES_THRESHOLD_FOR", "evidence_span": "130/80 mmHg xác định Tăng huyết áp giai đoạn 1", "confidence": 0.9},
        {"source_id": "p1_e2", "target_id": "p1_e6", "relation_type": "LEADS_TO", "evidence_span": "Tăng huyết áp dẫn đến Đột quỵ", "confidence": 0.92}
    ]

    pass2_relations = [
        {"source_id": "p2_e1", "target_id": "p2_e2", "relation_type": "CAUSES", "evidence_span": "Cường aldosteron dẫn đến Tăng huyết áp", "confidence": 0.9},
        {"source_id": "p2_e3", "target_id": "p2_e2", "relation_type": "TREATS", "evidence_span": "ACE inhibitor điều trị Tăng huyết áp", "confidence": 0.95},
        {"source_id": "p2_e4", "target_id": "p2_e5", "relation_type": "DEFINES_THRESHOLD_FOR", "evidence_span": "130/80 mmHg xác định Tăng huyết áp giai đoạn 1", "confidence": 0.88},
        {"source_id": "p2_e2", "target_id": "p2_e6", "relation_type": "LEADS_TO", "evidence_span": "Tăng huyết áp dẫn đến Đột quỵ", "confidence": 0.9}
    ]

    # 1. Consensus & Entity Merging
    merged_entities, id_map = merge_entities([pass1_entities, pass2_entities])
    assert len(merged_entities) == 6

    consensus_relations, conflicts = aggregate_relation_consensus([pass1_relations, pass2_relations], id_mapping=id_map, total_passes=2)
    assert len(conflicts) == 0
    assert len(consensus_relations) == 4

    # 2. UMLS Normalization
    normalized_entities, unmapped = normalize_entities(merged_entities, doc_id="hypertension_bench", output_dir=str(tmp_path))
    # All 5 clinical concept entities are mapped to CUI, 1 quantitative measurement is unmapped CUI (uses resolved_key fallback)
    assert len(unmapped) == 1
    assert unmapped[0]["entity_type"] == "Measurement"

    cui_map = {e["normalized_name"]: e["umls_cui"] for e in normalized_entities}
    assert cui_map["Tăng huyết áp"] == "C0020538"
    assert cui_map["Cường aldosteron nguyên phát"] in ("C1384514", "C0020438")
    assert cui_map["Đột quỵ"] == "C0038454"
    assert cui_map["ACE inhibitor"] == "C0003015"
    assert cui_map["Tăng huyết áp giai đoạn 1"] in ("C5231206", "C4073145")
    assert cui_map["130/80 mmHg"] is None

    # 3. Domain/Range Validation
    valid_relations, invalid_relations = validate_and_filter_relations(consensus_relations, normalized_entities, min_confidence=0.7)
    assert len(invalid_relations) == 0
    assert len(valid_relations) == 4

    # 4. Verify 4 Core Triplets
    type_triplets = []
    for r in valid_relations:
        s_ent = next(e for e in normalized_entities if e["id"] == r["source_id"])
        t_ent = next(e for e in normalized_entities if e["id"] == r["target_id"])
        type_triplets.append((s_ent["normalized_name"], s_ent["entity_type"], r["relation_type"], t_ent["normalized_name"], t_ent["entity_type"]))

    assert any(t[0] == "Cường aldosteron nguyên phát" and t[2] == "CAUSES" and t[3] == "Tăng huyết áp" for t in type_triplets)
    assert any(t[0] == "ACE inhibitor" and t[2] == "TREATS" and t[3] == "Tăng huyết áp" for t in type_triplets)
    assert any(t[0] == "130/80 mmHg" and t[2] == "DEFINES_THRESHOLD_FOR" and t[3] == "Tăng huyết áp giai đoạn 1" for t in type_triplets)
    assert any(t[0] == "Tăng huyết áp" and t[2] == "LEADS_TO" and t[3] == "Đột quỵ" for t in type_triplets)

    # 5. Verify Measurement Attributes
    meas_ent = next(e for e in normalized_entities if e["entity_type"] == "Measurement")
    assert meas_ent["attributes"]["systolic"] == 130
    assert meas_ent["attributes"]["diastolic"] == 80
    assert meas_ent["attributes"]["unit"] == "mmHg"

    # 6. Verify Neo4j Ingestion dry-run
    loader = Neo4jLoader()
    summary = loader.ingest_graph(normalized_entities, valid_relations, source_doc="hypertension_sample.txt", dry_run=True)
    assert summary["nodes_count"] == 6
    assert summary["relations_count"] == 4
    assert summary["status"] == "dry_run_success"


def test_conflict_detection_and_exclusion():
    """Verify that discordant relation types of equal rank across passes are flagged as conflict and excluded from valid graph."""
    pass1_entities = [
        {"id": "p1_e1", "text": "Thuốc X", "normalized_name": "Thuốc X", "entity_type": "Drug", "evidence_span": "..."},
        {"id": "p1_e2", "text": "Bệnh B", "normalized_name": "Bệnh B", "entity_type": "Disease", "evidence_span": "..."}
    ]
    pass2_entities = [
        {"id": "p2_e1", "text": "Thuốc X", "normalized_name": "Thuốc X", "entity_type": "Drug", "evidence_span": "..."},
        {"id": "p2_e2", "text": "Bệnh B", "normalized_name": "Bệnh B", "entity_type": "Disease", "evidence_span": "..."}
    ]
    # Pass 1: TREATS (rank 9), Pass 2: CONTRAINDICATED_IN (rank 9) -> True Contradiction
    pass1_rel = [{"source_id": "p1_e1", "target_id": "p1_e2", "relation_type": "TREATS", "evidence_span": "...", "confidence": 0.8}]
    pass2_rel = [{"source_id": "p2_e1", "target_id": "p2_e2", "relation_type": "CONTRAINDICATED_IN", "evidence_span": "...", "confidence": 0.8}]

    merged_entities, id_map = merge_entities([pass1_entities, pass2_entities])
    consensus, conflicts = aggregate_relation_consensus([pass1_rel, pass2_rel], id_mapping=id_map, total_passes=2)

    assert len(consensus) == 0
    assert len(conflicts) == 1
    assert conflicts[0]["status"] == "conflict"
