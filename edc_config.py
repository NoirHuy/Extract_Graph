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
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.80"))
    # Dense Vector Embedding Configuration (OpenRouter / OpenAI)
    EMBEDDING_API_BASE: str = os.getenv("EMBEDDING_API_BASE", "https://openrouter.ai/api/v1")
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY", "")
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "openai/text-embedding-3-large")
    EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    EMBEDDING_CACHE_FILE: str = os.getenv("EMBEDDING_CACHE_FILE", "data/dict/dictionary_embeddings.json")
    DENSE_SIMILARITY_THRESHOLD: float = float(os.getenv("DENSE_SIMILARITY_THRESHOLD", "0.75"))
    SCHEMA_VERSION: str = "1.0.0"

_settings = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
