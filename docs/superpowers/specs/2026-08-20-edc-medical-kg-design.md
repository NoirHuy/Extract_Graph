# Design Document: EDC Medical Knowledge Graph Extraction Pipeline

- **Date:** 2026-08-20
- **Status:** Approved
- **Topic:** Clinical Knowledge Graph Extraction with Extraction Data Contract (EDC), UMLS Normalization, Validation, and Neo4j Ingestion

---

## 1. Executive Summary & Objectives

The goal of this system is to extract a high-fidelity Clinical Medical Knowledge Graph (KG) from Vietnamese medical literature (MSD Manual style) using an Extraction Data Contract (EDC). The pilot disease is **Hypertension (Tăng huyết áp)**, and the system is architected to seamlessly generalize to other disease domains. The resulting Knowledge Graph will serve downstream applications including **GraphRAG**, **Multi-Agent Debate**, and **Clinical Decision Support Systems (CDSS)**.

The system is structured into five decoupled, testable, and contract-driven modules:
1. **Schema Registry**: Single source of truth for 16 Entity Types, 19 Relation Types, Domain/Range constraints, and UMLS STY/TUI mappings.
2. **LLM Extraction Module**: Dynamic OpenAI-compatible extraction client supporting both native JSON Schema and self-healing fallback JSON prompting, sentence-preserving chunking with overlap, and multi-pass extraction.
3. **UMLS Normalization Module**: 3-tier hybrid mapping strategy (Bilingual Medical Dictionary $\rightarrow$ UMLS REST API $\rightarrow$ Contextual LLM translation $\rightarrow$ Vector/Embedding similarity fallback $\ge 0.85$).
4. **Validation & Consensus Layer**: Multi-pass merging, relation consensus & conflict detection, strict Domain/Range enforcement, and confidence threshold filtering.
5. **Neo4j Ingestion Module**: Idempotent graph population via unique constraints, Cypher `MERGE`, and full provenance persistence (`evidence_span`, `confidence`, `source_document`, `created_at`).

---

## 2. System Architecture

```text
                               +-----------------------------+
                               |  Vietnamese Medical Text    |
                               |      (data/raw/*.txt)       |
                               +--------------+--------------+
                                              |
                                              v
                               +-----------------------------+
                               |    Text Chunker (Overlap)   |
                               +--------------+--------------+
                                              |
                                              v
                     +-----------------------------------------------+
                     |         LLM Extraction (Multi-Pass)           |
                     |  (OpenAI-Compatible API + JSON Schema / Fallback) |
                     +------------------------+----------------------+
                                              |
                                              v
                     +-----------------------------------------------+
                     |          Validation & Consensus Layer         |
                     |  - Entity Deduplication & Attribute Merging   |
                     |  - Relation Voting & Conflict Flagging        |
                     |  - Domain / Range Constraints Check           |
                     |  - Confidence Filtering (>= 0.7)              |
                     +------------------------+----------------------+
                                              |
                                              v
                     +-----------------------------------------------+
                     |            UMLS Normalization Layer           |
                     |  - Tier 1: Vi-En Medical Dict + UMLS REST API |
                     |  - Tier 2: LLM Context Translation to English |
                     |  - Tier 3: Vector / Cosine Similarity (>=0.85)|
                     |  - Audit Log for Unmapped Entities            |
                     +------------------------+----------------------+
                                              |
                                              v
                     +-----------------------------------------------+
                     |             Neo4j Ingestion Layer             |
                     |  - Unique Constraints Schema Creation         |
                     |  - Idempotent MERGE for Nodes & Edges         |
                     |  - Provenance Tracking & Auditing             |
                     +-----------------------------------------------+
```

---

## 3. Schema & Data Contract Specifications

### 3.1 Entity Types & UMLS Semantic Mapping
The system recognizes 16 entity types strictly mapped to UMLS Semantic Types (TUI) and Semantic Groups:

| Entity Type | UMLS STY | TUI | Semantic Group | Description |
|---|---|---|---|---|
| `Disease` | Disease or Syndrome | T047 | DISO | Major clinical disease category |
| `DiseaseSubtype` | Disease or Syndrome | T047 | DISO | Specific stage or subtype (e.g., Tăng huyết áp độ 1) |
| `Symptom` | Sign or Symptom | T184 | DISO | Subjective symptom reported by patient |
| `Sign` | Finding | T033 | DISO | Objective physical sign observed by clinician |
| `RiskFactor` | Finding / Individual Behavior | T033/T055 | DISO/PHEN | Modifiable or non-modifiable risk factor |
| `Cause` | Disease or Syndrome / Pathologic Function | T047/T046 | DISO | Underlying etiology or causal condition |
| `Mechanism` | Pathologic Function / Physiologic Function | T046/T039 | DISO/PHYS | Pathophysiological mechanism or pathway |
| `Complication` | Disease or Syndrome | T047 | DISO | Secondary pathology resulting from primary disease |
| `Test` | Diagnostic Procedure / Laboratory Procedure | T060/T059 | PROC | Diagnostic evaluation, lab test, imaging |
| `Measurement` | Laboratory or Test Result / Quantitative Concept | T034/T081 | CONC | Quantitative threshold or numerical value (e.g., 130/80 mmHg) |
| `Drug` | Pharmacologic Substance | T121 | CHEM | Specific medication active ingredient |
| `DrugClass` | Pharmacologic Substance | T121 | CHEM | Pharmacological class (e.g., ACE inhibitor, ARB) |
| `Treatment` | Therapeutic or Preventive Procedure | T061 | PROC | Non-pharmacologic therapy or intervention |
| `Organ` | Body Part, Organ, or Organ Component | T023 | ANAT | Anatomical target or organ system (e.g., Tim, Thận, Não) |
| `PatientGroup` | Population Group / Age Group | T098/T100 | LIVB | Specific demographic or clinical subpopulation |
| `Guideline` | Intellectual Product | T170 | CONC | Clinical guidelines and staging frameworks (e.g., JNC, ACC/AHA) |

### 3.2 Relation Types & Domain/Range Constraints

```json
[
  {"name": "IS_SUBTYPE_OF", "domain": ["DiseaseSubtype"], "range": ["Disease"]},
  {"name": "CAUSES", "domain": ["Cause"], "range": ["Disease","DiseaseSubtype"]},
  {"name": "INCREASES_RISK_OF", "domain": ["RiskFactor"], "range": ["Disease","Complication"]},
  {"name": "HAS_SYMPTOM", "domain": ["Disease","DiseaseSubtype"], "range": ["Symptom"]},
  {"name": "HAS_SIGN", "domain": ["Disease","DiseaseSubtype"], "range": ["Sign"]},
  {"name": "UNDERLIES", "domain": ["Mechanism"], "range": ["Disease","DiseaseSubtype"]},
  {"name": "PART_OF_MECHANISM", "domain": ["Mechanism"], "range": ["Mechanism"]},
  {"name": "LEADS_TO", "domain": ["Disease","DiseaseSubtype"], "range": ["Complication"]},
  {"name": "AFFECTS_ORGAN", "domain": ["Complication","Disease"], "range": ["Organ"]},
  {"name": "DIAGNOSES", "domain": ["Test"], "range": ["Disease","DiseaseSubtype"]},
  {"name": "DETECTS", "domain": ["Test"], "range": ["Sign","Complication"]},
  {"name": "MEASURES", "domain": ["Test"], "range": ["Measurement"]},
  {"name": "TREATS", "domain": ["Drug","DrugClass","Treatment"], "range": ["Disease","DiseaseSubtype"]},
  {"name": "CONTRAINDICATED_IN", "domain": ["Drug","DrugClass"], "range": ["Disease","PatientGroup"]},
  {"name": "PREFERRED_FOR", "domain": ["Drug","DrugClass"], "range": ["Disease","PatientGroup"]},
  {"name": "HAS_PREVALENCE", "domain": ["PatientGroup"], "range": ["Disease","DiseaseSubtype"]},
  {"name": "DEFINES_THRESHOLD_FOR", "domain": ["Measurement"], "range": ["DiseaseSubtype"]},
  {"name": "CLASSIFIES", "domain": ["Guideline"], "range": ["DiseaseSubtype"]},
  {"name": "MODIFIES", "domain": ["Mechanism","Measurement"], "range": ["Mechanism","Disease"]}
]
```

### 3.3 JSON Schema Contract for LLM
Every LLM call enforces strict JSON validation against `schema/edc_schema.json`:
- `entities`: Array of items containing `id`, `text`, `normalized_name`, `entity_type`, `evidence_span`, `umls_sty` (optional), `umls_cui` (set to `null` during extraction), `attributes` (optional object).
- `relations`: Array of items containing `source_id`, `target_id`, `relation_type`, `evidence_span`, `confidence` (float 0.0 - 1.0), `relation_properties` (optional object).

---

## 4. Module Detailed Design

### 4.1 LLM Client & Text Chunking
- **Client (`extraction/llm_client.py`)**:
  - Initializes `OpenAI(base_url=LLM_API_BASE, api_key=LLM_API_KEY)`.
  - Configurable timeout (120s) with exponential retry backoff.
  - Automatically queries available models from endpoint if `LLM_MODEL_NAME` is not explicitly set.
  - Probes and utilizes `response_format={"type": "json_schema"}` when supported; seamlessly falls back to embedded system prompt schema + strict JSON extraction + `jsonschema` verification with auto-healing retry (up to 2 attempts).
- **Text Chunker (`extraction/text_chunker.py`)**:
  - Segments Vietnamese clinical text along section headers and sentence boundaries without token truncation.
  - Retains 1-2 sentence overlapping windows between consecutive chunks to ensure cross-boundary relation preservation.
- **Prompts (`extraction/prompts.py`)**:
  - Standardized medical prompt including schema definitions, constraint rules, and few-shot examples for hypertension.
  - Enforces verbatim sentence extraction for `evidence_span`.

### 4.2 Multi-Pass & Consensus Validation
- **Multi-Pass Execution (`extraction/extract.py`)**: Runs $N$ independent extraction iterations (default $N=2$) per document chunk.
- **Entity Consensus (`validation/consensus.py`)**:
  - Matches entities on `(normalized_name, entity_type)`.
  - Merges duplicates, choosing the most comprehensive `evidence_span` and merging attribute payloads.
- **Relation Consensus (`validation/consensus.py`)**:
  - Shared relations across passes have their confidence boosted: $conf = \min(1.0, conf_{avg} + 0.15)$.
  - Single-occurrence relations retain initial confidence.
  - Conflicting relations (identical source and target, discordant `relation_type`) are flagged as `status: "conflict"` for clinical review.
- **Domain & Range Validator (`validation/validate_relations.py`)**:
  - Verifies that `source.entity_type` $\in \text{Domain}(R)$ and `target.entity_type` $\in \text{Range}(R)$.
  - Filters out relations with `confidence < 0.7` (configurable).

### 4.3 UMLS Normalization
- **Tier 1 (Curated Bilingual Dictionary & UMLS API)**:
  - Checks `data/dict/medical_vi_en_cui.json` for exact matches.
  - If `UMLS_API_KEY` is present, queries NLM UTS REST API (`/rest/search/current`) filtered by STY and SAB.
- **Tier 2 (LLM Contextual Translation)**:
  - If unmapped, invokes LLM to translate Vietnamese clinical term into standardized English MeSH/SNOMED term.
  - Queries UMLS API or local CUI directory with English term.
- **Tier 3 (Vector / Cosine Similarity Fallback)**:
  - Computes cosine similarity against candidate CUI terminology.
  - Threshold $\ge 0.85$ required for assignment.
- **Unmapped Audit Log**: Unresolved terms logged to `data/processed/{doc_id}_unmapped_entities.json`.

### 4.4 Neo4j Ingestion
- **Constraints Creation (`ingestion/neo4j_loader.py`)**:
  - Executes `CREATE CONSTRAINT IF NOT EXISTS FOR (n:<Label>) REQUIRE n.umls_cui IS UNIQUE` across all entity labels.
- **Node Ingestion**:
  - `MERGE` on `umls_cui` (if available) or `(normalized_name, entity_type)`.
  - Sets `name`, `normalized_name`, `entity_type`, `umls_cui`, `umls_sty`, `source_document`, `created_at`.
- **Edge Ingestion**:
  - Matches source and target nodes by CUI/name.
  - `MERGE (s)-[r:<RELATION_TYPE>]->(t)` setting `evidence_span`, `confidence`, `source_document`, `created_at`.

---

## 5. Verification & Testing Strategy

1. **LLM Capability Check (`tests/check_llm_capabilities.py`)**:
   - Verify connection to `http://103.56.160.46:20128/v1`.
   - List available models.
   - Verify `json_schema` structured output support and JSON fallback resilience.
2. **Hypertension Regression Suite (`tests/test_hypertension_extraction.py`)**:
   - End-to-end extraction and validation on pilot clinical hypertension excerpt.
   - Assert extraction of mandatory benchmark triplets:
     1. `(Cường aldosteron nguyên phát:Cause)-[:CAUSES]->(Tăng huyết áp:Disease)`
     2. `(ACE inhibitor:DrugClass)-[:TREATS]->(Tăng huyết áp:Disease)`
     3. `(130/80 mmHg:Measurement)-[:DEFINES_THRESHOLD_FOR]->(Tăng huyết áp:DiseaseSubtype)`
     4. `(Tăng huyết áp:Disease)-[:LEADS_TO]->(Đột quỵ:Complication)`
   - Assert 0% domain/range constraint violations in final output.
