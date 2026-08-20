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


def merge_entities(entity_lists: List[List[Dict[str, Any]]]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Deduplicate entities across multiple extraction passes.

    Matches entities on (normalized_name.strip().lower(), entity_type).
    Retains the longest evidence span, unions structured attributes,
    and returns canonical entities alongside an ID mapping (old_id -> canonical_id).
    """
    canonical_entities: Dict[str, Dict[str, Any]] = {}
    id_mapping: Dict[str, str] = {}
    next_canonical_id = 1

    for pass_entities in entity_lists:
        for ent in pass_entities:
            old_id = ent.get("id", "")
            norm_name = str(ent.get("normalized_name", "")).strip().lower()
            ent_type = str(ent.get("entity_type", "")).strip()
            key = f"{ent_type}:{norm_name}"

            if key not in canonical_entities:
                canonical_id = f"ent_{next_canonical_id}"
                next_canonical_id += 1
                canonical_ent = dict(ent)
                canonical_ent["id"] = canonical_id
                canonical_ent["attributes"] = dict(ent.get("attributes") or {})
                canonical_entities[key] = canonical_ent
            else:
                canonical_ent = canonical_entities[key]
                # Keep longest evidence span
                current_span = canonical_ent.get("evidence_span", "")
                new_span = ent.get("evidence_span", "")
                if len(new_span) > len(current_span):
                    canonical_ent["evidence_span"] = new_span

                # Union attributes
                new_attrs = ent.get("attributes") or {}
                canonical_ent["attributes"].update(new_attrs)

            id_mapping[old_id] = canonical_entities[key]["id"]

    return list(canonical_entities.values()), id_mapping


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

    for (src, tgt), rel_types_dict in pair_groups.items():
        if len(rel_types_dict) > 1:
            # Conflict detected across passes -> Check if tie-breaker can resolve
            types_by_rank = sorted(
                rel_types_dict.keys(),
                key=lambda t: _SPECIFICITY_RANK.get(t, 5),
                reverse=True,
            )
            top_type = types_by_rank[0]
            second_type = types_by_rank[1]
            top_rank = _SPECIFICITY_RANK.get(top_type, 5)
            second_rank = _SPECIFICITY_RANK.get(second_type, 5)

            # If top type is strictly more specific (e.g. UNDERLIES > MODIFIES)
            if top_rank > second_rank:
                chosen_occurrences = rel_types_dict[top_type]
                best_span = max((o.get("evidence_span", "") for o in chosen_occurrences), key=len, default="")
                
                # Combine confidence from both passes
                all_confs = [float(o.get("confidence", 0.8)) for occs in rel_types_dict.values() for o in occs]
                conf_product = 1.0
                for c in all_confs:
                    conf_product *= (1.0 - min(0.99, max(0.01, c)))
                stat_confidence = round(1.0 - conf_product, 4)

                consensus_relations.append({
                    "source_id": src,
                    "target_id": tgt,
                    "relation_type": top_type,
                    "confidence": stat_confidence,
                    "agreement_count": len(chosen_occurrences),
                    "total_passes": total_passes,
                    "agreement_ratio": round(len(chosen_occurrences) / total_passes, 2),
                    "evidence_span": best_span,
                    "relation_properties": {"resolved_alternate": second_type},
                    "status": "resolved_by_specificity",
                })
            else:
                # True contradiction of equal rank (e.g. TREATS vs CAUSES)
                variants = []
                for r_type, occurrences in rel_types_dict.items():
                    variants.append({
                        "relation_type": r_type,
                        "count": len(occurrences),
                        "mean_confidence": sum(o.get("confidence", 0.7) for o in occurrences) / len(occurrences),
                        "evidence_spans": [o.get("evidence_span", "") for o in occurrences],
                    })
                conflict_record = {
                    "source_id": src,
                    "target_id": tgt,
                    "status": "conflict",
                    "total_passes": total_passes,
                    "conflict_variants": variants,
                }
                conflict_relations.append(conflict_record)
        else:
            # Single relation type for this source-target pair
            (r_type, occurrences) = next(iter(rel_types_dict.items()))
            agreement_count = len(occurrences)

            # Statistical independent probability calculation: conf = 1 - prod(1 - c_i)
            conf_product = 1.0
            for occ in occurrences:
                c = float(occ.get("confidence", 0.7))
                conf_product *= (1.0 - min(0.99, max(0.01, c)))
            stat_confidence = round(1.0 - conf_product, 4)

            best_span = max((o.get("evidence_span", "") for o in occurrences), key=len, default="")
            relation_props = {}
            for occ in occurrences:
                if occ.get("relation_properties"):
                    relation_props.update(occ["relation_properties"])

            consensus_relations.append({
                "source_id": src,
                "target_id": tgt,
                "relation_type": r_type,
                "confidence": stat_confidence,
                "agreement_count": agreement_count,
                "total_passes": total_passes,
                "agreement_ratio": round(agreement_count / total_passes, 2),
                "evidence_span": best_span,
                "relation_properties": relation_props,
                "status": "agreed",
            })

    return consensus_relations, conflict_relations
