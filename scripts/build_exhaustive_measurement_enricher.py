import json
import sys
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.neo4j_loader import Neo4jLoader
from export.neo4j_exporter import Neo4jExporter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def infer_parameter_from_context(name: str, span: str, attrs: Dict[str, Any], doc_type: str) -> Dict[str, str]:
    """Smartly infer full self-describing name and parameter name from clinical context."""
    n_low = name.lower()
    s_low = span.lower()

    # 1. Diabetes measurements
    if "cholesterol" in s_low or "hdl" in n_low or "hdl" in s_low:
        if "< 35" in n_low or "< 35" in s_low:
            return {"new_name": "Mức HDL cholesterol: < 35 mg/dL (0.9 mmol/L)", "parameter": "Mức HDL cholesterol"}
    if "chất béo trung tính" in s_low or "triglyceride" in s_low or "250 mg" in n_low:
        if "> 250" in n_low or "> 250" in s_low:
            return {"new_name": "Mức chất béo trung tính (Triglyceride): > 250 mg/dL (2.8 mmol/L)", "parameter": "Mức chất béo trung tính (Triglyceride)"}

    if "carbohydrate-to-insulin" in s_low or "cir" in s_low or "15 gram:1" in n_low or "15 g" in s_low:
        return {"new_name": "Tỷ lệ Carbohydrate-to-Insulin (CIR): 15g : 1 đơn vị", "parameter": "Tỷ lệ Carbohydrate-to-Insulin (CIR)"}

    if "tự kháng thể" in n_low or "tự kháng thể" in s_low:
        return {"new_name": "Số lượng tự kháng thể hiện diện: >= 2 tự kháng thể", "parameter": "Số lượng tự kháng thể"}

    if "chỉ số khối cơ thể" in n_low or "bmi" in n_low or "bmi" in s_low or "khối cơ thể" in s_low:
        return {"new_name": "Chỉ số khối cơ thể (BMI) nguy cơ cao: >= 35 kg/m2", "parameter": "Chỉ số khối cơ thể (BMI)"}

    if "hba1c" in n_low or "hba1c" in s_low:
        if "< 7" in n_low or "<7" in n_low or "<7%" in s_low or "< 7%" in s_low:
            return {"new_name": "HbA1c mục tiêu chung: < 7.0%", "parameter": "HbA1c mục tiêu"}
        if "< 6,5" in n_low or "< 6.5" in n_low or "< 6,5%" in s_low:
            return {"new_name": "HbA1c mục tiêu kiểm soát chặt chẽ: < 6.5%", "parameter": "HbA1c mục tiêu"}
        if "1,5" in n_low or "2,0" in n_low or "1.5" in s_low:
            return {"new_name": "Mức chênh lệch HbA1c cao hơn mục tiêu: 1.5 - 2.0%", "parameter": "Mức chênh lệch HbA1c"}
        if "3 tháng" in n_low or "3 tháng" in s_low:
            return {"new_name": "Tần suất theo dõi HbA1c định kỳ: 3 tháng một lần", "parameter": "Tần suất theo dõi HbA1c"}
        if "6 tháng" in n_low or "6 tháng" in s_low:
            return {"new_name": "Tần suất theo dõi HbA1c khi kiểm soát tốt: 6 tháng một lần", "parameter": "Tần suất theo dõi HbA1c"}

    if "tir" in n_low or "trong khoảng" in s_low or "target range" in n_low:
        if "> 70" in n_low or "> 70" in s_low:
            return {"new_name": "Thời gian đường huyết trong khoảng mục tiêu (TIR 14 ngày): > 70%", "parameter": "Thời gian đường huyết trong khoảng mục tiêu (TIR)"}
        if "70 đến 180" in s_low or "70-180" in s_low or "target range" in n_low:
            return {"new_name": "Phạm vi đường huyết mục tiêu trên CGM (TIR): 70 - 180 mg/dL (3.9 - 9.9 mmol/L)", "parameter": "Phạm vi đường huyết mục tiêu trên CGM"}

    if "tbr" in n_low or "dưới mức" in s_low or "dưới 54" in s_low or "hypoglycemia" in n_low or "< 4%" in n_low or "< 3.0" in n_low:
        if "< 4%" in n_low or "< 70 mg/dl" in s_low:
            return {"new_name": "Thời gian CGM dưới ngưỡng mục tiêu (TBR < 70 mg/dL): < 4%", "parameter": "Thời gian CGM dưới ngưỡng mục tiêu (TBR)"}
        if "< 3.0" in n_low or "< 1%" in s_low or "54 mg" in s_low:
            return {"new_name": "Thời gian hạ đường huyết nghiêm trọng trên CGM (< 54 mg/dL): < 1%", "parameter": "Thời gian hạ đường huyết nghiêm trọng trên CGM"}

    if "sau ăn" in s_low or "180 mg/dl" in n_low:
        return {"new_name": "Đỉnh glucose máu sau ăn (1 - 2 giờ): < 180 mg/dL (10.0 mmol/L)", "parameter": "Đỉnh glucose máu sau ăn"}

    if "sucrose" in n_low or "5-15g" in n_low or "carbohydrate trong thời gian tập" in s_low:
        return {"new_name": "Lượng đường hấp thu nhanh xử trí hạ đường huyết: 5 - 15 g sucrose", "parameter": "Lượng đường hấp thu nhanh xử trí hạ đường huyết"}

    if "truyền" in s_low or "dextrose" in s_low or "đơn vị/giờ" in s_low or "ml/giờ" in s_low:
        if "1-2" in n_low or "unit" in n_low or "đơn vị" in n_low:
            return {"new_name": "Tốc độ truyền insulin tĩnh mạch: 1 - 2 đơn vị/giờ", "parameter": "Tốc độ truyền insulin tĩnh mạch"}
        if "5%" in n_low or "dextrose" in n_low:
            return {"new_name": "Nồng độ dung dịch Dextrose truyền kèm: 5% Dextrose", "parameter": "Nồng độ dung dịch Dextrose truyền kèm"}
        if "75-150" in n_low or "ml" in n_low:
            return {"new_name": "Tốc độ truyền dung dịch Dextrose: 75 - 150 mL/giờ", "parameter": "Tốc độ truyền dung dịch Dextrose"}

    if "48 giờ" in n_low or "48 tiếng" in s_low:
        return {"new_name": "Thời gian tạm ngừng metformin sau phẫu thuật: 48 giờ", "parameter": "Thời gian tạm ngừng metformin sau phẫu thuật"}

    if "lần một ngày" in s_low or "lần/ngày" in n_low or "4 lần" in s_low or "5 lần" in s_low:
        if "4" in n_low or "4 lần" in s_low:
            return {"new_name": "Tần suất tự kiểm tra đường huyết ở ĐTĐ Type 1: >= 4 lần/ngày", "parameter": "Tần suất tự kiểm tra đường huyết"}
        if "5" in n_low or "5 lần" in s_low:
            return {"new_name": "Tần suất theo dõi đường huyết khi dùng CGM/chích ngón: 1 đến >= 5 lần/ngày", "parameter": "Tần suất theo dõi đường huyết"}

    if "5 năm" in n_low or "5 năm" in s_low:
        return {"new_name": "Thời gian sàng lọc biến chứng sau chẩn đoán: 5 năm", "parameter": "Thời gian sàng lọc biến chứng sau chẩn đoán"}

    if "90" in n_low and "250" in n_low:
        return {"new_name": "Đường huyết mục tiêu trước tập thể dục: 90 - 250 mg/dL (5 - 14 mmol/L)", "parameter": "Đường huyết mục tiêu trước tập thể dục"}

    if "100" in n_low and "200" in n_low:
        return {"new_name": "Glucose huyết tương duy trì mục tiêu nội trú: 100 - 200 mg/dL (5.5 - 11.1 mmol/L)", "parameter": "Glucose huyết tương duy trì mục tiêu nội trú"}

    if "200 mg/dl" in n_low or "11,1 mmol" in n_low or "ngẫu nhiên" in s_low:
        return {"new_name": "Glucose huyết tương ngẫu nhiên chẩn đoán ĐTĐ: >= 200 mg/dL (11.1 mmol/L)", "parameter": "Glucose huyết tương ngẫu nhiên chẩn đoán ĐTĐ"}

    if "250" in n_low and "300" in n_low:
        return {"new_name": "Ngưỡng tăng đường huyết không ổn định: > 250 - 300 mg/dL (13.9 - 16.7 mmol/L)", "parameter": "Ngưỡng tăng đường huyết không ổn định"}

    if "> 65 tuổi" in n_low or "65 tuổi" in s_low:
        return {"new_name": "Độ tuổi có tỷ lệ suy giảm dung nạp glucose cao: > 65 tuổi", "parameter": "Độ tuổi có tỷ lệ suy giảm dung nạp glucose cao"}

    if "> 90%" in n_low or "90%" in s_low:
        return {"new_name": "Tỷ lệ hiện diện gen HLA nhạy cảm ở ĐTĐ Type 1: > 90%", "parameter": "Tỷ lệ hiện diện gen HLA nhạy cảm"}

    if "lượng đường trong máu" in n_low:
        return {"new_name": "Chỉ số nồng độ đường trong máu (Glucose máu)", "parameter": "Chỉ số nồng độ đường trong máu"}

    # 2. Hypertension measurements
    if "130/80" in n_low or "130 mm hg" in n_low or "130 mmhg" in n_low:
        if "tâm thu" in s_low or "systolic" in str(attrs):
            return {"new_name": "Huyết áp tâm thu lúc nghỉ xác định THA: >= 130 mmHg", "parameter": "Huyết áp tâm thu lúc nghỉ"}
        if "< 130/80" in n_low or "mục tiêu" in s_low:
            return {"new_name": "Huyết áp mục tiêu ở bệnh nhân đái tháo đường: < 130/80 mmHg", "parameter": "Huyết áp mục tiêu"}
        return {"new_name": "Huyết áp xác định chẩn đoán THA: >= 130/80 mmHg", "parameter": "Huyết áp xác định chẩn đoán THA"}

    if "80 mm hg" in n_low or "80 mmhg" in n_low:
        return {"new_name": "Huyết áp tâm trương lúc nghỉ xác định THA: >= 80 mmHg", "parameter": "Huyết áp tâm trương lúc nghỉ"}

    if "3,5 mmol" in n_low or "3.5 mmol" in n_low or "kali" in s_low:
        return {"new_name": "Nồng độ kali huyết tương: < 3.5 mmol/L", "parameter": "Nồng độ kali huyết tương"}

    if "10-20" in n_low:
        return {"new_name": "Mức giảm huyết áp tư thế: 10 - 20 mmHg", "parameter": "Mức giảm huyết áp tư thế"}

    if "15mmhg" in n_low or "15 mm hg" in n_low:
        return {"new_name": "Chênh lệch huyết áp giữa 2 tay: > 15 mmHg", "parameter": "Chênh lệch huyết áp giữa 2 tay"}

    if "1500 mg" in n_low:
        return {"new_name": "Lượng natri ăn vào mục tiêu: < 1500 mg/ngày", "parameter": "Lượng natri ăn vào mục tiêu"}

    if "2 ly" in n_low:
        return {"new_name": "Lượng cồn giới hạn ở nam giới: <= 2 ly/ngày", "parameter": "Lượng cồn giới hạn ở nam giới"}

    if "1 ly" in n_low:
        return {"new_name": "Lượng cồn giới hạn ở nữ giới: <= 1 ly/ngày", "parameter": "Lượng cồn giới hạn ở nữ giới"}

    if "4 loại thuốc" in n_low:
        return {"new_name": "Số lượng thuốc điều trị THA kháng trị: >= 4 loại thuốc", "parameter": "Số lượng thuốc điều trị THA kháng trị"}

    if "3 loại thuốc" in n_low:
        return {"new_name": "Số lượng thuốc phối hợp điều trị THA: 3 loại thuốc", "parameter": "Số lượng thuốc phối hợp điều trị THA"}

    if "2 loại thuốc" in n_low:
        return {"new_name": "Số lượng thuốc điều trị ban đầu THA giai đoạn 2: >= 2 loại thuốc", "parameter": "Số lượng thuốc điều trị ban đầu"}

    if "10%" in n_low:
        return {"new_name": "Nguy cơ tim mạch 10 năm (ASCVD): < 10%", "parameter": "Nguy cơ tim mạch 10 năm"}

    if "5%" in n_low:
        return {"new_name": "Nguy cơ tim mạch 10 năm (ASCVD): < 5%", "parameter": "Nguy cơ tim mạch 10 năm"}

    if "60-65" in n_low:
        return {"new_name": "Huyết áp tâm trương mục tiêu tối thiểu: 60 - 65 mmHg", "parameter": "Huyết áp tâm trương mục tiêu tối thiểu"}

    if "120 mmhg" in n_low:
        return {"new_name": "Huyết áp tâm thu bình thường: < 120 mmHg", "parameter": "Huyết áp tâm thu bình thường"}

    if "5 phút" in n_low:
        return {"new_name": "Thời gian nghỉ trước khi đo huyết áp: > 5 phút", "parameter": "Thời gian nghỉ trước khi đo huyết áp"}

    if "30 tuổi" in n_low:
        return {"new_name": "Độ tuổi nghi ngờ THA thứ phát: < 30 tuổi", "parameter": "Độ tuổi nghi ngờ THA thứ phát"}

    if "80%" in n_low:
        return {"new_name": "Kích thước túi khí vòng bít bao quanh cánh tay: > 80%", "parameter": "Kích thước túi khí vòng bít"}

    if "40%" in n_low:
        return {"new_name": "Chiều rộng túi khí vòng bít so với chu vi cánh tay: >= 40%", "parameter": "Chiều rộng túi khí vòng bít"}

    # Default fallback
    clean_param = name
    for sym in ["<", ">", ">=", "<=", "==", ":", "="]:
        clean_param = clean_param.replace(sym, "")
    return {"new_name": name, "parameter": f"Chỉ số {clean_param.strip()}"}


def process_file(json_path: Path, doc_type: str):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ents = data.get("entities", [])
    enriched_count = 0

    for e in ents:
        is_measurement = (
            e.get("entity_type") == "Measurement"
            or any(c.isdigit() for c in e.get("normalized_name", ""))
            or any(op in e.get("normalized_name", "") for op in ["<", ">", ">=", "<=", "%"])
        )
        # Exempt named guidelines, genes, virus
        name = e.get("normalized_name", "")
        if any(ex in name for ex in ["ACC/AHA", "HLA-", "SARS-", "Type 1", "loại 1", "loại 2", "Giai đoạn 1", "giai đoạn 2"]):
            continue

        if is_measurement:
            inferred = infer_parameter_from_context(
                name,
                e.get("evidence_span", ""),
                e.get("attributes") or {},
                doc_type
            )
            e["normalized_name"] = inferred["new_name"]
            e["entity_type"] = "Measurement"
            e["umls_cui"] = None
            e["umls_sty"] = None
            e["umls_tui"] = None
            e["match_tier"] = "Quantitative_Measurement"

            attrs = e.get("attributes") or {}
            attrs["parameter"] = inferred["parameter"]
            e["attributes"] = attrs
            enriched_count += 1

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Processed {json_path.name}: Enriched {enriched_count} Measurement entities.")
    return data


def main():
    print("=== EXHAUSTIVE CLINICAL MEASUREMENT ENRICHMENT ===")

    ht_path = Path("data/processed/hypertension/01_tanghuyetap_graph_final.json")
    db_path = Path("data/processed/diabetes/01_daithaoduong_graph_final.json")

    ht_data = process_file(ht_path, "hypertension")
    db_data = process_file(db_path, "diabetes")

    print("\nRefreshing Neo4j Database...")
    loader = Neo4jLoader()
    loader.ingest_graph(ht_data["entities"], ht_data["relations"], source_doc="01_tanghuyetap.txt")
    loader.ingest_graph(db_data["entities"], db_data["relations"], source_doc="01_daithaoduong.txt")
    loader.close()
    print("Ingested both documents cleanly into Neo4j.")

    print("\nRe-exporting all CSV files...")
    exporter = Neo4jExporter()
    exporter.export_all_to_csv("data/exports", source_doc="01_tanghuyetap.txt", category="hypertension")
    exporter.export_all_to_csv("data/exports", source_doc="01_daithaoduong.txt", category="diabetes")
    exporter.close()
    print("Exported all CSVs successfully!")


if __name__ == "__main__":
    main()
