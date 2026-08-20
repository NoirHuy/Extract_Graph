"""Endpoint Capability Prober for LLM Extraction.

Tests:
1. Connection to LLM_API_BASE
2. Lists available models
3. Probes structured output (`response_format={"type": "json_schema"}`)
4. Tests Vietnamese parsing resilience and JSON fallback
"""

import os
import sys
import json
import logging

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edc_config import get_settings
from extraction.llm_client import LLMClient
from schema.schema_registry import get_edc_json_schema

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    settings = get_settings()
    print("=" * 60)
    print("      LLM ENDPOINT CAPABILITY & RESILIENCE PROBER")
    print("=" * 60)
    print(f"Target Base URL: {settings.LLM_API_BASE}")
    print(f"API Key Set: {'Yes (' + settings.LLM_API_KEY[:4] + '...)' if settings.LLM_API_KEY else 'No'}")
    print(f"Configured Model: {settings.LLM_MODEL_NAME or '(Auto-detect)'}")
    print("-" * 60)

    client = LLMClient()

    # Step 1: List models
    print("\n[Step 1] Querying available models from endpoint...")
    try:
        models = client.list_models()
        if models:
            print(f"[OK] Successfully retrieved {len(models)} model(s):")
            for m in models:
                print(f"  - {m}")
        else:
            print("[WARN] Endpoint returned empty model list or models endpoint not implemented.")
    except Exception as e:
        print(f"[FAIL] Error querying models: {e}")

    # Step 2: Test Structured Output
    print("\n[Step 2] Testing Structured Output & Extraction Capability...")
    sample_text = "Bệnh nhân được chẩn đoán Tăng huyết áp giai đoạn 1 với huyết áp đo được là 135/85 mmHg. Bác sĩ chỉ định dùng ACE inhibitor."
    schema = get_edc_json_schema()

    try:
        payload = client.extract_structured(
            system_prompt="Bạn là chuyên gia y tế trích xuất thực thể và quan hệ theo schema JSON.",
            user_text=sample_text,
            schema=schema,
            temperature=0.0,
        )
        print("[OK] Structured extraction successful!")
        print(f"Native json_schema supported: {client._native_json_schema_supported}")
        print("\nExtracted Entities:")
        for ent in payload.get("entities", []):
            print(f"  - [{ent.get('entity_type')}] {ent.get('normalized_name')} (Span: '{ent.get('evidence_span')}')")
        print("\nExtracted Relations:")
        for rel in payload.get("relations", []):
            print(f"  - {rel.get('source_id')} -[{rel.get('relation_type')}]-> {rel.get('target_id')} (Conf: {rel.get('confidence')})")
        print("\n" + "=" * 60)
        print("ALL LLM CAPABILITY CHECKS PASSED")
        print("=" * 60)
    except Exception as e:
        print(f"[FAIL] Structured extraction failed: {e}")
        print("\nNotice: You can configure valid credentials in .env file (LLM_API_KEY, LLM_MODEL_NAME).")


if __name__ == "__main__":
    main()
