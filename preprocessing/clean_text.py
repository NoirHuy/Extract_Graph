"""Medical Clinical Text Preprocessing & Cleaning Engine.

Performs robust text cleaning prior to chunking and LLM extraction:
1. Unicode NFC normalization (crucial for Vietnamese composite vs precomposed tone marks).
2. Standardization of medical symbols, hyphens, and comparison operators (>=, <=, +/-).
3. Removal of citation artifacts, footnote markers, and noisy cross-references (e.g. '[1]', '(xem bảng 1)').
4. Normalization of whitespace, paragraph breaks, and punctuation.
"""

import re
import unicodedata
from typing import Dict


def clean_clinical_text(raw_text: str) -> str:
    """Preprocess and normalize raw Vietnamese medical text."""
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

    # 4. Remove Numeric Footnote / Citation brackets e.g. [1], [12], [1-3]
    text = re.sub(r"\[\d+(?:[\s,\-–]\d+)*\]", "", text)

    # 5. Remove Parenthetical Cross-References like (xem bảng 1), (xem phần X)
    text = re.sub(r"\((?:xem\s+(?:bảng|hình|phần|mục|chương)[^\)]*)\)", "", text, flags=re.IGNORECASE)

    # 6. Normalize Multiple Spaces within lines (preserving newlines)
    lines = []
    for line in text.split("\n"):
        clean_line = re.sub(r"[ \t]+", " ", line).strip()
        # Remove trailing standalone reference asterisks e.g. "Người trưởng thành*" -> "Người trưởng thành"
        clean_line = re.sub(r"(?<=\w)\*+$", "", clean_line)
        if clean_line:
            lines.append(clean_line)

    cleaned_text = "\n".join(lines)
    return cleaned_text
