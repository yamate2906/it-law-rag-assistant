"""Cấu hình dùng chung cho toàn bộ backend (Postgres/pgvector, Neo4j, Gemini, DeepSeek)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

load_dotenv(BACKEND_DIR / ".env", override=True)

# --- Khối Neural: PostgreSQL + pgvector -------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:password@localhost:5433/law_db",
).strip()
COLLECTION_NAME = os.getenv("PGVECTOR_COLLECTION", "it_law_documents")
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "gemini").strip().lower()
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# --- Khối Symbolic: Neo4j ----------------------------------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123").strip()
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# --- LLM (DeepSeek trực tiếp hoặc qua OpenRouter) ----------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_CHAT_MODEL = os.getenv("OPENROUTER_CHAT_MODEL", "deepseek/deepseek-chat")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", os.getenv("OPENROUTER_MAX_TOKENS", "2048")))


def create_llm(temperature: float = 0.0, timeout: int = 120, max_tokens: int | None = None):
    """Ưu tiên DeepSeek API gốc nếu có DEEPSEEK_API_KEY, ngược lại dùng OpenRouter."""
    from langchain_openai import ChatOpenAI

    load_dotenv(BACKEND_DIR / ".env", override=True)
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    limit_tokens = max_tokens or int(
        os.getenv("LLM_MAX_TOKENS", os.getenv("OPENROUTER_MAX_TOKENS", "2048"))
    )

    if deepseek_key:
        return ChatOpenAI(
            model=os.getenv("DEEPSEEK_MODEL", DEEPSEEK_MODEL),
            api_key=deepseek_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL),
            temperature=temperature,
            max_tokens=limit_tokens,
            max_retries=3,
            timeout=timeout,
        )
    if openrouter_key:
        return ChatOpenAI(
            model=os.getenv("OPENROUTER_CHAT_MODEL", OPENROUTER_CHAT_MODEL),
            api_key=openrouter_key,
            base_url=os.getenv("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
            temperature=temperature,
            max_tokens=limit_tokens,
            max_retries=3,
            timeout=timeout,
        )
    raise RuntimeError(
        "Thiếu khóa LLM. Khai báo DEEPSEEK_API_KEY hoặc OPENROUTER_API_KEY trong backend/.env."
    )


@lru_cache(maxsize=1)
def get_embeddings():
    load_dotenv(BACKEND_DIR / ".env", override=True)
    provider = os.getenv("EMBEDDING_PROVIDER", EMBEDDING_PROVIDER).strip().lower()
    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("Thiếu OPENAI_API_KEY trong backend/.env.")
        return OpenAIEmbeddings(model=os.getenv("OPENAI_EMBEDDING_MODEL", OPENAI_EMBEDDING_MODEL))
    if provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Thiếu GEMINI_API_KEY trong backend/.env.")
        return GoogleGenerativeAIEmbeddings(
            model=os.getenv("GEMINI_EMBEDDING_MODEL", EMBEDDING_MODEL),
            google_api_key=api_key,
        )
    raise RuntimeError("EMBEDDING_PROVIDER phải là 'gemini' hoặc 'openai'.")


def create_neo4j_driver():
    from neo4j import GraphDatabase

    if not NEO4J_PASSWORD:
        raise RuntimeError("Thiếu NEO4J_PASSWORD trong backend/.env.")
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
