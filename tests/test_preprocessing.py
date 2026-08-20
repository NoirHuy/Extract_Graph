import pytest
from preprocessing.clean_text import clean_clinical_text


def test_clean_clinical_text_unicode_nfc():
    # Test decomposed unicode vs precomposed
    raw = "Tăng huyết a\u0301p [1] [2-4] (xem bảng 1)."
    cleaned = clean_clinical_text(raw)
    assert "[1]" not in cleaned
    assert "[2-4]" not in cleaned
    assert "(xem bảng 1)" not in cleaned
    assert "Tăng huyết áp" in cleaned


def test_clean_clinical_text_operators_and_quotes():
    raw = "“Tăng huyết áp” ≥ 130/80 mmHg ± 5 mmHg – nguy cơ cao."
    cleaned = clean_clinical_text(raw)
    assert '"Tăng huyết áp"' in cleaned
    assert ">= 130/80 mmHg" in cleaned
    assert "+/- 5 mmHg" in cleaned
    assert "-" in cleaned
