"""Agent 3: Graph Structure & Redundancy Inspector (Kỹ sư Cấu trúc Đồ thị Tri thức)."""

from typing import Any, Dict, List, Set, Tuple
from evaluation.schemas import AgentReviewReport, TripletReviewItem


class GraphStructureAgent:
    """Agent 3: Audits graph topology, detects exact/near duplicates, self-loops, and contradictory edges."""

    def __init__(self):
        self.name = "Graph_Structure_Inspector_Agent"

    def review_all(self, rows: List[Dict[str, Any]]) -> AgentReviewReport:
        reviews = []
        pass_c = 0
        warn_c = 0
        fail_c = 0

        seen_triplets: Dict[Tuple[str, str, str], int] = {}
        seen_contradictions: Dict[Tuple[str, str], str] = {}

        for idx, row in enumerate(rows, 1):
            s_name = str(row.get("Thực thể nguồn (Source)", "")).strip().lower()
            rel = str(row.get("Quan hệ lâm sàng (Relation)", "")).strip()
            t_name = str(row.get("Thực thể đích (Target)", "")).strip().lower()

            raw_s = row.get("Thực thể nguồn (Source)", "")
            raw_t = row.get("Thực thể đích (Target)", "")

            # 1. Self-Loop Check (Node connecting to itself)
            if s_name and s_name == t_name:
                fail_c += 1
                reviews.append(TripletReviewItem(
                    row_index=idx,
                    source_name=raw_s,
                    relation_type=rel,
                    target_name=raw_t,
                    status="FAIL",
                    agent_name=self.name,
                    issue_type="Self_Loop_Inconsistency",
                    critique=f"Lỗi đồ thị: Thực thể '{raw_s}' tự liên kết với chính nó qua quan hệ '{rel}'.",
                ))
                continue

            # 2. Duplicate Triplet Check
            triplet_key = (s_name, rel, t_name)
            if triplet_key in seen_triplets:
                first_row = seen_triplets[triplet_key]
                fail_c += 1
                reviews.append(TripletReviewItem(
                    row_index=idx,
                    source_name=raw_s,
                    relation_type=rel,
                    target_name=raw_t,
                    status="FAIL",
                    agent_name=self.name,
                    issue_type="Duplicate_Triplet",
                    critique=f"Trùng lặp hoàn toàn với dòng {first_row}: ({raw_s} -> {rel} -> {raw_t}).",
                ))
                continue
            else:
                seen_triplets[triplet_key] = idx

            # 3. Contradictory Edges (e.g. A CAUSES B and A TREATS B simultaneously)
            pair_key = (s_name, t_name)
            if pair_key in seen_contradictions:
                prev_rel = seen_contradictions[pair_key]
                if (rel in ("Điều trị", "TREATS") and prev_rel in ("Là nguyên nhân gây ra", "CAUSES")) or \
                   (rel in ("Là nguyên nhân gây ra", "CAUSES") and prev_rel in ("Điều trị", "TREATS")):
                    warn_c += 1
                    reviews.append(TripletReviewItem(
                        row_index=idx,
                        source_name=raw_s,
                        relation_type=rel,
                        target_name=raw_t,
                        status="WARNING",
                        agent_name=self.name,
                        issue_type="Contradictory_Edge_Pair",
                        critique=f"Nghi vấn mâu thuẫn: Thực thể '{raw_s}' vừa '{prev_rel}' vừa '{rel}' cho '{raw_t}'.",
                    ))
                    continue
            else:
                seen_contradictions[pair_key] = rel

            # Passed
            pass_c += 1
            reviews.append(TripletReviewItem(
                row_index=idx,
                source_name=raw_s,
                relation_type=rel,
                target_name=raw_t,
                status="PASS",
                agent_name=self.name,
                critique="Cấu trúc topo đồ thị hợp lệ, không bị lặp cạnh hoặc tạo vòng lặp mâu thuẫn."
            ))

        return AgentReviewReport(
            agent_name=self.name,
            total_reviewed=len(rows),
            pass_count=pass_c,
            warning_count=warn_c,
            fail_count=fail_c,
            reviews=reviews,
        )
