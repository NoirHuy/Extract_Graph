"""Resilient OpenAI-Compatible LLM Client supporting Structured Output and Self-Healing JSON Fallback."""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
import jsonschema
from openai import OpenAI, APIConnectionError, InternalServerError, RateLimitError
from edc_config import get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Wrapper client for OpenAI-compatible LLM endpoints with auto-retry and structured output fallback."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: float = 120.0,
    ):
        settings = get_settings()
        self.base_url = base_url or settings.LLM_API_BASE
        self.api_key = api_key or settings.LLM_API_KEY
        self.model_name = model_name or settings.LLM_MODEL_NAME
        self.timeout = timeout
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)
        self._native_json_schema_supported: Optional[bool] = None

    def list_models(self) -> List[str]:
        """Fetch available models from the endpoint."""
        try:
            res = self.client.models.list()
            return [m.id for m in res.data]
        except Exception as e:
            logger.warning(f"Could not retrieve model list from {self.base_url}: {e}")
            return []

    def get_model_name(self) -> str:
        """Resolve model name; query endpoint if not configured."""
        if self.model_name:
            return self.model_name
        models = self.list_models()
        if models:
            self.model_name = models[0]
            logger.info(f"Auto-selected model: {self.model_name}")
            return self.model_name
        # Fallback default
        self.model_name = "default-model"
        return self.model_name

    def _strip_markdown_fence(self, content: str) -> str:
        """Strip markdown ```json ... ``` blocks from raw LLM output."""
        clean = content.strip()
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return clean

    def _call_with_retry(self, messages: List[Dict[str, Any]], response_format: Optional[Dict[str, Any]] = None, temperature: float = 0.0) -> str:
        """Execute chat completion with exponential backoff on network/5xx errors."""
        model = self.get_model_name()
        max_retries = 3
        backoff = 2.0

        for attempt in range(1, max_retries + 1):
            try:
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if response_format:
                    kwargs["response_format"] = response_format

                response = self.client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                return content
            except (APIConnectionError, InternalServerError, RateLimitError) as e:
                logger.warning(f"LLM call attempt {attempt}/{max_retries} failed ({type(e).__name__}: {e}). Backoff {backoff}s...")
                if attempt == max_retries:
                    raise
                time.sleep(backoff)
                backoff *= 2
            except Exception as e:
                # Catch other API errors such as unsupported response_format
                raise

    def extract_structured(
        self,
        system_prompt: str,
        user_text: str,
        schema: Dict[str, Any],
        few_shot_examples: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """Extract structured JSON payload adhering to schema, with self-healing retry on parse/schema failure."""
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if few_shot_examples:
            messages.extend(few_shot_examples)
        messages.append({"role": "user", "content": f"VĂN BẢN CẦN TRÍCH XUẤT:\n{user_text}"})

        # Try native response_format json_schema if not yet determined or known to work
        if self._native_json_schema_supported is not False:
            try:
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "ClinicalKGExtraction",
                        "strict": True,
                        "schema": schema,
                    },
                }
                raw_text = self._call_with_retry(messages, response_format=response_format, temperature=temperature)
                clean_text = self._strip_markdown_fence(raw_text)
                payload = json.loads(clean_text)
                jsonschema.validate(instance=payload, schema=schema)
                self._native_json_schema_supported = True
                return payload
            except Exception as e:
                logger.info(f"Native json_schema failed or unsupported ({e}). Falling back to prompt JSON schema parsing...")
                self._native_json_schema_supported = False

        # Fallback Mode: Prompt-based structured extraction with self-healing retries
        current_messages = list(messages)
        max_healing_attempts = 2

        for healing_attempt in range(max_healing_attempts + 1):
            raw_text = self._call_with_retry(current_messages, response_format=None, temperature=temperature)
            clean_text = self._strip_markdown_fence(raw_text)

            try:
                payload = json.loads(clean_text)
                jsonschema.validate(instance=payload, schema=schema)
                return payload
            except (json.JSONDecodeError, jsonschema.ValidationError) as err:
                if healing_attempt == max_healing_attempts:
                    logger.error(f"Failed to parse valid structured JSON after {max_healing_attempts} retries: {err}")
                    raise ValueError(f"LLM structured extraction failed schema validation: {err}\nRaw text: {raw_text}")

                logger.warning(f"JSON validation error (attempt {healing_attempt+1}): {err}. Requesting self-healing fix...")
                current_messages.append({"role": "assistant", "content": raw_text})
                current_messages.append({
                    "role": "user",
                    "content": f"JSON của bạn không hợp lệ hoặc vi phạm schema với lỗi: {err}. Hãy sửa lại và chỉ trả về chuỗi JSON thuần hợp lệ tuân thủ schema.",
                })
