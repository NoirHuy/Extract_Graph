import subprocess
import sys
import shutil
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def run_command(cmd_list, desc):
    print(f"\n=======================================================")
    print(f"  RUNNING: {desc}")
    print(f"  COMMAND: {' '.join(cmd_list)}")
    print(f"=======================================================")
    res = subprocess.run(cmd_list, capture_output=True, text=True, encoding="utf-8")
    print(res.stdout)
    if res.stderr:
        print("STDERR:", res.stderr)
    if res.returncode != 0:
        print(f"[!] Error running {desc} (Exit code {res.returncode})")
        sys.exit(res.returncode)
    return res.stdout


def main():
    # 1. Pipeline for 03_tanghuyetapcapcuu.txt
    run_command(
        [sys.executable, "main.py", "run-all", "--input", "data/raw/hypertension/03_tanghuyetapcapcuu.txt", "--passes", "2"],
        "Extraction Pipeline for 03_tanghuyetapcapcuu.txt"
    )

    # Evaluate 03
    eval_03_csv = "data/exports/hypertension/03_tanghuyetapcapcuu_clinical_knowledge_summary.csv"
    run_command(
        [sys.executable, "main.py", "evaluate", "--input", eval_03_csv, "--output-dir", "data/reports/hypertension_03_capcuu"],
        "Multi-Agent Clinical Evaluation for 03_tanghuyetapcapcuu.txt"
    )
    # Copy friendly verified CSV
    src_03 = Path("data/reports/hypertension_03_capcuu/03_tanghuyetapcapcuu_clinical_knowledge_summary_verified.csv")
    if src_03.exists():
        dst_03 = Path("data/reports/hypertension/03_TangHuyetApCapCuu.csv")
        shutil.copyfile(src_03, dst_03)
        print(f"Created certified copy: {dst_03}")

    # 2. Pipeline for 04_tanghuyetapdobenhlymachthan.txt
    run_command(
        [sys.executable, "main.py", "run-all", "--input", "data/raw/hypertension/04_tanghuyetapdobenhlymachthan.txt", "--passes", "2"],
        "Extraction Pipeline for 04_tanghuyetapdobenhlymachthan.txt"
    )

    # Evaluate 04
    eval_04_csv = "data/exports/hypertension/04_tanghuyetapdobenhlymachthan_clinical_knowledge_summary.csv"
    run_command(
        [sys.executable, "main.py", "evaluate", "--input", eval_04_csv, "--output-dir", "data/reports/hypertension_04_machthan"],
        "Multi-Agent Clinical Evaluation for 04_tanghuyetapdobenhlymachthan.txt"
    )
    # Copy friendly verified CSV
    src_04 = Path("data/reports/hypertension_04_machthan/04_tanghuyetapdobenhlymachthan_clinical_knowledge_summary_verified.csv")
    if src_04.exists():
        dst_04 = Path("data/reports/hypertension/04_TangHuyetApDoBenhLyMachThan.csv")
        shutil.copyfile(src_04, dst_04)
        print(f"Created certified copy: {dst_04}")

    print("\n=======================================================")
    print("  ALL 03 AND 04 PIPELINES & EVALUATIONS FINISHED!")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
