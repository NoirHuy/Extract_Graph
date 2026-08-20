"""UMLS Normalization Orchestrator with 3-Tier Hybrid Strategy and Audit Logging."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from edc_config import get_settings
from extraction.llm_client import LLMClient
from normalization.dictionary_lookup import DictionaryLookup
from normalization.umls_client import UMLSClient
from normalization.vector_fallback import VectorFallbackMatcher
from schema.schema_registry import ENTITY_TYPES

logger = logging.getLogger(__name__)


def translate_term_to_english_with_llm(term_vi: str, entity_type: str, client: Optional[LLMClient] = None) -> Optional[str]:
    """Translate Vietnamese clinical term into standard English MeSH/SNOMED term."""
    if client is None:
        client = LLMClient()

    prompt = (
        f"Hãy dịch thuật ngữ y khoa tiếng Việt sau sang thuật ngữ y khoa tiếng Anh chuẩn (chuẩn MeSH hoặc SNOMED CT).\n"
        f"Loại thực thể: {entity_type}\n"
        f"Thuật ngữ tiếng Việt: \"{term_vi}\"\n"
        f"Chỉ trả về duy nhất cụm từ tiếng Anh, không thêm bất kỳ văn bản nào khác."
    )
    try:
        translated = client._call_with_retry(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        clean = translated.strip().strip('"').strip("'")
        return clean if clean else None
    except Exception as e:
        logger.warning(f"LLM translation failed for '{term_vi}': {e}")
        return None


import re

def is_pure_measurement_value(text: str, ent_type: str, attributes: Optional[Dict[str, Any]] = None) -> bool:
    """Detect if an entity is a numeric measurement, threshold value, or dosage count
    (e.g. '< 10%', '> 160 mm Hg', '130/80 mmHg', '4 loại thuốc trở lên', '>= 2 loại thuốc')
    rather than a controlled medical concept noun (e.g. 'Huyết áp tâm thu', 'Cung lượng tim', 'Thuốc ức chế men chuyển')."""
    clean = text.strip()
    clean_lower = clean.lower()

    # 1. Any entity starting with comparison operators or numbers + units
    if re.match(r"^[\d<>=±\-\+]+", clean):
        # Exclude controlled named entities that start with numbers (e.g., "11-Beta-Hydroxylase")
        if not re.search(r"[a-zA-Z]{4,}", clean) or any(u in clean_lower for u in ["mmhg", "mm hg", "mmol", "mg", "loại thuốc", "thuốc", "tuổi", "%"]):
            return True

    # 2. Threshold phrases or counts (e.g. "4 loại thuốc trở lên", "10 đến 20 mm hg", "từ 120 đến 129 mm hg")
    if re.search(r"\b\d+\s*(?:loại thuốc|thuốc|mmhg|mm hg|mmol|mg|%|tuổi|phút|giờ)\b", clean_lower):
        if not any(noun in clean_lower for noun in ["huyết áp tâm thu", "huyết áp tâm trương", "cung lượng", "sức cản", "creatinine", "kali", "natri", "canxi", "glucose", "vòng eo", "chiều cao", "cân nặng"]):
            return True

    # 3. Measurement type with numeric digits
    if ent_type == "Measurement":
        if re.search(r"\d", clean):
            if not any(noun in clean_lower for noun in ["huyết áp tâm thu", "huyết áp tâm trương", "cung lượng", "sức cản", "creatinine", "kali", "natri", "canxi", "glucose"]):
                return True

    return False


def normalize_entities(
    entities: List[Dict[str, Any]],
    doc_id: str = "document",
    output_dir: Optional[str] = None,
    client: Optional[LLMClient] = None,
    dict_lookup: Optional[DictionaryLookup] = None,
    umls_client: Optional[UMLSClient] = None,
    vector_matcher: Optional[VectorFallbackMatcher] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Normalize entities by assigning UMLS CUI and STY across 3 hybrid tiers.

    Returns:
        (normalized_entities, unmapped_entities)
    """
    settings = get_settings()
    if dict_lookup is None:
        dict_lookup = DictionaryLookup()
    if umls_client is None:
        umls_client = UMLSClient()
    if vector_matcher is None:
        vector_matcher = VectorFallbackMatcher(default_threshold=settings.SIMILARITY_THRESHOLD)

    normalized_list: List[Dict[str, Any]] = []
    unmapped_list: List[Dict[str, Any]] = []

    for ent in entities:
        norm_name = str(ent.get("normalized_name", "")).strip()
        ent_type = str(ent.get("entity_type", "")).strip()
        ent_copy = dict(ent)

        cui: Optional[str] = None
        sty: Optional[str] = None
        tui: Optional[str] = None
        match_tier: Optional[str] = None

        # Check if entity is a quantitative numeric value / threshold (No CUI applicable)
        if is_pure_measurement_value(norm_name, ent_type, ent.get("attributes")):
            match_tier = "Quantitative_Measurement"
            cui = None
            sty = None
            tui = None
        else:
            # --- TIER 1: Curated Bilingual Dictionary Cache ---
            dict_res = dict_lookup.lookup(norm_name)
            if dict_res:
                cui = dict_res.get("cui")
                tui = dict_res.get("tui")
                sty = dict_res.get("sty") or ENTITY_TYPES.get(ent_type, {}).get("sty", "Finding")
                match_tier = "Tier1_Dictionary"

            # --- TIER 2: LLM Context Translation -> UMLS REST API ---
            if not cui and settings.UMLS_API_KEY:
                en_term = translate_term_to_english_with_llm(norm_name, ent_type, client=client)
                if en_term:
                    from scripts.verify_umls_dict import search_best_umls_concept
                    concept = search_best_umls_concept(en_term, entity_type=ent_type, api_key=settings.UMLS_API_KEY)
                    if concept:
                        cui = concept.get("cui")
                        sty = concept.get("sty")
                        tui = concept.get("tui")
                        match_tier = f"Tier2_LLM_UMLS_REST({en_term})"
                        dict_lookup.add_entry(norm_name, en_term, cui, tui or "T033", ent_type)

            # --- TIER 3: Vector / Dense Embedding Fallback Matcher ---
            if not cui:
                candidates = list(dict_lookup._entries.values())
                vec_res = vector_matcher.find_best_match(norm_name, candidates)
                if vec_res:
                    cui = vec_res.get("cui")
                    tui = vec_res.get("tui")
                    sty = vec_res.get("sty") or ENTITY_TYPES.get(ent_type, {}).get("sty", "Finding")
                    match_tier = f"Tier3_VectorSimilarity({vec_res.get('similarity_score', 0):.2f})"

        # Assign resolved fields
        ent_copy["umls_cui"] = cui
        ent_copy["umls_sty"] = sty or (ENTITY_TYPES.get(ent_type, {}).get("sty") if cui else None)
        ent_copy["umls_tui"] = tui
        ent_copy["match_tier"] = match_tier

        normalized_list.append(ent_copy)

        if not cui and match_tier != "Quantitative_Measurement":
            unmapped_list.append({
                "id": ent.get("id"),
                "normalized_name": norm_name,
                "entity_type": ent_type,
                "evidence_span": ent.get("evidence_span"),
                "reason": "No match found across Tier 1 (Dict), Tier 2 (UMLS REST), and Tier 3 (Similarity >= 0.85)",
            })

    # Save unmapped audit log
    out_dir_path = Path(output_dir or "data/processed")
    out_dir_path.mkdir(parents=True, exist_ok=True)
    stem = Path(doc_id).stem
    unmapped_file = out_dir_path / f"{stem}_unmapped_entities.json"

    with open(unmapped_file, "w", encoding="utf-8") as f:
        json.dump(unmapped_list, f, ensure_ascii=False, indent=2)

    logger.info(
        f"Normalization complete: {len(normalized_list) - len(unmapped_list)}/{len(normalized_list)} "
        f"entities mapped to UMLS CUI. Logged {len(unmapped_list)} unmapped entities to {unmapped_file}"
    )

    return normalized_list, unmapped_list
