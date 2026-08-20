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
1. **Entity Types (16 loại) & Hướng dẫn phân loại chuẩn xác:**
   - `Disease`: Bệnh lý chính (vd: Tăng huyết áp, Đái tháo đường).
   - `DiseaseSubtype`: Thể bệnh, giai đoạn, phân loại bệnh (vd: Tăng huyết áp nguyên phát, Tăng huyết áp thứ phát, Tăng huyết áp giai đoạn 1, Tăng huyết áp cấp cứu, Tăng huyết áp kháng thuốc, Phì đại thất trái).
   - `Complication`: Biến chứng do bệnh gây ra (vd: Đột quỵ, Nhồi máu cơ tim, Suy tim, Bệnh võng mạc do tăng huyết áp, Bệnh não tăng huyết áp, Bóc tách động mạch chủ).
   - `Cause`: Nguyên nhân / Bệnh lý căn nguyên dẫn đến bệnh khác (vd: Cường aldosteron nguyên phát, Hẹp động mạch thận, Ngưng thở khi ngủ, U tủy thượng thận, Hội chứng Cushing, Hẹp động mạch chủ).
   - `Mechanism`: Cơ chế sinh bệnh học, hoạt chất sinh học, hormone, enzym, peptide tham gia cơ chế (vd: Kích thích thần kinh giao cảm, Kháng insulin, Angiotensin II, Renin, Aldosteron, Norepinephrine, Oxit nitric, Bradykinin, Co thắt phế quản). TUYỆT ĐỐI KHÔNG gán Angiotensin II hay Renin là Measurement!
   - `DrugClass`: Nhóm thuốc điều trị (vd: Thuốc ức chế men chuyển, Thuốc chẹn thụ thể angiotensin, Thuốc chẹn kênh canxi, Thuốc lợi tiểu thiazide, Thuốc chẹn beta, Thuốc đối kháng aldosterone).
   - `Drug`: Tên hoạt chất thuốc cụ thể (vd: Spironolactone, Captopril, Amlodipine, Metformin, Salbutamol).
   - `Treatment`: Biện pháp can thiệp, phẫu thuật, thay đổi hành vi/lối sống (vd: Thay đổi lối sống, Các biện pháp điều trị không dùng thuốc, Giáo dục bệnh nhân, Liệu pháp kích hoạt Baroreflex).
   - `Test`: Kỹ thuật xét nghiệm, thăm dò, đo đạc, tiền sử (vd: ECG, Đo huyết áp, Nghiên cứu giấc ngủ, Khám thực thể, Tiền sử, HbA1c, FEV1).
   - `Measurement`: Chỉ số định lượng / Ngưỡng số đo lâm sàng cụ thể.
     * QUY TẮC BẮT BUỘC VỀ TÊN THỰC THỂ MEASUREMENT: Tên thực thể (`normalized_name`) BẮT BUỘC PHẢI GẮN LIỀN VỚI TÊN THÔNG SỐ / XÉT NGHIỆM ĐO LƯỜNG, TUYỆT ĐỐI KHÔNG ĐƯỢC ĐỂ MỘT CON SỐ TRƠ TRỌI!
       - SAI: `130/80 mmHg`, `> 200 mg/dL`, `5 năm`, `> 65 tuổi`, `100 và 200 mg/dL`, `< 3.5 mmol/L`
       - ĐÚNG: `Huyết áp lúc nghỉ >= 130/80 mmHg`, `Glucose ngẫu nhiên > 200 mg/dL`, `Thời gian sàng lọc biến chứng sau chẩn đoán: 5 năm`, `Độ tuổi: > 65 tuổi`, `Glucose huyết tương duy trì: 100 - 200 mg/dL`, `Nồng độ kali huyết tương < 3.5 mmol/L`, `HbA1c mục tiêu < 6.5%`.
     * Trong trường `attributes`, trích xuất chi tiết: `parameter` (tên thông số đo), `value`, `unit`, `operator`, `systolic`, `diastolic`, `min_value`, `max_value`.
   - `RiskFactor`: Yếu tố nguy cơ (vd: Di truyền, Hút thuốc lá, Béo phì, Thời gian ngủ ngắn, Cam thảo, Ăn nhiều muối).
   - `Organ`: Cơ quan cơ thể (vd: Tim, Thận, Não, Mắt, Phổi, Tuyến thượng thận).
   - `Guideline`: Văn bản hướng dẫn / thang điểm phân loại lâm sàng (vd: ACC/AHA, JNC 8, Keith-Wagener-Barker, GINA, GOLD).

2. **QUY TẮC BẮT BUỘC VỀ EVIDENCE_SPAN (NGUYÊN VĂN 100%):**
   - `evidence_span` của cả Entity và Relation **BẮT BUỘC PHẢI LÀ MỘT CÂU HOẶC ĐOẠN TRÍCH NGUYÊN VĂN 100% CỦA VĂN BẢN ĐANG ĐỌC**.
   - **CẤM TUYỆT ĐỐI**: KHÔNG ĐƯỢC tự ý chèn dấu ba chấm (`...`), KHÔNG ĐƯỢC tự tóm tắt, KHÔNG ĐƯỢC sửa chữ, KHÔNG ĐƯỢC nối dính tiêu đề với câu nội dung. Hãy trích dẫn chính xác nguyên vẹn cả câu chứa thực thể và quan hệ.

3. **Hướng dẫn phân biệt quan hệ chính xác:**
   - Dùng `LEADS_TO`: Khi Bệnh/Nguyên nhân gây ra Biến chứng (Complication) (vd: Tăng huyết áp -> LEADS_TO -> Đột quỵ / Bệnh não tăng huyết áp).
   - Dùng `CAUSES`: Khi Nguyên nhân (Cause) gây ra Bệnh/Thể bệnh (vd: Cường aldosteron -> CAUSES -> Tăng huyết áp thứ phát).
   - Dùng `INCREASES_RISK_OF`: Khi Yếu tố nguy cơ (RiskFactor) làm tăng nguy cơ mắc Bệnh.
   - Dùng `UNDERLIES`: Khi Cơ chế (Mechanism) hoặc hoạt chất tham gia sinh bệnh học của Bệnh.
   - Dùng `AFFECTS_ORGAN`: Khi Bệnh/Biến chứng/Cơ chế gây tổn thương Cơ quan (Organ).
   - Dùng `DEFINES_THRESHOLD_FOR`: Khi Số đo/Ngưỡng (Measurement) định nghĩa tiêu chuẩn chẩn đoán cho Thể bệnh (DiseaseSubtype).
   - Dùng `TREATS`: Khi Thuốc/Nhóm thuốc/Biện pháp can thiệp (Treatment) điều trị Bệnh.
   - Dùng `DIAGNOSES`: Khi Kỹ thuật xét nghiệm (Test) dùng để chẩn đoán Bệnh/Nguyên nhân.
   - Dùng `CLASSIFIES`: Khi Hướng dẫn điều trị (Guideline) phân loại Thể bệnh.

4. **ĐỊNH DẠNG ĐẦU RA:**
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
                            "text": "huyết áp từ 130/80 mmHg",
                            "normalized_name": "Huyết áp xác định chẩn đoán >= 130/80 mmHg",
                            "entity_type": "Measurement",
                            "evidence_span": "Theo hướng dẫn của ACC/AHA, Tăng huyết áp giai đoạn 1 được xác định khi huyết áp từ 130/80 mmHg.",
                            "umls_cui": None,
                            "attributes": {"parameter": "Huyết áp xác định chẩn đoán", "systolic": 130, "diastolic": 80, "unit": "mmHg", "operator": ">="},
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
