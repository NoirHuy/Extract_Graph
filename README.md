# EDC Medical Knowledge Graph Pipeline

Hệ thống trích xuất **Đồ thị Tri thức Y khoa (Clinical Knowledge Graph)** từ tài liệu lâm sàng tiếng Việt theo chuẩn **Extraction Data Contract (EDC)**, chuẩn hóa **UMLS CUI/STY**, và nạp vào cơ sở dữ liệu đồ thị **Neo4j**.

Hệ thống được thiết kế phục vụ downstream cho **GraphRAG**, **Multi-Agent Debate**, và **Hệ thống Hỗ trợ Ra Quyết định Lâm sàng (CDSS)**.

---

## 1. Cấu trúc Dự án

```text
Extract_EDC_2/
├── schema/
│   ├── edc_schema.json              # JSON Schema ràng buộc đầu ra LLM
│   └── schema_registry.py          # Quản lý 16 Entity Types, 19 Relation Types, Domain/Range
├── extraction/
│   ├── llm_client.py                # Client gọi LLM (OpenAI-compatible) với Dual-Mode & auto-retry
│   ├── text_chunker.py              # Chunking văn bản tiếng Việt bảo tồn ranh giới câu & heading
│   ├── prompts.py                   # System prompt chuẩn y khoa + Few-shot examples
│   └── extract.py                   # Runner trích xuất multi-pass
├── normalization/
│   ├── dictionary_lookup.py         # Tier 1: Từ điển song ngữ y khoa Việt - Anh tích hợp
│   ├── umls_client.py               # Tier 2: UMLS UTS REST API Client lọc theo STY/SAB
│   ├── vector_fallback.py           # Tier 3: Vector / N-gram Cosine Similarity Matcher (>= 0.85)
│   └── umls_normalize.py            # Điều phối 3-Tier Normalization & ghi log unmapped entities
├── validation/
│   ├── consensus.py                 # Hợp nhất thực thể, tính statistical confidence, bắt conflict
│   └── validate_relations.py        # Kiểm tra Domain/Range và lọc confidence threshold
├── ingestion/
│   └── neo4j_loader.py              # Khởi tạo Unique Constraints trên `resolved_key` & nạp Neo4j
├── data/
│   ├── raw/                         # Chứa tài liệu văn bản gốc (.txt, .md)
│   ├── processed/                   # Chứa artifacts JSON sau từng công đoạn
│   └── dict/                        # Từ điển ánh xạ thuật ngữ y khoa (Vi-En-CUI)
├── tests/
│   ├── check_llm_capabilities.py    # Script probe endpoint kiểm tra hỗ trợ structured output
│   ├── test_schema_registry.py      # Test schema và domain/range
│   ├── test_text_chunker.py         # Test chunker tiếng Việt
│   ├── test_llm_client.py           # Test client LLM
│   ├── test_extract.py              # Test multi-pass runner
│   ├── test_validation_consensus.py # Test consensus và validation
│   ├── test_umls_normalize.py       # Test 3-tier normalization
│   ├── test_neo4j_loader.py         # Test Cypher query & resolved_key
│   └── test_hypertension_extraction.py # Test suite hồi quy toàn trình trên ca tăng huyết áp
├── main.py                          # Unified CLI Entrypoint
├── config.py / edc_config.py        # Quản lý cấu hình & biến môi trường
└── requirements.txt                 # Phụ thuộc thư viện
```

---

## 2. Cài đặt & Cấu hình Môi trường

### 2.1 Cài đặt thư viện
```bash
pip install -r requirements.txt
```

### 2.2 Thiết lập file `.env`
Tạo file `.env` từ `.env.example`:
```bash
cp .env.example .env
```
Điền các giá trị thực tế:
```ini
LLM_API_BASE=http://103.56.160.46:20128/v1
LLM_API_KEY=your_actual_api_key_here
LLM_MODEL_NAME=
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j
UMLS_API_KEY=your_umls_api_key_here  # Tùy chọn, dùng cho Tier 2 UMLS REST API
DEFAULT_PASSES=2
CONFIDENCE_THRESHOLD=0.7
SIMILARITY_THRESHOLD=0.85
```

---

## 3. Hướng dẫn Sử dụng

### 3.1 Kiểm tra khả năng của Endpoint LLM
```bash
python main.py probe-llm
# hoặc:
python tests/check_llm_capabilities.py
```

### 3.2 Chạy toàn trình Pipeline (End-to-End)
Chạy toàn bộ từ file văn bản thô vào Neo4j (kèm multi-pass $N=2$):
```bash
python main.py run-all --input data/raw/hypertension_sample.txt --passes 2
```

Chạy chế độ thử nghiệm không ghi database (`--dry-run`):
```bash
python main.py run-all --input data/raw/hypertension_sample.txt --passes 2 --dry-run
```

### 3.3 Chạy từng bước độc lập (Modular Step-by-Step)
- **Bước 1: Trích xuất LLM thô:**
  ```bash
  python main.py extract --input data/raw/hypertension_sample.txt --passes 2
  ```
- **Bước 2: Nạp kết quả đã chuẩn hóa vào Neo4j:**
  ```bash
  python main.py ingest --entities data/processed/hypertension_sample_entities.json --relations data/processed/hypertension_sample_relations.json --dry-run
  ```

---

## 4. Chạy Bộ Kiểm thử Tự động (Regression Test Suite)

Chạy toàn bộ kiểm thử:
```bash
pytest -v
```

Kiểm thử riêng bộ hồi quy ca bệnh Tăng huyết áp:
```bash
pytest tests/test_hypertension_extraction.py -v
```
