"""Validation Layer for Domain/Range Constraints, Confidence Thresholding, and Auto-Remapping."""

import logging
from typing import Any, Dict, List, Tuple
from schema.schema_registry import is_valid_relation

logger = logging.getLogger(__name__)

# Canonical remapping for near-miss relations with strong clinical intent
_CANONICAL_REMAPPINGS = [
    # If LLM uses INCREASES_RISK_OF between Disease and Complication, can normalize to LEADS_TO or keep if allowed
    (("Disease", "INCREASES_RISK_OF", "Complication"), "LEADS_TO"),
    (("DiseaseSubtype", "INCREASES_RISK_OF", "Complication"), "LEADS_TO"),
    (("Cause", "UNDERLIES", "Mechanism"), "PART_OF_MECHANISM"),
]


def validate_and_filter_relations(
    relations: List[Dict[str, Any]],
    entities: List[Dict[str, Any]],
    min_confidence: float = 0.7,
    auto_remap: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate relations against Domain/Range constraints in Schema Registry and filter by confidence.

    Supports intelligent auto-remapping for near-miss clinical relations.
    Returns:
        (valid_relations, invalid_relations)
    """
    entity_type_map = {e.get("id"): e.get("entity_type") for e in entities}
    valid_relations: List[Dict[str, Any]] = []
    invalid_relations: List[Dict[str, Any]] = []

    for rel in relations:
        rel_copy = dict(rel)
        src_id = rel_copy.get("source_id")
        tgt_id = rel_copy.get("target_id")
        rel_type = rel_copy.get("relation_type")
        conf = float(rel_copy.get("confidence", 1.0))

        src_type = entity_type_map.get(src_id)
        tgt_type = entity_type_map.get(tgt_id)

        if not src_type or not tgt_type:
            rel_copy["rejection_reason"] = f"Missing entity endpoint: src={src_type}, tgt={tgt_type}"
            invalid_relations.append(rel_copy)
            continue

        # Check confidence threshold
        if conf < min_confidence:
            rel_copy["rejection_reason"] = f"Confidence {conf} below threshold {min_confidence}"
            invalid_relations.append(rel_copy)
            continue

        # Check domain & range constraints
        if not is_valid_relation(src_type, rel_type, tgt_type):
            remapped = False
            if auto_remap:
                for (from_src, from_rel, from_tgt), target_rel in _CANONICAL_REMAPPINGS:
                    if src_type == from_src and rel_type == from_rel and tgt_type == from_tgt:
                        if is_valid_relation(src_type, target_rel, tgt_type):
                            logger.info(f"Auto-remapped relation: {src_type} -[{rel_type}]-> {tgt_type} to [{target_rel}]")
                            rel_copy["relation_type"] = target_rel
                            rel_copy["remapped_from"] = rel_type
                            remapped = True
                            break

            if not remapped and not is_valid_relation(src_type, rel_copy.get("relation_type"), tgt_type):
                rel_copy["rejection_reason"] = f"Domain/Range violation: {src_type} -[{rel_type}]-> {tgt_type}"
                invalid_relations.append(rel_copy)
                continue

        valid_relations.append(rel_copy)

    return valid_relations, invalid_relations
