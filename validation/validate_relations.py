"""Validation Layer for Domain/Range Constraints and Confidence Thresholding."""

import logging
from typing import Any, Dict, List, Tuple
from schema.schema_registry import is_valid_relation

logger = logging.getLogger(__name__)


def validate_and_filter_relations(
    relations: List[Dict[str, Any]],
    entities: List[Dict[str, Any]],
    min_confidence: float = 0.7,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate relations against Domain/Range constraints in Schema Registry and filter by confidence.

    Returns:
        (valid_relations, invalid_relations)
    """
    entity_type_map = {e.get("id"): e.get("entity_type") for e in entities}
    valid_relations: List[Dict[str, Any]] = []
    invalid_relations: List[Dict[str, Any]] = []

    for rel in relations:
        src_id = rel.get("source_id")
        tgt_id = rel.get("target_id")
        rel_type = rel.get("relation_type")
        conf = float(rel.get("confidence", 1.0))

        src_type = entity_type_map.get(src_id)
        tgt_type = entity_type_map.get(tgt_id)

        if not src_type or not tgt_type:
            inv_rec = dict(rel)
            inv_rec["rejection_reason"] = f"Missing entity endpoint: src={src_type}, tgt={tgt_type}"
            invalid_relations.append(inv_rec)
            continue

        # Check confidence threshold
        if conf < min_confidence:
            inv_rec = dict(rel)
            inv_rec["rejection_reason"] = f"Confidence {conf} below threshold {min_confidence}"
            invalid_relations.append(inv_rec)
            continue

        # Check domain & range constraints
        if not is_valid_relation(src_type, rel_type, tgt_type):
            inv_rec = dict(rel)
            inv_rec["rejection_reason"] = f"Domain/Range violation: {src_type} -[{rel_type}]-> {tgt_type}"
            invalid_relations.append(inv_rec)
            continue

        valid_relations.append(rel)

    return valid_relations, invalid_relations
