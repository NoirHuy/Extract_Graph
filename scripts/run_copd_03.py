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
    # Pipeline for 03_dieutridotcap.txt
    run_command(
        [sys.executable, "main.py", "run-all", "--input", "data/raw/copd/03_dieutridotcap.txt", "--passes", "2"],
        "Extraction Pipeline for 03_dieutridotcap.txt"
    )

    # Evaluate 03
    eval_03_csv = "data/exports/copd/03_dieutridotcap_clinical_knowledge_summary.csv"
    run_command(
        [sys.executable, "main.py", "evaluate", "--input", eval_03_csv, "--output-dir", "data/reports/copd_03_dotcap"],
        "Multi-Agent Clinical Evaluation for 03_dieutridotcap.txt"
    )
    # Copy friendly verified CSV
    src_03 = Path("data/reports/copd_03_dotcap/03_dieutridotcap_clinical_knowledge_summary_verified.csv")
    if src_03.exists():
        dst_03 = Path("data/reports/copd/03_DieuTriDotCapCOPD.csv")
        shutil.copyfile(src_03, dst_03)
        print(f"Created certified copy: {dst_03}")

    print("\n=======================================================")
    print("  COPD 03 PIPELINE & EVALUATION FINISHED!")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
