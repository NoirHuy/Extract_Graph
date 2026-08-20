import pytest
from preprocessing.clean_text import clean_clinical_text


def test_clean_clinical_text_unicode_nfc():
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


def test_clean_clinical_text_msd_manual_artifacts():
    raw = """Tăng huyết áp

Đánh giá toàn diện: Thg 2 2025 TheoMatthew R. Weir, MD | Được bình duyệt bởiJonathan G. Howlett, MD
Cập nhật lần cuối: Thg 5 2025
Tăng huyết áp là tình trạng tăng liên tục của huyết áp tâm thu lúc nghỉ (≥ 130 mmHg).

Căn nguyên
|
Sinh lý bệnh
|
Triệu chứng và Dấu hiệu
|
Chẩn đoán

Nhiều người trong số này không biết rằng họ bị tăng huyết áp (1).
Ngay cả khi dùng thuốc, gần 60% có BP ≥ 140/90 mm Hg (1).

Tài liệu tham khảo chung
1. Million Hearts: Estimated Hypertension Prevalence. https://millionhearts.hhs.gov
2. Vasan RS, Beiser A, et al. Framingham Heart Study. JAMA 287(8):1003-1010, 2002 doi:10.1001/jama.287.8.1003

Căn nguyên của tăng huyết áp
Tăng huyết áp có thể do nguyên phát hoặc thứ phát.
"""
    cleaned = clean_clinical_text(raw)

    # Headers and navigation bars removed
    assert "Đánh giá toàn diện:" not in cleaned
    assert "Cập nhật lần cuối:" not in cleaned
    assert "Được bình duyệt bởi" not in cleaned
    assert "|\n" not in cleaned

    # Reference bibliography list removed
    assert "Million Hearts" not in cleaned
    assert "Framingham Heart Study" not in cleaned
    assert "doi:10.1001" not in cleaned

    # Inline (1) removed but medical content and (>= 130 mmHg) preserved
    assert "họ bị tăng huyết áp." in cleaned or "họ bị tăng huyết áp" in cleaned
    assert ">= 130 mmHg" in cleaned
    assert ">= 140/90 mm Hg" in cleaned
    assert "Căn nguyên của tăng huyết áp" in cleaned
