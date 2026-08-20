"""Tier 3: Hybrid Dense Vector & Character/N-Gram Similarity Fallback Matcher.

Features:
1. Dense Semantic Vector Embeddings: Powered by openai/text-embedding-3-large via OpenRouter.
2. Persistent Vector Caching: Saves dictionary embeddings to avoid repeated API requests.
3. Graceful N-Gram Fallback: Falls back to character 3-gram cosine similarity when offline/no API key.
"""

import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from edc_config import get_settings

logger = logging.getLogger(__name__)


def _get_ngrams(text: str, n: int = 3) -> set:
    """Extract character n-grams for lightweight string matching."""
    clean = re.sub(r"[^\w\s]", "", text.lower()).strip()
    padded = f"  {clean}  "
    return {padded[i : i + n] for i in range(len(padded) - n + 1)}


def _ngram_cosine_similarity(s1: str, s2: str) -> float:
    """Compute character n-gram cosine similarity between two strings."""
    ng1 = _get_ngrams(s1)
    ng2 = _get_ngrams(s2)
    if not ng1 or not ng2:
        return 0.0
    intersection = len(ng1.intersection(ng2))
    return intersection / math.sqrt(len(ng1) * len(ng2))


def _dense_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two dense embedding vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot_product / (norm1 * norm2)


class DenseEmbeddingClient:
    """Client for generating and caching dense embeddings via OpenRouter / OpenAI API."""

    def __init__(self, api_base: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None):
        settings = get_settings()
        self.api_base = (api_base or settings.EMBEDDING_API_BASE).rstrip("/")
        self.api_key = api_key or settings.EMBEDDING_API_KEY
        self.model = model or settings.EMBEDDING_MODEL_NAME
        self.dimensions = settings.EMBEDDING_DIMENSIONS
        self.cache_file = Path(settings.EMBEDDING_CACHE_FILE)
        self.cache: Dict[str, List[float]] = self._load_cache()

    def _load_cache(self) -> Dict[str, List[float]]:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load embedding cache: {e}")
        return {}

    def save_cache(self):
        """Persist embedding cache to disk."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save embedding cache: {e}")

    def is_available(self) -> bool:
        """Check if API key is configured for remote embeddings."""
        return bool(self.api_key and not self.api_key.startswith("your_"))

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for a single text, utilizing cache if present."""
        clean_text = text.strip()
        if not clean_text:
            return None

        if clean_text in self.cache:
            return self.cache[clean_text]

        if not self.is_available():
            return None

        url = f"{self.api_base}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": clean_text,
            "dimensions": self.dimensions,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                embedding = data["data"][0]["embedding"]
                self.cache[clean_text] = embedding
                return embedding
            else:
                logger.warning(f"OpenRouter embedding error ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.warning(f"Embedding request failed for '{clean_text}': {e}")

        return None

    def get_batch_embeddings(self, texts: List[str]) -> Dict[str, List[float]]:
        """Compute embeddings for a batch of texts and cache them."""
        results = {}
        missing = []
        for t in texts:
            clean = t.strip()
            if not clean:
                continue
            if clean in self.cache:
                results[clean] = self.cache[clean]
            else:
                missing.append(clean)

        if not missing or not self.is_available():
            return results

        url = f"{self.api_base}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # Batch requests in chunks of 50
        chunk_size = 50
        for i in range(0, len(missing), chunk_size):
            chunk = missing[i : i + chunk_size]
            payload = {
                "model": self.model,
                "input": chunk,
                "dimensions": self.dimensions,
            }
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("data", []):
                        idx = item["index"]
                        emb = item["embedding"]
                        orig_text = chunk[idx]
                        self.cache[orig_text] = emb
                        results[orig_text] = emb
                else:
                    logger.warning(f"Batch embedding error ({resp.status_code}): {resp.text}")
            except Exception as e:
                logger.warning(f"Batch embedding request failed: {e}")

        self.save_cache()
        return results


class VectorFallbackMatcher:
    """Computes similarity against candidate CUIs using dense neural embeddings with n-gram fallback."""

    def __init__(self, default_threshold: Optional[float] = None):
        settings = get_settings()
        self.ngram_threshold = default_threshold or settings.SIMILARITY_THRESHOLD
        self.dense_threshold = settings.DENSE_SIMILARITY_THRESHOLD
        self.embedding_client = DenseEmbeddingClient()

    def find_best_match(
        self,
        term: str,
        candidate_entries: List[Dict[str, Any]],
        threshold: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Find the candidate with highest similarity using Dense Vectors first, then N-Gram fallback."""
        if not candidate_entries:
            return None

        # 1. Try Dense Neural Embedding Matching (openai/text-embedding-3-large)
        if self.embedding_client.is_available() or len(self.embedding_client.cache) > 0:
            term_embedding = self.embedding_client.get_embedding(term)
            if term_embedding:
                best_dense_match = None
                best_dense_score = 0.0

                for cand in candidate_entries:
                    cand_name = cand.get("name") or cand.get("en") or cand.get("text", "")
                    cand_emb = self.embedding_client.get_embedding(cand_name)
                    if cand_emb:
                        score = _dense_cosine_similarity(term_embedding, cand_emb)
                        if score > best_dense_score:
                            best_dense_score = score
                            best_dense_match = cand

                thresh = threshold if threshold is not None else self.dense_threshold
                if best_dense_match and best_dense_score >= thresh:
                    logger.info(
                        f"Dense Vector matched '{term}' -> '{best_dense_match.get('cui')}' "
                        f"({best_dense_match.get('name') or best_dense_match.get('en')}) "
                        f"[score={best_dense_score:.3f} >= {thresh}]"
                    )
                    res = dict(best_dense_match)
                    res["similarity_score"] = best_dense_score
                    res["match_strategy"] = "dense_embedding"
                    return res

        # 2. Fallback to Character N-Gram Cosine Similarity
        thresh = threshold if threshold is not None else self.ngram_threshold
        best_ngram_match = None
        best_ngram_score = 0.0

        for cand in candidate_entries:
            cand_name = cand.get("name") or cand.get("en") or cand.get("text", "")
            score = _ngram_cosine_similarity(term, cand_name)
            if score > best_ngram_score:
                best_ngram_score = score
                best_ngram_match = cand

        if best_ngram_match and best_ngram_score >= thresh:
            logger.info(
                f"N-Gram fallback matched '{term}' -> '{best_ngram_match.get('cui')}' "
                f"[score={best_ngram_score:.3f} >= {thresh}]"
            )
            res = dict(best_ngram_match)
            res["similarity_score"] = best_ngram_score
            res["match_strategy"] = "ngram_cosine"
            return res

        return None
