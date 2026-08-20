# EDC Medical Knowledge Graph Pipeline

Hệ thống trích xuất **Đồ thị Tri thức Y khoa (Clinical Knowledge Graph)** từ tài liệu lâm sàng tiếng Việt theo chuẩn **Extraction Data Contract (EDC)**, chuẩn hóa **UMLS CUI/STY**, nạp vào cơ sở dữ liệu đồ thị **Neo4j**, và hỗ trợ **Xuất bảng CSV trực quan** cho chuyên gia y tế.

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
│   ├── consensus.py                 # Hợp nhất thực thể, tính statistical confidence, Semantic Tie-Breaker
│   └── validate_relations.py        # Kiểm tra Domain/Range và Auto-Remapping quan hệ
├── ingestion/
│   └── neo4j_loader.py              # Khởi tạo Unique Constraints trên `resolved_key` & nạp Neo4j
├── export/
│   └── neo4j_exporter.py            # Trích xuất Knowledge Graph từ Neo4j ra các file CSV trực quan
├── data/
│   ├── raw/                         # Chứa tài liệu văn bản gốc (.txt, .md)
│   ├── processed/                   # Chứa artifacts JSON sau từng công đoạn
│   ├── exports/                     # Chứa các file CSV xuất ra để xem trên Excel
│   └── dict/                        # Từ điển ánh xạ thuật ngữ y khoa (Vi-En-CUI)
├── tests/                           # 26 Unit & Regression Tests
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
```ini
LLM_API_BASE=http://103.56.160.46:20128/v1
LLM_API_KEY=your_actual_api_key_here
LLM_MODEL_NAME=
NEO4J_URI=neo4j+s://a2cdb10c.databases.neo4j.io
NEO4J_USERNAME=a2cdb10c
NEO4J_PASSWORD=your_neo4j_password
NEO4J_DATABASE=neo4j
UMLS_API_KEY=
DEFAULT_PASSES=2
CONFIDENCE_THRESHOLD=0.7
SIMILARITY_THRESHOLD=0.85
```

---

## 3. Hướng dẫn Sử dụng

### 3.1 Kiểm tra khả năng của Endpoint LLM
```bash
python main.py probe-llm
```

### 3.2 Chạy toàn trình Pipeline (End-to-End)
Trích xuất từ file văn bản thô, chuẩn hóa UMLS, và nạp vào Neo4j:
```bash
python main.py run-all --input data/raw/hypertension_sample.txt --passes 2
```

### 3.3 Xuất kết quả Knowledge Graph từ Neo4j ra file CSV (Excel-Friendly)
Trích xuất toàn bộ đồ thị tri thức từ Neo4j thành 3 bảng CSV trực quan lưu tại `data/exports/`:
```bash
python main.py export --output-dir data/exports
```
Các file được tạo ra bao gồm:
1. `clinical_knowledge_summary.csv`: Bảng tổng hợp bộ 3 tri thức lâm sàng tiếng Việt (Thực thể nguồn $\rightarrow$ Quan hệ $\rightarrow$ Thực thể đích kèm mã CUI, độ tin cậy và bằng chứng câu gốc).
2. `relationships_triplets.csv`: Toàn bộ các cạnh quan hệ chi tiết.
3. `nodes_entities.csv`: Toàn bộ danh sách các node thực thể và thuộc tính.

---

## 4. Chạy Bộ Kiểm thử Tự động
```bash
pytest -v
```
