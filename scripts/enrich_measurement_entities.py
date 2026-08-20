import json
import sys
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.neo4j_loader import Neo4jLoader
from export.neo4j_exporter import Neo4jExporter

# 1. Measurement Enrichment Mapping for Hypertension
HYPERTENSION_MEASUREMENT_MAPPING = {
    ">= 130 mmhg": {
        "new_name": "Huyết áp tâm thu lúc nghỉ: >= 130 mmHg",
        "parameter": "Huyết áp tâm thu lúc nghỉ",
    },
    ">= 80 mmhg": {
        "new_name": "Huyết áp tâm trương lúc nghỉ: >= 80 mmHg",
        "parameter": "Huyết áp tâm trương lúc nghỉ",
    },
    "< 3,5 mmol/l": {
        "new_name": "Nồng độ kali huyết tương: < 3.5 mmol/L",
        "parameter": "Nồng độ kali huyết tương",
    },
    "10-20 mmhg": {
        "new_name": "Mức giảm huyết áp tư thế: 10 - 20 mmHg",
        "parameter": "Mức giảm huyết áp tư thế",
    },
    "> 15mmhg": {
        "new_name": "Chênh lệch huyết áp giữa 2 tay: > 15 mmHg",
        "parameter": "Chênh lệch huyết áp giữa 2 tay",
    },
    "130/80 mmhg": {
        "new_name": "Huyết áp xác định chẩn đoán THA: 130/80 mmHg",
        "parameter": "Huyết áp xác định chẩn đoán THA",
    },
    "< 1500 mg/ngày": {
        "new_name": "Lượng natri ăn vào mục tiêu: < 1500 mg/ngày",
        "parameter": "Lượng natri ăn vào mục tiêu",
    },
    "<= 2 ly mỗi ngày": {
        "new_name": "Lượng cồn giới hạn ở nam giới: <= 2 ly/ngày",
        "parameter": "Lượng cồn giới hạn ở nam giới",
    },
    "<= 1 ly mỗi ngày": {
        "new_name": "Lượng cồn giới hạn ở nữ giới: <= 1 ly/ngày",
        "parameter": "Lượng cồn giới hạn ở nữ giới",
    },
    "4 loại thuốc trở lên": {
        "new_name": "Số lượng thuốc điều trị THA kháng trị: >= 4 loại thuốc",
        "parameter": "Số lượng thuốc điều trị THA kháng trị",
    },
    "3 loại thuốc hạ huyết áp": {
        "new_name": "Số lượng thuốc phối hợp điều trị: 3 loại thuốc",
        "parameter": "Số lượng thuốc phối hợp điều trị",
    },
    ">= 2 loại thuốc": {
        "new_name": "Số lượng thuốc điều trị ban đầu THA giai đoạn 2: >= 2 loại thuốc",
        "parameter": "Số lượng thuốc điều trị ban đầu",
    },
    "< 10%": {
        "new_name": "Nguy cơ tim mạch 10 năm (ASCVD): < 10%",
        "parameter": "Nguy cơ tim mạch 10 năm",
    },
    "< 5%": {
        "new_name": "Nguy cơ tim mạch 10 năm (ASCVD): < 5%",
        "parameter": "Nguy cơ tim mạch 10 năm",
    },
    "60-65 mmhg": {
        "new_name": "Huyết áp tâm trương mục tiêu tối thiểu: 60 - 65 mmHg",
        "parameter": "Huyết áp tâm trương mục tiêu tối thiểu",
    },
    "120 mmhg": {
        "new_name": "Huyết áp tâm thu bình thường: < 120 mmHg",
        "parameter": "Huyết áp tâm thu bình thường",
    },
    "> 5 phút": {
        "new_name": "Thời gian nghỉ trước khi đo huyết áp: > 5 phút",
        "parameter": "Thời gian nghỉ trước khi đo huyết áp",
    },
    "< 30 tuổi": {
        "new_name": "Độ tuổi nghi ngờ THA thứ phát: < 30 tuổi",
        "parameter": "Độ tuổi nghi ngờ THA thứ phát",
    },
    "> 65 tuổi": {
        "new_name": "Độ tuổi người cao tuổi mắc THA: > 65 tuổi",
        "parameter": "Độ tuổi người cao tuổi",
    },
    "> 80%": {
        "new_name": "Kích thước túi khí vòng bít bao quanh cánh tay: > 80%",
        "parameter": "Kích thước túi khí vòng bít",
    },
    ">= 40%": {
        "new_name": "Chiều rộng túi khí vòng bít so với chu vi cánh tay: >= 40%",
        "parameter": "Chiều rộng túi khí vòng bít",
    },
}

# 2. Measurement Enrichment Mapping for Diabetes
DIABETES_MEASUREMENT_MAPPING = {
    "100 và 200 mg/dl": {
        "new_name": "Glucose huyết tương duy trì mục tiêu: 100 - 200 mg/dL",
        "parameter": "Glucose huyết tương duy trì mục tiêu",
    },
    "5 năm": {
        "new_name": "Thời gian sàng lọc biến chứng sau chẩn đoán ĐTĐ Type 1: 5 năm",
        "parameter": "Thời gian sàng lọc biến chứng sau chẩn đoán",
    },
    "90 mg/dl đến 250 mg/dl": {
        "new_name": "Đường huyết mục tiêu trước tập thể dục: 90 - 250 mg/dL",
        "parameter": "Đường huyết mục tiêu trước tập thể dục",
    },
    "< 130/80 mm hg": {
        "new_name": "Huyết áp mục tiêu ở bệnh nhân đái tháo đường: < 130/80 mmHg",
        "parameter": "Huyết áp mục tiêu ở bệnh nhân đái tháo đường",
    },
    "> 200 mg/dl (> 11,1 mmol/l)": {
        "new_name": "Glucose huyết tương ngẫu nhiên chẩn đoán ĐTĐ: > 200 mg/dL",
        "parameter": "Glucose huyết tương ngẫu nhiên",
    },
    "> 250 đến 300 mg/dl [13,9 đến 16,7 mmol/l]": {
        "new_name": "Ngưỡng tăng đường huyết không ổn định: > 250 - 300 mg/dL",
        "parameter": "Ngưỡng tăng đường huyết không ổn định",
    },
    "> 65 tuổi": {
        "new_name": "Độ tuổi mắc suy giảm dung nạp glucose: > 65 tuổi",
        "parameter": "Độ tuổi mắc suy giảm dung nạp glucose",
    },
    "> 90%": {
        "new_name": "Tỷ lệ mang gen nhạy cảm HLA ở ĐTĐ Type 1: > 90%",
        "parameter": "Tỷ lệ mang gen nhạy cảm HLA",
    },
    "hba1c < 6,5%": {
        "new_name": "HbA1c mục tiêu kiểm soát chặt chẽ: < 6.5%",
        "parameter": "HbA1c mục tiêu kiểm soát chặt chẽ",
    },
    "3 tháng một lần": {
        "new_name": "Tần suất theo dõi HbA1c định kỳ: 3 tháng một lần",
        "parameter": "Tần suất theo dõi HbA1c",
    },
    "6 tháng một lần": {
        "new_name": "Tần suất theo dõi HbA1c khi kiểm soát tốt: 6 tháng một lần",
        "parameter": "Tần suất theo dõi HbA1c khi kiểm soát tốt",
    },
    "< 4%": {
        "new_name": "Thời gian CGM dưới ngưỡng mục tiêu (TBR): < 4%",
        "parameter": "Thời gian CGM dưới ngưỡng mục tiêu (TBR)",
    },
    "lượng đường trong máu": {
        "new_name": "Chỉ số lượng đường trong máu",
        "parameter": "Lượng đường trong máu",
    },
}


def enrich_graph_payload(json_path: Path, mapping: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """Enrich Measurement entities with full parameter names and attributes in the graph json."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entities = data.get("entities", [])
    for ent in entities:
        norm_lower = ent.get("normalized_name", "").strip().lower()
        text_lower = ent.get("text", "").strip().lower()

        matched_info = mapping.get(norm_lower) or mapping.get(text_lower)
        if matched_info:
            ent["normalized_name"] = matched_info["new_name"]
            ent["entity_type"] = "Measurement"
            ent["umls_cui"] = None
            ent["umls_sty"] = None
            ent["umls_tui"] = None
            ent["match_tier"] = "Quantitative_Measurement"

            attrs = ent.get("attributes") or {}
            attrs["parameter"] = matched_info["parameter"]
            ent["attributes"] = attrs

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def main():
    print("Enriching Measurement entities for Hypertension and Diabetes...")

    # 1. Process Hypertension
    ht_path = Path("data/processed/hypertension/01_tanghuyetap_graph_final.json")
    if ht_path.exists():
        ht_data = enrich_graph_payload(ht_path, HYPERTENSION_MEASUREMENT_MAPPING)
        print(f"Enriched {len(ht_data['entities'])} entities for Hypertension.")

    # 2. Process Diabetes
    db_path = Path("data/processed/diabetes/01_daithaoduong_graph_final.json")
    if db_path.exists():
        db_data = enrich_graph_payload(db_path, DIABETES_MEASUREMENT_MAPPING)
        print(f"Enriched {len(db_data['entities'])} entities for Diabetes.")

    # 3. Ingest into Neo4j
    print("\nRefreshing Neo4j Knowledge Graph...")
    loader = Neo4jLoader()

    if ht_path.exists():
        loader.ingest_graph(ht_data["entities"], ht_data["relations"], source_doc="01_tanghuyetap.txt")
        print("Ingested Hypertension into Neo4j.")

    if db_path.exists():
        loader.ingest_graph(db_data["entities"], db_data["relations"], source_doc="01_daithaoduong.txt")
        print("Ingested Diabetes into Neo4j.")

    loader.close()

    # 4. Re-export CSVs
    print("\nRe-exporting all CSVs with rich parameter attributes...")
    exporter = Neo4jExporter()

    if ht_path.exists():
        exporter.export_all_to_csv("data/exports", source_doc="01_tanghuyetap.txt", category="hypertension")
        print("Exported Hypertension CSVs.")

    if db_path.exists():
        exporter.export_all_to_csv("data/exports", source_doc="01_daithaoduong.txt", category="diabetes")
        print("Exported Diabetes CSVs.")

    exporter.close()
    print("\n=== ALL ENRICHMENTS AND EXPORTS COMPLETED SUCCESSFULLY! ===")


if __name__ == "__main__":
    main()
