import csv
import sys
from pathlib import Path
from typing import Dict, Tuple, Any, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def merge_hypertension_files():
    files = [
        Path("data/reports/hypertension/TangHuyetAp.csv"),
        Path("data/reports/hypertension/02_ThuocDieuTriTangHuyetAp.csv"),
        Path("data/reports/hypertension/03_TangHuyetApCapCuu.csv"),
        Path("data/reports/hypertension/04_TangHuyetApDoBenhLyMachThan.csv"),
    ]

    print("=== GỘP 4 TỆP DỮ LIỆU ĐÃ THẨM ĐỊNH CỦA CHUYÊN KHOA TĂNG HUYẾT ÁP ===")
    
    all_raw_rows = []
    seen_triplets: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    
    fieldnames = []

    for fpath in files:
        if not fpath.exists():
            print(f"[!] Warning: File {fpath} does not exist.")
            continue
        with open(fpath, "r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))
            if not fieldnames and reader:
                fieldnames = list(reader[0].keys())
            print(f"Đọc {fpath.name}: {len(reader)} bộ ba")
            for row in reader:
                all_raw_rows.append(row)
                s = str(row.get("Thực thể nguồn (Source)", "")).strip().lower()
                r = str(row.get("Quan hệ lâm sàng (Relation)", "")).strip()
                t = str(row.get("Thực thể đích (Target)", "")).strip().lower()
                key = (s, r, t)

                if key not in seen_triplets:
                    seen_triplets[key] = dict(row)
                else:
                    existing = seen_triplets[key]
                    # Keep longest evidence span and non-empty CUI
                    if len(row.get("Bằng chứng văn bản gốc (Evidence Span)", "")) > len(existing.get("Bằng chứng văn bản gốc (Evidence Span)", "")):
                        existing["Bằng chứng văn bản gốc (Evidence Span)"] = row.get("Bằng chứng văn bản gốc (Evidence Span)", "")
                    if (not existing.get("Mã CUI nguồn") or existing.get("Mã CUI nguồn") == "Chưa có") and row.get("Mã CUI nguồn") and row.get("Mã CUI nguồn") != "Chưa có":
                        existing["Mã CUI nguồn"] = row.get("Mã CUI nguồn")
                    if (not existing.get("Mã CUI đích") or existing.get("Mã CUI đích") == "Chưa có") and row.get("Mã CUI đích") and row.get("Mã CUI đích") != "Chưa có":
                        existing["Mã CUI đích"] = row.get("Mã CUI đích")

    merged_rows = list(seen_triplets.values())

    # Sort alphabetically by Source, Relation, Target
    merged_rows.sort(key=lambda x: (
        x.get("Thực thể nguồn (Source)", "").lower(),
        x.get("Quan hệ lâm sàng (Relation)", "").lower(),
        x.get("Thực thể đích (Target)", "").lower()
    ))

    # Re-index STT
    for i, row in enumerate(merged_rows, 1):
        row["STT"] = str(i)

    # Export to master file
    out_file = Path("data/reports/hypertension/TangHuyetAp_TongHop_Verified.csv")
    with open(out_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged_rows)

    # Also update general clinical_knowledge_summary_verified.csv
    summary_verified = Path("data/reports/hypertension/clinical_knowledge_summary_verified.csv")
    with open(summary_verified, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged_rows)

    print(f"\nTổng số dòng trước khi khử trùng: {len(all_raw_rows)}")
    print(f"Tổng số bộ ba độc nhất SAU KHI GỘP & KHỬ TRÙNG: {len(merged_rows)} bộ ba")
    print(f"Đã lưu tệp tổng hợp tại:")
    print(f"  1. {out_file}")
    print(f"  2. {summary_verified}\n")


if __name__ == "__main__":
    merge_hypertension_files()
