"""Agent 1: Clinical Fact-Checking Specialist (Bác sĩ Thẩm định Lâm sàng qua LLM)."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple
from evaluation.schemas import AgentReviewReport, TripletReviewItem
from extraction.llm_client import LLMClient

logger = logging.getLogger(__name__)

CLINICAL_REVIEW_SYSTEM_PROMPT = """Bạn là Bác sĩ Chuyên khoa Trưởng Ban Thẩm định Lâm sàng (Chief Clinical Reviewer) trong Hội đồng AI Y tế.
Nhiệm vụ của bạn là kiểm tra, phản biện từng bộ ba tri thức (Clinical Triplet) được trích xuất từ tài liệu y khoa.

Với mỗi bộ ba:
1. Source Entity (Thực thể nguồn)
2. Relation (Quan hệ lâm sàng)
3. Target Entity (Thực thể đích)
4. Evidence Span (Đoạn trích văn bản gốc)

Yêu cầu thẩm định:
- Xác định xem mối quan hệ giữa Source và Target có đúng sự thật y khoa và đúng với câu trích dẫn Evidence Span hay không.
- Bắt lỗi quan hệ ngược chiều (ví dụ: Bệnh gây ra Căn nguyên là SAI, phải là Căn nguyên gây ra Bệnh).
- Bắt lỗi suy diễn quá mức (Hallucination) không có trong bài.
- Gán trạng thái: "PASS" (Đạt chuẩn), "WARNING" (Có thể chấp nhận nhưng chưa chặt chẽ), hoặc "FAIL" (Sai y khoa / Ngược chiều).
- Nếu có lỗi, đưa ra giải thích y khoa (critique) và đề xuất sửa đổi (suggested_fix).

Trả về định dạng JSON đúng schema sau:
{
  "reviews": [
    {
      "row_index": 1,
      "status": "PASS" | "WARNING" | "FAIL",
      "issue_type": "Inverted_Causality" | "Hallucination" | "Weak_Grounding" | "None",
      "critique": "Giải thích chi tiết",
      "suggested_fix": {
        "source": "tên sửa",
        "relation": "quan hệ sửa",
        "target": "đích sửa"
      }
    }
  ]
}"""


class ClinicalFactCheckAgent:
    """Agent 1: Audits triplets against verbatim evidence spans using real LLM calls
    with resilient rule-based fallback."""

    def __init__(self, client: Optional[LLMClient] = None, use_llm: bool = True):
        self.client = client or LLMClient()
        self.name = "Clinical_Doctor_Agent"
        self.use_llm = use_llm

    def _review_triplet_rule_based(self, row_idx: int, row_data: Dict[str, Any]) -> TripletReviewItem:
        s_name = str(row_data.get("Thực thể nguồn (Source)", ""))
        s_type = str(row_data.get("Loại nguồn (Type)", ""))
        rel = str(row_data.get("Quan hệ lâm sàng (Relation)", ""))
        t_name = str(row_data.get("Thực thể đích (Target)", ""))
        t_type = str(row_data.get("Loại đích (Type)", ""))
        span = str(row_data.get("Bằng chứng văn bản gốc (Evidence Span)", ""))

        # 1. Inverted Causality
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

        # 2. Check grounding
        s_lower = s_name.lower()
        t_lower = t_name.lower()
        span_lower = span.lower()

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

    def _review_batch_llm(self, batch_items: List[Tuple[int, Dict[str, Any]]]) -> List[TripletReviewItem]:
        """Review a batch of triplets with a single LLM call."""
        user_prompt_data = []
        for idx, row in batch_items:
            user_prompt_data.append({
                "row_index": idx,
                "source": row.get("Thực thể nguồn (Source)", ""),
                "relation": row.get("Quan hệ lâm sàng (Relation)", ""),
                "target": row.get("Thực thể đích (Target)", ""),
                "evidence_span": row.get("Bằng chứng văn bản gốc (Evidence Span)", "")
            })

        user_text = f"Hãy thẩm định các bộ ba tri thức sau:\n```json\n{json.dumps(user_prompt_data, ensure_ascii=False, indent=2)}\n```"

        schema = {
            "type": "object",
            "properties": {
                "reviews": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "row_index": {"type": "integer"},
                            "status": {"type": "string", "enum": ["PASS", "WARNING", "FAIL"]},
                            "issue_type": {"type": "string"},
                            "critique": {"type": "string"},
                            "suggested_fix": {"type": ["object", "null"]}
                        },
                        "required": ["row_index", "status", "critique"]
                    }
                }
            },
            "required": ["reviews"]
        }

        try:
            res = self.client.extract_structured(
                system_prompt=CLINICAL_REVIEW_SYSTEM_PROMPT,
                user_text=user_text,
                schema=schema,
                temperature=0.0
            )
            raw_reviews = {item["row_index"]: item for item in res.get("reviews", [])}

            results = []
            for idx, row in batch_items:
                if idx in raw_reviews:
                    r = raw_reviews[idx]
                    results.append(TripletReviewItem(
                        row_index=idx,
                        source_name=row.get("Thực thể nguồn (Source)", ""),
                        relation_type=row.get("Quan hệ lâm sàng (Relation)", ""),
                        target_name=row.get("Thực thể đích (Target)", ""),
                        status=r.get("status", "PASS"),
                        agent_name=self.name,
                        issue_type=r.get("issue_type") if r.get("issue_type") != "None" else None,
                        critique=r.get("critique", "Đạt chuẩn lâm sàng."),
                        suggested_fix=r.get("suggested_fix")
                    ))
                else:
                    results.append(self._review_triplet_rule_based(idx, row))
            return results
        except Exception as e:
            logger.warning(f"LLM review failed for batch ({e}). Falling back to rule-based evaluation.")
            return [self._review_triplet_rule_based(idx, row) for idx, row in batch_items]

    def review_all(self, rows: List[Dict[str, Any]]) -> AgentReviewReport:
        indexed_rows = list(enumerate(rows, 1))

        if self.use_llm:
            batch_size = 15
            batches = [indexed_rows[i:i + batch_size] for i in range(0, len(indexed_rows), batch_size)]
            logger.info(f"Clinical Doctor Agent: Reviewing {len(rows)} triplets across {len(batches)} parallel LLM batches...")

            all_reviews = []
            with ThreadPoolExecutor(max_workers=5) as executor:
                batch_results = list(executor.map(self._review_batch_llm, batches))
                for b_res in batch_results:
                    all_reviews.extend(b_res)
        else:
            all_reviews = [self._review_triplet_rule_based(idx, row) for idx, row in indexed_rows]

        pass_c = sum(1 for r in all_reviews if r.status == "PASS")
        warn_c = sum(1 for r in all_reviews if r.status == "WARNING")
        fail_c = sum(1 for r in all_reviews if r.status == "FAIL")

        return AgentReviewReport(
            agent_name=self.name,
            total_reviewed=len(rows),
            pass_count=pass_c,
            warning_count=warn_c,
            fail_count=fail_c,
            reviews=all_reviews,
        )
