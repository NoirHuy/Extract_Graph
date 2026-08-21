import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from export.neo4j_exporter import Neo4jExporter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def reexport_all():
    exporter = Neo4jExporter()

    docs = [
        ("01_tanghuyetap.txt", "hypertension"),
        ("02_thuocdieutri.txt", "hypertension"),
        ("01_daithaoduong.txt", "diabetes"),
        ("01_copd.txt", "copd"),
        ("henphequan.txt", "asthma"),
    ]

    print("=== RE-EXPORTING ALL KNOWLEDGE GRAPH CSV FILES ===")
    for doc, cat in docs:
        res = exporter.export_all_to_csv(
            output_dir="data/exports",
            source_doc=doc,
            category=cat
        )
        print(f"Exported [{doc}] -> {res['clinical_summary_csv']}")

    # Also export category-wide aggregates
    for cat in ["hypertension", "diabetes", "copd", "asthma"]:
        res_cat = exporter.export_all_to_csv(
            output_dir="data/exports",
            source_doc=None,
            category=cat
        )
        print(f"Exported Category Summary for [{cat}] -> {res_cat['clinical_summary_csv']}")

    exporter.close()
    print("\nAll exports refreshed cleanly without any file overwrites!")


if __name__ == "__main__":
    reexport_all()
