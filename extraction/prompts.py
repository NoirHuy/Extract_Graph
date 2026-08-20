"""Prompts, Few-Shot Examples and Negative Guidelines for Medical Knowledge Graph Extraction."""

import json
from typing import Any, Dict, List
from schema.schema_registry import get_edc_json_schema


def get_extraction_system_prompt() -> str:
    """Generate system prompt containing schema rules, constraints, and JSON schema contract."""
    schema = get_edc_json_schema()
    schema_str = json.dumps(schema, ensure_ascii=False, indent=2)

    return f"""Bạn là một chuyên gia AI & Bác sĩ Y khoa chuyên trích xuất Knowledge Graph từ tài liệu lâm sàng tiếng Việt.
Nhiệm vụ của bạn là đọc kỹ đoạn văn bản y khoa được cung cấp, trích xuất chính xác các Thực thể (Entities) và Quan hệ (Relations) tuân thủ chặt chẽ Extraction Data Contract (EDC).

### QUY TẮC RÀNG BUỘC VÀ HƯỚNG DẪN QUAN HỆ:
1. **Entity Types (16 loại):**
   - Disease, DiseaseSubtype, Symptom, Sign, RiskFactor, Cause, Mechanism, Complication, Test, Measurement, Drug, DrugClass, Treatment, Organ, PatientGroup, Guideline.
2. **Hướng dẫn phân biệt quan hệ chính xác (Tránh nhầm lẫn):**
   - Dùng `LEADS_TO`: Khi một Bệnh (Disease/DiseaseSubtype) hoặc Nguyên nhân (Cause) gây ra hoặc dẫn đến một Biến chứng (Complication) (vd: Tăng huyết áp -> LEADS_TO -> Đột quỵ).
   - Dùng `INCREASES_RISK_OF`: Khi một Yếu tố nguy cơ (RiskFactor) hoặc Bệnh lý nền làm gia tăng nguy cơ mắc Bệnh/Biến chứng.
   - Dùng `UNDERLIES`: Khi một Cơ chế sinh lý bệnh (Mechanism) hoặc Nguyên nhân (Cause) là cơ sở sinh bệnh học của Bệnh (vd: Tăng tái hấp thu natri -> UNDERLIES -> Tăng huyết áp).
   - Dùng `AFFECTS_ORGAN`: Khi Bệnh (Disease), Biến chứng (Complication) hoặc Cơ chế (Mechanism) gây tổn thương hoặc diễn ra tại một Cơ quan (Organ) (vd: Tổn thương -> AFFECTS_ORGAN -> Tim/Thận/Não).
   - Dùng `DEFINES_THRESHOLD_FOR`: Khi một Số đo/Ngưỡng (Measurement) định nghĩa tiêu chuẩn chẩn đoán cho Thể bệnh (DiseaseSubtype) (vd: 130/80 mmHg -> DEFINES_THRESHOLD_FOR -> Tăng huyết áp giai đoạn 1).
   - Dùng `TREATS`: Khi Thuốc (Drug), Nhóm thuốc (DrugClass) hoặc Biện pháp điều trị (Treatment) dùng để điều trị Bệnh.
   - Dùng `CLASSIFIES`: Khi Hướng dẫn điều trị (Guideline) phân loại Thể bệnh (DiseaseSubtype).
3. **Thuộc tính thực thể:**
   - `id`: Định danh duy nhất trong đoạn trích (vd: "e1", "e2", ...)
   - `text`: Từ/cụm từ nguyên văn xuất hiện trong văn bản
   - `normalized_name`: Tên thực thể chuẩn hóa (bằng tiếng Việt có dấu, viết hoa chữ cái đầu hoặc thuật ngữ y khoa)
   - `entity_type`: Thuộc 1 trong 16 loại trên
   - `evidence_span`: Câu/cụm câu nguyên văn trong văn bản chứa thực thể này (DÙNG CHO TRUY VẾT, KHÔNG TỰ DIỄN GIẢI)
   - `umls_cui`: Luôn để giá trị `null` (xử lý ở module riêng)
   - `attributes`: Đối tượng chứa các thuộc tính bổ sung. Riêng `Measurement` cần trích xuất rõ các số đo nếu có (vd: {{"systolic": 130, "diastolic": 80, "unit": "mmHg"}})
4. **Thuộc tính quan hệ:**
   - `source_id`, `target_id`: ID của thực thể nguồn và đích
   - `relation_type`: Thuộc 1 trong 19 quan hệ trên
   - `confidence`: Điểm tin cậy (0.0 đến 1.0)
   - `evidence_span`: Câu nguyên văn chứng minh quan hệ này
5. **ĐỊNH DẠNG ĐẦU RA:**
   - Chỉ trả về duy nhất một chuỗi JSON hợp lệ tuân theo JSON Schema bên dưới.
   - KHÔNG bọc chuỗi trong markdown fence ```json hoặc giải thích thêm bất kỳ điều gì.

JSON SCHEMA:
{schema_str}
"""


def get_few_shot_examples() -> List[Dict[str, Any]]:
    """Return few-shot demonstration examples for clinical hypertension extraction."""
    return [
        {
            "role": "user",
            "content": "VĂN BẢN LÂM SÀNG:\nTheo hướng dẫn của ACC/AHA, Tăng huyết áp giai đoạn 1 được xác định khi huyết áp từ 130/80 mmHg. Cường aldosteron nguyên phát làm tăng tái hấp thu natri tại ống thận, là một nguyên nhân gây Tăng huyết áp thứ phát. Thuốc ức chế men chuyển (ACE inhibitor) điều trị hiệu quả Tăng huyết áp và làm giảm nguy cơ Đột quỵ gây tổn thương Não.",
        },
        {
            "role": "assistant",
            "content": json.dumps(
                {
                    "entities": [
                        {
                            "id": "e1",
                            "text": "ACC/AHA",
                            "normalized_name": "ACC/AHA",
                            "entity_type": "Guideline",
                            "evidence_span": "Theo hướng dẫn của ACC/AHA, Tăng huyết áp giai đoạn 1 được xác định khi huyết áp từ 130/80 mmHg.",
                            "umls_cui": None,
                            "attributes": {},
                        },
                        {
                            "id": "e2",
                            "text": "Tăng huyết áp giai đoạn 1",
                            "normalized_name": "Tăng huyết áp giai đoạn 1",
                            "entity_type": "DiseaseSubtype",
                            "evidence_span": "Theo hướng dẫn của ACC/AHA, Tăng huyết áp giai đoạn 1 được xác định khi huyết áp từ 130/80 mmHg.",
                            "umls_cui": None,
                            "attributes": {},
                        },
                        {
                            "id": "e3",
                            "text": "130/80 mmHg",
                            "normalized_name": "130/80 mmHg",
                            "entity_type": "Measurement",
                            "evidence_span": "Theo hướng dẫn của ACC/AHA, Tăng huyết áp giai đoạn 1 được xác định khi huyết áp từ 130/80 mmHg.",
                            "umls_cui": None,
                            "attributes": {"systolic": 130, "diastolic": 80, "unit": "mmHg"},
                        },
                        {
                            "id": "e4",
                            "text": "Cường aldosteron nguyên phát",
                            "normalized_name": "Cường aldosteron nguyên phát",
                            "entity_type": "Cause",
                            "evidence_span": "Cường aldosteron nguyên phát làm tăng tái hấp thu natri tại ống thận, là một nguyên nhân gây Tăng huyết áp thứ phát.",
                            "umls_cui": None,
                            "attributes": {},
                        },
                        {
                            "id": "e5",
                            "text": "tăng tái hấp thu natri",
                            "normalized_name": "Tăng tái hấp thu natri",
                            "entity_type": "Mechanism",
                            "evidence_span": "Cường aldosteron nguyên phát làm tăng tái hấp thu natri tại ống thận, là một nguyên nhân gây Tăng huyết áp thứ phát.",
                            "umls_cui": None,
                            "attributes": {},
                        },
                        {
                            "id": "e6",
                            "text": "Tăng huyết áp thứ phát",
                            "normalized_name": "Tăng huyết áp thứ phát",
                            "entity_type": "DiseaseSubtype",
                            "evidence_span": "Cường aldosteron nguyên phát làm tăng tái hấp thu natri tại ống thận, là một nguyên nhân gây Tăng huyết áp thứ phát.",
                            "umls_cui": None,
                            "attributes": {},
                        },
                        {
                            "id": "e7",
                            "text": "Thuốc ức chế men chuyển (ACE inhibitor)",
                            "normalized_name": "ACE inhibitor",
                            "entity_type": "DrugClass",
                            "evidence_span": "Thuốc ức chế men chuyển (ACE inhibitor) điều trị hiệu quả Tăng huyết áp và làm giảm nguy cơ Đột quỵ gây tổn thương Não.",
                            "umls_cui": None,
                            "attributes": {},
                        },
                        {
                            "id": "e8",
                            "text": "Tăng huyết áp",
                            "normalized_name": "Tăng huyết áp",
                            "entity_type": "Disease",
                            "evidence_span": "Thuốc ức chế men chuyển (ACE inhibitor) điều trị hiệu quả Tăng huyết áp và làm giảm nguy cơ Đột quỵ gây tổn thương Não.",
                            "umls_cui": None,
                            "attributes": {},
                        },
                        {
                            "id": "e9",
                            "text": "Đột quỵ",
                            "normalized_name": "Đột quỵ",
                            "entity_type": "Complication",
                            "evidence_span": "Thuốc ức chế men chuyển (ACE inhibitor) điều trị hiệu quả Tăng huyết áp và làm giảm nguy cơ Đột quỵ gây tổn thương Não.",
                            "umls_cui": None,
                            "attributes": {},
                        },
                        {
                            "id": "e10",
                            "text": "Não",
                            "normalized_name": "Não",
                            "entity_type": "Organ",
                            "evidence_span": "Thuốc ức chế men chuyển (ACE inhibitor) điều trị hiệu quả Tăng huyết áp và làm giảm nguy cơ Đột quỵ gây tổn thương Não.",
                            "umls_cui": None,
                            "attributes": {},
                        },
                    ],
                    "relations": [
                        {
                            "source_id": "e1",
                            "target_id": "e2",
                            "relation_type": "CLASSIFIES",
                            "evidence_span": "Theo hướng dẫn của ACC/AHA, Tăng huyết áp giai đoạn 1 được xác định khi huyết áp từ 130/80 mmHg.",
                            "confidence": 0.95,
                        },
                        {
                            "source_id": "e3",
                            "target_id": "e2",
                            "relation_type": "DEFINES_THRESHOLD_FOR",
                            "evidence_span": "Theo hướng dẫn của ACC/AHA, Tăng huyết áp giai đoạn 1 được xác định khi huyết áp từ 130/80 mmHg.",
                            "confidence": 0.95,
                        },
                        {
                            "source_id": "e4",
                            "target_id": "e5",
                            "relation_type": "PART_OF_MECHANISM",
                            "evidence_span": "Cường aldosteron nguyên phát làm tăng tái hấp thu natri tại ống thận",
                            "confidence": 0.95,
                        },
                        {
                            "source_id": "e4",
                            "target_id": "e6",
                            "relation_type": "CAUSES",
                            "evidence_span": "Cường aldosteron nguyên phát là một nguyên nhân gây Tăng huyết áp thứ phát.",
                            "confidence": 0.95,
                        },
                        {
                            "source_id": "e5",
                            "target_id": "e6",
                            "relation_type": "UNDERLIES",
                            "evidence_span": "tăng tái hấp thu natri tại ống thận, là một nguyên nhân gây Tăng huyết áp thứ phát.",
                            "confidence": 0.95,
                        },
                        {
                            "source_id": "e7",
                            "target_id": "e8",
                            "relation_type": "TREATS",
                            "evidence_span": "Thuốc ức chế men chuyển (ACE inhibitor) điều trị hiệu quả Tăng huyết áp",
                            "confidence": 0.95,
                        },
                        {
                            "source_id": "e8",
                            "target_id": "e9",
                            "relation_type": "LEADS_TO",
                            "evidence_span": "Tăng huyết áp và làm giảm nguy cơ Đột quỵ",
                            "confidence": 0.95,
                        },
                        {
                            "source_id": "e9",
                            "target_id": "e10",
                            "relation_type": "AFFECTS_ORGAN",
                            "evidence_span": "Đột quỵ gây tổn thương Não.",
                            "confidence": 0.95,
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
        }
    ]
