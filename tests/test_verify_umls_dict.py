import json
import pytest
from unittest.mock import MagicMock, patch
from scripts.verify_umls_dict import verify_and_heal_dictionary

def test_verify_and_heal_dictionary_flow(tmp_path):
    mock_dict = {
        "tăng huyết áp": {"en": "Hypertension", "cui": "C0020538", "tui": "T047", "entity_type": "Disease"},
        "thuốc giả": {"en": "Fake Drug Concept", "cui": "C9999999", "tui": "T121", "entity_type": "Drug"},
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
        elif term == "Fake Drug Concept":
            # Return true official CUI C0000001 (mismatch)
            mock_resp.json.return_value = {
                "result": {
                    "results": [
                        {"ui": "C0000001", "name": "Real Drug", "semanticTypes": ["Pharmacologic Substance"]}
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
    assert report["mismatched_cui_count"] == 1
    assert report["not_found_count"] == 0
    
    # Check updated dict content
    with open(dict_file, "r", encoding="utf-8") as f:
        updated_dict = json.load(f)
    assert updated_dict["tăng huyết áp"]["cui"] == "C0020538"
    assert updated_dict["thuốc giả"]["cui"] == "C0000001"
