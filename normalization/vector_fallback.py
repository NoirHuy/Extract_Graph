"""Tier 3: Vector & Character/N-Gram Similarity Fallback Matcher."""

import logging
import math
import re
from typing import Any, Dict, List, Optional
from edc_config import get_settings

logger = logging.getLogger(__name__)


def _get_ngrams(text: str, n: int = 3) -> set:
    clean = re.sub(r"[^\w\s]", "", text.lower()).strip()
    padded = f"  {clean}  "
    return {padded[i : i + n] for i in range(len(padded) - n + 1)}


def _ngram_cosine_similarity(s1: str, s2: str) -> float:
    ng1 = _get_ngrams(s1)
    ng2 = _get_ngrams(s2)
    if not ng1 or not ng2:
        return 0.0
    intersection = len(ng1.intersection(ng2))
    return intersection / math.sqrt(len(ng1) * len(ng2))


class VectorFallbackMatcher:
    """Computes similarity against candidate CUIs when direct lookup fails."""

    def __init__(self, default_threshold: Optional[float] = None):
        settings = get_settings()
        self.default_threshold = default_threshold or settings.SIMILARITY_THRESHOLD

    def find_best_match(
        self,
        term: str,
        candidate_entries: List[Dict[str, Any]],
        threshold: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Find the candidate with the highest similarity score exceeding the threshold."""
        thresh = threshold if threshold is not None else self.default_threshold
        best_match = None
        best_score = 0.0

        for cand in candidate_entries:
            cand_name = cand.get("name") or cand.get("en") or cand.get("text", "")
            score = _ngram_cosine_similarity(term, cand_name)
            if score > best_score:
                best_score = score
                best_match = cand

        if best_match and best_score >= thresh:
            logger.info(f"Vector fallback matched '{term}' -> '{best_match.get('cui')}' (score={best_score:.3f} >= {thresh})")
            res = dict(best_match)
            res["similarity_score"] = best_score
            return res

        return None
