"""Công đoạn 3 - Khối Symbolic: xây dựng Đồ thị Tri thức pháp lý trên Neo4j.

Kiến trúc trích xuất 3 tầng (Tất định + LLM + Kiểm chứng Symbolic + Vector Index):
  Tầng 1 (tất định) : legal_parser bóc tách Văn bản -> Điều -> Khoản -> Điểm, khung phạt tiền
                      (regex), hành vi bị nghiêm cấm / quy phạm trong Luật, hình thức xử phạt
                      bổ sung / biện pháp khắc phục, điều kiện áp dụng và tham chiếu chéo.
  Tầng 2 (LLM)      : DeepSeek đọc từng Điều, trả JSON (Pydantic validate) gồm hành vi đã chuẩn hóa,
                      chủ thể, điều kiện. Mức phạt LLM được ĐỐI CHIẾU với regex; regex luôn thắng.
  Tầng 3 (Neural)   : nhúng tên hành vi bằng Gemini và tạo Vector Index ngay trong Neo4j.

Schema đồ thị:
  (:LegalDoc)<-[:PART_OF]-(:Article)<-[:PART_OF]-(:Clause)<-[:DEFINED_IN]-(:Action)
  (:Action)-[:PENALIZED_BY]->(:Penalty)-[:APPLIES_TO]->(:Subject)
  (:Action)-[:COMMITTED_BY]->(:Subject)       (:Action)-[:HAS_CONDITION]->(:Condition)
  (:Action)-[:HAS_SANCTION]->(:Sanction)      (:Article)-[:REFERENCES]->(:Article)

Cách chạy (trong thư mục backend):
  python graph_ingest.py --no-llm --priority-only  # dựng khung xương + nhúng các Điều trọng tâm (nhanh)
  python graph_ingest.py --no-llm                  # dựng khung xương + nhúng toàn bộ hành vi
  python graph_ingest.py                           # đầy đủ: khung xương + LLM + embedding
  python graph_ingest.py --reset --workers 6       # xóa đồ thị cũ rồi dựng lại
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from config import DATA_DIR, NEO4J_DATABASE, create_llm, create_neo4j_driver, get_embeddings
from legal_parser import Article, Clause, LegalDocument, clause_id, load_corpus
from legal_rules import DECREE_RULES, INDIVIDUAL, ORGANIZATION

EXTRACTOR_VERSION = "neo4j-v2"
ACTION_VECTOR_INDEX = "action_embedding"
ACTION_FULLTEXT_INDEX = "action_fulltext"
ARTICLE_FULLTEXT_INDEX = "article_fulltext"
DEFAULT_EMBEDDING_DIM = 3072

SUBJECT_CATEGORIES = {"INDIVIDUAL", "ORGANIZATION", "STATE_AGENCY", "ANY"}
CATEGORY_LABELS = {
    "INDIVIDUAL": "Cá nhân",
    "ORGANIZATION": "Tổ chức",
    "STATE_AGENCY": "Cơ quan nhà nước",
    "ANY": "Mọi cơ quan, tổ chức, cá nhân",
}

# Các Điều trọng tâm thường xuyên được truy vấn để ưu tiên nhúng Vector nhanh
PRIORITY_ARTICLES: dict[str, set[int]] = {
    "15/2020/NĐ-CP": {4, 83, 84, 99, 100, 101, 102, 103, 104, 105, 106},
    "24/2018/QH14": {8, 16, 17, 18, 19, 24, 26, 29},
    "67/2006/QH11": {9, 12, 16, 21, 70, 71, 72},
    "20/2023/QH15": {6, 8, 22},
    "24/2023/QH15": {9, 13},
    "60/2024/QH15": {10, 14},
    "100/2015/QH13": {12, 155, 156, 285, 286, 287, 288, 289, 290, 291, 292, 293, 294, 331},
}

_CONDITION_RE = re.compile(
    r"(nhưng chưa đến mức truy cứu trách nhiệm hình sự|"
    r"mà chưa đến mức truy cứu trách nhiệm hình sự|"
    r"trong trường hợp tái phạm hoặc vi phạm nhiều lần)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Pydantic schema cho đầu ra LLM (ép kiểu, loại bỏ rác)
# ---------------------------------------------------------------------------
class ExtractedSubject(BaseModel):
    name: str
    category: str = "ANY"

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, value: Any) -> str:
        value = str(value or "ANY").strip().upper()
        return value if value in SUBJECT_CATEGORIES else "ANY"


class ExtractedFine(BaseModel):
    min: int | None = None
    max: int | None = None


class ExtractedNorm(BaseModel):
    clause: int | None = None
    point: str | None = None
    name: str = Field(min_length=3)
    kind: Literal["VIOLATION", "PROHIBITED", "OBLIGATION", "RIGHT"] = "VIOLATION"
    subjects: list[ExtractedSubject] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    fine: ExtractedFine | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: Any) -> str:
        value = str(value or "VIOLATION").strip().upper()
        return value if value in {"VIOLATION", "PROHIBITED", "OBLIGATION", "RIGHT"} else "VIOLATION"

    @field_validator("point", mode="before")
    @classmethod
    def _point(cls, value: Any) -> str | None:
        if value in (None, "", "null"):
            return None
        return str(value).strip().strip(")").lower()[:1] or None

    @field_validator("clause", mode="before")
    @classmethod
    def _clause(cls, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class ArticleExtraction(BaseModel):
    norms: list[ExtractedNorm] = Field(default_factory=list)


EXTRACTION_PROMPT = """Bạn là chuyên gia pháp chế, trích xuất tri thức có cấu trúc từ MỘT Điều luật Việt Nam.
Văn bản: {doc_title}
{article_heading} (Chương {chapter})

Nội dung đã được tách sẵn theo Khoản/Điểm:
<article>
{structured_text}
</article>

Hãy liệt kê mọi QUY PHẠM (norm) trong Điều này. Mỗi quy phạm gắn với đúng một Khoản/Điểm:
- kind: VIOLATION (hành vi vi phạm bị xử phạt), PROHIBITED (hành vi bị nghiêm cấm),
        OBLIGATION (nghĩa vụ/trách nhiệm phải làm), RIGHT (quyền được làm).
- name: tên hành vi ngắn gọn, chuẩn hóa, tối đa 25 từ, giữ thuật ngữ pháp lý gốc.
- subjects: chủ thể thực hiện; category ∈ INDIVIDUAL | ORGANIZATION | STATE_AGENCY | ANY.
- conditions: điều kiện/tình tiết áp dụng nếu văn bản nêu rõ (vd: "chưa đến mức truy cứu trách nhiệm hình sự").
- fine: khung phạt tiền (số nguyên VNĐ) nếu Khoản quy định phạt tiền, ngược lại null.
- KHÔNG tạo quy phạm cho Khoản "Hình thức xử phạt bổ sung" và "Biện pháp khắc phục hậu quả".
- Điều chỉ định nghĩa/giải thích từ ngữ/phạm vi điều chỉnh -> trả về "norms": [].
- Chỉ dùng thông tin có trong văn bản, không suy diễn.

Chỉ trả về MỘT JSON object hợp lệ, không markdown:
{{"norms": [{{"clause": 1, "point": "a", "name": "...", "kind": "VIOLATION",
  "subjects": [{{"name": "...", "category": "ORGANIZATION"}}],
  "conditions": [], "fine": {{"min": 10000000, "max": 20000000}}}}]}}
"""


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------
def _key(*parts: str) -> str:
    raw = "\0".join(" ".join(str(p).casefold().split()) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _clean(text: str, limit: int = 600) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _parse_json(content: Any) -> dict:
    if isinstance(content, list):
        content = "\n".join(str(i.get("text", "")) if isinstance(i, dict) else str(i) for i in content)
    text = str(content or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Không tìm thấy JSON object trong phản hồi LLM")
    return json.loads(text[start : end + 1])


def _clause_kind(clause: Clause) -> str:
    head = clause.text[:70].casefold()
    if head.startswith("hình thức xử phạt bổ sung"):
        return "SUPPLEMENTARY"
    if head.startswith("biện pháp khắc phục hậu quả"):
        return "REMEDIAL"
    if clause.fine_min is not None or clause.warning:
        return "PENALTY"
    return "OTHER"


def _infer_norm_kind(article_title: str, clause_text: str, doc_type: str) -> str | None:
    if doc_type == "CRIMINAL_CODE":
        if re.search(r"phạt tiền|phạt cải tạo|phạt tù", clause_text, re.I):
            return "CRIME"
        return None
    combined = f"{article_title} {clause_text[:120]}".casefold()
    if any(skip in article_title.casefold() for skip in ("phạm vi điều chỉnh", "đối tượng áp dụng", "giải thích từ ngữ", "hiệu lực thi hành", "trách nhiệm thi hành")):
        return None
    if "nghiêm cấm" in combined or "bị cấm" in combined:
        return "PROHIBITED"
    if "quyền và nghĩa vụ" in combined or "trách nhiệm" in combined or "nghĩa vụ" in combined:
        return "OBLIGATION"
    if "quyền của" in combined or "được quyền" in combined:
        return "RIGHT"
    if any(kw in combined for kw in ("bảo vệ", "phòng ngừa", "xử lý", "quản lý", "an toàn", "an ninh mạng", "dữ liệu", "chữ ký điện tử", "hợp đồng điện tử")):
        return "OBLIGATION"
    return None


_SANCTION_REF = re.compile(
    r"((?:điểm\s+[a-zđ](?:\s*(?:,|và)\s*(?:điểm\s+)?[a-zđ](?![a-zà-ỹ]))*\s+)?"
    r"(?:các\s+)?khoản\s+\d+(?:\s*(?:,|và)\s*(?:khoản\s+)?\d+)*)\s+(?:của\s+)?Điều này",
    re.IGNORECASE,
)


def _sanction_targets(text: str) -> list[tuple[int, str | None]]:
    """'điểm b khoản 4 Điều này' -> [(4,'b')]; 'các khoản 1 và 2 Điều này' -> [(1,None),(2,None)]."""
    targets: list[tuple[int, str | None]] = []
    for match in _SANCTION_REF.finditer(text):
        fragment = match.group(1)
        clause_part = fragment[fragment.casefold().find("khoản") :]
        clauses = [int(n) for n in re.findall(r"\d+", clause_part)]
        letters = re.findall(
            r"điểm\s+([a-zđ])|(?:,|và)\s*([a-zđ])(?![a-zà-ỹ])",
            fragment[: fragment.casefold().find("khoản")],
            re.I,
        )
        letters = [a or b for a, b in letters]
        if letters and len(clauses) == 1:
            targets.extend((clauses[0], letter.lower()) for letter in letters)
        else:
            targets.extend((number, None) for number in clauses)
    return targets


def _fine_action_name(clause: Clause) -> str:
    match = re.search(r"đối với (?:hành vi |một trong các hành vi sau:?)?(.*)", clause.text, re.I)
    return _clean(match.group(1) if match else clause.text, 300).rstrip(".;:")


def _base_subject(doc_code: str, article_number: int) -> str | None:
    config = DECREE_RULES.get(doc_code)
    if not config:
        return None
    low, high = config["scope"]
    if not low <= article_number <= high:
        return None
    return INDIVIDUAL if article_number in config["individual_base_articles"] else config["base_subject"]


def _extract_conditions(text: str) -> list[dict[str, str]]:
    found = {m.group(1).strip().lower() for m in _CONDITION_RE.finditer(text or "")}
    return [{"key": _key(c), "name": c} for c in sorted(found)]


# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------
SCHEMA_QUERIES = [
    "CREATE CONSTRAINT legaldoc_code IF NOT EXISTS FOR (n:LegalDoc) REQUIRE n.code IS UNIQUE",
    "CREATE CONSTRAINT article_id IF NOT EXISTS FOR (n:Article) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT clause_id IF NOT EXISTS FOR (n:Clause) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT action_id IF NOT EXISTS FOR (n:Action) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT penalty_id IF NOT EXISTS FOR (n:Penalty) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT sanction_id IF NOT EXISTS FOR (n:Sanction) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT subject_key IF NOT EXISTS FOR (n:Subject) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT condition_key IF NOT EXISTS FOR (n:Condition) REQUIRE n.key IS UNIQUE",
    f"CREATE FULLTEXT INDEX {ACTION_FULLTEXT_INDEX} IF NOT EXISTS FOR (n:Action) ON EACH [n.name, n.text]",
    f"CREATE FULLTEXT INDEX {ARTICLE_FULLTEXT_INDEX} IF NOT EXISTS FOR (n:Article) ON EACH [n.title, n.text]",
    f"CREATE VECTOR INDEX {ACTION_VECTOR_INDEX} IF NOT EXISTS FOR (n:Action) ON (n.embedding) "
    f"OPTIONS {{indexConfig: {{`vector.dimensions`: {DEFAULT_EMBEDDING_DIM}, `vector.similarity_function`: 'cosine'}}}}",
]


def setup_schema(driver) -> None:
    with driver.session(database=NEO4J_DATABASE) as session:
        for query in SCHEMA_QUERIES:
            session.run(query).consume()
    print("[NEO4J] Đã tạo constraints + full-text index + vector index.")


def reset_graph(driver) -> None:
    with driver.session(database=NEO4J_DATABASE) as session:
        session.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 2000 ROWS").consume()
    print("[NEO4J] Đã xóa toàn bộ đồ thị cũ.")


def _write_skeleton(tx, document: LegalDocument, article: Article) -> dict[str, int]:
    tx.run(
        """
        MERGE (d:LegalDoc {code: $code})
        SET d.title = $title, d.short = $short, d.type = $type, d.sources = $sources
        MERGE (a:Article {id: $id})
        SET a.doc_code = $code, a.number = $number, a.title = $atitle, a.chapter = $chapter,
            a.text = $text, a.source = $source, a.page = $page, a.label = $label
        MERGE (a)-[:PART_OF]->(d)
        """,
        code=document.code,
        title=document.title,
        short=document.short,
        type=document.doc_type,
        sources=document.sources,
        id=article.id,
        number=article.number,
        atitle=article.title,
        chapter=article.chapter,
        text=article.text,
        source=article.source,
        page=article.page,
        label=f"Điều {article.number} {document.short}",
    )
    if article.references:
        tx.run(
            """
            MATCH (a:Article {id: $id})
            UNWIND $refs AS ref
            MATCH (b:Article {doc_code: $code, number: ref})
            MERGE (a)-[:REFERENCES]->(b)
            """,
            id=article.id,
            refs=article.references,
            code=document.code,
        )

    clauses, penalty_actions, law_actions, sanctions = [], [], [], []
    base_subject = _base_subject(document.code, article.number)
    for clause in article.clauses:
        cid = clause_id(document.code, article.number, clause.number)
        kind = _clause_kind(clause)
        clauses.append({
            "id": cid,
            "number": clause.number,
            "text": clause.text,
            "kind": kind,
            "fine_min": clause.fine_min,
            "fine_max": clause.fine_max,
            "warning": clause.warning,
            "label": f"Khoản {clause.number} Điều {article.number}",
        })
        if kind == "PENALTY":
            penalty_type = "FINE" if clause.fine_min is not None else "WARNING"
            penalty = {
                "id": f"{cid}:{penalty_type}",
                "type": penalty_type,
                "min": clause.fine_min,
                "max": clause.fine_max,
                "warning": clause.warning,
                "base_subject": base_subject,
            }
            clause_conds = _extract_conditions(clause.text)
            items = [(p.letter, p.text) for p in clause.points] or [("_", _fine_action_name(clause))]
            for letter, text in items:
                conds = clause_conds or _extract_conditions(text)
                penalty_actions.append({
                    "id": f"{cid}:{letter}",
                    "clause_id": cid,
                    "point": None if letter == "_" else letter,
                    "name": _clean(text, 300).rstrip(".;:"),
                    "text": text,
                    "penalty": penalty,
                    "conditions": conds,
                })
        elif kind in {"SUPPLEMENTARY", "REMEDIAL"}:
            items = [(p.letter, p.text) for p in clause.points] or [("_", clause.text)]
            for letter, text in items:
                description = re.sub(
                    r"^(Hình thức xử phạt bổ sung|Biện pháp khắc phục hậu quả)\s*:?\s*",
                    "",
                    text,
                    flags=re.I,
                )
                sanctions.append({
                    "id": f"{cid}:{letter}",
                    "type": kind,
                    "description": _clean(description, 500),
                    "targets": [
                        {"clause_id": clause_id(document.code, article.number, num), "point": pt}
                        for num, pt in _sanction_targets(text)
                    ],
                })
        elif document.doc_type in {"LAW", "CRIMINAL_CODE"}:
            norm_kind = _infer_norm_kind(article.title, clause.text, document.doc_type)
            if norm_kind:
                items = [(p.letter, p.text) for p in clause.points] or [("_", clause.text)]
                for letter, text in items:
                    clean_name = _clean(f"{article.title}: {text}" if letter == "_" and len(text) < 80 else text, 300).rstrip(".;:")
                    law_actions.append({
                        "id": f"{cid}:{letter}",
                        "clause_id": cid,
                        "point": None if letter == "_" else letter,
                        "name": clean_name,
                        "text": text,
                        "kind": norm_kind,
                        "conditions": _extract_conditions(text),
                    })

    tx.run(
        """
        MATCH (a:Article {id: $article_id})
        UNWIND $clauses AS c
        MERGE (k:Clause {id: c.id})
        SET k.number = c.number, k.text = c.text, k.kind = c.kind, k.fine_min = c.fine_min,
            k.fine_max = c.fine_max, k.warning = c.warning, k.label = c.label
        MERGE (k)-[:PART_OF]->(a)
        """,
        article_id=article.id,
        clauses=clauses,
    )
    if penalty_actions:
        tx.run(
            """
            UNWIND $actions AS x
            MATCH (k:Clause {id: x.clause_id})
            MERGE (act:Action {id: x.id})
            ON CREATE SET act.name = x.name, act.kind = 'VIOLATION', act.source = 'parser'
            SET act.text = x.text, act.point = x.point, act.article_id = $article_id
            MERGE (act)-[r:DEFINED_IN]->(k) SET r.point = x.point
            MERGE (p:Penalty {id: x.penalty.id})
            SET p.type = x.penalty.type, p.min_amount = x.penalty.min, p.max_amount = x.penalty.max,
                p.warning = x.penalty.warning, p.base_subject = x.penalty.base_subject
            MERGE (act)-[:PENALIZED_BY]->(p)
            FOREACH (c IN x.conditions |
                MERGE (cond:Condition {key: c.key}) ON CREATE SET cond.name = c.name
                MERGE (act)-[:HAS_CONDITION]->(cond)
            )
            WITH p, x WHERE x.penalty.base_subject IS NOT NULL
            MERGE (s:Subject {key: x.penalty.base_subject})
            ON CREATE SET s.name = CASE x.penalty.base_subject WHEN 'ORGANIZATION' THEN 'Tổ chức'
                                                               ELSE 'Cá nhân' END,
                          s.category = x.penalty.base_subject
            MERGE (p)-[:APPLIES_TO]->(s)
            """,
            actions=penalty_actions,
            article_id=article.id,
        )
    if law_actions:
        tx.run(
            """
            UNWIND $actions AS x
            MATCH (k:Clause {id: x.clause_id})
            MERGE (act:Action {id: x.id})
            ON CREATE SET act.name = x.name, act.kind = x.kind, act.source = 'parser'
            SET act.text = x.text, act.point = x.point, act.article_id = $article_id, act.kind = x.kind
            MERGE (act)-[r:DEFINED_IN]->(k) SET r.point = x.point
            FOREACH (c IN x.conditions |
                MERGE (cond:Condition {key: c.key}) ON CREATE SET cond.name = c.name
                MERGE (act)-[:HAS_CONDITION]->(cond)
            )
            """,
            actions=law_actions,
            article_id=article.id,
        )
    if sanctions:
        tx.run(
            """
            UNWIND $sanctions AS s
            MERGE (n:Sanction {id: s.id})
            SET n.type = s.type, n.description = s.description
            WITH n, s UNWIND s.targets AS t
            MATCH (act:Action)-[:DEFINED_IN]->(:Clause {id: t.clause_id})
            WHERE t.point IS NULL OR act.point = t.point
            MERGE (act)-[:HAS_SANCTION]->(n)
            """,
            sanctions=sanctions,
        )
    return {
        "clauses": len(clauses),
        "actions": len(penalty_actions) + len(law_actions),
        "sanctions": len(sanctions),
    }


def _write_llm(tx, document: LegalDocument, article: Article, extraction: ArticleExtraction) -> dict:
    parsed = {c.number: c for c in article.clauses}
    stats = {"norms": 0, "fine_checked": 0, "fine_mismatch": 0}
    rows = []
    used_ids: set[str] = set()
    for index, norm in enumerate(extraction.norms):
        clause = parsed.get(norm.clause) if norm.clause else None
        if clause and _clause_kind(clause) in {"SUPPLEMENTARY", "REMEDIAL"}:
            continue
        if clause:
            cid = clause_id(document.code, article.number, clause.number)
            point_letters = {p.letter for p in clause.points}
            letter = norm.point if norm.point in point_letters else "_"
            action_id = f"{cid}:{letter}" if (letter != "_" or not clause.points) else f"{cid}:llm{index}"
            if action_id in used_ids:
                action_id = f"{cid}:llm{index}"
        else:
            cid, letter, action_id = None, None, f"{article.id}:llm{index}"
        used_ids.add(action_id)

        # Kiểm chứng Symbolic: so khung phạt LLM với regex (regex là ground truth)
        if clause and clause.fine_min is not None and norm.fine and norm.fine.min is not None:
            stats["fine_checked"] += 1
            if (norm.fine.min, norm.fine.max) != (clause.fine_min, clause.fine_max):
                stats["fine_mismatch"] += 1

        rows.append({
            "id": action_id,
            "clause_id": cid,
            "point": letter if letter not in (None, "_") else None,
            "name": _clean(norm.name, 300),
            "kind": norm.kind,
            "subjects": [
                {"key": f"{s.category}:{_key(s.name)}", "name": _clean(s.name, 150), "category": s.category}
                for s in norm.subjects
                if s.name.strip()
            ],
            "conditions": [{"key": _key(c), "name": _clean(c, 300)} for c in norm.conditions if c.strip()],
            "fine_min": norm.fine.min if norm.fine else None,
            "fine_max": norm.fine.max if norm.fine else None,
        })
    stats["norms"] = len(rows)

    tx.run(
        """
        UNWIND $rows AS r
        MERGE (act:Action {id: r.id})
        SET act.name = r.name, act.kind = r.kind, act.article_id = $article_id,
            act.source = CASE WHEN act.source = 'parser' THEN 'parser+llm' ELSE coalesce(act.source, 'llm') END,
            act.text = coalesce(act.text, r.name), act.point = coalesce(act.point, r.point),
            act.llm_fine_min = r.fine_min, act.llm_fine_max = r.fine_max
        WITH act, r
        CALL (act, r) {
            MATCH (k:Clause {id: r.clause_id})
            MERGE (act)-[:DEFINED_IN]->(k)
        }
        CALL (act, r) {
            MATCH (a:Article {id: $article_id}) WHERE r.clause_id IS NULL
            MERGE (act)-[:DEFINED_IN]->(a)
        }
        CALL (act, r) {
            UNWIND r.subjects AS s
            MERGE (sub:Subject {key: s.key}) ON CREATE SET sub.name = s.name, sub.category = s.category
            MERGE (act)-[:COMMITTED_BY]->(sub)
        }
        CALL (act, r) {
            UNWIND r.conditions AS c
            MERGE (cond:Condition {key: c.key}) ON CREATE SET cond.name = c.name
            MERGE (act)-[:HAS_CONDITION]->(cond)
        }
        """,
        rows=rows,
        article_id=article.id,
    )
    tx.run(
        """
        MATCH (a:Article {id: $id})
        SET a.llm_done = true, a.llm_version = $version, a.llm_at = $at,
            a.llm_fine_checked = $checked, a.llm_fine_mismatch = $mismatch
        """,
        id=article.id,
        version=EXTRACTOR_VERSION,
        at=datetime.now(timezone.utc).isoformat(),
        checked=stats["fine_checked"],
        mismatch=stats["fine_mismatch"],
    )
    return stats


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
def _structured_text(article: Article) -> str:
    if not article.clauses:
        return _clean(article.text, 6000)
    lines = []
    for clause in article.clauses:
        if clause.points:
            intro = clause.text.split(" a) ")[0]
            lines.append(f"Khoản {clause.number}: {_clean(intro, 800)}")
            lines.extend(f"   Điểm {p.letter}) {_clean(p.text, 800)}" for p in clause.points)
        else:
            lines.append(f"Khoản {clause.number}: {_clean(clause.text, 1200)}")
    return "\n".join(lines)


def extract_article(llm, document: LegalDocument, article: Article) -> ArticleExtraction:
    prompt = EXTRACTION_PROMPT.format(
        doc_title=document.title,
        article_heading=article.heading(),
        chapter=article.chapter or "-",
        structured_text=_structured_text(article),
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = llm.invoke(prompt)
            return ArticleExtraction.model_validate(_parse_json(response.content))
        except (ValueError, ValidationError) as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{type(last_error).__name__}: {last_error}")


def _articles_done(driver) -> set[str]:
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(
            "MATCH (a:Article) WHERE a.llm_version = $v RETURN a.id AS id", v=EXTRACTOR_VERSION
        )
        return {record["id"] for record in result}


def run_llm_enrichment(
    driver, documents: list[LegalDocument], workers: int, force: bool, limit: int | None
):
    done = set() if force else _articles_done(driver)
    jobs = [(d, a) for d in documents for a in d.articles if a.id not in done]
    if limit:
        jobs = jobs[:limit]
    if not jobs:
        print("[LLM] Tất cả Điều đã được trích xuất (dùng --force để chạy lại).")
        return
    print(f"[LLM] Trích xuất {len(jobs)} Điều với {workers} luồng song song...")
    llm = create_llm(temperature=0)
    totals = {"norms": 0, "fine_checked": 0, "fine_mismatch": 0, "failed": 0}

    with ThreadPoolExecutor(max_workers=workers) as pool, driver.session(database=NEO4J_DATABASE) as session:
        futures = {pool.submit(extract_article, llm, d, a): (d, a) for d, a in jobs}
        for index, future in enumerate(as_completed(futures), start=1):
            document, article = futures[future]
            try:
                extraction = future.result()
                stats = session.execute_write(_write_llm, document, article, extraction)
                for key in ("norms", "fine_checked", "fine_mismatch"):
                    totals[key] += stats[key]
                print(
                    f"  [{index}/{len(jobs)}] {article.id}: {stats['norms']} quy phạm"
                    + (
                        f", lệch khung phạt {stats['fine_mismatch']}/{stats['fine_checked']}"
                        if stats["fine_checked"]
                        else ""
                    )
                )
            except Exception as exc:
                totals["failed"] += 1
                print(f"  [{index}/{len(jobs)}] {article.id}: LỖI {exc}")

    checked = totals["fine_checked"] or 1
    print("\n[LLM] Tổng kết trích xuất:")
    print(f"  Quy phạm được MERGE      : {totals['norms']}")
    print(f"  Điều lỗi                 : {totals['failed']}")
    print(
        f"  Độ khớp khung phạt LLM   : {100 * (1 - totals['fine_mismatch'] / checked):.1f}% "
        f"({totals['fine_checked'] - totals['fine_mismatch']}/{totals['fine_checked']}) - regex được ưu tiên"
    )


# ---------------------------------------------------------------------------
# Embedding hành vi -> Vector Index trong Neo4j
# ---------------------------------------------------------------------------
def embed_actions(driver, batch_size: int = 80, priority_only: bool = False) -> None:
    priority_ids: list[str] = [
        f"{doc_code}:Điều {art_num}"
        for doc_code, nums in PRIORITY_ARTICLES.items()
        for art_num in nums
    ]
    with driver.session(database=NEO4J_DATABASE) as session:
        if priority_only:
            rows = session.run(
                """
                MATCH (act:Action)
                WHERE act.embedding IS NULL AND act.article_id IN $priority_ids
                OPTIONAL MATCH (act)-[:DEFINED_IN]->(:Clause)-[:PART_OF]->(a:Article)
                RETURN act.id AS id, act.name AS name, act.text AS text, a.title AS article
                """,
                priority_ids=priority_ids,
            ).data()
        else:
            rows = session.run(
                """
                MATCH (act:Action) WHERE act.embedding IS NULL
                OPTIONAL MATCH (act)-[:DEFINED_IN]->(:Clause)-[:PART_OF]->(a:Article)
                RETURN act.id AS id, act.name AS name, act.text AS text, a.title AS article
                """
            ).data()

    if not rows:
        print("[EMBED] Mọi hành vi mục tiêu đã có embedding.")
        return

    embeddings = get_embeddings()
    print(f"[EMBED] Nhúng {len(rows)} hành vi bằng Gemini ({embeddings.model})...")
    dimensions = DEFAULT_EMBEDDING_DIM
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        texts = [
            f"{r['name']}. {r['text'] if r['text'] and r['text'] != r['name'] else ''} ({r['article'] or ''})"
            for r in batch
        ]
        for attempt in range(6):
            try:
                vectors = embeddings.embed_documents(texts)
                break
            except Exception as exc:
                message = str(exc).upper()
                if ("429" in message or "RESOURCE_EXHAUSTED" in message) and attempt < 5:
                    if "PERDAY" in message:
                        print("[EMBED] Hết quota Gemini theo ngày - dừng, chạy lại sau sẽ tiếp tục.")
                        return
                    print("[EMBED] Bị giới hạn tốc độ, chờ 60 giây...")
                    time.sleep(60)
                    continue
                raise
        dimensions = len(vectors[0])
        with driver.session(database=NEO4J_DATABASE) as session:
            session.run(
                """
                UNWIND $items AS item
                MATCH (act:Action {id: item.id})
                CALL db.create.setNodeVectorProperty(act, 'embedding', item.vector)
                """,
                items=[{"id": r["id"], "vector": v} for r, v in zip(batch, vectors)],
            ).consume()
        print(f"  {min(start + batch_size, len(rows))}/{len(rows)}")

    with driver.session(database=NEO4J_DATABASE) as session:
        session.run(
            f"""
            CREATE VECTOR INDEX {ACTION_VECTOR_INDEX} IF NOT EXISTS
            FOR (n:Action) ON (n.embedding)
            OPTIONS {{indexConfig: {{`vector.dimensions`: {int(dimensions)}, `vector.similarity_function`: 'cosine'}}}}
            """
        ).consume()
    print(f"[EMBED] Đã cập nhật Vector Index '{ACTION_VECTOR_INDEX}' ({dimensions} chiều).")


def print_stats(driver) -> None:
    with driver.session(database=NEO4J_DATABASE) as session:
        nodes = session.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC"
        ).data()
        rels = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY n DESC"
        ).data()
    print("\n[THỐNG KÊ ĐỒ THỊ]")
    print("  Node: " + ", ".join(f"{r['label']}={r['n']}" for r in nodes))
    print("  Cạnh: " + ", ".join(f"{r['type']}={r['n']}" for r in rels))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    parser = argparse.ArgumentParser(description="Xây dựng đồ thị tri thức Luật CNTT trên Neo4j")
    parser.add_argument("--reset", action="store_true", help="Xóa toàn bộ đồ thị trước khi nạp")
    parser.add_argument("--no-llm", action="store_true", help="Chỉ dựng khung xương tất định")
    parser.add_argument("--skip-embeddings", action="store_true", help="Không nhúng hành vi")
    parser.add_argument("--priority-only", action="store_true", help="Chỉ nhúng Vector cho các Điều trọng tâm")
    parser.add_argument("--force", action="store_true", help="Trích xuất LLM lại cả các Điều đã xong")
    parser.add_argument("--workers", type=int, default=4, help="Số luồng gọi LLM song song")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số Điều gửi LLM (thử nghiệm)")
    args = parser.parse_args()

    documents = load_corpus(DATA_DIR)
    driver = create_neo4j_driver()
    try:
        driver.verify_connectivity()
    except Exception as exc:
        print(f"[DỪNG] Không kết nối được Neo4j ({exc}). Chạy: docker compose up -d neo4j")
        return 1

    try:
        if args.reset:
            reset_graph(driver)
        setup_schema(driver)

        totals = {"clauses": 0, "actions": 0, "sanctions": 0}
        with driver.session(database=NEO4J_DATABASE) as session:
            for document in documents:
                for article in document.articles:
                    stats = session.execute_write(_write_skeleton, document, article)
                    for key in totals:
                        totals[key] += stats[key]
        print(
            f"[SKELETON] {sum(len(d.articles) for d in documents)} Điều, {totals['clauses']} Khoản, "
            f"{totals['actions']} hành vi/quy phạm, {totals['sanctions']} biện pháp bổ sung/khắc phục."
        )

        if not args.no_llm:
            run_llm_enrichment(driver, documents, args.workers, args.force, args.limit)
        if not args.skip_embeddings:
            embed_actions(driver, priority_only=args.priority_only)
        print_stats(driver)
        return 0
    except Exception as exc:
        print(f"[DỪNG] {type(exc).__name__}: {exc}")
        return 1
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
