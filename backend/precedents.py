"""Validated, provenance-preserving import for manually curated court precedents.

The importer never extracts holdings from raw judgments with an LLM. Each record
must identify the official source and the legal text it cites or interprets.
"""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class StatuteReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_code: str = Field(min_length=3, max_length=100)
    article_number: str = Field(min_length=1, max_length=20)
    clause_number: int | None = Field(default=None, ge=1)
    point: str | None = Field(default=None, min_length=1, max_length=5)
    relation: Literal["CITES", "INTERPRETS", "APPLIES"] = "CITES"
    supporting_quote: str = Field(min_length=10, max_length=3000)


class PrecedentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9._/-]{2,120}$")
    title: str = Field(min_length=5, max_length=500)
    court: str = Field(min_length=2, max_length=200)
    decision_number: str = Field(min_length=1, max_length=100)
    decision_date: date
    status: Literal["ACTIVE", "WITHDRAWN", "UNKNOWN"] = "UNKNOWN"
    status_source: str | None = Field(default=None, max_length=1000)
    source_url: HttpUrl
    material_facts: str = Field(min_length=20, max_length=12000)
    legal_issue: str = Field(min_length=10, max_length=5000)
    holding: str = Field(min_length=10, max_length=8000)
    reasoning: str = Field(min_length=10, max_length=12000)
    references: list[StatuteReference] = Field(min_length=1, max_length=40)
    tags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("source_url")
    @classmethod
    def _official_source_only(cls, value: HttpUrl) -> HttpUrl:
        host = (urlparse(str(value)).hostname or "").lower()
        if host != "toaan.gov.vn" and not host.endswith(".toaan.gov.vn"):
            raise ValueError("Án lệ phải trỏ tới nguồn thuộc tên miền chính thức toaan.gov.vn")
        return value

    @field_validator("status_source")
    @classmethod
    def _status_has_source(cls, value: str | None, info) -> str | None:
        if info.data.get("status") in {"ACTIVE", "WITHDRAWN"} and not value:
            raise ValueError("Trạng thái ACTIVE/WITHDRAWN cần status_source chính thức")
        if value:
            host = (urlparse(value).hostname or "").lower()
            if host != "toaan.gov.vn" and not host.endswith(".toaan.gov.vn"):
                raise ValueError("status_source phải thuộc tên miền chính thức toaan.gov.vn")
        return value


def load_precedent_manifest(path: Path) -> list[PrecedentRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("precedents") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("Manifest phải là một mảng hoặc object có trường 'precedents'")
    parsed = [PrecedentRecord.model_validate(record) for record in records]
    ids = [record.id for record in parsed]
    if len(ids) != len(set(ids)):
        raise ValueError("Manifest có id án lệ bị trùng")
    return parsed


def _write_precedent(tx, record: PrecedentRecord, source_file: str) -> int:
    tx.run(
        """
        MATCH (p:Precedent {id: $id})
        OPTIONAL MATCH (p)-[r:CITES|INTERPRETS|APPLIES]->(:Article)
        DELETE r
        """,
        id=record.id,
    ).consume()
    tx.run(
        """
        MERGE (p:Precedent {id: $id})
        SET p.title = $title, p.court = $court, p.decision_number = $decision_number,
            p.decision_date = date($decision_date), p.status = $status,
            p.status_source = $status_source, p.source_url = $source_url,
            p.material_facts = $material_facts, p.legal_issue = $legal_issue,
            p.holding = $holding, p.reasoning = $reasoning, p.tags = $tags,
            p.source_file = $source_file, p.reference_specs = $reference_specs,
            p.provenance_status = 'CURATED_FROM_OFFICIAL_SOURCE'
        """,
        id=record.id,
        title=record.title,
        court=record.court,
        decision_number=record.decision_number,
        decision_date=record.decision_date.isoformat(),
        status=record.status,
        status_source=record.status_source,
        source_url=str(record.source_url),
        material_facts=record.material_facts,
        legal_issue=record.legal_issue,
        holding=record.holding,
        reasoning=record.reasoning,
        tags=record.tags,
        source_file=source_file,
        reference_specs=[reference.model_dump(mode="json") for reference in record.references],
    ).consume()

    resolved = 0
    for reference in record.references:
        relation_type = {"CITES": "CITES", "INTERPRETS": "INTERPRETS", "APPLIES": "APPLIES"}[reference.relation]
        reference_key = hashlib.sha256(
            "\0".join((
                relation_type,
                reference.doc_code,
                reference.article_number,
                str(reference.clause_number or ""),
                reference.point or "",
                reference.supporting_quote,
            )).encode("utf-8")
        ).hexdigest()
        result = tx.run(
            f"""
            MATCH (p:Precedent {{id: $id}})
            MATCH (a:Article {{doc_code: $doc_code, number: $article_number}})
            MERGE (p)-[r:{relation_type} {{id: $reference_id}}]->(a)
            SET r.clause_number = $clause_number, r.point = $point,
                r.supporting_quote = $supporting_quote, r.source_url = $source_url
            RETURN count(a) AS linked
            """,
            id=record.id,
            reference_id=reference_key,
            doc_code=reference.doc_code,
            article_number=reference.article_number,
            clause_number=reference.clause_number,
            point=reference.point,
            supporting_quote=reference.supporting_quote,
            source_url=str(record.source_url),
        ).single()
        if result:
            resolved += int(result["linked"] or 0)
    tx.run(
        """
        MATCH (p:Precedent {id: $id})
        SET p.resolved_reference_count = $resolved,
            p.unresolved_reference_count = $attempted - $resolved,
            p.reference_status = CASE WHEN $attempted = $resolved THEN 'ALL_RESOLVED'
                                      ELSE 'NEEDS_ARTICLE_LINK_REVIEW' END
        """,
        id=record.id,
        resolved=resolved,
        attempted=len(record.references),
    ).consume()
    return resolved


def ingest_precedents(driver, records: list[PrecedentRecord], source_file: str) -> dict[str, int]:
    from config import NEO4J_DATABASE
    from graph_ingest import setup_schema

    setup_schema(driver)
    summary = {"precedents": 0, "resolved_references": 0, "attempted_references": 0}
    with driver.session(database=NEO4J_DATABASE) as session:
        for record in records:
            summary["resolved_references"] += session.execute_write(
                _write_precedent, record, source_file
            )
            summary["attempted_references"] += len(record.references)
            summary["precedents"] += 1
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nạp án lệ đã được tuyển chọn và kiểm chứng vào Neo4j")
    parser.add_argument("manifest", type=Path, help="JSON manifest theo schema precedents/README.md")
    args = parser.parse_args(argv)
    records = load_precedent_manifest(args.manifest)
    if not records:
        print("Manifest hợp lệ nhưng chưa có án lệ nào để nạp.")
        return 0

    from config import create_neo4j_driver

    driver = create_neo4j_driver()
    try:
        driver.verify_connectivity()
        summary = ingest_precedents(driver, records, args.manifest.name)
        print(
            f"Đã đồng bộ {summary['precedents']} án lệ; "
            f"liên kết được {summary['resolved_references']}/{summary['attempted_references']} căn cứ Điều/Khoản."
        )
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
