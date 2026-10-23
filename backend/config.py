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
    "postgresql+psycopg2://admin:admin2906@localhost:5433/law_db",
)
COLLECTION_NAME = os.getenv("PGVECTOR_COLLECTION", "it_law_documents")
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "gemini").strip().lower()
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# --- Khối Symbolic: Neo4j ----------------------------------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "lawgraph2906")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# --- LLM (DeepSeek trực tiếp hoặc qua OpenRouter) ----------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_CHAT_MODEL = os.getenv("OPENROUTER_CHAT_MODEL", "deepseek/deepseek-chat")


def create_llm(temperature: float = 0.0, timeout: int = 120):
    """Ưu tiên DeepSeek API gốc nếu có DEEPSEEK_API_KEY, ngược lại dùng OpenRouter."""
    from langchain_openai import ChatOpenAI

    if DEEPSEEK_API_KEY:
        return ChatOpenAI(
            model=DEEPSEEK_MODEL,
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            temperature=temperature,
            max_retries=3,
            timeout=timeout,
        )
    if OPENROUTER_API_KEY:
        return ChatOpenAI(
            model=OPENROUTER_CHAT_MODEL,
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            temperature=temperature,
            max_retries=3,
            timeout=timeout,
        )
    raise RuntimeError(
        "Thiếu khóa LLM. Khai báo DEEPSEEK_API_KEY hoặc OPENROUTER_API_KEY trong backend/.env."
    )


@lru_cache(maxsize=1)
def get_embeddings():
    if EMBEDDING_PROVIDER == "openai":
        from langchain_openai import OpenAIEmbeddings

        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("Thiếu OPENAI_API_KEY trong backend/.env.")
        return OpenAIEmbeddings(model=OPENAI_EMBEDDING_MODEL)
    if EMBEDDING_PROVIDER == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        if not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError("Thiếu GEMINI_API_KEY trong backend/.env.")
        return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    raise RuntimeError("EMBEDDING_PROVIDER phải là 'gemini' hoặc 'openai'.")


def create_neo4j_driver():
    from neo4j import GraphDatabase

    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
