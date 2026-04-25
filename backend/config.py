"""Configuration — env vars and a lazy Gemini LLM factory.

The LLM is created on first use (not at import) so that module imports
succeed even when GOOGLE_API_KEY is not yet set (e.g., during tooling).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# Use the OS trust store (Windows cert store on Windows) for all TLS calls.
# Required for corporate networks that do SSL inspection — without this,
# Tavily / Google / mem0 calls fail with CERTIFICATE_VERIFY_FAILED.
# Safe on non-corporate networks; falls back to system roots.
try:  # pragma: no cover — best-effort
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
MEM0_API_KEY = os.getenv("MEM0_API_KEY", "")

# MODEL_NAME = "gemini-2.5-flash-lite"
MODEL_NAME = "gemini-3.1-flash-lite-preview"


@lru_cache(maxsize=1)
def get_llm() -> ChatGoogleGenerativeAI:
    if not GOOGLE_API_KEY:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        temperature=0.3,
        google_api_key=GOOGLE_API_KEY,
    )
