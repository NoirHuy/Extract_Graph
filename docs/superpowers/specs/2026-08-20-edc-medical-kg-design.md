# Design Document: EDC Medical Knowledge Graph Extraction Pipeline (v1.1)

- **Date:** 2026-08-20
- **Status:** Approved with Revisions
- **Version:** 1.1.0
- **Topic:** Clinical Knowledge Graph Extraction with Extraction Data Contract (EDC), UMLS Normalization, Validation & Consensus, and Neo4j Ingestion

---

## 1. Executive Summary & Objectives

The goal of this system is to extract a high-fidelity Clinical Medical Knowledge Graph (KG) from Vietnamese medical literature (MSD Manual style) using an Extraction Data Contract (EDC). The pilot disease is **Hypertension (Tăng huyết áp)**, and the system is architected to seamlessly generalize to other disease domains. The resulting Knowledge Graph serves downstream applications including **GraphRAG**, **Multi-Agent Debate**, and **Clinical Decision Support Systems (CDSS)**.

The system is structured into five decoupled, testable, and contract-driven modules:
1. **Schema Registry**: Single source of truth for 16 Entity Types, 19 Relation Types, Domain/Range constraints, UMLS STY/TUI mappings, and structured attribute schemas (e.g. for `Measurement`).
2. **LLM Extraction Module**: Dynamic OpenAI-compatible extraction client supporting both native JSON Schema and self-healing fallback JSON prompting, sentence-preserving chunking with plain-text/markdown heading heuristics, and configurable pass execution ($N \ge 1$).
3. **UMLS Normalization Module**: 3-tier hybrid mapping strategy with semantic type validation (Local Vi-En Dict Cache $\rightarrow$ Contextual LLM translation + UMLS REST API $\rightarrow$ Vector/Embedding similarity fallback $\ge 0.85$).
4. **Validation & Consensus Layer**: Agreement check / multi-pass consensus with statistical confidence aggregation, dedicated conflict queuing, strict Domain/Range enforcement, and confidence filtering ($\ge 0.7$).
5. **Neo4j Ingestion Module**: Idempotent graph population via `resolved_key` unique constraints (immune to `null` CUI duplication), Cypher `MERGE`, schema versioning (`schema_version`), and full provenance persistence (`evidence_span`, `confidence`, `agreement_count`, `source_document`, `created_at`, `updated_at`).

---

## 2. Architecture & Data Flow

```text
                               +-------------------------------------+
                               |   Vietnamese Medical Text Input     |
                               |    (.txt plain text or .md file)    |
                               +------------------+------------------+
                                                  |
                                                  v
                               +-------------------------------------+
                               | Text Chunker with Heading Heuristic |
                               |   & 2-Sentence Overlapping Window   |
                               +------------------+------------------+
                                                  |
                                                  v
                     +-------------------------------------------------------+
                     |             LLM Extraction Module                     |
                     |  - Configurable N passes (Default N=2, Dev N=1)       |
                     |  - OpenAI-Compatible endpoint + JSON Schema / Prompt  |
                     |  - Output: Entities (cui=null) + Relations + Spans    |
                     +----------------------------+--------------------------+
                                                  |
                                                  v
                     +-------------------------------------------------------+
                     |           Validation & Consensus Layer                |
                     |  - Entity Deduplication on (normalized_name, type)    |
                     |  - Agreement Check:                                   |
                     |      * Matched relations: statistical confidence &    |
                     |        agreement_count recorded                       |
                     |      * Conflicted relations (same pair, diff type):   |
                     |        flagged & routed to review queue file          |
                     |  - Domain & Range Semantic Validation                 |
                     |  - Confidence Filtering (conf >= 0.7)                 |
                     +----------------------------+--------------------------+
                                                  |
                                                  v
                     +-------------------------------------------------------+
                     |              UMLS Normalization Layer                 |
                     |  - Tier 1: Curated Vi-En CUI Dict Cache               |
                     |  - Tier 2: LLM Context Translation -> UMLS REST API  |
                     |    + STY / Semantic Group Sanity Verification         |
                     |  - Tier 3: Embedding Similarity Fallback (>= 0.85)    |
                     |  - Audit Log: data/processed/{doc}_unmapped.json      |
                     +----------------------------+--------------------------+
                                                  |
                                                  v
                     +-------------------------------------------------------+
                     |               Neo4j Ingestion Layer                   |
                     |  - Unique Constraint on resolved_key                  |
                     |  - Schema Versioning (schema_version: "1.0.0")        |
                     |  - Idempotent MERGE for Nodes & Edges                 |
                     |  - Conflict Exclusion from Active Graph Reasoning     |
                     +-------------------------------------------------------+
```

---

## 3. Detailed Data Contract & Schema Specifications

### 3.1 Entity Types & UMLS Semantic Mapping
16 entity types strictly mapped to UMLS Semantic Types (TUI) and Semantic Groups:

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
| `Measurement` | Laboratory or Test Result / Quantitative Concept | T034/T081 | CONC | Quantitative threshold or numerical value |
| `Drug` | Pharmacologic Substance | T121 | CHEM | Specific medication active ingredient |
| `DrugClass` | Pharmacologic Substance | T121 | CHEM | Pharmacological class (e.g., ACE inhibitor, ARB) |
| `Treatment` | Therapeutic or Preventive Procedure | T061 | PROC | Non-pharmacologic therapy or intervention |
| `Organ` | Body Part, Organ, or Organ Component | T023 | ANAT | Anatomical target or organ system (e.g., Tim, Thận, Não) |
| `PatientGroup` | Population Group / Age Group | T098/T100 | LIVB | Specific demographic or clinical subpopulation |
| `Guideline` | Intellectual Product | T170 | CONC | Clinical guidelines and staging frameworks (e.g., JNC, ACC/AHA) |

### 3.2 Structured Attributes Specification (for `Measurement`)
To enable downstream CDSS and GraphRAG without unstructured string re-parsing, `Measurement` entities support structured attributes:
```json
{
  "systolic": 130,
  "diastolic": 80,
  "value": 130,
  "unit": "mmHg",
  "operator": ">="
}
```

### 3.3 Relation Types & Domain/Range Constraints

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

---

## 4. Module Implementation Details

### 4.1 LLM Client & Text Chunking
- **Client (`extraction/llm_client.py`)**:
  - `OpenAI(base_url=LLM_API_BASE, api_key=LLM_API_KEY)`.
  - Configurable timeout (120s) with exponential retry backoff.
  - Automatically queries available models from endpoint if `LLM_MODEL_NAME` is not explicitly set.
  - Dual-mode: tests `response_format={"type": "json_schema"}`; falls back to system prompt embedded schema + regex JSON stripper + `jsonschema` validation with up to 2 auto-healing retries.
- **Text Chunker (`extraction/text_chunker.py`)**:
  - Input format support: Raw text (.txt) and Markdown (.md).
  - Heading detection heuristics for plain text:
    1. Markdown headers (`#`, `##`, `###`, `**Heading**`).
    2. Short lines ($< 80$ chars) without trailing punctuation ending in standard sentence terminators.
    3. Roman numeral / alphanumeric section prefixes (e.g., `I.`, `1.`, `A.`).
  - Sentence-boundary splitting with configurable overlap window (default 2 sentences) to prevent cross-boundary relationship loss.

### 4.2 Validation, Agreement & Consensus Layer
- **Multi-Pass Configuration**:
  - Configurable `--passes N` (default $N=2$ for production consensus, $N=1$ for fast dev/test, $N=3$ for full voting).
- **Entity Merging**:
  - Key: `(normalized_name.strip().lower(), entity_type)`.
  - Merges duplicate entities across passes, keeping the longest `evidence_span` and unioning `attributes`.
- **Confidence & Agreement Metric**:
  - Separate `confidence` calculation and `agreement_count` metadata:
    $$\text{confidence} = 1 - \prod_{i=1}^{k} (1 - \text{conf}_i)$$
    (or $\max(\text{conf}_i)$ if preferred via configuration).
  - Explicit metadata tracked per relation: `agreement_count: int`, `total_passes: int`, `agreement_ratio: float`.
- **Conflict Handling Policy**:
  - Definition: Same `(source_id, target_id)` pair extracted with conflicting `relation_type` across passes (e.g. Pass 1: `CAUSES`, Pass 2: `INCREASES_RISK_OF`).
  - Policy:
    1. Flag relation with `status: "conflict"`, storing conflicting variants in `conflict_details`.
    2. Write all conflicts to `data/processed/{doc_id}_conflicts.json` for human auditor or Multi-Agent Debate resolution.
    3. **Exclude** conflicted relations from the primary active Neo4j graph by default (can be overridden via `--ingest-disputed` to tag as `:DISPUTED_RELATION`).
- **Domain & Range Validator (`validation/validate_relations.py`)**:
  - Enforces `source.entity_type` $\in \text{Domain}(R)$ and `target.entity_type` $\in \text{Range}(R)$.
  - Filters out relations with `confidence < 0.7`.

### 4.3 UMLS Normalization
- **Tier 1 (Curated Vi-En CUI Dictionary Cache)**:
  - Check local curated file `data/dict/medical_vi_en_cui.json` (seeded with core cardiovascular/hypertension terms).
  - High speed, zero network dependency.
- **Tier 2 (Contextual LLM Translation & UMLS REST API)**:
  - If not in Tier 1 cache, invoke LLM to translate Vietnamese clinical term to standard English medical term (MeSH/SNOMED).
  - Query UMLS REST API (`https://uts-ws.nlm.nih.gov/rest/search/current`) with English term and filter by `sabs=SNOMEDCT_US,MSH,RXNORM`.
  - **Sanity Check**: Verify that the returned CUI's Semantic Type (`sty`) matches the expected Semantic Group of `entity_type`. If incompatible (e.g. `Cause` mapped to `CHEM`), reject the match.
  - On successful lookup, cache the Vi-En-CUI mapping in local cache for future iterations.
- **Tier 3 (Embedding / Vector Similarity Fallback)**:
  - Compute cosine similarity against candidate CUI terminology.
  - Model: Default multilingual / lightweight sentence-transformers (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` or local candidate cosine matcher).
  - Configurable threshold `SIMILARITY_THRESHOLD=0.85`.
- **Unmapped Audit Log**:
  - All entities with unassigned CUI are recorded in `data/processed/{doc_id}_unmapped_entities.json` with reason.

### 4.4 Neo4j Ingestion & Idempotency
- **Primary Key Strategy (`resolved_key`)**:
  - Every node receives a deterministic unique key:
    - If `umls_cui` present: `resolved_key = "CUI:" + umls_cui`
    - If `umls_cui` is `null`: `resolved_key = entity_type + ":" + normalized_name.strip().lower()`
  - Constraint in Neo4j: `CREATE CONSTRAINT IF NOT EXISTS FOR (n:Entity) REQUIRE n.resolved_key IS UNIQUE`.
  - Immune to `null` CUI duplication bugs and allows seamless future CUI backfilling without node duplication.
- **Schema Versioning & Provenance**:
  - Properties stored on nodes: `resolved_key`, `name`, `normalized_name`, `entity_type`, `umls_cui`, `umls_sty`, `schema_version` (e.g. `"1.0.0"`), `source_document`, `created_at`, `updated_at`.
  - Properties stored on relationships: `relation_type`, `evidence_span`, `confidence`, `agreement_count`, `total_passes`, `schema_version`, `source_document`, `created_at`, `updated_at`.
- **Idempotent Cypher Ingestion**:
  - Node MERGE: `MERGE (n:<Label> {resolved_key: $resolved_key}) ON CREATE SET n.created_at = timestamp(), n.updated_at = timestamp(), ... ON MATCH SET n.updated_at = timestamp(), ...`
  - Relationship MERGE: `MERGE (s)-[r:<RELATION_TYPE>]->(t) ON CREATE SET r.created_at = timestamp() ON MATCH SET r.updated_at = timestamp()`

---

## 5. Verification & Testing Strategy

1. **LLM Capability Check (`tests/check_llm_capabilities.py`)**:
   - Query endpoint model list (`GET /models`).
   - Validate `response_format={"type": "json_schema"}` vs prompt JSON fallback.
2. **Regression & Robustness Suite (`tests/test_hypertension_extraction.py`)**:
   - Run end-to-end pipeline on clinical hypertension benchmark text.
   - Assert extraction of 4 mandatory benchmark relations:
     1. `(Cường aldosteron nguyên phát:Cause)-[:CAUSES]->(Tăng huyết áp:Disease)`
     2. `(ACE inhibitor:DrugClass)-[:TREATS]->(Tăng huyết áp:Disease)`
     3. `(130/80 mmHg:Measurement)-[:DEFINES_THRESHOLD_FOR]->(Tăng huyết áp:DiseaseSubtype)`
     4. `(Tăng huyết áp:Disease)-[:LEADS_TO]->(Đột quỵ:Complication)`
   - Assert structured `attributes` on `Measurement` (systolic=130, diastolic=80, unit=mmHg).
   - Assert conflict detection test case (simulated discordant relation types flagged and routed to `_conflicts.json`).
   - Assert 0% domain/range constraint violations.
