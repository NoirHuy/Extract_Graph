import pytest
from extraction.text_chunker import chunk_vietnamese_text, TextChunk

def test_chunking_with_headings_and_overlap():
    sample_text = """
1. Định nghĩa và Phân loại
Tăng huyết áp là bệnh lý mạn tính nguy hiểm. Bệnh được chia thành độ 1 và độ 2. Ngưỡng chẩn đoán là 130/80 mmHg.

2. Nguyên nhân
Nguyên nhân bao gồm cường aldosteron và hẹp động mạch thận. Cường aldosteron làm giữ muối nước gây tăng áp lực.

3. Điều trị
Sử dụng thuốc ức chế men chuyển. Thuốc giúp hạ áp hiệu quả.
"""
    chunks = chunk_vietnamese_text(sample_text.strip(), max_chunk_chars=200, overlap_sentences=1)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert isinstance(chunk, TextChunk)
        assert len(chunk.text) > 0
        assert chunk.section_title != ""

def test_plain_text_with_markdown_headers():
    md_text = """
# Tăng Huyết Áp

## Dấu hiệu lâm sàng
Bệnh nhân thường không có triệu chứng rõ ràng. Một số trường hợp có đau đầu hoặc chóng mặt khi huyết áp tăng cao.

## Chẩn đoán
Đo huyết áp đúng quy trình tại phòng khám. Cần đo lặp lại ít nhất hai lần ở các thời điểm khác nhau.
"""
    chunks = chunk_vietnamese_text(md_text.strip(), max_chunk_chars=500, overlap_sentences=1)
    assert len(chunks) >= 1
    assert any("Dấu hiệu lâm sàng" in c.section_title or "Chẩn đoán" in c.section_title for c in chunks)

def test_no_header_fallback():
    raw_text = "Đây là câu thứ nhất. Đây là câu thứ hai. Đây là câu thứ ba dài hơn một chút. Đây là câu thứ tư kết thúc đoạn."
    chunks = chunk_vietnamese_text(raw_text, max_chunk_chars=100, overlap_sentences=1)
    assert len(chunks) >= 2
    assert chunks[0].section_title == "General"
