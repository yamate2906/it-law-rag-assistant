"""Shared temporal and provenance helpers for versioned legal knowledge."""

from __future__ import annotations

from datetime import date
import hashlib
import json
from typing import Any


def parse_as_of(value: date | str | None) -> date:
    """Return the legal evaluation date, defaulting to today's local date."""
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def is_effective_on(
    effective_from: date | str | None,
    effective_to: date | str | None,
    as_of: date | str | None = None,
) -> bool:
    """Use inclusive legal effective-date boundaries; unknown boundaries stay open."""
    at = parse_as_of(as_of)
    start = date.fromisoformat(str(effective_from)) if effective_from else None
    end = date.fromisoformat(str(effective_to)) if effective_to else None
    return (start is None or start <= at) and (end is None or at <= end)


def provision_version_id(
    doc_code: str,
    article_number: int | str,
    source_file: str,
    text: str,
    effective_from: date | str | None,
    effective_to: date | str | None,
) -> str:
    """Stable ID for an immutable article-text snapshot with its source and interval."""
    payload: dict[str, Any] = {
        "doc_code": doc_code,
        "article_number": str(article_number),
        "source_file": source_file,
        "text": " ".join((text or "").split()),
        "effective_from": str(effective_from) if effective_from else None,
        "effective_to": str(effective_to) if effective_to else None,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
