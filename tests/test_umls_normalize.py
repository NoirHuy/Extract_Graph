import pytest
from normalization.dictionary_lookup import DictionaryLookup
from normalization.vector_fallback import VectorFallbackMatcher
from normalization.umls_normalize import normalize_entities

def test_dictionary_tier1_lookup():
    dict_lookup = DictionaryLookup()
    res = dict_lookup.lookup("tăng huyết áp")
    assert res is not None
    assert res["cui"] == "C0020538"
    assert res["tui"] == "T047"

def test_dictionary_case_and_alias_lookup():
    dict_lookup = DictionaryLookup()
    res = dict_lookup.lookup("ACE INHIBITOR")
    assert res is not None
    assert res["cui"] == "C0003015"

def test_vector_fallback_ngram_matcher():
    matcher = VectorFallbackMatcher()
    candidates = [
        {"name": "Essential hypertension", "cui": "C0085580", "sty": "Disease or Syndrome"},
        {"name": "Secondary hypertension", "cui": "C0155616", "sty": "Disease or Syndrome"},
        {"name": "Asthma", "cui": "C0004096", "sty": "Disease or Syndrome"},
    ]
    match = matcher.find_best_match("Essential hypertension stage 1", candidates, threshold=0.60)
    assert match is not None
    assert match["cui"] == "C0085580"

def test_dense_embedding_matcher_with_mock():
    from normalization.vector_fallback import _dense_cosine_similarity, VectorFallbackMatcher
    
    # 1. Cosine similarity math check
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    assert _dense_cosine_similarity(v1, v2) == 1.0
    assert _dense_cosine_similarity(v1, v3) == 0.0

    # 2. Test matcher with pre-populated cache
    matcher = VectorFallbackMatcher()
    matcher.embedding_client.cache["khó thở khi nằm"] = [0.8, 0.6, 0.0]
    matcher.embedding_client.cache["Orthopnea"] = [0.79, 0.61, 0.0]
    matcher.embedding_client.cache["Hypertension"] = [0.0, 0.1, 0.9]

    candidates = [
        {"name": "Orthopnea", "cui": "C0029353", "sty": "Sign or Symptom"},
        {"name": "Hypertension", "cui": "C0020538", "sty": "Disease or Syndrome"},
    ]

    match = matcher.find_best_match("khó thở khi nằm", candidates, threshold=0.75)
    assert match is not None
    assert match["cui"] == "C0029353"
    assert match["match_strategy"] == "dense_embedding"


def test_normalize_entities_flow(tmp_path):
    entities = [
        {
            "id": "e1",
            "text": "Tăng huyết áp",
            "normalized_name": "Tăng huyết áp",
            "entity_type": "Disease",
            "evidence_span": "Tăng huyết áp là...",
            "attributes": {}
        },
        {
            "id": "e2",
            "text": "Thuật ngữ chưa từng thấy 999",
            "normalized_name": "Thuật ngữ chưa từng thấy 999",
            "entity_type": "Disease",
            "evidence_span": "Văn bản thử nghiệm",
            "attributes": {}
        }
    ]
    normalized, unmapped = normalize_entities(entities, doc_id="test_doc", output_dir=str(tmp_path))
    assert normalized[0]["umls_cui"] == "C0020538"
    assert normalized[0]["umls_sty"] == "Disease or Syndrome"
    assert normalized[1]["umls_cui"] is None
    assert len(unmapped) == 1
    assert unmapped[0]["normalized_name"] == "Thuật ngữ chưa từng thấy 999"
