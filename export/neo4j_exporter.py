"""Neo4j Knowledge Graph Exporter to Intuitive CSV Files."""

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from edc_config import get_settings

logger = logging.getLogger(__name__)

# Vietnamese translation map for clinical relations
RELATION_VN_MAP: Dict[str, str] = {
    "IS_SUBTYPE_OF": "Là phân loại / thể bệnh của",
    "CAUSES": "Là nguyên nhân gây ra",
    "INCREASES_RISK_OF": "Làm tăng nguy cơ mắc",
    "HAS_SYMPTOM": "Có triệu chứng cơ năng",
    "HAS_SIGN": "Có dấu hiệu thực thể",
    "UNDERLIES": "Là cơ chế sinh bệnh học của",
    "PART_OF_MECHANISM": "Là một phần của cơ chế",
    "LEADS_TO": "Dẫn đến biến chứng",
    "AFFECTS_ORGAN": "Gây tổn thương cơ quan",
    "DIAGNOSES": "Dùng để chẩn đoán",
    "DETECTS": "Giúp phát hiện",
    "MEASURES": "Đo lường chỉ số",
    "TREATS": "Điều trị",
    "CONTRAINDICATED_IN": "Chống chỉ định cho",
    "PREFERRED_FOR": "Ưu tiên chỉ định cho",
    "HAS_PREVALENCE": "Tỷ lệ lưu hành ở nhóm",
    "DEFINES_THRESHOLD_FOR": "Xác định ngưỡng chẩn đoán cho",
    "CLASSIFIES": "Phân loại thể bệnh",
    "MODIFIES": "Làm thay đổi / điều biến",
}


class Neo4jExporter:
    """Exports Knowledge Graph nodes and relationships from Neo4j into intuitive CSV files."""

    def __init__(
        self,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ):
        settings = get_settings()
        self.uri = uri or settings.NEO4J_URI
        self.username = username or settings.NEO4J_USERNAME
        self.password = password or settings.NEO4J_PASSWORD
        self.database = database or settings.NEO4J_DATABASE
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
                self._driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j at {self.uri}: {e}")
                raise
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def clear_database(self):
        """Detach delete all nodes and relationships in Neo4j."""
        driver = self._get_driver()
        session_kwargs = {}
        if self.database and self.database not in ("neo4j", "default", ""):
            session_kwargs["database"] = self.database

        with driver.session(**session_kwargs) as session:
            session.run("MATCH (n) DETACH DELETE n")
        logger.info("Successfully cleared all nodes and relationships from Neo4j database.")

    def fetch_nodes(self, source_doc: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query entity nodes from Neo4j, optionally filtered by source_document."""
        driver = self._get_driver()
        session_kwargs = {}
        if self.database and self.database not in ("neo4j", "default", ""):
            session_kwargs["database"] = self.database

        where_clauses = ["NOT (labels(n) = ['Entity'])"]
        params = {}
        if source_doc:
            where_clauses.append("n.source_document = $source_doc")
            params["source_doc"] = source_doc

        where_stmt = " WHERE " + " AND ".join(where_clauses)

        query = f"""
        MATCH (n)
        {where_stmt}
        RETURN
            coalesce(n.resolved_key, elementId(n)) AS id,
            coalesce(n.name, n.normalized_name, '') AS name,
            coalesce(n.normalized_name, n.name, '') AS normalized_name,
            coalesce(n.entity_type, [lbl IN labels(n) WHERE lbl <> 'Entity'][0], 'Entity') AS entity_type,
            [lbl IN labels(n) WHERE lbl <> 'Entity'] AS labels,
            coalesce(n.umls_cui, '') AS umls_cui,
            coalesce(n.umls_sty, '') AS umls_sty,
            coalesce(n.attributes, '{{}}') AS attributes,
            coalesce(n.source_document, '') AS source_document,
            toString(n.created_at) AS created_at
        ORDER BY entity_type, name
        """
        with driver.session(**session_kwargs) as session:
            result = session.run(query, params)
            return [dict(record.data()) for record in result]

    def fetch_relationships(self, source_doc: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query relationships with source and target details from Neo4j, optionally filtered by source_doc."""
        driver = self._get_driver()
        session_kwargs = {}
        if self.database and self.database not in ("neo4j", "default", ""):
            session_kwargs["database"] = self.database

        where_stmt = ""
        params = {}
        if source_doc:
            where_stmt = "WHERE r.source_document = $source_doc"
            params["source_doc"] = source_doc

        query = f"""
        MATCH (s)-[r]->(t)
        {where_stmt}
        RETURN
            coalesce(s.name, s.normalized_name, '') AS source_name,
            coalesce(s.entity_type, [lbl IN labels(s) WHERE lbl <> 'Entity'][0], 'Entity') AS source_type,
            coalesce(s.umls_cui, '') AS source_cui,
            type(r) AS relation_type,
            coalesce(t.name, t.normalized_name, '') AS target_name,
            coalesce(t.entity_type, [lbl IN labels(t) WHERE lbl <> 'Entity'][0], 'Entity') AS target_type,
            coalesce(t.umls_cui, '') AS target_cui,
            coalesce(r.confidence, 1.0) AS confidence,
            coalesce(r.agreement_count, 1) AS agreement_count,
            coalesce(r.total_passes, 1) AS total_passes,
            coalesce(r.evidence_span, '') AS evidence_span,
            coalesce(r.source_document, '') AS source_document,
            toString(r.created_at) AS created_at
        ORDER BY source_name, relation_type, target_name
        """
        with driver.session(**session_kwargs) as session:
            result = session.run(query, params)
            return [dict(record.data()) for record in result]

    def _safe_open_csv(self, file_path: Path):
        """Safely open a file for writing, with fallback if currently locked by Excel."""
        try:
            return open(file_path, "w", encoding="utf-8-sig", newline=""), file_path
        except PermissionError:
            fallback_path = file_path.with_name(f"{file_path.stem}_new{file_path.suffix}")
            logger.warning(f"File {file_path.name} is currently locked (e.g. open in Excel). Writing to {fallback_path.name} instead.")
            return open(fallback_path, "w", encoding="utf-8-sig", newline=""), fallback_path

    def export_all_to_csv(
        self,
        output_dir: str = "data/exports",
        source_doc: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Export nodes, relationships, and human-readable clinical summary in Vietnamese to CSV files."""
        out_path = Path(output_dir)
        if category and not output_dir.endswith(category):
            out_path = out_path / category
        out_path.mkdir(parents=True, exist_ok=True)

        nodes = self.fetch_nodes(source_doc=source_doc)
        relationships = self.fetch_relationships(source_doc=source_doc)

        nodes_csv_target = out_path / "nodes_entities.csv"
        relations_csv_target = out_path / "relationships_triplets.csv"
        summary_csv_target = out_path / "clinical_knowledge_summary.csv"

        # 1. Export Nodes CSV
        f_nodes, nodes_csv_file = self._safe_open_csv(nodes_csv_target)
        with f_nodes as f:
            fieldnames = [
                "id",
                "name",
                "normalized_name",
                "entity_type",
                "umls_cui",
                "umls_sty",
                "attributes",
                "source_document",
                "created_at",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for n in nodes:
                writer.writerow(n)

        # 2. Export Relationships CSV (Triplets)
        f_rels, relations_csv_file = self._safe_open_csv(relations_csv_target)
        with f_rels as f:
            fieldnames = [
                "source_name",
                "source_type",
                "source_cui",
                "relation_type",
                "target_name",
                "target_type",
                "target_cui",
                "confidence",
                "agreement_count",
                "total_passes",
                "evidence_span",
                "source_document",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in relationships:
                writer.writerow(r)

        # 3. Export Human-Friendly Clinical Knowledge Summary Table
        f_sum, summary_csv_file = self._safe_open_csv(summary_csv_target)
        with f_sum as f:
            fieldnames = [
                "STT",
                "Thực thể nguồn (Source)",
                "Loại nguồn (Type)",
                "Mã CUI nguồn",
                "Quan hệ lâm sàng (Relation)",
                "Thực thể đích (Target)",
                "Loại đích (Type)",
                "Mã CUI đích",
                "Bằng chứng văn bản gốc (Evidence Span)",
                "Tài liệu nguồn",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for idx, r in enumerate(relationships, 1):
                raw_rel = r.get("relation_type", "")
                vn_rel = RELATION_VN_MAP.get(raw_rel, raw_rel)
                writer.writerow({
                    "STT": idx,
                    "Thực thể nguồn (Source)": r.get("source_name"),
                    "Loại nguồn (Type)": r.get("source_type"),
                    "Mã CUI nguồn": r.get("source_cui") or "Chưa có",
                    "Quan hệ lâm sàng (Relation)": vn_rel,
                    "Thực thể đích (Target)": r.get("target_name"),
                    "Loại đích (Type)": r.get("target_type"),
                    "Mã CUI đích": r.get("target_cui") or "Chưa có",
                    "Bằng chứng văn bản gốc (Evidence Span)": r.get("evidence_span"),
                    "Tài liệu nguồn": r.get("source_document"),
                })

        logger.info(f"Successfully exported {len(nodes)} nodes and {len(relationships)} relationships to {out_path}")
        return {
            "output_dir": str(out_path),
            "nodes_csv": str(nodes_csv_file),
            "relations_csv": str(relations_csv_file),
            "clinical_summary_csv": str(summary_csv_file),
            "nodes_count": len(nodes),
            "relations_count": len(relationships),
        }


def main():
    parser = argparse.ArgumentParser(description="Export Knowledge Graph from Neo4j to CSV files")
    parser.add_argument("--output-dir", default="data/exports", help="Output directory for CSV files (default: data/exports)")
    parser.add_argument("--category", default=None, help="Document category subfolder (e.g. hypertension, diabetes)")
    parser.add_argument("--source-doc", default=None, help="Filter export by specific source document name")
    parser.add_argument("--clear-db", action="store_true", help="Clear all data from Neo4j database")
    args = parser.parse_args()

    exporter = Neo4jExporter()
    if args.clear_db:
        exporter.clear_database()
        print("Neo4j database cleared successfully.")
        exporter.close()
        return

    res = exporter.export_all_to_csv(output_dir=args.output_dir, source_doc=args.source_doc, category=args.category)
    print("\n" + "=" * 65)
    print("  EXPORT COMPLETED SUCCESSFULLY")
    print("=" * 65)
    if args.source_doc:
        print(f"Filtered by Document: {args.source_doc}")
    print(f"Target Directory: {res['output_dir']}")
    print(f"Exported Nodes ({res['nodes_count']}): {res['nodes_csv']}")
    print(f"Exported Triplets ({res['relations_count']}): {res['relations_csv']}")
    print(f"Clinical Summary Table: {res['clinical_summary_csv']}")
    print("=" * 65 + "\n")
    exporter.close()


if __name__ == "__main__":
    main()
