import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

for cat, file_path in [
    ("hypertension", "data/processed/hypertension/01_tanghuyetap_graph_final.json"),
    ("diabetes", "data/processed/diabetes/01_daithaoduong_graph_final.json")
]:
    p = Path(file_path)
    if not p.exists():
        continue
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"\n=======================================================")
    print(f"       MEASUREMENTS IN {cat.upper()} ({len(data['entities'])} entities)")
    print(f"=======================================================")
    m_count = 0
    for e in data["entities"]:
        if e.get("entity_type") == "Measurement":
            m_count += 1
            has_param = "parameter" in (e.get("attributes") or {})
            print(f"[{m_count}] {'[OK]' if has_param else '[MISSING PARAM]'} \"{e.get('normalized_name')}\"")
            print(f"    Attributes: {e.get('attributes')}")
            print(f"    Span: {e.get('evidence_span')}\n")
