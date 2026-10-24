"""OpenAI-compatible chat completions client."""
from __future__ import annotations

import os
import time
import httpx
from pathlib import Path
from dotenv import load_dotenv

from eyes_core.config import ROOT

ENV_PATH = ROOT / ".env.model"

def load_model_env():
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)

load_model_env()

class LLMConfig:
    def __init__(self):
        self.provider = os.environ.get("MODEL_PROVIDER", "")
        self.model = os.environ.get("MODEL_NAME", "")
        self.api_key = os.environ.get("MODEL_API_KEY", "")
        self.base_url = os.environ.get("MODEL_BASE_URL", "https://api.openai.com/v1")
        self.timeout = float(os.environ.get("MODEL_TIMEOUT_SECONDS", "60"))
        self.max_retries = int(os.environ.get("MODEL_MAX_RETRIES", "2"))
        self.temperature = float(os.environ.get("MODEL_TEMPERATURE", "0.2"))
        self.max_output_tokens = int(os.environ.get("MODEL_MAX_OUTPUT_TOKENS", "2048"))

    def validate(self):
        if not self.api_key:
            raise RuntimeError("MODEL_API_KEY is missing in .env.model")
        if not self.model:
            raise RuntimeError("MODEL_NAME is missing in .env.model")
        if not self.base_url:
            raise RuntimeError("MODEL_BASE_URL is missing in .env.model")

class LLMClient:
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()

    def chat(self, messages: list[dict], temperature: float | None = None, max_tokens: int | None = None) -> dict:
        self.config.validate()
        temp = self.config.temperature if temperature is None else temperature
        mtok = self.config.max_output_tokens if max_tokens is None else max_tokens
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": mtok,
            "response_format": {"type": "json_object"},
        }
        last_err = None
        for attempt in range(self.config.max_retries + 1):
            try:
                with httpx.Client(timeout=self.config.timeout) as c:
                    r = c.post(url, headers=headers, json=body)
                    r.raise_for_status()
                    data = r.json()
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                return {
                    "provider": self.config.provider or "openai-compatible",
                    "model": self.config.model,
                    "content": content,
                    "raw": data,
                    "latency_ms": None,
                }
            except Exception as e:
                last_err = e
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"LLM call failed after retries: {last_err}")

    def redact(self, text: str) -> str:
        # basic secret redaction
        import re
        text = re.sub(r"sk-[A-Za-z0-9_-]{10,}", "[REDACTED]", text)
        text = re.sub(r"MODEL_API_KEY=\S+", "MODEL_API_KEY=[REDACTED]", text)
        return text
