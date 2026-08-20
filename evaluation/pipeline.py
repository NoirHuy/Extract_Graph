"""Multi-Agent Evaluation Pipeline Orchestrator."""

import csv
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from evaluation.agents.clinical_agent import ClinicalFactCheckAgent
from evaluation.agents.ontology_agent import OntologyAuditorAgent
from evaluation.agents.graph_agent import GraphStructureAgent
from evaluation.agents.adjudicator_agent import ChiefMedicalAdjudicator
from evaluation.schemas import EvaluationScorecard

logger = logging.getLogger(__name__)


class MultiAgentEvaluator:
    """Orchestrates the 4-agent clinical review board in parallel."""

    def __init__(self):
        self.clinical_agent = ClinicalFactCheckAgent()
        self.ontology_agent = OntologyAuditorAgent()
        self.graph_agent = GraphStructureAgent()
        self.adjudicator = ChiefMedicalAdjudicator()

    def evaluate_csv(
        self,
        csv_path: str,
        output_dir: Optional[str] = None,
    ) -> Tuple[EvaluationScorecard, Path, Path]:
        """Read CSV, dispatch 3 reviewer agents in parallel, adjudicate, and save reports."""
        csv_file = Path(csv_path)
        if not csv_file.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        # Read CSV rows
        with open(csv_file, "r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))

        logger.info(f"Loaded {len(reader)} clinical knowledge rows from {csv_file.name}")

        # Dispatch 3 review agents in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            fut_clinical = executor.submit(self.clinical_agent.review_all, reader)
            fut_ontology = executor.submit(self.ontology_agent.review_all, reader)
            fut_graph = executor.submit(self.graph_agent.review_all, reader)

            clinical_report = fut_clinical.result()
            ontology_report = fut_ontology.result()
            graph_report = fut_graph.result()

        # Adjudicate and auto-heal
        scorecard, healed_rows = self.adjudicator.adjudicate(
            doc_name=csv_file.name,
            raw_rows=reader,
            clinical_report=clinical_report,
            ontology_report=ontology_report,
            graph_report=graph_report,
        )

        out_path = Path(output_dir or "data/reports")
        out_path.mkdir(parents=True, exist_ok=True)
        stem = csv_file.stem

        # 1. Export Markdown Scorecard
        md_file = out_path / f"{stem}_evaluation_scorecard.md"
        self.adjudicator.export_scorecard_markdown(scorecard, md_file)

        # 2. Export JSON Report
        json_file = out_path / f"{stem}_evaluation_report.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(scorecard.model_dump(), f, ensure_ascii=False, indent=2)

        # 3. Export Verified Triplet CSV (Exact format as original summary CSV, containing only verified triplets)
        verified_csv = out_path / f"{stem}_verified.csv"
        fieldnames = list(reader[0].keys()) if reader else []
        with open(verified_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(healed_rows)
        logger.info(f"Successfully exported {len(healed_rows)} certified/verified triplets to {verified_csv}")

        logger.info(f"Evaluation complete for {csv_file.name}. Score: {scorecard.overall_quality_score}/100. Saved to {md_file}")
        return scorecard, md_file, json_file, verified_csv
