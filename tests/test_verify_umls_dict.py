import json
import pytest
from unittest.mock import MagicMock, patch
from scripts.verify_umls_dict import verify_and_heal_dictionary, audit_dictionary_integrity, UMLS_SEMANTIC_NETWORK

def test_verify_and_heal_dictionary_flow(tmp_path):
    mock_dict = {
        "tăng huyết áp": {"en": "Hypertension", "cui": "C0020538", "tui": "T047", "sty": "Disease or Syndrome", "entity_type": "Disease"},
        "metformin": {"en": "Metformin", "cui": "C0025598", "tui": "T121", "sty": "Organic Chemical", "entity_type": "Drug"},
    }
    
    dict_file = tmp_path / "test_dict.json"
    report_file = tmp_path / "report.json"
    
    with open(dict_file, "w", encoding="utf-8") as f:
        json.dump(mock_dict, f, ensure_ascii=False)
        
    def mock_umls_get(url, params=None, timeout=10):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        term = params.get("string", "") if params else ""
        if term == "Hypertension":
            mock_resp.json.return_value = {
                "result": {
                    "results": [
                        {"ui": "C0020538", "name": "Hypertensive disease", "semanticTypes": ["Disease or Syndrome"]}
                    ]
                }
            }
        elif term == "Metformin":
            # Multiple STYs: Organic Chemical and Pharmacologic Substance
            mock_resp.json.return_value = {
                "result": {
                    "results": [
                        {"ui": "C0025598", "name": "Metformin", "semanticTypes": ["Organic Chemical", "Pharmacologic Substance"]}
                    ]
                }
            }
        else:
            mock_resp.json.return_value = {"result": {"results": []}}
        return mock_resp

    with patch("requests.get", side_effect=mock_umls_get):
        report = verify_and_heal_dictionary(
            dict_path=str(dict_file),
            report_path=str(report_file),
            apply_fixes=True,
            api_key="dummy_key",
        )
        
    assert report["total_entries"] == 2
    assert report["verified_matches"] == 1
    assert report["mismatched_or_healed_count"] == 1
    assert report["collision_count"] == 0
    assert report["tui_sty_mismatch_count"] == 0
    
    # Check updated dict content: Drug Metformin priority picked Pharmacologic Substance -> T121
    with open(dict_file, "r", encoding="utf-8") as f:
        updated_dict = json.load(f)
    assert updated_dict["metformin"]["cui"] == "C0025598"
    assert updated_dict["metformin"]["sty"] == "Pharmacologic Substance"
    assert updated_dict["metformin"]["tui"] == "T121"
