"""Unit and integration tests for Multi-Agent Clinical Evaluation Committee."""

import csv
import pytest
from pathlib import Path

from evaluation.agents.clinical_agent import ClinicalFactCheckAgent
from evaluation.agents.ontology_agent import OntologyAuditorAgent
from evaluation.agents.graph_agent import GraphStructureAgent
from evaluation.agents.adjudicator_agent import ChiefMedicalAdjudicator
from evaluation.pipeline import MultiAgentEvaluator


@pytest.fixture
def sample_csv_data(tmp_path):
    rows = [
        {
            "STT": "1",
            "Thực thể nguồn (Source)": "Cường aldosteron nguyên phát",
            "Loại nguồn (Type)": "Cause",
            "Mã CUI nguồn": "C0020438",
            "Chỉ số nguồn (Attributes)": "",
            "Quan hệ lâm sàng (Relation)": "Là nguyên nhân gây ra",
            "Thực thể đích (Target)": "Tăng huyết áp thứ phát",
            "Loại đích (Type)": "DiseaseSubtype",
            "Mã CUI đích": "C0155616",
            "Chỉ số đích (Attributes)": "",
            "Bằng chứng văn bản gốc (Evidence Span)": "Cường aldosteron nguyên phát là nguyên nhân gây ra Tăng huyết áp thứ phát.",
            "Tài liệu nguồn": "test.txt",
        },
        {
            "STT": "2",
            "Thực thể nguồn (Source)": "Tăng huyết áp",
            "Loại nguồn (Type)": "Disease",
            "Mã CUI nguồn": "C0020538",
            "Chỉ số nguồn (Attributes)": "",
            "Quan hệ lâm sàng (Relation)": "Là nguyên nhân gây ra",
            "Thực thể đích (Target)": "U tủy thượng thận",
            "Loại đích (Type)": "Cause",  # Inverted causality bug
            "Mã CUI đích": "C0031511",
            "Chỉ số đích (Attributes)": "",
            "Bằng chứng văn bản gốc (Evidence Span)": "U tủy thượng thận gây tăng huyết áp.",
            "Tài liệu nguồn": "test.txt",
        },
        {
            "STT": "3",
            "Thực thể nguồn (Source)": "Huyết áp >= 140/90 mmHg",
            "Loại nguồn (Type)": "Measurement",
            "Mã CUI nguồn": "C0596271",  # Invalid CUI assigned to Measurement
            "Chỉ số nguồn (Attributes)": "Thông số: Huyết áp; Giá trị: >= 140/90 mmHg",
            "Quan hệ lâm sàng (Relation)": "Xác định ngưỡng chẩn đoán cho",
            "Thực thể đích (Target)": "Tăng huyết áp",
            "Loại đích (Type)": "Disease",
            "Mã CUI đích": "C0020538",
            "Chỉ số đích (Attributes)": "",
            "Bằng chứng văn bản gốc (Evidence Span)": "Huyết áp >= 140/90 mmHg xác định Tăng huyết áp.",
            "Tài liệu nguồn": "test.txt",
        },
        {
            "STT": "4",
            "Thực thể nguồn (Source)": "Cường aldosteron nguyên phát",
            "Loại nguồn (Type)": "Cause",
            "Mã CUI nguồn": "C0020438",
            "Chỉ số nguồn (Attributes)": "",
            "Quan hệ lâm sàng (Relation)": "Là nguyên nhân gây ra",
            "Thực thể đích (Target)": "Tăng huyết áp thứ phát",
            "Loại đích (Type)": "DiseaseSubtype",
            "Mã CUI đích": "C0155616",
            "Chỉ số đích (Attributes)": "",
            "Bằng chứng văn bản gốc (Evidence Span)": "Cường aldosteron nguyên phát là nguyên nhân gây ra Tăng huyết áp thứ phát.",
            "Tài liệu nguồn": "test.txt",
        },
    ]

    csv_path = tmp_path / "test_clinical_summary.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return str(csv_path), rows


def test_clinical_agent_detects_inverted_causality(sample_csv_data):
    _, rows = sample_csv_data
    agent = ClinicalFactCheckAgent()
    report = agent.review_all(rows)

    assert report.total_reviewed == 4
    assert report.fail_count == 1
    failed_item = [r for r in report.reviews if r.status == "FAIL"][0]
    assert failed_item.issue_type == "Inverted_Causality"
    assert "U tủy thượng thận" in failed_item.target_name


def test_ontology_agent_detects_invalid_measurement_cui(sample_csv_data):
    _, rows = sample_csv_data
    agent = OntologyAuditorAgent()
    report = agent.review_all(rows)

    assert report.total_reviewed == 4
    assert report.fail_count == 1
    failed_item = [r for r in report.reviews if r.status == "FAIL"][0]
    assert failed_item.issue_type == "Invalid_Measurement_CUI"
    assert failed_item.suggested_fix == {"source_cui": "Chưa có"}


def test_graph_agent_detects_duplicate_triplet(sample_csv_data):
    _, rows = sample_csv_data
    agent = GraphStructureAgent()
    report = agent.review_all(rows)

    assert report.total_reviewed == 4
    assert report.fail_count == 1
    dup_item = [r for r in report.reviews if r.status == "FAIL"][0]
    assert dup_item.issue_type == "Duplicate_Triplet"


def test_adjudicator_scorecard_and_auto_healing(sample_csv_data):
    _, rows = sample_csv_data
    c_agent = ClinicalFactCheckAgent()
    o_agent = OntologyAuditorAgent()
    g_agent = GraphStructureAgent()
    adjudicator = ChiefMedicalAdjudicator()

    c_report = c_agent.review_all(rows)
    o_report = o_agent.review_all(rows)
    g_report = g_agent.review_all(rows)

    scorecard, healed_rows = adjudicator.adjudicate("test.txt", rows, c_report, o_report, g_report)

    assert scorecard.total_triplets == 4
    assert 0 <= scorecard.overall_quality_score <= 100
    # Strict filtering dropped 3 failed rows (Row 2 inverted causality, Row 3 invalid CUI, Row 4 duplicate)
    assert len(healed_rows) == 1
    assert healed_rows[0]["STT"] == "1"
    assert "Cường aldosteron" in healed_rows[0]["Thực thể nguồn (Source)"]


def test_end_to_end_multi_agent_pipeline(sample_csv_data, tmp_path):
    csv_path, _ = sample_csv_data
    evaluator = MultiAgentEvaluator()

    scorecard, md_file, json_file, verified_csv = evaluator.evaluate_csv(
        csv_path=csv_path,
        output_dir=str(tmp_path)
    )

    assert Path(md_file).exists()
    assert Path(json_file).exists()
    assert Path(verified_csv).exists()
    assert scorecard.total_triplets == 4
