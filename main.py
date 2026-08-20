"""Unified CLI Controller for EDC Medical Knowledge Graph Pipeline.

Commands:
  probe-llm      Probe the LLM endpoint capabilities and list available models.
  extract        Run multi-pass LLM extraction on a raw medical document.
  consensus      Merge entities and aggregate relation consensus across passes.
  normalize      Map normalized_name to UMLS CUI using 3-tier hybrid strategy.
  validate       Validate domain/range constraints and filter by confidence.
  ingest         Ingest normalized entities and validated relations into Neo4j.
  export         Export Knowledge Graph from Neo4j into intuitive CSV files with category subfolders.
  verify-dict    Verify and heal dictionary CUIs against live NLM UMLS UTS Search API (anti-hallucination).
  run-all        Execute the entire pipeline end-to-end from input document to Neo4j with auto-classified subfolders.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from edc_config import get_settings
from export.neo4j_exporter import Neo4jExporter
from extraction.extract import run_extraction_pipeline
from extraction.llm_client import LLMClient
from ingestion.neo4j_loader import Neo4jLoader
from normalization.umls_normalize import normalize_entities
from validation.consensus import aggregate_relation_consensus, merge_entities
from validation.validate_relations import validate_and_filter_relations

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def resolve_processed_dir(input_path: Path, output_dir: Optional[str] = None) -> Path:
    """Auto-detect category subfolder from input path (e.g. data/raw/hypertension/doc.txt -> data/processed/hypertension)."""
    if output_dir and output_dir != "data/processed":
        target = Path(output_dir)
    else:
        raw_root = Path("data/raw").resolve()
        try:
            rel = input_path.resolve().relative_to(raw_root)
            if len(rel.parts) > 1:
                category = rel.parent
                target = Path("data/processed") / category
            else:
                target = Path("data/processed")
        except ValueError:
            target = Path("data/processed")

    target.mkdir(parents=True, exist_ok=True)
    return target


def run_full_pipeline(
    input_file: str,
    passes: int = 2,
    min_confidence: float = 0.7,
    output_dir: Optional[str] = None,
    dry_run: bool = False,
):
    """Execute end-to-end EDC Knowledge Graph Pipeline."""
    input_path = Path(input_file)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)

    doc_name = input_path.name
    doc_stem = input_path.stem
    out_dir = resolve_processed_dir(input_path, output_dir)

    with open(input_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    print("\n" + "=" * 65)
    print(f"  STARTING EDC MEDICAL KG PIPELINE FOR: {doc_name}")
    print(f"  Target Processed Folder: {out_dir}")
    print("=" * 65)

    # 1. Extraction (Multi-Pass)
    print("\n[Step 1/5] Running LLM Extraction...")
    extractions = run_extraction_pipeline(
        text=raw_text,
        passes=passes,
        source_doc=doc_name,
        output_dir=str(out_dir),
    )

    pass_entities = [res.entities for res in extractions]
    pass_relations = [res.relations for res in extractions]

    # 2. Validation & Consensus Layer
    print("\n[Step 2/5] Merging Entities & Aggregating Multi-Pass Consensus...")
    canonical_entities, id_mapping = merge_entities(pass_entities)
    consensus_relations, conflicts = aggregate_relation_consensus(
        pass_relations, id_mapping=id_mapping, total_passes=passes
    )

    if conflicts:
        conflict_file = out_dir / f"{doc_stem}_conflicts.json"
        with open(conflict_file, "w", encoding="utf-8") as f:
            json.dump(conflicts, f, ensure_ascii=False, indent=2)
        logger.warning(f"Detected {len(conflicts)} conflicting relation(s). Saved to {conflict_file}")

    # 3. UMLS Normalization
    print("\n[Step 3/5] Performing 3-Tier UMLS Normalization...")
    normalized_entities, unmapped_entities = normalize_entities(
        canonical_entities,
        doc_id=doc_name,
        output_dir=str(out_dir),
    )

    # 4. Domain / Range & Confidence Validation
    print("\n[Step 4/5] Enforcing Domain/Range Constraints & Confidence Filtering...")
    valid_relations, invalid_relations = validate_and_filter_relations(
        consensus_relations,
        normalized_entities,
        min_confidence=min_confidence,
    )

    if invalid_relations:
        inv_file = out_dir / f"{doc_stem}_invalid_relations.json"
        with open(inv_file, "w", encoding="utf-8") as f:
            json.dump(invalid_relations, f, ensure_ascii=False, indent=2)
        logger.info(f"Filtered out {len(invalid_relations)} invalid/low-confidence relations to {inv_file}")

    # Save final validated graph payload
    final_payload = {
        "source_document": doc_name,
        "schema_version": get_settings().SCHEMA_VERSION,
        "entities": normalized_entities,
        "relations": valid_relations,
        "metrics": {
            "total_raw_entities": sum(len(e) for e in pass_entities),
            "canonical_entities": len(normalized_entities),
            "mapped_umls_cui": len(normalized_entities) - len(unmapped_entities),
            "unmapped_entities": len(unmapped_entities),
            "total_raw_relations": sum(len(r) for r in pass_relations),
            "consensus_relations": len(consensus_relations),
            "conflicting_relations": len(conflicts),
            "valid_final_relations": len(valid_relations),
            "invalid_relations": len(invalid_relations),
        },
    }

    final_file = out_dir / f"{doc_stem}_graph_final.json"
    with open(final_file, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved complete Knowledge Graph dataset to {final_file}")

    # 5. Neo4j Ingestion
    print("\n[Step 5/5] Ingesting into Neo4j Graph Database...")
    loader = Neo4jLoader()
    summary = loader.ingest_graph(
        entities=normalized_entities,
        relations=valid_relations,
        source_doc=doc_name,
        dry_run=dry_run,
    )

    print("\n" + "=" * 65)
    print("  EDC PIPELINE EXECUTION FINISHED SUCCESSFULLY")
    print("=" * 65)
    print(f"Document: {doc_name}")
    print(f"Target Directory: {out_dir}")
    print(f"Canonical Nodes: {len(normalized_entities)} (UMLS Mapped: {len(normalized_entities) - len(unmapped_entities)})")
    print(f"Valid Relationships: {len(valid_relations)} (Conflicts: {len(conflicts)})")
    print(f"Ingestion Status: {summary.get('status')}")
    print("=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="EDC Clinical Medical Knowledge Graph Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. probe-llm
    subparsers.add_parser("probe-llm", help="Probe LLM endpoint capabilities and list available models")

    # 2. run-all
    run_all_p = subparsers.add_parser("run-all", help="Run full pipeline end-to-end from text into Neo4j")
    run_all_p.add_argument("--input", required=True, help="Input clinical text file (.txt, .md)")
    run_all_p.add_argument("--passes", type=int, default=2, help="Number of extraction passes (default: 2)")
    run_all_p.add_argument("--min-confidence", type=float, default=0.7, help="Minimum relation confidence (default: 0.7)")
    run_all_p.add_argument("--output-dir", default=None, help="Output directory (default: auto-detected from subfolder)")
    run_all_p.add_argument("--dry-run", action="store_true", help="Dry run without writing to Neo4j")

    # 3. extract
    extract_p = subparsers.add_parser("extract", help="Run multi-pass extraction only")
    extract_p.add_argument("--input", required=True, help="Input text file")
    extract_p.add_argument("--passes", type=int, default=2, help="Extraction passes")
    extract_p.add_argument("--output-dir", default="data/processed", help="Output directory")

    # 4. ingest
    ingest_p = subparsers.add_parser("ingest", help="Ingest processed graph JSON into Neo4j")
    ingest_p.add_argument("--entities", required=True, help="Entities JSON file")
    ingest_p.add_argument("--relations", required=True, help="Relations JSON file")
    ingest_p.add_argument("--source-doc", default="document.txt", help="Source document name")
    ingest_p.add_argument("--dry-run", action="store_true", help="Dry run without writing to Neo4j")

    # 5. export
    export_p = subparsers.add_parser("export", help="Export Knowledge Graph from Neo4j into intuitive CSV files")
    export_p.add_argument("--output-dir", default="data/exports", help="Output directory for CSV files (default: data/exports)")
    export_p.add_argument("--category", default=None, help="Document category subfolder (e.g. hypertension, diabetes)")
    export_p.add_argument("--source-doc", default=None, help="Filter export by specific source document (e.g. hypertension_sample.txt)")
    export_p.add_argument("--clear-db", action="store_true", help="Clear all data in Neo4j database")

    # 6. verify-dict
    verify_p = subparsers.add_parser("verify-dict", help="Verify and heal dictionary CUIs against live NLM UMLS UTS Search API")
    verify_p.add_argument("--dict-path", default="data/dict/medical_vi_en_cui.json", help="Path to dictionary JSON")
    verify_p.add_argument("--report-path", default="data/dict/umls_verification_report.json", help="Path to output report")
    verify_p.add_argument("--apply-fixes", action="store_true", help="Automatically heal and write verified official CUIs to dictionary")
    verify_p.add_argument("--api-key", default=None, help="UMLS API Key")

    args = parser.parse_args()

    if args.command == "probe-llm":
        from tests.check_llm_capabilities import main as probe_main
        probe_main()
    elif args.command == "run-all":
        run_full_pipeline(
            input_file=args.input,
            passes=args.passes,
            min_confidence=args.min_confidence,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
        )
    elif args.command == "extract":
        with open(args.input, "r", encoding="utf-8") as f:
            content = f.read()
        run_extraction_pipeline(content, passes=args.passes, source_doc=Path(args.input).name, output_dir=args.output_dir)
    elif args.command == "ingest":
        with open(args.entities, "r", encoding="utf-8") as f:
            ents = json.load(f)
        with open(args.relations, "r", encoding="utf-8") as f:
            rels = json.load(f)
        loader = Neo4jLoader()
        summary = loader.ingest_graph(ents, rels, source_doc=args.source_doc, dry_run=args.dry_run)
        print(json.dumps(summary, indent=2))
    elif args.command == "export":
        exporter = Neo4jExporter()
        if args.clear_db:
            exporter.clear_database()
            print("Neo4j database cleared successfully.")
            exporter.close()
            return

        res = exporter.export_all_to_csv(
            output_dir=args.output_dir,
            source_doc=args.source_doc,
            category=args.category,
        )
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
    elif args.command == "verify-dict":
        from scripts.verify_umls_dict import verify_and_heal_dictionary
        report = verify_and_heal_dictionary(
            dict_path=args.dict_path,
            report_path=args.report_path,
            apply_fixes=args.apply_fixes,
            api_key=args.api_key,
        )
        print("\n" + "=" * 75)
        print("  UMLS CUI & SEMANTIC NETWORK (TUI/STY) INTEGRITY REPORT")
        print("=" * 75)
        print(f"Total Dictionary Entries:      {report['total_entries']}")
        print(f"Verified Exact Matches:        {report['verified_matches']} ({report['verified_matches']/report['total_entries']*100:.1f}%)")
        print(f"Healed / Synchronized Entries: {report['mismatched_or_healed_count']}")
        print(f"Explicit Null / Not Found:     {report['not_found_count']}")
        print(f"CUI Collisions (Duplicates):    {report['collision_count']}")
        print(f"TUI <-> STY Mismatches:        {report['tui_sty_mismatch_count']}")
        print(f"Report File:                   {args.report_path}")
        print("=" * 75)
        if args.apply_fixes:
            print("\n Applied verified official CUIs & synchronized TUIs/STYs to dictionary successfully.")
        else:
            print("\n Run with '--apply-fixes' to automatically synchronize dictionary with official UMLS Semantic Network.")
        print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
