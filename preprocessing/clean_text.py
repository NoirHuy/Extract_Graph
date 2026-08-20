"""Medical Clinical Text Preprocessing & Cleaning Engine.

Performs robust text cleaning on raw clinical documents (e.g. MSD Manual, clinical guidelines):
1. Unicode NFC normalization.
2. Stripping MSD reviewer metadata, update dates, and pipe navigation bars.
3. Stripping bibliographic reference sections ('Tài liệu tham khảo...').
4. Removing inline citation markers ([1], (1), (xem bảng...)) while preserving clinical abbreviations & percentages.
5. Standardizing operators (>=, <=, +/-) and line breaks.
"""

import re
import unicodedata
from typing import Dict, List


def clean_clinical_text(raw_text: str) -> str:
    """Preprocess and normalize raw Vietnamese medical text from clinical sources."""
    if not raw_text:
        return ""

    # 1. Unicode NFC Normalization
    text = unicodedata.normalize("NFC", raw_text)

    # 2. Standardize Line Breaks (CRLF -> LF)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Standardize Typography and Comparison Operators
    replacements: Dict[str, str] = {
        "“": '"',
        "”": '"',
        "„": '"',
        "‘": "'",
        "’": "'",
        "–": "-",  # en-dash
        "—": "-",  # em-dash
        "≥": ">= ",
        "≤": "<= ",
        "±": "+/-",
        "…": "...",
        "\u00a0": " ",  # non-breaking space
        "\u200b": "",   # zero-width space
    }
    for orig, rep in replacements.items():
        text = text.replace(orig, rep)

    # 4. Remove Header Reviewer & Date Metadata lines
    lines = text.split("\n")
    cleaned_lines: List[str] = []
    in_reference_block = False

    for line in lines:
        stripped = line.strip()

        # Skip empty or lone pipe lines
        if not stripped or stripped == "|":
            continue

        # Skip MSD header metadata
        if (
            stripped.startswith("Đánh giá toàn diện:")
            or stripped.startswith("Cập nhật lần cuối:")
            or "Được bình duyệt bởi" in stripped
        ):
            continue

        # Skip navigation bar lines containing multiple pipe characters
        if stripped.count("|") >= 2:
            continue

        # Detect start of reference section
        if re.match(r"^Tài liệu tham khảo(?:\s+[a-zà-ỹ\s]+)?$", stripped, flags=re.IGNORECASE):
            in_reference_block = True
            continue

        # While inside a reference block, skip numbered citation lines or web links
        if in_reference_block:
            # Check if this line is still a bibliographic citation
            is_citation = (
                re.match(r"^\d+\.\s+[A-Z]", stripped)
                or "doi:" in stripped.lower()
                or "http://" in stripped.lower()
                or "https://" in stripped.lower()
                or re.match(r"^[A-Z][a-zA-Z\s]+(?:\d{4}|\d+\(\d+\))", stripped)
            )
            # Check if a new major medical heading has begun
            is_new_heading = bool(
                re.match(
                    r"^(?:Căn nguyên|Sinh lý bệnh|Bệnh lý|Triệu chứng|Chẩn đoán|Điều trị|Tiên lượng|Những điểm chính|Bất thường|Hệ thống|Hệ Renin|Sự thiếu hụt|Cách đo|Các số đo|Tiền sử|Khám thực thể|Xét nghiệm|Thuốc|Kiểm soát)",
                    stripped,
                    flags=re.IGNORECASE,
                )
            )
            if is_new_heading:
                in_reference_block = False
            elif is_citation or len(stripped) < 120:
                continue
            else:
                in_reference_block = False

        cleaned_lines.append(stripped)

    text = "\n".join(cleaned_lines)

    # 5. Remove Numeric Bracket Footnotes e.g. [1], [12], [1-3]
    text = re.sub(r"\[\d+(?:[\s,\-–]\d+)*\]", "", text)

    # 6. Remove Parenthetical Numeric Citations e.g. (1), (2), (1, 2) when NOT containing % or units or letters
    text = re.sub(r"(?<=\w)\s*\(\d+(?:[\s,–\-]\d+)*\)", "", text)

    # 7. Remove Parenthetical Cross-References like (xem bảng 1), (xem phần X)
    text = re.sub(r"\((?:xem\s+(?:bảng|hình|phần|mục|chương)[^\)]*)\)", "", text, flags=re.IGNORECASE)

    # 8. Clean trailing asterisks and normalize spaces
    final_lines: List[str] = []
    for line in text.split("\n"):
        clean_line = re.sub(r"[ \t]+", " ", line).strip()
        # Remove trailing standalone reference asterisks e.g. "Người trưởng thành*" -> "Người trưởng thành"
        clean_line = re.sub(r"(?<=\w)\*+$", "", clean_line)
        # Skip standalone "Bảng" lines that have no content
        if clean_line.lower() in ("bảng", "hình ảnh", "đa phương tiện"):
            continue
        if clean_line:
            final_lines.append(clean_line)

    cleaned_text = "\n\n".join(final_lines)
    return cleaned_text
