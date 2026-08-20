"""Multi-Pass Consensus, Entity Deduplication and Semantic Conflict Tie-Breaking."""

import logging
from typing import Any, Dict, List, Optional, Tuple
from schema.schema_registry import is_valid_relation

logger = logging.getLogger(__name__)

# Specificity hierarchy: higher number = more clinically specific
_SPECIFICITY_RANK: Dict[str, int] = {
    "UNDERLIES": 10,
    "PART_OF_MECHANISM": 10,
    "DEFINES_THRESHOLD_FOR": 10,
    "DIAGNOSES": 9,
    "TREATS": 9,
    "CONTRAINDICATED_IN": 9,
    "PREFERRED_FOR": 9,
    "CAUSES": 8,
    "LEADS_TO": 8,
    "AFFECTS_ORGAN": 8,
    "IS_SUBTYPE_OF": 8,
    "INCREASES_RISK_OF": 7,
    "HAS_SYMPTOM": 7,
    "HAS_SIGN": 7,
    "DETECTS": 7,
    "MEASURES": 7,
    "CLASSIFIES": 7,
    "HAS_PREVALENCE": 6,
    "MODIFIES": 4,
}

# Entity type specificity hierarchy to resolve type conflicts during deduplication
_ENTITY_TYPE_SPECIFICITY: Dict[str, int] = {
    "DiseaseSubtype": 10,
    "DrugClass": 10,
    "Measurement": 10,
    "Cause": 9,
    "Mechanism": 9,
    "Complication": 8,
    "Disease": 8,
    "Drug": 8,
    "Test": 8,
    "Symptom": 8,
    "Sign": 8,
    "Treatment": 8,
    "RiskFactor": 8,
    "Organ": 8,
    "PatientGroup": 8,
    "Guideline": 8,
    "Entity": 1,
}


def merge_entities(entity_lists: List[List[Dict[str, Any]]]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Deduplicate entities across multiple extraction passes by canonical normalized_name.

    Resolves type conflicts by prioritizing more specific entity types (e.g. DiseaseSubtype > Disease).
    Retains the longest evidence span, unions structured attributes,
    and returns canonical entities alongside an ID mapping (old_id -> canonical_id).
    """
    name_to_canonical: Dict[str, Dict[str, Any]] = {}
    id_mapping: Dict[str, str] = {}
    next_canonical_id = 1

    for pass_entities in entity_lists:
        for ent in pass_entities:
            old_id = ent.get("id", "")
            norm_name = str(ent.get("normalized_name") or ent.get("text", "")).strip().lower()
            ent_type = str(ent.get("entity_type", "")).strip() or "Entity"

            if not norm_name:
                continue

            if norm_name not in name_to_canonical:
                canonical_id = f"ent_{next_canonical_id}"
                next_canonical_id += 1
                canonical_ent = dict(ent)
                canonical_ent["id"] = canonical_id
                canonical_ent["entity_type"] = ent_type
                canonical_ent["attributes"] = dict(ent.get("attributes") or {})
                name_to_canonical[norm_name] = canonical_ent
            else:
                canonical_ent = name_to_canonical[norm_name]
                # If current entity type is more specific, update canonical type
                current_type = canonical_ent.get("entity_type", "Entity")
                current_rank = _ENTITY_TYPE_SPECIFICITY.get(current_type, 5)
                new_rank = _ENTITY_TYPE_SPECIFICITY.get(ent_type, 5)
                if new_rank > current_rank:
                    canonical_ent["entity_type"] = ent_type

                # Keep longest evidence span
                current_span = canonical_ent.get("evidence_span", "")
                new_span = ent.get("evidence_span", "")
                if len(new_span) > len(current_span):
                    canonical_ent["evidence_span"] = new_span

                # Union attributes
                new_attrs = ent.get("attributes") or {}
                canonical_ent["attributes"].update(new_attrs)

            id_mapping[old_id] = name_to_canonical[norm_name]["id"]

    return list(name_to_canonical.values()), id_mapping


def aggregate_relation_consensus(
    relation_lists: List[List[Dict[str, Any]]],
    id_mapping: Dict[str, str],
    total_passes: int = 2,
    entities: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Aggregate relations across multi-pass runs with statistical confidence, conflict detection and smart tie-breaking.

    - Concordant relations: Computes confidence = 1 - product(1 - c_i), records agreement_count.
    - Conflicting relations (same source & target, discordant relation_type):
      Applies Semantic Tie-Breaker by Specificity Rank if applicable, otherwise flags as 'conflict'.
    Returns (consensus_relations, conflict_relations).
    """
    pair_groups: Dict[Tuple[str, str], Dict[str, List[Dict[str, Any]]]] = {}

    for pass_rels in relation_lists:
        for rel in pass_rels:
            raw_src = rel.get("source_id", "")
            raw_tgt = rel.get("target_id", "")
            src_canon = id_mapping.get(raw_src, raw_src)
            tgt_canon = id_mapping.get(raw_tgt, raw_tgt)
            rel_type = rel.get("relation_type", "")

            if not src_canon or not tgt_canon or src_canon == tgt_canon:
                continue

            pair_key = (src_canon, tgt_canon)
            if pair_key not in pair_groups:
                pair_groups[pair_key] = {}

            if rel_type not in pair_groups[pair_key]:
                pair_groups[pair_key][rel_type] = []

            pair_groups[pair_key][rel_type].append(rel)

    consensus_relations: List[Dict[str, Any]] = []
    conflict_relations: List[Dict[str, Any]] = []

    for (src_canon, tgt_canon), type_map in pair_groups.items():
        if len(type_map) == 1:
            # Full agreement on relation type
            rel_type, instances = list(type_map.items())[0]
            conf = _combine_confidences([inst.get("confidence", 0.8) for inst in instances])
            longest_span = max(
                (inst.get("evidence_span", "") for inst in instances),
                key=len,
                default="",
            )
            consensus_relations.append({
                "source_id": src_canon,
                "target_id": tgt_canon,
                "relation_type": rel_type,
                "confidence": conf,
                "agreement_count": len(instances),
                "total_passes": total_passes,
                "evidence_span": longest_span,
            })
        else:
            # Discordant relation types between same source and target
            ranked_types = sorted(
                type_map.keys(),
                key=lambda t: (_SPECIFICITY_RANK.get(t, 0), len(type_map[t])),
                reverse=True,
            )
            best_type = ranked_types[0]
            second_type = ranked_types[1]
            best_rank = _SPECIFICITY_RANK.get(best_type, 0)
            second_rank = _SPECIFICITY_RANK.get(second_type, 0)

            # Check if specificity tie-breaker can resolve it
            if best_rank > second_rank:
                instances = type_map[best_type]
                conf = _combine_confidences([inst.get("confidence", 0.8) for inst in instances])
                longest_span = max(
                    (inst.get("evidence_span", "") for inst in instances),
                    key=len,
                    default="",
                )
                logger.info(
                    f"Semantic Tie-Breaker resolved conflict for ({src_canon} -> {tgt_canon}): "
                    f"Selected '{best_type}' (rank={best_rank}) over '{second_type}' (rank={second_rank})"
                )
                consensus_relations.append({
                    "source_id": src_canon,
                    "target_id": tgt_canon,
                    "relation_type": best_type,
                    "confidence": conf,
                    "agreement_count": len(instances),
                    "total_passes": total_passes,
                    "evidence_span": longest_span,
                    "status": "resolved_by_specificity",
                })
            else:
                # True irresolvable conflict with equal support and equal specificity
                conflict_record = {
                    "source_id": src_canon,
                    "target_id": tgt_canon,
                    "conflict_variants": list(type_map.keys()),
                    "competing_relations": {
                        t: {
                            "pass_count": len(insts),
                            "avg_confidence": sum(i.get("confidence", 0.8) for i in insts) / len(insts),
                            "evidence_spans": [i.get("evidence_span", "") for i in insts],
                        }
                        for t, insts in type_map.items()
                    },
                    "status": "conflict",
                }
                conflict_relations.append(conflict_record)

    return consensus_relations, conflict_relations


def _combine_confidences(confidences: List[float]) -> float:
    """Calculate multi-pass consolidated confidence: 1 - prod(1 - c_i), capped at 0.99."""
    if not confidences:
        return 0.5
    prob_all_wrong = 1.0
    for c in confidences:
        prob_all_wrong *= (1.0 - min(0.99, max(0.01, c)))
    combined = 1.0 - prob_all_wrong
    return round(min(0.99, max(0.1, combined)), 4)
