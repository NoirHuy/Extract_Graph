import pytest
from unittest.mock import MagicMock, patch
from ingestion.neo4j_loader import Neo4jLoader

def test_resolved_key_generation():
    loader = Neo4jLoader(uri="bolt://localhost:7687", username="neo4j", password="password")
    
    entity_with_cui = {"entity_type": "Disease", "normalized_name": "Tăng huyết áp", "umls_cui": "C0020538"}
    assert loader.compute_resolved_key(entity_with_cui) == "CUI:C0020538"
    
    entity_without_cui = {"entity_type": "Disease", "normalized_name": "Tăng huyết áp", "umls_cui": None}
    assert loader.compute_resolved_key(entity_without_cui) == "Disease:tăng huyết áp"

def test_ingest_graph_dry_run():
    loader = Neo4jLoader(uri="bolt://localhost:7687", username="neo4j", password="password")
    entities = [
        {"id": "e1", "text": "Tăng huyết áp", "normalized_name": "Tăng huyết áp", "entity_type": "Disease", "umls_cui": "C0020538", "umls_sty": "Disease or Syndrome", "evidence_span": "span1"},
        {"id": "e2", "text": "Đột quỵ", "normalized_name": "Đột quỵ", "entity_type": "Complication", "umls_cui": "C0038454", "umls_sty": "Disease or Syndrome", "evidence_span": "span2"}
    ]
    relations = [
        {"source_id": "e1", "target_id": "e2", "relation_type": "LEADS_TO", "confidence": 0.95, "evidence_span": "Tăng HA dẫn đến đột quỵ", "agreement_count": 2, "total_passes": 2}
    ]
    summary = loader.ingest_graph(entities, relations, source_doc="hypertension.txt", dry_run=True)
    assert summary["nodes_count"] == 2
    assert summary["relations_count"] == 1
    assert summary["status"] == "dry_run_success"

def test_ingest_graph_with_mock_driver():
    loader = Neo4jLoader(uri="bolt://localhost:7687", username="neo4j", password="password")
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    loader._driver = mock_driver

    entities = [
        {"id": "e1", "text": "Tăng huyết áp", "normalized_name": "Tăng huyết áp", "entity_type": "Disease", "umls_cui": "C0020538", "umls_sty": "Disease or Syndrome", "evidence_span": "span1"}
    ]
    relations = []
    summary = loader.ingest_graph(entities, relations, source_doc="hypertension.txt", dry_run=False)
    assert summary["nodes_count"] == 1
    assert summary["status"] == "success"
    assert mock_session.run.called
