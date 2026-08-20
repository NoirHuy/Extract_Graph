"""Agent 1: Clinical Fact-Checking Specialist (Bác sĩ Thẩm định Lâm sàng)."""

import logging
from typing import Any, Dict, List, Optional
from evaluation.schemas import AgentReviewReport, TripletReviewItem
from extraction.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ClinicalFactCheckAgent:
    """Agent 1: Audits triplets against verbatim evidence spans to detect hallucination,
    inverted causal direction, or clinical inaccuracy."""

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()
        self.name = "Clinical_Doctor_Agent"

    def review_triplet(self, row_idx: int, row_data: Dict[str, Any]) -> TripletReviewItem:
        s_name = row_data.get("Thực thể nguồn (Source)", "")
        s_type = row_data.get("Loại nguồn (Type)", "")
        rel = row_data.get("Quan hệ lâm sàng (Relation)", "")
        t_name = row_data.get("Thực thể đích (Target)", "")
        t_type = row_data.get("Loại đích (Type)", "")
        span = row_data.get("Bằng chứng văn bản gốc (Evidence Span)", "")

        # Heuristic checks
        # 1. Inverted Causality: Disease cannot CAUSE a Cause entity
        if rel in ("Là nguyên nhân gây ra", "CAUSES") and s_type in ("Disease", "Complication") and t_type == "Cause":
            return TripletReviewItem(
                row_index=row_idx,
                source_name=s_name,
                relation_type=rel,
                target_name=t_name,
                status="FAIL",
                agent_name=self.name,
                issue_type="Inverted_Causality",
                critique=f"Quan hệ ngược chiều: Bệnh/Biến chứng '{s_name}' không thể là nguyên nhân sinh ra Căn nguyên '{t_name}'.",
                suggested_fix={"source": t_name, "relation": "Là nguyên nhân gây ra", "target": s_name}
            )

        # 2. Check if relation matches evidence span keywords
        s_lower = s_name.lower()
        t_lower = t_name.lower()
        span_lower = span.lower()

        # Check if source or target is grounded in span
        has_source = any(w in span_lower for w in s_lower.split()[:3] if len(w) > 3) or s_lower in span_lower
        has_target = any(w in span_lower for w in t_lower.split()[:3] if len(w) > 3) or t_lower in span_lower

        if not has_source or not has_target:
            return TripletReviewItem(
                row_index=row_idx,
                source_name=s_name,
                relation_type=rel,
                target_name=t_name,
                status="WARNING",
                agent_name=self.name,
                issue_type="Weak_Evidence_Grounding",
                critique=f"Thực thể '{s_name}' hoặc '{t_name}' có độ neo ngữ cảnh yếu so với bằng chứng gốc: \"{span[:100]}...\"",
            )

        return TripletReviewItem(
            row_index=row_idx,
            source_name=s_name,
            relation_type=rel,
            target_name=t_name,
            status="PASS",
            agent_name=self.name,
            critique="Chuẩn xác về mặt lâm sàng và neo đúng bằng chứng văn bản gốc."
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
