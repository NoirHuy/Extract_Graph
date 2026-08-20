"""Agent 4: Chief Medical Adjudicator (Trưởng ban Phân xử & Chấm điểm Tổng kết)."""

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple
from evaluation.schemas import AgentReviewReport, EvaluationScorecard, TripletReviewItem

logger = logging.getLogger(__name__)


class ChiefMedicalAdjudicator:
    """Agent 4: Aggregates reviews from Clinical, UMLS, and Graph agents.
    Calculates quantitative quality scores (0-100), outputs Scorecard & auto-healed CSV."""

    def __init__(self):
        self.name = "Chief_Medical_Adjudicator"

    def calculate_score(self, report: AgentReviewReport) -> float:
        if report.total_reviewed == 0:
            return 100.0
        # Formula: (Pass * 1.0 + Warning * 0.7 + Fail * 0.0) / Total * 100
        score = ((report.pass_count * 1.0) + (report.warning_count * 0.7)) / report.total_reviewed * 100.0
        return round(score, 2)

    def adjudicate(
        self,
        doc_name: str,
        raw_rows: List[Dict[str, Any]],
        clinical_report: AgentReviewReport,
        ontology_report: AgentReviewReport,
        graph_report: AgentReviewReport,
    ) -> Tuple[EvaluationScorecard, List[Dict[str, Any]]]:
        """Aggregate reports, compute weighted scores, and generate auto-healed dataset."""
        c_score = self.calculate_score(clinical_report)
        o_score = self.calculate_score(ontology_report)
        g_score = self.calculate_score(graph_report)

        # Weighted: Clinical (40%), Ontology (35%), Graph Structure (25%)
        overall = round((c_score * 0.40) + (o_score * 0.35) + (g_score * 0.25), 2)

        # Assign Grade
        if overall >= 95:
            grade = "A+ (Xuất sắc / Chuẩn lâm sàng)"
        elif overall >= 90:
            grade = "A (Rất tốt)"
        elif overall >= 80:
            grade = "B (Khá / Cần lưu ý vài điểm)"
        elif overall >= 70:
            grade = "C (Trung bình)"
        else:
            grade = "D (Cần kiểm tra lại)"

        findings = []
        if clinical_report.fail_count > 0:
            findings.append(f"Phát hiện {clinical_report.fail_count} lỗi nghiêm trọng về logic lâm sàng / ngược chiều quan hệ.")
        if ontology_report.fail_count > 0:
            findings.append(f"Phát hiện {ontology_report.fail_count} lỗi sai lệch mã UMLS CUI / gán nhầm mã cho số đo.")
        if graph_report.fail_count > 0:
            findings.append(f"Phát hiện {graph_report.fail_count} lỗi topo đồ thị / lặp cạnh.")

        if not findings:
            findings.append("Tất cả các tiêu chuẩn lâm sàng, định danh UMLS và cấu trúc đồ thị đều đạt chuẩn xuất sắc!")

        # Auto-Healing logic
        healed_rows: List[Dict[str, Any]] = []
        healed_count = 0
        flagged_count = 0

        # Collect issues by row index
        all_reviews: List[TripletReviewItem] = (
            clinical_report.reviews + ontology_report.reviews + graph_report.reviews
        )
        row_issues: Dict[int, List[TripletReviewItem]] = {}
        for rev in all_reviews:
            if rev.status in ("WARNING", "FAIL"):
                row_issues.setdefault(rev.row_index, []).append(rev)

        flagged_count = len(row_issues)
        verified_rows: List[Dict[str, Any]] = []

        for idx, row in enumerate(raw_rows, 1):
            row_copy = dict(row)
            issues = row_issues.get(idx, [])

            # Strictly DROP any triplet that failed clinical, ontology or graph reviews
            is_failed = any(issue.status == "FAIL" for issue in issues)
            if is_failed:
                continue

            healed = False
            for issue in issues:
                if issue.suggested_fix:
                    for k, v in issue.suggested_fix.items():
                        if k == "source_cui":
                            row_copy["Mã CUI nguồn"] = v
                            healed = True
                        elif k == "target_cui":
                            row_copy["Mã CUI đích"] = v
                            healed = True
                        elif k == "relation":
                            row_copy["Quan hệ lâm sàng (Relation)"] = v
                            healed = True

            if healed:
                healed_count += 1

            # Re-index STT sequentially from 1 to N
            row_copy["STT"] = str(len(verified_rows) + 1)
            verified_rows.append(row_copy)

        scorecard = EvaluationScorecard(
            document_name=doc_name,
            total_triplets=len(raw_rows),
            clinical_accuracy_score=c_score,
            ontology_integrity_score=o_score,
            graph_consistency_score=g_score,
            overall_quality_score=overall,
            grade=grade,
            summary_findings=findings,
            agent_reports={
                clinical_report.agent_name: clinical_report,
                ontology_report.agent_name: ontology_report,
                graph_report.agent_name: graph_report,
            },
            flagged_rows_count=flagged_count,
            auto_healed_rows_count=healed_count,
        )

        return scorecard, verified_rows

    def export_scorecard_markdown(self, scorecard: EvaluationScorecard, output_file: Path):
        """Export comprehensive evaluation scorecard to Markdown."""
        output_file.parent.mkdir(parents=True, exist_ok=True)

        md = []
        md.append(f"# 🩺 BÁO CÁO THẨM ĐỊNH Y KHOA ĐA TÁC TỬ (MULTI-AGENT CLINICAL EVALUATION)")
        md.append(f"**Tài liệu:** `{scorecard.document_name}` | **Tổng số bộ 3 tri thức:** `{scorecard.total_triplets}`")
        md.append(f"**Điểm Chất Lượng Toàn diện:** **`{scorecard.overall_quality_score} / 100`** — **Xếp loại:** **{scorecard.grade}**\n")

        md.append(f"## 📊 Bảng Điểm Thành Phần")
        md.append(f"| Hội đồng Chuyên môn | Điểm số (0-100) | Đạt chuẩn (Pass) | Cảnh báo (Warning) | Lỗi (Fail) |")
        md.append(f"|---|:---:|:---:|:---:|:---:|")

        for ag_name, rpt in scorecard.agent_reports.items():
            ag_title = ag_name.replace("_", " ")
            sc = self.calculate_score(rpt)
            md.append(f"| **{ag_title}** | **{sc}** | {rpt.pass_count} | {rpt.warning_count} | {rpt.fail_count} |")

        md.append(f"\n## 🔍 Kết luận của Trưởng Ban Hội Chẩn (Chief Adjudicator)")
        for find in scorecard.summary_findings:
            md.append(f"- {find}")

        md.append(f"\n- **Tổng số dòng có cảnh báo/nghi vấn:** `{scorecard.flagged_rows_count} / {scorecard.total_triplets}`")
        md.append(f"- **Tổng số dòng đã được tự động chữa lành:** `{scorecard.auto_healed_rows_count}`")

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
