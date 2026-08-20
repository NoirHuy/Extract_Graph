import json
import pytest
from unittest.mock import MagicMock, patch
from extraction.extract import run_extraction_pipeline, ExtractionResult

def test_run_extraction_multi_pass(tmp_path):
    mock_payload = {
        "entities": [
            {
                "id": "e1",
                "text": "Tăng huyết áp",
                "normalized_name": "Tăng huyết áp",
                "entity_type": "Disease",
                "evidence_span": "Tăng huyết áp là bệnh mạn tính.",
                "umls_cui": None,
                "attributes": {}
            }
        ],
        "relations": []
    }
    
    with patch("extraction.extract.LLMClient.extract_structured", return_value=mock_payload):
        results = run_extraction_pipeline(
            text="1. Định nghĩa\nTăng huyết áp là bệnh mạn tính nguy hiểm.",
            passes=2,
            source_doc="test_doc.txt",
            output_dir=str(tmp_path)
        )
        assert len(results) == 2
        assert results[0].pass_index == 1
        assert results[1].pass_index == 2
        assert len(results[0].entities) == 1
        assert results[0].entities[0]["normalized_name"] == "Tăng huyết áp"
