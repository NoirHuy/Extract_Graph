"""Idempotent Neo4j Ingestion Module using Deterministic resolved_key Unique Constraints."""

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from edc_config import get_settings
from schema.schema_registry import ENTITY_TYPES

logger = logging.getLogger(__name__)


class Neo4jLoader:
    """Manages idempotent graph database ingestion into Neo4j."""

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
        self.schema_version = settings.SCHEMA_VERSION
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

    def compute_resolved_key(self, entity: Dict[str, Any]) -> str:
        """Calculate the deterministic resolved_key for an entity.

        If UMLS CUI is available, uses 'CUI:<umls_cui>'.
        If UMLS CUI is null, uses '<entity_type>:<normalized_name_lowercase>'.
        """
        cui = entity.get("umls_cui")
        if cui and str(cui).strip().upper() not in ("NONE", "NULL", ""):
            return f"CUI:{str(cui).strip().upper()}"
        ent_type = str(entity.get("entity_type", "Entity")).strip()
        norm_name = str(entity.get("normalized_name", "")).strip().lower()
        return f"{ent_type}:{norm_name}"

    def setup_constraints(self, session):
        """Create uniqueness constraints for Entity base label and specific entity types."""
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Entity) REQUIRE n.resolved_key IS UNIQUE"
        ]
        for ent_label in ENTITY_TYPES.keys():
            queries.append(
                f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:`{ent_label}`) REQUIRE n.resolved_key IS UNIQUE"
            )
        for q in queries:
            try:
                session.run(q)
            except Exception as e:
                logger.warning(f"Could not execute constraint '{q}': {e}")

    def ingest_graph(
        self,
        entities: List[Dict[str, Any]],
        relations: List[Dict[str, Any]],
        source_doc: str = "document.txt",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Ingest entities and relations into Neo4j with idempotency and provenance tracking."""
        if dry_run:
            logger.info(f"[Dry-Run] Ingesting {len(entities)} nodes and {len(relations)} edges for '{source_doc}'")
            return {
                "nodes_count": len(entities),
                "relations_count": len(relations),
                "source_document": source_doc,
                "status": "dry_run_success",
            }

        driver = self._get_driver()
        entity_key_map: Dict[str, str] = {}

        # Handle Aura and custom database names
        session_kwargs = {}
        if self.database and self.database not in ("neo4j", "default", ""):
            session_kwargs["database"] = self.database

        with driver.session(**session_kwargs) as session:
            # 1. Setup constraints
            self.setup_constraints(session)

            # 2. Ingest Nodes
            for ent in entities:
                resolved_key = self.compute_resolved_key(ent)
                ent_id = ent.get("id", "")
                if ent_id:
                    entity_key_map[ent_id] = resolved_key

                ent_type = ent.get("entity_type", "Entity")
                label = ent_type if ent_type in ENTITY_TYPES else "Entity"

                node_query = f"""
                MERGE (n:`{label}`:Entity {{resolved_key: $resolved_key}})
                ON CREATE SET
                    n.name = $name,
                    n.normalized_name = $normalized_name,
                    n.entity_type = $entity_type,
                    n.umls_cui = $umls_cui,
                    n.umls_sty = $umls_sty,
                    n.attributes = $attributes,
                    n.source_document = $source_doc,
                    n.schema_version = $schema_version,
                    n.created_at = datetime(),
                    n.updated_at = datetime()
                ON MATCH SET
                    n.name = $name,
                    n.umls_cui = coalesce($umls_cui, n.umls_cui),
                    n.umls_sty = coalesce($umls_sty, n.umls_sty),
                    n.updated_at = datetime()
                """

                params = {
                    "resolved_key": resolved_key,
                    "name": ent.get("text") or ent.get("normalized_name"),
                    "normalized_name": ent.get("normalized_name"),
                    "entity_type": ent_type,
                    "umls_cui": ent.get("umls_cui"),
                    "umls_sty": ent.get("umls_sty"),
                    "attributes": json.dumps(ent.get("attributes") or {}, ensure_ascii=False),
                    "source_doc": source_doc,
                    "schema_version": self.schema_version,
                }
                session.run(node_query, params)

            # 3. Ingest Relationships
            for rel in relations:
                src_id = rel.get("source_id", "")
                tgt_id = rel.get("target_id", "")
                src_key = entity_key_map.get(src_id)
                tgt_key = entity_key_map.get(tgt_id)
                rel_type = rel.get("relation_type", "RELATED_TO")

                if not src_key or not tgt_key:
                    logger.warning(f"Skipping relation with unresolved key: src={src_id}, tgt={tgt_id}")
                    continue

                rel_query = f"""
                MATCH (s:Entity {{resolved_key: $src_key}})
                MATCH (t:Entity {{resolved_key: $tgt_key}})
                MERGE (s)-[r:`{rel_type}`]->(t)
                ON CREATE SET
                    r.evidence_span = $evidence_span,
                    r.confidence = $confidence,
                    r.agreement_count = $agreement_count,
                    r.total_passes = $total_passes,
                    r.relation_properties = $relation_properties,
                    r.source_document = $source_doc,
                    r.schema_version = $schema_version,
                    r.created_at = datetime(),
                    r.updated_at = datetime()
                ON MATCH SET
                    r.confidence = $confidence,
                    r.agreement_count = $agreement_count,
                    r.updated_at = datetime()
                """

                rel_params = {
                    "src_key": src_key,
                    "tgt_key": tgt_key,
                    "evidence_span": rel.get("evidence_span", ""),
                    "confidence": float(rel.get("confidence", 1.0)),
                    "agreement_count": int(rel.get("agreement_count", 1)),
                    "total_passes": int(rel.get("total_passes", 1)),
                    "relation_properties": json.dumps(rel.get("relation_properties") or {}, ensure_ascii=False),
                    "source_doc": source_doc,
                    "schema_version": self.schema_version,
                }
                session.run(rel_query, rel_params)

        logger.info(f"Ingestion finished: {len(entities)} nodes and {len(relations)} relationships merged into Neo4j.")
        return {
            "nodes_count": len(entities),
            "relations_count": len(relations),
            "source_document": source_doc,
            "status": "success",
        }


def main():
    parser = argparse.ArgumentParser(description="Ingest Knowledge Graph into Neo4j")
    parser.add_argument("--entities", required=True, help="Path to normalized entities JSON")
    parser.add_argument("--relations", required=True, help="Path to validated relations JSON")
    parser.add_argument("--source-doc", default="document.txt", help="Source document name")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without connecting to Neo4j")
    args = parser.parse_args()

    with open(args.entities, "r", encoding="utf-8") as f:
        entities = json.load(f)
    with open(args.relations, "r", encoding="utf-8") as f:
        relations = json.load(f)

    loader = Neo4jLoader()
    summary = loader.ingest_graph(entities, relations, source_doc=args.source_doc, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
