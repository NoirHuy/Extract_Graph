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
