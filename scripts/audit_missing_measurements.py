import csv
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def audit_category(cat: str):
    csv_path = Path(f"data/exports/{cat}/clinical_knowledge_summary.csv")
    print(f"\n=======================================================")
    print(f"             AUDITING {cat.upper()} CSV")
    print(f"=======================================================")
    
    missing_count = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        for i, row in enumerate(reader, 1):
            s_name = row["Thực thể nguồn (Source)"]
            s_type = row["Loại nguồn (Type)"]
            s_attr = row["Chỉ số nguồn (Attributes)"]
            
            t_name = row["Thực thể đích (Target)"]
            t_type = row["Loại đích (Type)"]
            t_attr = row["Chỉ số đích (Attributes)"]
            
            span = row["Bằng chứng văn bản gốc (Evidence Span)"]
            
            # Check source
            is_num_source = (s_type == "Measurement" or any(c.isdigit() for c in s_name) or any(op in s_name for op in ["<", ">", ">=", "<=", "%"]))
            # Exclude standard named guidelines or genes like ACC/AHA, HLA-DR3, SARS-CoV-2
            if any(exempt in s_name for exempt in ["ACC/AHA", "HLA-", "SARS-", "Type 1", "loại 1", "loại 2", "Giai đoạn 1", "giai đoạn 2", "Giai đoạn"]):
                is_num_source = False
                
            if is_num_source and "Thông số:" not in s_attr:
                missing_count += 1
                print(f"[Row {i}] SOURCE: \"{s_name}\" ({s_type})")
                print(f"   Current Attr: {s_attr}")
                print(f"   Span: {span}\n")
                
            # Check target
            is_num_target = (t_type == "Measurement" or any(c.isdigit() for c in t_name) or any(op in t_name for op in ["<", ">", ">=", "<=", "%"]))
            if any(exempt in t_name for exempt in ["ACC/AHA", "HLA-", "SARS-", "Type 1", "loại 1", "loại 2", "Giai đoạn 1", "giai đoạn 2", "Giai đoạn"]):
                is_num_target = False
                
            if is_num_target and "Thông số:" not in t_attr:
                missing_count += 1
                print(f"[Row {i}] TARGET: \"{t_name}\" ({t_type})")
                print(f"   Current Attr: {t_attr}")
                print(f"   Span: {span}\n")

    print(f"Total entries needing parameter context in {cat.upper()}: {missing_count}")

if __name__ == "__main__":
    audit_category("hypertension")
    audit_category("diabetes")
