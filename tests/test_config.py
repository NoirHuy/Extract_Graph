import os
import pytest
from edc_config import get_settings

def test_default_settings():
    settings = get_settings()
    assert settings.LLM_API_BASE == "http://103.56.160.46:20128/v1"
    assert settings.DEFAULT_PASSES == 2
    assert settings.CONFIDENCE_THRESHOLD == 0.7
    assert settings.SIMILARITY_THRESHOLD in (0.80, 0.85)
    assert settings.EMBEDDING_MODEL_NAME == "openai/text-embedding-3-large"
    assert settings.SCHEMA_VERSION == "1.0.0"
