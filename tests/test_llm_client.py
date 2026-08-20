import json
import pytest
from unittest.mock import MagicMock, patch
from extraction.llm_client import LLMClient

def test_strip_markdown_fence():
    client = LLMClient(base_url="http://mock-endpoint/v1", api_key="test-key", model_name="mock-model")
    raw_with_fence = '```json\n{"entities": [], "relations": []}\n```'
    assert client._strip_markdown_fence(raw_with_fence) == '{"entities": [], "relations": []}'

def test_extract_structured_with_mock_json():
    client = LLMClient(base_url="http://mock-endpoint/v1", api_key="test-key", model_name="mock-model")
    client._native_json_schema_supported = False
    
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
