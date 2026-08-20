"""Multi-Pass Extraction Runner for Clinical Medical Knowledge Graph."""

import argparse
import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from edc_config import get_settings
from extraction.llm_client import LLMClient
from extraction.prompts import get_extraction_system_prompt, get_few_shot_examples
from extraction.text_chunker import chunk_vietnamese_text
from schema.schema_registry import get_edc_json_schema

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    pass_index: int
    entities: List[Dict[str, Any]]
    relations: List[Dict[str, Any]]
    source_doc: str


def run_extraction_pipeline(
    text: str,
    passes: int = 2,
    source_doc: str = "document.txt",
    output_dir: Optional[str] = None,
    client: Optional[LLMClient] = None,
) -> List[ExtractionResult]:
    """Execute multi-pass extraction on the given clinical document text."""
    if client is None:
        client = LLMClient()

    chunks = chunk_vietnamese_text(text)
    logger.info(f"Segmented document '{source_doc}' into {len(chunks)} chunk(s). Running {passes} pass(es)...")

    system_prompt = get_extraction_system_prompt()
    few_shots = get_few_shot_examples()
    schema = get_edc_json_schema()

    results: List[ExtractionResult] = []

    for p in range(1, passes + 1):
        temp = 0.0 if p == 1 else min(0.7, 0.2 * (p - 1))
        logger.info(f"--- Starting Extraction Pass {p}/{passes} (temperature={temp:.1f}) ---")

        all_pass_entities: List[Dict[str, Any]] = []
        all_pass_relations: List[Dict[str, Any]] = []

        for chunk in chunks:
            logger.info(f"Extracting Chunk {chunk.chunk_id}/{len(chunks)}: '{chunk.section_title}' ({len(chunk.text)} chars)...")
            try:
                payload = client.extract_structured(
                    system_prompt=system_prompt,
                    user_text=chunk.text,
                    schema=schema,
                    few_shot_examples=few_shots,
                    temperature=temp,
                )

                chunk_prefix = f"p{p}_c{chunk.chunk_id}_"
                id_map = {}

                # Remap entity IDs to be globally unique within this pass
                for ent in payload.get("entities", []):
                    old_id = ent.get("id", "")
                    new_id = f"{chunk_prefix}{old_id}"
                    id_map[old_id] = new_id
                    ent_copy = dict(ent)
                    ent_copy["id"] = new_id
                    ent_copy["chunk_id"] = chunk.chunk_id
                    ent_copy["section_title"] = chunk.section_title
                    all_pass_entities.append(ent_copy)

                # Remap relation IDs
                for rel in payload.get("relations", []):
                    rel_copy = dict(rel)
                    rel_copy["source_id"] = id_map.get(rel.get("source_id"), rel.get("source_id"))
                    rel_copy["target_id"] = id_map.get(rel.get("target_id"), rel.get("target_id"))
                    rel_copy["chunk_id"] = chunk.chunk_id
                    all_pass_relations.append(rel_copy)

            except Exception as e:
                logger.error(f"Error extracting Chunk {chunk.chunk_id} in Pass {p}: {e}")

        res = ExtractionResult(
            pass_index=p,
            entities=all_pass_entities,
            relations=all_pass_relations,
            source_doc=source_doc,
        )
        results.append(res)

    # Save intermediate raw extractions
    out_dir_path = Path(output_dir or "data/processed")
    out_dir_path.mkdir(parents=True, exist_ok=True)
    doc_stem = Path(source_doc).stem
    out_file = out_dir_path / f"{doc_stem}_extracted_raw.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)

    logger.info(f"Extraction complete. Saved raw results to {out_file}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Run Multi-Pass Extraction on Clinical Text")
    parser.add_argument("--input", required=True, help="Path to input text or markdown file")
    parser.add_argument("--passes", type=int, default=2, help="Number of extraction passes (default: 2)")
    parser.add_argument("--output-dir", default="data/processed", help="Output directory for processed artifacts")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    run_extraction_pipeline(
        text=content,
        passes=args.passes,
        source_doc=input_path.name,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
