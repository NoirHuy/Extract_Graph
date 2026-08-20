"""UMLS Normalization package for EDC Medical Knowledge Graph Pipeline."""
from .dictionary_lookup import DictionaryLookup
from .umls_client import UMLSClient
from .vector_fallback import VectorFallbackMatcher
from .umls_normalize import normalize_entities, translate_term_to_english_with_llm

__all__ = [
    "DictionaryLookup",
    "UMLSClient",
    "VectorFallbackMatcher",
    "normalize_entities",
    "translate_term_to_english_with_llm",
]
