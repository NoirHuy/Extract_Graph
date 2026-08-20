# EDC Medical Knowledge Graph Extraction Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade 5-module pipeline extracting clinical medical knowledge graphs from Vietnamese medical text into Neo4j with UMLS CUI normalization, multi-pass consensus, and strict schema validation.

**Architecture:** Contract-Driven Layered Pipeline with Schema Registry single source of truth, dual-mode OpenAI-compatible LLM client with self-healing fallback, 3-tier hybrid UMLS normalization, multi-pass agreement check, and idempotent Neo4j loader using deterministic `resolved_key` constraints.

**Tech Stack:** Python 3.10+, OpenAI Python SDK, Pydantic, jsonschema, neo4j driver, requests, python-dotenv, pytest.

## Global Constraints

- Primary Language of Input: Vietnamese clinical texts (MSD Manual format).
- Schema: 16 Entity Types, 19 Relation Types strictly mapped to UMLS Semantic Types (TUI) and Domain/Range rules.
- Environment variables: `LLM_API_BASE` (default `http://103.56.160.46:20128/v1`), `LLM_API_KEY`, `LLM_MODEL_NAME`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `UMLS_API_KEY`, `SIMILARITY_THRESHOLD`.
- Idempotency & Unique Keys: Node identity strictly based on `resolved_key` (`"CUI:" + umls_cui` or `entity_type + ":" + normalized_name.strip().lower()`).
- Provenance: Preserve verbatim `evidence_span`, `confidence`, `agreement_count`, `total_passes`, `source_document`, `schema_version` on nodes and relationships.

---

### Task 1: Environment Configuration, Dependencies & Seed Data Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config.py`
- Create: `data/dict/medical_vi_en_cui.json`
- Create: `data/raw/hypertension_sample.txt`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `config.Settings` (Pydantic / dataclass settings loader reading environment variables with sensible defaults).

- [ ] **Step 1: Write the failing test for configuration**

```python
# tests/test_config.py
import os
import pytest
from config import get_settings

def test_default_settings():
    settings = get_settings()
    assert settings.LLM_API_BASE == "http://103.56.160.46:20128/v1"
    assert settings.DEFAULT_PASSES == 2
    assert settings.CONFIDENCE_THRESHOLD == 0.7
    assert settings.SIMILARITY_THRESHOLD == 0.85
    assert settings.SCHEMA_VERSION == "1.0.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'config')

- [ ] **Step 3: Implement dependencies, config, .env.example, seed dictionary, and sample data**

`requirements.txt`:
```text
openai>=1.20.0
pydantic>=2.5.0
jsonschema>=4.20.0
neo4j>=5.15.0
requests>=2.31.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

`config.py`:
```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    LLM_API_BASE: str = os.getenv("LLM_API_BASE", "http://103.56.160.46:20128/v1")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "dummy-key")
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "")
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USERNAME: str = os.getenv("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "password")
    NEO4J_DATABASE: str = os.getenv("NEO4J_DATABASE", "neo4j")
    UMLS_API_KEY: str = os.getenv("UMLS_API_KEY", "")
    DEFAULT_PASSES: int = int(os.getenv("DEFAULT_PASSES", "2"))
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.7"))
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.85"))
    SCHEMA_VERSION: str = "1.0.0"

_settings = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

`.env.example`:
```bash
LLM_API_BASE=http://103.56.160.46:20128/v1
LLM_API_KEY=your_api_key_here
LLM_MODEL_NAME=
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=neo4j
UMLS_API_KEY=
DEFAULT_PASSES=2
CONFIDENCE_THRESHOLD=0.7
SIMILARITY_THRESHOLD=0.85
```

`data/dict/medical_vi_en_cui.json`:
```json
{
  "tăng huyết áp": {"en": "Hypertension", "cui": "C0020538", "tui": "T047", "entity_type": "Disease"},
  "tăng huyết áp nguyên phát": {"en": "Essential hypertension", "cui": "C0085580", "tui": "T047", "entity_type": "DiseaseSubtype"},
  "tăng huyết áp thứ phát": {"en": "Secondary hypertension", "cui": "C0155615", "tui": "T047", "entity_type": "DiseaseSubtype"},
  "tăng huyết áp giai đoạn 1": {"en": "Stage 1 hypertension", "cui": "C4073145", "tui": "T047", "entity_type": "DiseaseSubtype"},
  "cường aldosteron nguyên phát": {"en": "Primary Hyperaldosteronism", "cui": "C0020438", "tui": "T047", "entity_type": "Cause"},
  "đột quỵ": {"en": "Stroke", "cui": "C0038454", "tui": "T047", "entity_type": "Complication"},
  "nhồi máu cơ tim": {"en": "Myocardial Infarction", "cui": "C0027051", "tui": "T047", "entity_type": "Complication"},
  "suy tim": {"en": "Heart Failure", "cui": "C0018801", "tui": "T047", "entity_type": "Complication"},
  "thuốc ức chế men chuyển": {"en": "Angiotensin-Converting Enzyme Inhibitors", "cui": "C0003015", "tui": "T121", "entity_type": "DrugClass"},
  "ace inhibitor": {"en": "Angiotensin-Converting Enzyme Inhibitors", "cui": "C0003015", "tui": "T121", "entity_type": "DrugClass"},
  "thuốc chẹn thụ thể angiotensin": {"en": "Angiotensin Receptor Antagonists", "cui": "C0139702", "tui": "T121", "entity_type": "DrugClass"},
  "arb": {"en": "Angiotensin Receptor Antagonists", "cui": "C0139702", "tui": "T121", "entity_type": "DrugClass"},
  "thuốc chẹn kênh canxi": {"en": "Calcium Channel Blockers", "cui": "C0006684", "tui": "T121", "entity_type": "DrugClass"},
  "thuốc lợi tiểu thiazide": {"en": "Thiazide Diuretics", "cui": "C0039864", "tui": "T121", "entity_type": "DrugClass"},
  "đau đầu": {"en": "Headache", "cui": "C0018681", "tui": "T184", "entity_type": "Symptom"},
  "chóng mặt": {"en": "Dizziness", "cui": "C0012833", "tui": "T184", "entity_type": "Symptom"},
  "tim": {"en": "Heart", "cui": "C0018787", "tui": "T023", "entity_type": "Organ"},
  "thận": {"en": "Kidney", "cui": "C0022646", "tui": "T023", "entity_type": "Organ"},
  "não": {"en": "Brain", "cui": "C0006104", "tui": "T023", "entity_type": "Organ"}
}
```

`data/raw/hypertension_sample.txt`:
```text
TĂNG HUYẾT ÁP (HYPERTENSION)

1. Định nghĩa và Phân loại
Tăng huyết áp là tình trạng huyết áp động mạch tăng cao mạn tính. Theo hướng dẫn của ACC/AHA, Tăng huyết áp giai đoạn 1 được xác định khi huyết áp tâm thu từ 130 đến 139 mmHg hoặc huyết áp tâm trương từ 80 đến 89 mmHg (ngưỡng 130/80 mmHg). Tăng huyết áp gồm hai thể chính: Tăng huyết áp nguyên phát (vô căn) chiếm khoảng 90-95% các trường hợp và Tăng huyết áp thứ phát.

2. Nguyên nhân và Sinh lý bệnh
Nguyên nhân gây Tăng huyết áp thứ phát bao gồm bệnh nhu mô thận, hẹp động mạch thận, và Cường aldosteron nguyên phát. Cường aldosteron nguyên phát làm tăng tái hấp thu natri và giữ nước tại ống thận, là một nguyên nhân quan trọng dẫn đến Tăng huyết áp.

3. Biến chứng
Nếu không được kiểm soát tốt, Tăng huyết áp lâu ngày gây tổn thương các cơ quan đích như Tim, Não, Thận và Mắt. Tăng huyết áp là yếu tố nguy cơ chính dẫn đến Đột quỵ, Nhồi máu cơ tim và Suy tim mạn tính.

4. Điều trị
Mục tiêu điều trị là hạ huyết áp về mức an toàn. Các nhóm thuốc hạ áp hàng đầu bao gồm: Thuốc ức chế men chuyển (ACE inhibitor), Thuốc chẹn thụ thể angiotensin (ARB), Thuốc chẹn kênh canxi và Thuốc lợi tiểu thiazide. Thuốc ức chế men chuyển (ACE inhibitor) được chỉ định phổ biến để điều trị Tăng huyết áp và giúp bảo vệ chức năng thận ở bệnh nhân đái tháo đường.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 1**

```bash
git add requirements.txt .env.example config.py data/ tests/test_config.py
git commit -m "feat(core): setup dependencies, config loader, seed data and test suite"
```

---

### Task 2: Schema Registry & EDC JSON Schema Contract

**Files:**
- Create: `schema/edc_schema.json`
- Create: `schema/schema_registry.py`
- Create: `schema/__init__.py`
- Test: `tests/test_schema_registry.py`

**Interfaces:**
- Produces:
  - `schema_registry.ENTITY_TYPES`: Dict mapping entity type to `(STY, TUI, SemanticGroup)`.
  - `schema_registry.RELATION_TYPES`: List of relation constraint objects `{"name": str, "domain": list[str], "range": list[str]}`.
  - `schema_registry.get_edc_json_schema() -> dict`: Returns the full JSON schema.
  - `schema_registry.validate_extraction_payload(payload: dict) -> bool`: Validates raw extraction JSON against EDC schema.
  - `schema_registry.is_valid_relation(source_type: str, relation_type: str, target_type: str) -> bool`: Checks domain/range validity.

- [ ] **Step 1: Write the failing test for Schema Registry**

```python
# tests/test_schema_registry.py
import pytest
from schema.schema_registry import (
    ENTITY_TYPES,
    RELATION_TYPES,
    get_edc_json_schema,
    validate_extraction_payload,
    is_valid_relation,
)

def test_entity_types_count_and_mapping():
    assert len(ENTITY_TYPES) == 16
    assert ENTITY_TYPES["Disease"]["tui"] == "T047"
    assert ENTITY_TYPES["DrugClass"]["tui"] == "T121"
    assert ENTITY_TYPES["Measurement"]["group"] == "CONC"

def test_relation_domain_range_validation():
    assert is_valid_relation("Cause", "CAUSES", "Disease") is True
    assert is_valid_relation("DrugClass", "TREATS", "Disease") is True
    assert is_valid_relation("Measurement", "DEFINES_THRESHOLD_FOR", "DiseaseSubtype") is True
    assert is_valid_relation("Disease", "LEADS_TO", "Complication") is True
    # Invalid combinations
    assert is_valid_relation("Drug", "HAS_SYMPTOM", "Organ") is False
    assert is_valid_relation("Disease", "CAUSES", "Test") is False

def test_validate_extraction_payload():
    valid_payload = {
        "entities": [
            {
                "id": "e1",
                "text": "Tăng huyết áp",
                "normalized_name": "Tăng huyết áp",
                "entity_type": "Disease",
                "evidence_span": "Tăng huyết áp là tình trạng...",
                "umls_cui": None
            }
        ],
        "relations": [
            {
                "source_id": "e1",
                "target_id": "e2",
                "relation_type": "LEADS_TO",
                "evidence_span": "Tăng huyết áp dẫn đến đột quỵ",
                "confidence": 0.95
            }
        ]
    }
    assert validate_extraction_payload(valid_payload) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schema_registry.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement `schema/edc_schema.json` and `schema/schema_registry.py`**

`schema/edc_schema.json`: Complete JSON Schema as defined in the spec.
`schema/schema_registry.py`: Logic implementing entity mappings, relations, domain/range checks, and jsonschema validator.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_schema_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 2**

```bash
git add schema/ tests/test_schema_registry.py
git commit -m "feat(schema): implement Schema Registry and EDC JSON schema validator"
```

---

### Task 3: Vietnamese Text Chunker with Heading Detection & Overlap

**Files:**
- Create: `extraction/text_chunker.py`
- Create: `extraction/__init__.py`
- Test: `tests/test_text_chunker.py`

**Interfaces:**
- Produces:
  - `TextChunk(chunk_id: int, text: str, start_char: int, end_char: int, section_title: str)`
  - `chunk_vietnamese_text(text: str, max_chunk_chars: int = 1500, overlap_sentences: int = 2) -> list[TextChunk]`

- [ ] **Step 1: Write the failing test for text chunking**

```python
# tests/test_text_chunker.py
import pytest
from extraction.text_chunker import chunk_vietnamese_text, TextChunk

def test_chunking_with_headings_and_overlap():
    sample_text = """
1. Định nghĩa và Phân loại
Tăng huyết áp là bệnh lý mạn tính nguy hiểm. Bệnh được chia thành độ 1 và độ 2. Ngưỡng chẩn đoán là 130/80 mmHg.

2. Nguyên nhân
Nguyên nhân bao gồm cường aldosteron và hẹp động mạch thận. Cường aldosteron làm giữ muối nước gây tăng áp lực.

3. Điều trị
Sử dụng thuốc ức chế men chuyển. Thuốc giúp hạ áp hiệu quả.
"""
    chunks = chunk_vietnamese_text(sample_text.strip(), max_chunk_chars=200, overlap_sentences=1)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert isinstance(chunk, TextChunk)
        assert len(chunk.text) > 0
        assert chunk.section_title != ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_text_chunker.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `extraction/text_chunker.py`**

Implement sentence splitting honoring Vietnamese punctuation (`.`, `!`, `?`, `\n\n`), heading heuristics (markdown `#`, numbered headings `1.`, `2.`, short uppercase/bold titles), and sentence overlap preserving cross-boundary relations.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_text_chunker.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 3**

```bash
git add extraction/text_chunker.py tests/test_text_chunker.py
git commit -m "feat(extraction): implement sentence-preserving Vietnamese text chunker with heading detection"
```

---

### Task 4: LLM Client with Dual-Mode Structured Output & Probing Script

**Files:**
- Create: `extraction/llm_client.py`
- Create: `extraction/prompts.py`
- Create: `tests/check_llm_capabilities.py`
- Test: `tests/test_llm_client.py`

**Interfaces:**
- Produces:
  - `LLMClient(base_url, api_key, model_name)`
  - `LLMClient.list_models() -> list[str]`
  - `LLMClient.extract_structured(system_prompt: str, user_text: str, schema: dict, temperature: float = 0.0) -> dict`
  - `prompts.get_extraction_system_prompt() -> str`
  - `prompts.get_few_shot_examples() -> list[dict]`

- [ ] **Step 1: Write the failing test for LLM Client (using mock / responses)**

```python
# tests/test_llm_client.py
import pytest
from unittest.mock import MagicMock, patch
from extraction.llm_client import LLMClient

def test_extract_structured_with_json_fallback():
    client = LLMClient(base_url="http://mock-endpoint/v1", api_key="test-key", model_name="mock-model")
    
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='```json\n{"entities": [], "relations": []}\n```'))
    ]
    
    with patch.object(client.client.chat.completions, 'create', return_value=mock_response):
        result = client.extract_structured(
            system_prompt="Test prompt",
            user_text="Sample text",
            schema={"type": "object", "properties": {"entities": {"type": "array"}, "relations": {"type": "array"}}, "required": ["entities", "relations"]}
        )
        assert "entities" in result
        assert "relations" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_client.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `extraction/prompts.py`, `extraction/llm_client.py`, and `tests/check_llm_capabilities.py`**

Implement `LLMClient` with:
- Dual-mode: tests `response_format={"type": "json_schema", ...}`, falls back on schema-embedded system prompt + regex JSON stripper + `jsonschema` verification + auto-healing retry (2 attempts).
- Timeout (120s) and exponential backoff retry.
- `tests/check_llm_capabilities.py` executable standalone CLI script to probe model list, test structured output support, and print results.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 4**

```bash
git add extraction/llm_client.py extraction/prompts.py tests/check_llm_capabilities.py tests/test_llm_client.py
git commit -m "feat(extraction): implement resilient dual-mode LLM client and capability prober"
```

---

### Task 5: Multi-Pass Extraction Runner

**Files:**
- Create: `extraction/extract.py`
- Test: `tests/test_extract.py`

**Interfaces:**
- Produces:
  - `ExtractionResult(chunk_id: int, pass_index: int, entities: list[dict], relations: list[dict])`
  - `run_extraction_pipeline(text: str, passes: int = 2, source_doc: str = "sample.txt") -> list[ExtractionResult]`

- [ ] **Step 1: Write the failing test for multi-pass extraction runner**

```python
# tests/test_extract.py
import pytest
from unittest.mock import MagicMock, patch
from extraction.extract import run_extraction_pipeline

def test_run_extraction_multi_pass():
    mock_payload = {
        "entities": [
            {"id": "e1", "text": "Tăng huyết áp", "normalized_name": "Tăng huyết áp", "entity_type": "Disease", "evidence_span": "Tăng huyết áp là..."}
        ],
        "relations": []
    }
    with patch("extraction.extract.LLMClient.extract_structured", return_value=mock_payload):
        results = run_extraction_pipeline(text="Tăng huyết áp là bệnh mạn tính.", passes=2, source_doc="test.txt")
        assert len(results) == 2
        assert results[0].pass_index == 1
        assert results[1].pass_index == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_extract.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `extraction/extract.py`**

Implement multi-pass extraction with chunking, progress reporting, and output saving to `data/processed/{doc_id}_extracted_raw.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_extract.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 5**

```bash
git add extraction/extract.py tests/test_extract.py
git commit -m "feat(extraction): implement multi-pass extraction pipeline runner"
```

---

### Task 6: Validation, Agreement & Consensus Layer

**Files:**
- Create: `validation/validate_relations.py`
- Create: `validation/consensus.py`
- Create: `validation/__init__.py`
- Test: `tests/test_validation_consensus.py`

**Interfaces:**
- Produces:
  - `merge_entities(entity_lists: list[list[dict]]) -> list[dict]`: Deduplicates by `(normalized_name.strip().lower(), entity_type)`, preserves longest evidence span, unions attributes.
  - `aggregate_relation_consensus(relation_lists: list[list[dict]], total_passes: int) -> tuple[list[dict], list[dict]]`: Computes statistical confidence, records `agreement_count`, detects conflicts and returns `(valid_consensus_relations, conflict_relations)`.
  - `validate_and_filter_relations(relations: list[dict], entities: list[dict], min_confidence: float = 0.7) -> list[dict]`: Checks Domain/Range constraints against Schema Registry and confidence threshold.

- [ ] **Step 1: Write the failing test for validation and consensus**

```python
# tests/test_validation_consensus.py
import pytest
from validation.consensus import merge_entities, aggregate_relation_consensus
from validation.validate_relations import validate_and_filter_relations

def test_entity_merging_longest_span():
    pass1_entities = [
        {"id": "e1", "text": "Tăng HA", "normalized_name": "Tăng huyết áp", "entity_type": "Disease", "evidence_span": "Tăng HA ngắn", "attributes": {"key1": "val1"}}
    ]
    pass2_entities = [
        {"id": "e2", "text": "Tăng huyết áp", "normalized_name": "Tăng huyết áp", "entity_type": "Disease", "evidence_span": "Tăng huyết áp là câu dài hơn nhiều", "attributes": {"key2": "val2"}}
    ]
    merged = merge_entities([pass1_entities, pass2_entities])
    assert len(merged) == 1
    assert merged[0]["evidence_span"] == "Tăng huyết áp là câu dài hơn nhiều"
    assert "key1" in merged[0]["attributes"] and "key2" in merged[0]["attributes"]

def test_relation_agreement_and_statistical_confidence():
    rel1 = [{"source_id": "e1", "target_id": "e2", "relation_type": "CAUSES", "evidence_span": "span1", "confidence": 0.8}]
    rel2 = [{"source_id": "e1", "target_id": "e2", "relation_type": "CAUSES", "evidence_span": "span2", "confidence": 0.8}]
    consensus, conflicts = aggregate_relation_consensus([rel1, rel2], total_passes=2)
    assert len(consensus) == 1
    assert len(conflicts) == 0
    assert consensus[0]["agreement_count"] == 2
    # 1 - (1-0.8)*(1-0.8) = 1 - 0.04 = 0.96
    assert pytest.approx(consensus[0]["confidence"], 0.01) == 0.96

def test_relation_conflict_detection():
    rel1 = [{"source_id": "e1", "target_id": "e2", "relation_type": "CAUSES", "evidence_span": "span1", "confidence": 0.8}]
    rel2 = [{"source_id": "e1", "target_id": "e2", "relation_type": "INCREASES_RISK_OF", "evidence_span": "span2", "confidence": 0.8}]
    consensus, conflicts = aggregate_relation_consensus([rel1, rel2], total_passes=2)
    assert len(conflicts) == 1
    assert conflicts[0]["status"] == "conflict"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validation_consensus.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `validation/consensus.py` and `validation/validate_relations.py`**

Implement:
- Entity deduplication with longest evidence span and attribute union.
- Statistical relation agreement aggregation with `agreement_count`, `total_passes`, and `agreement_ratio`.
- Conflict detection (same source-target, discordant relation type) routed to dedicated conflict list.
- Domain/range enforcement and confidence threshold filtering ($\ge 0.7$).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validation_consensus.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 6**

```bash
git add validation/ tests/test_validation_consensus.py
git commit -m "feat(validation): implement entity merging, statistical consensus, conflict queue, and domain/range filter"
```

---

### Task 7: UMLS Normalization Module with 3-Tier Hybrid Lookup

**Files:**
- Create: `normalization/dictionary_lookup.py`
- Create: `normalization/umls_client.py`
- Create: `normalization/vector_fallback.py`
- Create: `normalization/umls_normalize.py`
- Create: `normalization/__init__.py`
- Test: `tests/test_umls_normalize.py`

**Interfaces:**
- Produces:
  - `DictionaryLookup.lookup(term: str) -> Optional[dict]`
  - `UMLSClient.search_cui(term_en: str, expected_sty: Optional[str] = None) -> Optional[dict]`
  - `VectorFallbackMatcher.find_best_match(term: str, candidates: list[dict], threshold: float = 0.85) -> Optional[dict]`
  - `normalize_entities(entities: list[dict], doc_id: str = "doc") -> tuple[list[dict], list[dict]]`: Returns `(normalized_entities, unmapped_entities)` and writes unmapped entities to `data/processed/{doc_id}_unmapped_entities.json`.

- [ ] **Step 1: Write the failing test for UMLS Normalization**

```python
# tests/test_umls_normalize.py
import pytest
from normalization.dictionary_lookup import DictionaryLookup
from normalization.umls_normalize import normalize_entities

def test_dictionary_tier1_lookup():
    dict_lookup = DictionaryLookup()
    res = dict_lookup.lookup("tăng huyết áp")
    assert res is not None
    assert res["cui"] == "C0020538"
    assert res["tui"] == "T047"

def test_normalize_entities_flow():
    entities = [
        {"id": "e1", "text": "Tăng huyết áp", "normalized_name": "Tăng huyết áp", "entity_type": "Disease", "evidence_span": "..."},
        {"id": "e2", "text": "Thuật ngữ lạ 123", "normalized_name": "Thuật ngữ lạ 123", "entity_type": "Disease", "evidence_span": "..."}
    ]
    normalized, unmapped = normalize_entities(entities, doc_id="test_doc")
    assert normalized[0]["umls_cui"] == "C0020538"
    assert normalized[0]["umls_sty"] == "Disease or Syndrome"
    assert normalized[1]["umls_cui"] is None
    assert len(unmapped) == 1
    assert unmapped[0]["normalized_name"] == "Thuật ngữ lạ 123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_umls_normalize.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `normalization/` components**

Implement Tier 1 (Dict Lookup), Tier 2 (LLM Context Translation + UMLS REST Client with Semantic Type Sanity Verification), Tier 3 (Cosine Similarity Fallback with configurable threshold), and unmapped audit logger.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_umls_normalize.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 7**

```bash
git add normalization/ tests/test_umls_normalize.py
git commit -m "feat(normalization): implement 3-tier hybrid UMLS normalization with STY sanity validation"
```

---

### Task 8: Neo4j Ingestion Module with `resolved_key` Constraints

**Files:**
- Create: `ingestion/neo4j_loader.py`
- Create: `ingestion/__init__.py`
- Test: `tests/test_neo4j_loader.py`

**Interfaces:**
- Produces:
  - `Neo4jLoader(uri, username, password, database)`
  - `Neo4jLoader.compute_resolved_key(entity: dict) -> str`: Returns `"CUI:" + cui` or `entity_type + ":" + normalized_name.strip().lower()`.
  - `Neo4jLoader.setup_constraints()`
  - `Neo4jLoader.ingest_graph(entities: list[dict], relations: list[dict], source_doc: str, schema_version: str = "1.0.0") -> dict`: Returns summary `{"nodes_created": int, "relationships_created": int}`.

- [ ] **Step 1: Write the failing test for Neo4j loader logic**

```python
# tests/test_neo4j_loader.py
import pytest
from ingestion.neo4j_loader import Neo4jLoader

def test_resolved_key_generation():
    loader = Neo4jLoader(uri="bolt://localhost:7687", username="neo4j", password="password")
    
    entity_with_cui = {"entity_type": "Disease", "normalized_name": "Tăng huyết áp", "umls_cui": "C0020538"}
    assert loader.compute_resolved_key(entity_with_cui) == "CUI:C0020538"
    
    entity_without_cui = {"entity_type": "Disease", "normalized_name": "Tăng huyết áp", "umls_cui": None}
    assert loader.compute_resolved_key(entity_without_cui) == "Disease:tăng huyết áp"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_neo4j_loader.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `ingestion/neo4j_loader.py`**

Implement:
- Deterministic `resolved_key` calculation.
- Constraint initialization: `CREATE CONSTRAINT IF NOT EXISTS FOR (n:Entity) REQUIRE n.resolved_key IS UNIQUE` and for individual entity labels.
- Node MERGE query setting `resolved_key`, `name`, `normalized_name`, `entity_type`, `umls_cui`, `umls_sty`, `source_document`, `schema_version`, `created_at`, `updated_at`.
- Relationship MERGE query setting `evidence_span`, `confidence`, `agreement_count`, `total_passes`, `source_document`, `schema_version`, `created_at`, `updated_at`.
- Dry-run mode for testing without a live Neo4j database instance.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_neo4j_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 8**

```bash
git add ingestion/ tests/test_neo4j_loader.py
git commit -m "feat(ingestion): implement idempotent Neo4j ingestion with resolved_key unique constraints"
```

---

### Task 9: Unified CLI Coordinator, Regression Suite & Documentation

**Files:**
- Create: `main.py`
- Create: `tests/test_hypertension_extraction.py`
- Create: `README.md`

**Interfaces:**
- Produces:
  - CLI commands: `probe-llm`, `extract`, `consensus`, `normalize`, `validate`, `ingest`, `run-all`.
  - Regression test suite asserting the 4 mandatory benchmark relations, structured Measurement attributes, conflict handling, and domain/range validity.

- [ ] **Step 1: Write the failing end-to-end regression test**

```python
# tests/test_hypertension_extraction.py
import pytest
from schema.schema_registry import is_valid_relation
from validation.consensus import merge_entities, aggregate_relation_consensus
from validation.validate_relations import validate_and_filter_relations
from normalization.umls_normalize import normalize_entities

def test_hypertension_benchmark_triplets():
    raw_entities = [
        {"id": "e1", "text": "Cường aldosteron nguyên phát", "normalized_name": "Cường aldosteron nguyên phát", "entity_type": "Cause", "evidence_span": "Cường aldosteron nguyên phát là nguyên nhân..."},
        {"id": "e2", "text": "Tăng huyết áp", "normalized_name": "Tăng huyết áp", "entity_type": "Disease", "evidence_span": "Tăng huyết áp là tình trạng..."},
        {"id": "e3", "text": "ACE inhibitor", "normalized_name": "ACE inhibitor", "entity_type": "DrugClass", "evidence_span": "Thuốc ức chế men chuyển (ACE inhibitor) điều trị..."},
        {"id": "e4", "text": "130/80 mmHg", "normalized_name": "130/80 mmHg", "entity_type": "Measurement", "evidence_span": "ngưỡng 130/80 mmHg", "attributes": {"systolic": 130, "diastolic": 80, "unit": "mmHg"}},
        {"id": "e5", "text": "Tăng huyết áp giai đoạn 1", "normalized_name": "Tăng huyết áp giai đoạn 1", "entity_type": "DiseaseSubtype", "evidence_span": "Tăng huyết áp giai đoạn 1 được xác định..."},
        {"id": "e6", "text": "Đột quỵ", "normalized_name": "Đột quỵ", "entity_type": "Complication", "evidence_span": "Tăng huyết áp dẫn đến Đột quỵ"}
    ]
    
    raw_relations = [
        {"source_id": "e1", "target_id": "e2", "relation_type": "CAUSES", "evidence_span": "Cường aldosteron là nguyên nhân dẫn đến Tăng huyết áp", "confidence": 0.9},
        {"source_id": "e3", "target_id": "e2", "relation_type": "TREATS", "evidence_span": "ACE inhibitor điều trị Tăng huyết áp", "confidence": 0.95},
        {"source_id": "e4", "target_id": "e5", "relation_type": "DEFINES_THRESHOLD_FOR", "evidence_span": "130/80 mmHg xác định Tăng huyết áp giai đoạn 1", "confidence": 0.88},
        {"source_id": "e2", "target_id": "e6", "relation_type": "LEADS_TO", "evidence_span": "Tăng huyết áp dẫn đến Đột quỵ", "confidence": 0.92}
    ]
    
    normalized_entities, unmapped = normalize_entities(raw_entities, doc_id="benchmark")
    validated_relations = validate_and_filter_relations(raw_relations, normalized_entities, min_confidence=0.7)
    
    assert len(validated_relations) == 4
    rel_types = [r["relation_type"] for r in validated_relations]
    assert "CAUSES" in rel_types
    assert "TREATS" in rel_types
    assert "DEFINES_THRESHOLD_FOR" in rel_types
    assert "LEADS_TO" in rel_types
```

- [ ] **Step 2: Run test to verify it fails (or passes once modules are linked)**

Run: `pytest tests/test_hypertension_extraction.py -v`

- [ ] **Step 3: Implement `main.py` and `README.md`**

Implement argparse CLI in `main.py` supporting:
- `probe-llm`
- `extract --input <file> --passes <N>`
- `consensus --input-raw <file>`
- `normalize --input-entities <file>`
- `validate --input-relations <file> --input-entities <file>`
- `ingest --input-data <file> [--dry-run]`
- `run-all --input <file> --passes 2`

Write concise Vietnamese/English `README.md` with installation, environment configuration, quick start, and testing instructions.

- [ ] **Step 4: Run full test suite to verify 100% pass**

Run: `pytest -v`
Expected: ALL PASS

- [ ] **Step 5: Commit Task 9**

```bash
git add main.py tests/test_hypertension_extraction.py README.md
git commit -m "feat(cli): implement unified CLI coordinator, regression test suite and README"
```
