"""Agent 2: UMLS & Ontology Integrity Auditor (Chuyên gia Phân loại & Định danh Y học)."""

import re
from typing import Any, Dict, List, Optional
from evaluation.schemas import AgentReviewReport, TripletReviewItem
from schema.schema_registry import ENTITY_TYPES


class OntologyAuditorAgent:
    """Agent 2: Audits UMLS CUIs, TUIs, STYs and prevents assigning obscure codes to quantitative numbers."""

    def __init__(self):
        self.name = "UMLS_Ontology_Auditor_Agent"

    def review_triplet(self, row_idx: int, row_data: Dict[str, Any]) -> TripletReviewItem:
        s_name = row_data.get("Thực thể nguồn (Source)", "")
        s_type = row_data.get("Loại nguồn (Type)", "")
        s_cui = row_data.get("Mã CUI nguồn", "")
        rel = row_data.get("Quan hệ lâm sàng (Relation)", "")
        t_name = row_data.get("Thực thể đích (Target)", "")
        t_type = row_data.get("Loại đích (Type)", "")
        t_cui = row_data.get("Mã CUI đích", "")

        # 1. Check if pure measurement was assigned a CUI (Error)
        if s_type == "Measurement" and s_cui not in ("", "Chưa có", "None", None):
            # Check if name is purely numerical/threshold
            if re.match(r"^[\d<>=±\-\+]+", s_name) or any(u in s_name.lower() for u in ["mmhg", "mmol", "mg/dl", "%", "loại thuốc"]):
                return TripletReviewItem(
                    row_index=row_idx,
                    source_name=s_name,
                    relation_type=rel,
                    target_name=t_name,
                    status="FAIL",
                    agent_name=self.name,
                    issue_type="Invalid_Measurement_CUI",
                    critique=f"Thực thể số đo '{s_name}' không được phép gán mã CUI '{s_cui}'. Phải để 'Chưa có' / Định lượng.",
                    suggested_fix={"source_cui": "Chưa có"}
                )

        if t_type == "Measurement" and t_cui not in ("", "Chưa có", "None", None):
            if re.match(r"^[\d<>=±\-\+]+", t_name) or any(u in t_name.lower() for u in ["mmhg", "mmol", "mg/dl", "%", "loại thuốc"]):
                return TripletReviewItem(
                    row_index=row_idx,
                    source_name=s_name,
                    relation_type=rel,
                    target_name=t_name,
                    status="FAIL",
                    agent_name=self.name,
                    issue_type="Invalid_Measurement_CUI",
                    critique=f"Thực thể số đo đích '{t_name}' không được phép gán mã CUI '{t_cui}'. Phải để 'Chưa có' / Định lượng.",
                    suggested_fix={"target_cui": "Chưa có"}
                )

        # 2. Check Entity Type validity
        if s_type not in ENTITY_TYPES:
            return TripletReviewItem(
                row_index=row_idx,
                source_name=s_name,
                relation_type=rel,
                target_name=t_name,
                status="WARNING",
                agent_name=self.name,
                issue_type="Unknown_Entity_Type",
                critique=f"Loại thực thể nguồn '{s_type}' không nằm trong 16 loại chuẩn của EDC Schema."
            )

        if t_type not in ENTITY_TYPES:
            return TripletReviewItem(
                row_index=row_idx,
                source_name=s_name,
                relation_type=rel,
                target_name=t_name,
                status="WARNING",
                agent_name=self.name,
                issue_type="Unknown_Entity_Type",
                critique=f"Loại thực thể đích '{t_type}' không nằm trong 16 loại chuẩn của EDC Schema."
            )

        # 3. Check CUI formatting (C followed by 7 digits)
        for cui_val, ent_name in [(s_cui, s_name), (t_cui, t_name)]:
            if cui_val and cui_val != "Chưa có":
                if not re.match(r"^C\d{7}$", cui_val.strip()):
                    return TripletReviewItem(
                        row_index=row_idx,
                        source_name=s_name,
                        relation_type=rel,
                        target_name=t_name,
                        status="WARNING",
                        agent_name=self.name,
                        issue_type="Malformed_CUI_Format",
                        critique=f"Mã CUI '{cui_val}' của thực thể '{ent_name}' không đúng định dạng NLM UMLS (Cxxxxxxx)."
                    )

        return TripletReviewItem(
            row_index=row_idx,
            source_name=s_name,
            relation_type=rel,
            target_name=t_name,
            status="PASS",
            agent_name=self.name,
            critique="Định danh y khoa UMLS, STY và phân loại thực thể hợp lệ."
        )

    def review_all(self, rows: List[Dict[str, Any]]) -> AgentReviewReport:
        reviews = []
        pass_c = 0
        warn_c = 0
        fail_c = 0

        for idx, row in enumerate(rows, 1):
            rev = self.review_triplet(idx, row)
            reviews.append(rev)
            if rev.status == "PASS":
                pass_c += 1
            elif rev.status == "WARNING":
                warn_c += 1
            else:
                fail_c += 1

        return AgentReviewReport(
            agent_name=self.name,
            total_reviewed=len(rows),
            pass_count=pass_c,
            warning_count=warn_c,
            fail_count=fail_c,
            reviews=reviews,
        )
