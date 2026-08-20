import os
import csv
import pytest
from unittest.mock import MagicMock
from export.neo4j_exporter import Neo4jExporter

def test_export_to_csv_files(tmp_path):
    exporter = Neo4jExporter(uri="bolt://localhost:7687", username="neo4j", password="password")
    
    # Mock records
    mock_node_records = [
        {
            "id": "CUI:C0020538",
            "name": "Tăng huyết áp",
            "normalized_name": "Tăng huyết áp",
            "entity_type": "Disease",
            "labels": ["Disease"],
            "umls_cui": "C0020538",
            "umls_sty": "Disease or Syndrome",
            "attributes": "{}",
            "source_document": "sample.txt",
        }
    ]
    
    mock_rel_records = [
        {
            "source_name": "Tăng huyết áp",
            "source_type": "Disease",
            "source_cui": "C0020538",
            "relation_type": "LEADS_TO",
            "target_name": "Đột quỵ",
            "target_type": "Complication",
            "target_cui": "C0038454",
            "confidence": 0.99,
            "agreement_count": 2,
            "total_passes": 2,
            "evidence_span": "Tăng huyết áp dẫn đến Đột quỵ",
            "source_document": "sample.txt",
        }
    ]
    
    mock_session = MagicMock()
    mock_session.run.side_effect = [
        [MagicMock(data=lambda r=rec: r) for rec in mock_node_records],
        [MagicMock(data=lambda r=rec: r) for rec in mock_rel_records],
    ]
    
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    exporter._driver = mock_driver
    
    files = exporter.export_all_to_csv(output_dir=str(tmp_path))
    
    assert os.path.exists(files["nodes_csv"])
    assert os.path.exists(files["relations_csv"])
    assert os.path.exists(files["clinical_summary_csv"])
    assert files["nodes_count"] == 1
    assert files["relations_count"] == 1
    
    # Verify CSV content
    with open(files["clinical_summary_csv"], "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["Thực thể nguồn (Source)"] == "Tăng huyết áp"
        assert rows[0]["Quan hệ lâm sàng (Relation)"] == "Dẫn đến biến chứng"
        assert rows[0]["Thực thể đích (Target)"] == "Đột quỵ"
        assert "Đồng thuận (Passes)" not in rows[0]
        assert "Độ tin cậy (%)" not in rows[0]
