"""Backend API FastAPI - Hợp nhất Neuro-Symbolic AI cho Trợ lý ảo Luật CNTT.

Kiến trúc Hybrid Retrieval:
1. Luồng Neural   : Tìm kiếm vector tương đồng ngữ nghĩa từ PostgreSQL (pgvector).
2. Luồng Symbolic :
   - Phân tích câu hỏi (analyze_question): nhận diện chủ thể (cá nhân/tổ chức), độ tuổi, số hiệu Điều, tên Luật.
   - Tra cứu Đồ thị tri thức (Neo4j) 4 tầng: Số hiệu Điều + Vector Index ('action_embedding')
     + Full-text Index ('action_fulltext') + Cầu nối Neural->Symbolic ('article_id').
   - Bộ suy luận tất định (apply_penalty_rules): tính toán chính xác khung phạt theo Điều 4 NĐ 15/2020,
     kiểm tra trần lĩnh vực, điều kiện độ tuổi theo luật (không để LLM tự tính nhầm).
3. Hợp nhất (Fusion) & Sinh câu trả lời:
   - DeepSeek/OpenRouter tổng hợp câu trả lời dựa trên cả 2 nguồn tri thức.
   - Đồng thời sinh phản hồi Naive RAG (chỉ dùng vector) để so sánh đối chứng A/B trực quan.
   - Trả về cấu trúc đồ thị (nodes, edges) và dấu vết suy luận (rule steps) cho Frontend.
"""

from __future__ import annotations

import re
import sys
import warnings
from typing import Any

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*LangChainPendingDeprecationWarning.*")
warnings.filterwarnings("ignore", message=".*This class is pending deprecation.*")
warnings.filterwarnings("ignore", message=".*Please use JSONB instead of JSON.*")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_community.vectorstores import PGVector

from config import (
    DATABASE_URL,
    COLLECTION_NAME,
    NEO4J_DATABASE,
    create_llm,
    create_neo4j_driver,
    get_embeddings,
)
from legal_rules import (
    analyze_question,
    apply_penalty_rules,
    QueryFacts,
)

CONNECTION_STRING = DATABASE_URL

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = FastAPI(
    title="IT Law Neuro-Symbolic Assistant API",
    description="Hệ thống tư vấn pháp luật CNTT kết hợp Vector Search (Neural) và Knowledge Graph + Rule Engine (Symbolic)",
    version="2.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Khởi tạo Drivers & Models
# ---------------------------------------------------------------------------
neo4j_driver = create_neo4j_driver()
embeddings = get_embeddings()
llm = create_llm(temperature=0.1)

try:
    vector_db = PGVector(
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
        embedding_function=embeddings,
    )
except Exception as e:
    print(f"[CẢNH BÁO] Không thể kết nối ngay với PGVector: {e}")
    vector_db = None


class HistoryItem(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    question: str
    comparison_mode: bool = True
    history: list[HistoryItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Các hàm truy vấn Đồ thị Tri thức (Symbolic Graph Retrieval)
# ---------------------------------------------------------------------------
def _sanitize_fulltext_query(text: str) -> str:
    """Lọc các ký tự đặc biệt của cú pháp Lucene và loại bỏ stopwords pháp lý để tìm hành vi thực tế."""
    cleaned = re.sub(r"[^\w\s\dà-ỹÀ-Ỹ]", " ", text)
    words = [w.strip() for w in cleaned.split() if len(w.strip()) > 1]

    legal_stop_words = {
        "là", "gì", "thế", "nào", "cho", "tôi", "hỏi", "bị", "phạt", "bao", "nhiêu", "tiền",
        "nghị", "định", "luật", "thông", "tư", "điều", "khoản", "điểm", "bộ", "số", "của", "và", "theo",
        "về", "có", "không", "như", "được", "tại", "trong", "quy", "với", "hành", "vi", "mức",
    }
    keywords = [w for w in words if w.lower() not in legal_stop_words and not w.isdigit()]
    if not keywords:
        return ""
    return " OR ".join(f'"{kw}"' for kw in keywords[:8])


# Đoạn Cypher dùng chung để bung thông tin từ node (:Action) ra Văn bản, Điều, Khoản, Mức phạt, Biện pháp khắc phục
_ACTION_EXPAND_CYPHER = """
MATCH (act)-[:DEFINED_IN]->(parent)
OPTIONAL MATCH (parent:Clause)-[:PART_OF]->(a_clause:Article)
WITH act, score,
     CASE WHEN parent:Clause THEN parent ELSE NULL END AS k,
     CASE WHEN parent:Article THEN parent ELSE a_clause END AS a
WHERE a IS NOT NULL
MATCH (a)-[:PART_OF]->(doc:LegalDoc)
OPTIONAL MATCH (act)-[:PENALIZED_BY]->(p:Penalty)
OPTIONAL MATCH (act)-[:HAS_SANCTION]->(s:Sanction)
OPTIONAL MATCH (act)-[:HAS_CONDITION]->(cond:Condition)
OPTIONAL MATCH (a)-[:REFERENCES]->(ref_art:Article)
RETURN doc.code AS doc_code, doc.short AS doc_short,
       a.id AS article_id, a.number AS article_number, a.title AS article_title,
       k.number AS clause_number, k.text AS clause_text,
       act.id AS action_id, act.name AS action_name, act.kind AS action_kind, act.point AS point,
       p.type AS penalty_type, p.min_amount AS min_amount, p.max_amount AS max_amount,
       p.warning AS warning, p.base_subject AS base_subject,
       collect(DISTINCT s.description) AS sanctions,
       collect(DISTINCT cond.name) AS conditions,
       collect(DISTINCT ref_art.number) AS ref_articles,
       score
ORDER BY score DESC
"""


def query_knowledge_graph(
    facts: QueryFacts,
    raw_question: str,
    neural_article_ids: list[str] | None = None,
    query_vector: list[float] | None = None,
) -> dict[str, Any]:
    """Truy vấn đồ thị Neo4j 4 tầng: Số Điều + Vector Index + Full-text + Cầu nối PGVector."""
    if facts.invalid_docs:
        return {
            "matched_actions": [],
            "penalty_calculations": [],
            "rule_steps": [{
                "rule": "INVALID_DOCUMENT_GUARDRAIL",
                "basis": "Hệ thống văn bản QPPL Việt Nam",
                "detail": f"Văn bản '{', '.join(facts.invalid_docs)}' không tồn tại trong hệ thống pháp luật.",
            }],
            "graph_view": {"nodes": [], "edges": []},
        }

    matched_actions = []
    graph_nodes = []
    graph_edges = []
    seen_node_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(node_id: str, label: str, node_type: str, data: dict):
        if node_id not in seen_node_ids:
            seen_node_ids.add(node_id)
            graph_nodes.append({
                "id": node_id,
                "label": label,
                "type": node_type,
                "data": data,
            })

    def add_edge(source: str, target: str, rel_type: str):
        edge_key = (source, target, rel_type)
        if edge_key not in seen_edges:
            seen_edges.add(edge_key)
            graph_edges.append({
                "source": source,
                "target": target,
                "label": rel_type,
            })

    results: list[dict[str, Any]] = []
    seen_action_ids: set[str] = set()

    def merge_rows(new_rows: list[dict[str, Any]]):
        for r in new_rows:
            aid = r.get("action_id")
            if aid and aid not in seen_action_ids:
                seen_action_ids.add(aid)
                results.append(r)

    with neo4j_driver.session(database=NEO4J_DATABASE) as session:
        # Tầng 1: Người dùng chỉ định rõ số Điều (VD: "Điều 101...", "Điều 8 Luật An ninh mạng...")
        if facts.article_refs:
            cypher_art = (
                """
                MATCH (a:Article)-[:PART_OF]->(d:LegalDoc)
                WHERE a.number IN $article_refs
                  AND ($doc_hints = [] OR d.code IN $doc_hints)
                MATCH (act:Action)-[:DEFINED_IN]->(parent)
                WHERE parent = a OR (parent:Clause AND (parent)-[:PART_OF]->(a))
                WITH act, 1.0 AS score
                """
                + _ACTION_EXPAND_CYPHER
                + " LIMIT 10"
            )
            try:
                rows_art = session.run(
                    cypher_art,
                    article_refs=facts.article_refs,
                    doc_hints=facts.doc_hints,
                ).data()
                if not rows_art and facts.doc_hints:
                    rows_art = session.run(
                        cypher_art,
                        article_refs=facts.article_refs,
                        doc_hints=[],
                    ).data()
                merge_rows(rows_art)
            except Exception as e:
                print(f"[LỖI Neo4j Article Lookup]: {e}")

        # Tầng 2: Tìm kiếm Vector ngữ nghĩa trực tiếp trên node (:Action)
        if len(results) < 5 and query_vector:
            cypher_vec = (
                """
                CALL db.index.vector.queryNodes('action_embedding', 6, $embedding)
                YIELD node AS act, score
                WHERE score >= 0.62
                """
                + _ACTION_EXPAND_CYPHER
                + " LIMIT 5"
            )
            try:
                merge_rows(session.run(cypher_vec, embedding=query_vector).data())
            except Exception as e:
                print(f"[THÔNG BÁO Vector Index Neo4j]: {e}")

        # Tầng 3: Tìm kiếm từ khóa bằng Full-text Index ('action_fulltext')
        if len(results) < 5:
            ft_query = _sanitize_fulltext_query(raw_question)
            if ft_query:
                cypher_ft = (
                    """
                    CALL db.index.fulltext.queryNodes('action_fulltext', $query_text)
                    YIELD node AS act, score
                    """
                    + _ACTION_EXPAND_CYPHER
                    + " LIMIT 5"
                )
                try:
                    merge_rows(session.run(cypher_ft, query_text=ft_query).data())
                except Exception as e:
                    print(f"[LỖI Fulltext Neo4j]: {e}")

        # Tầng 4: Cầu nối Neural -> Symbolic (nhảy từ article_id của PGVector sang Neo4j)
        if not results and neural_article_ids:
            cypher_bridge = (
                """
                MATCH (a:Article) WHERE a.id IN $article_ids
                MATCH (act:Action)-[:DEFINED_IN]->(parent)
                WHERE parent = a OR (parent:Clause AND (parent)-[:PART_OF]->(a))
                WITH act, 0.5 AS score
                """
                + _ACTION_EXPAND_CYPHER
                + " LIMIT 6"
            )
            try:
                merge_rows(session.run(cypher_bridge, article_ids=neural_article_ids).data())
            except Exception as e:
                print(f"[LỖI Bridge PGVector -> Neo4j]: {e}")

        # Xây dựng cấu trúc trực quan cho đồ thị và tính toán khung phạt
        penalty_calcs = []
        rule_steps = []

        for row in results[:8]:
            doc_code = row["doc_code"]
            art_num = row["article_number"]
            clause_num = row.get("clause_number")
            doc_node_id = f"doc:{doc_code}"
            art_node_id = f"art:{row['article_id']}"
            act_node_id = f"act:{row['action_id']}"

            add_node(doc_node_id, row["doc_short"], "LegalDoc", {"code": doc_code})
            add_node(art_node_id, f"Điều {art_num}", "Article", {"title": row["article_title"]})
            add_edge(art_node_id, doc_node_id, "PART_OF")

            prefix = f"K.{clause_num}" if clause_num else f"Đ.{art_num}"
            if row.get("point"):
                prefix += f".{row['point']}"
            action_label = f"{prefix}: {row['action_name'][:35]}..."
            add_node(act_node_id, action_label, "Action", {"full_name": row["action_name"]})
            add_edge(act_node_id, art_node_id, "DEFINED_IN")

            clean_sanctions = [s for s in (row.get("sanctions") or []) if s]
            clean_conditions = [c for c in (row.get("conditions") or []) if c]
            ref_articles = sorted([r for r in (row.get("ref_articles") or []) if r])

            penalty_info = {
                "type": row.get("penalty_type") or "FINE",
                "min_amount": row.get("min_amount"),
                "max_amount": row.get("max_amount"),
                "base_subject": row.get("base_subject"),
            }

            # Áp dụng bộ suy luận luật cứng (Deterministic Rule Engine)
            calc = apply_penalty_rules(penalty_info, doc_code, art_num, facts)
            clause_str = (
                f"Khoản {clause_num}" + (f" Điểm {row['point']}" if row.get("point") else "")
                if clause_num
                else "Quy định chung tại Điều"
            )

            if calc["results"]:
                penalty_calcs.append({
                    "action": row["action_name"],
                    "article": f"Điều {art_num} ({row['doc_short']})",
                    "clause": clause_str,
                    "calculations": calc["results"],
                    "sanctions": clean_sanctions,
                    "conditions": clean_conditions,
                    "ref_articles": ref_articles,
                })
                rule_steps.extend(calc["steps"])

                pen_node_id = f"pen:{row['action_id']}"
                pen_label = "Phạt: " + " | ".join(
                    f"{r['subject_label']}: {r['display']}" for r in calc["results"] if r["applicable"]
                )
                if not any(r["applicable"] for r in calc["results"]):
                    pen_label = calc["results"][0]["display"]
                add_node(pen_node_id, pen_label[:65], "Penalty", {"calc": calc["results"]})
                add_edge(act_node_id, pen_node_id, "PENALIZED_BY")

            # Bổ sung Node Biện pháp khắc phục / Hình thức phạt bổ sung lên đồ thị
            if clean_sanctions:
                sanc_node_id = f"sanc:{row['action_id']}"
                add_node(
                    sanc_node_id,
                    f"Khắc phục: {clean_sanctions[0][:38]}...",
                    "Sanction",
                    {"items": clean_sanctions},
                )
                add_edge(act_node_id, sanc_node_id, "HAS_SANCTION")

            matched_actions.append({
                "doc_code": doc_code,
                "doc_title": row["doc_short"],
                "article_number": art_num,
                "article_title": row["article_title"],
                "clause_number": clause_num,
                "point": row.get("point"),
                "action_name": row["action_name"],
                "action_kind": row.get("action_kind") or "VIOLATION",
                "min_amount": row.get("min_amount"),
                "max_amount": row.get("max_amount"),
                "sanctions": clean_sanctions,
                "conditions": clean_conditions,
                "ref_articles": ref_articles,
            })

    # Loại bỏ các bước suy luận trùng lặp
    unique_steps = []
    seen_step_keys = set()
    for s in rule_steps:
        key = (s["rule"], s["detail"])
        if key not in seen_step_keys:
            seen_step_keys.add(key)
            unique_steps.append(s)

    return {
        "matched_actions": matched_actions,
        "penalty_calculations": penalty_calcs,
        "rule_steps": unique_steps,
        "graph_view": {
            "nodes": graph_nodes,
            "edges": graph_edges,
        },
    }


# ---------------------------------------------------------------------------
# Prompt Templates cho Neuro-Symbolic vs Naive RAG
# ---------------------------------------------------------------------------
NEURO_SYMBOLIC_PROMPT = """
Bạn là Trợ lý ảo tư vấn Luật Công nghệ thông tin và An toàn mạng Việt Nam, ứng dụng kiến trúc Neuro-Symbolic AI.
Nhiệm vụ của bạn là đưa ra lời tư vấn pháp lý CHÍNH XÁC, RÕ RÀNG, ĐẦY ĐỦ CĂN CỨ theo đúng thông tin được cung cấp.

=== [1. KẾT QUẢ SUY LUẬN LOGIC TẤT ĐỊNH (SYMBOLIC ENGINE - GROUND TRUTH BẮT BUỘC TUÂN THỦ)] ===
{symbolic_facts}

=== [2. TRÍCH ĐOẠN VĂN BẢN QUY PHẠM PHÁP LUẬT (NEURAL VECTOR RETRIEVAL)] ===
{neural_context}

=== CÂU HỎI CỦA NGƯỜI DÙNG ===
{question}

=== YÊU CẦU TRẢ LỜI ===
1. Khẳng định rõ hành vi có vi phạm không (hoặc bị nghiêm cấm/có nghĩa vụ gì), căn cứ vào Điểm, Khoản, Điều, Văn bản nào.
2. NÊU CHÍNH XÁC mức phạt tiền cho từng chủ thể (Tổ chức vs Cá nhân) theo đúng kết quả tính toán ở Mục [1].
   Khi trình bày mức phạt theo chủ thể, BẮT BUỘC ghi số tiền phạt ngay sau tên chủ thể trên từng dòng riêng biệt theo mẫu:
   - **Đối với Tổ chức (Công ty/Doanh nghiệp)**: Phạt tiền từ **[mức tối thiểu] đồng đến [mức tối đa] đồng** (mức phạt gốc theo quy định).
   - **Đối với Cá nhân (Nhân viên/Người dùng)**: Phạt tiền từ **[mức tối thiểu] đồng đến [mức tối đa] đồng** (bằng 1/2 mức phạt của tổ chức theo Điều 4 Khoản 3 Nghị định 15/2020/NĐ-CP).
3. Nếu Mục [1] hoặc Mục [2] có tình tiết độ tuổi (dưới 14 tuổi, từ đủ 14 đến dưới 16 tuổi, từ đủ 16 đến dưới 18 tuổi), hoặc ngoại lệ Điều 106 (áp dụng trực tiếp cho cá nhân/người chơi), hoặc hình thức xử phạt bổ sung / biện pháp khắc phục hậu quả (buộc gỡ bỏ thông tin sai sự thật, thu hồi tên miền...), BẮT BUỘC phải nêu đầy đủ.
4. Giọng điệu chuyên nghiệp, khách quan, trình bày bằng gạch đầu dòng rõ ràng, dễ hiểu cho người dân và doanh nghiệp.
5. NGUYÊN TẮC BẢO VỆ CHỐNG ẢO GIÁC (ANTI-HALLUCINATION GUARDRAIL):
   - Tuyệt đối KHÔNG tự bịa ra thông tin, mức tiền phạt hoặc số hiệu văn bản pháp luật.
   - Nếu câu hỏi đề cập đến một văn bản, nghị định hoặc luật KHÔNG TỒN TẠI hoặc ngoài phạm vi, bạn PHẢI NÊU RÕ RÀNG rằng văn bản đó không tồn tại hoặc không nằm trong phạm vi cơ sở dữ liệu.
"""

NAIVE_RAG_PROMPT = """
Bạn là một trợ lý AI tư vấn luật. Dựa vào các đoạn văn bản trích dẫn sau đây, hãy trả lời câu hỏi của người dùng.
Không tự bịa ra thông tin.

Văn bản trích dẫn:
{neural_context}

Câu hỏi:
{question}

Trả lời:
"""

prompt_neuro_symbolic = PromptTemplate(
    template=NEURO_SYMBOLIC_PROMPT,
    input_variables=["symbolic_facts", "neural_context", "question"],
)
prompt_naive = PromptTemplate(
    template=NAIVE_RAG_PROMPT,
    input_variables=["neural_context", "question"],
)


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    neo4j_ok = False
    try:
        neo4j_driver.verify_connectivity()
        neo4j_ok = True
    except Exception:
        pass

    return {
        "status": "healthy",
        "neo4j_connected": neo4j_ok,
        "pgvector_ready": vector_db is not None,
    }


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Câu hỏi không được để trống.")

    # Nếu có lịch sử hội thoại, ghép ngữ cảnh câu trước để hỗ trợ hỏi nối tiếp (Multi-turn)
    contextual_question = question
    if request.history:
        recent_turns = [f"{h.role}: {h.text[:200]}" for h in request.history[-2:]]
        contextual_question = f"Ngữ cảnh trước: {' | '.join(recent_turns)}\nCâu hỏi hiện tại: {question}"

    # 1. Bóc tách ý định & Thực thể (Symbolic NLU)
    facts = analyze_question(question)

    # GUARDRAIL 1: Phát hiện văn bản KHÔNG TỒN TẠI (ví dụ: Nghị định 9999/2025/NĐ-CP)
    if facts.invalid_docs:
        invalid_name = ", ".join(facts.invalid_docs)
        guardrail_answer = (
            f"⚠️ **CẢNH BÁO CĂN CỨ PHÁP LÝ: VĂN BẢN KHÔNG TỒN TẠI**\n\n"
            f"Trong hệ thống văn bản quy phạm pháp luật Việt Nam **hoàn toàn không tồn tại '{invalid_name}'** "
            f"(văn bản này không có thực).\n\n"
            f"**Căn cứ pháp luật:**\n"
            f"- Theo Luật Ban hành văn bản quy phạm pháp luật, Nghị định của Chính phủ được đánh số thứ tự trong từng năm "
            f"theo định dạng `[Số thứ tự]/[Năm ban hành]/NĐ-CP` (ví dụ: *Nghị định số 15/2020/NĐ-CP*).\n"
            f"- Số lượng nghị định ban hành mỗi năm thường dưới 200 nghị định, số hiệu **{invalid_name}** là không có thực.\n\n"
            f"**Phạm vi dữ liệu của Trợ lý ảo:**\n"
            f"Hệ thống chuyên sâu về **Pháp luật Công nghệ thông tin, Viễn thông & An toàn thông tin mạng**, hiện gồm:\n"
            f"1. **Nghị định số 15/2020/NĐ-CP** (Xử phạt vi phạm hành chính bưu chính, viễn thông, CNTT, mạng xã hội).\n"
            f"2. **Luật An ninh mạng 2018** (Luật số 24/2018/QH14).\n"
            f"3. **Luật Công nghệ thông tin 2006** (Luật số 67/2006/QH11).\n"
            f"4. **Luật Giao dịch điện tử 2023** (20/2023/QH15), **Luật Viễn thông 2023** (24/2023/QH15), **Luật Dữ liệu 2024** (60/2024/QH15).\n"
            f"5. **Bộ luật Hình sự 2015** (Nhóm tội phạm trong lĩnh vực CNTT, mạng viễn thông).\n\n"
            f"👉 *Vui lòng kiểm tra lại số hiệu văn bản hoặc mô tả rõ hành vi vi phạm cụ thể để tôi tra cứu giúp bạn.*"
        )
        return {
            "answer": guardrail_answer,
            "naive_answer": guardrail_answer if request.comparison_mode else None,
            "symbolic_reasoning": {
                "facts": facts.to_dict(),
                "matched_actions": [],
                "penalty_calculations": [],
                "rule_steps": [{
                    "rule": "INVALID_DOCUMENT_GUARDRAIL",
                    "basis": "Luật Ban hành văn bản QPPL",
                    "detail": f"Chặn xử lý vì văn bản '{invalid_name}' không tồn tại trong hệ thống pháp luật.",
                }],
            },
            "graph_view": {"nodes": [], "edges": []},
            "sources": [],
        }

    # GUARDRAIL 2: Phát hiện văn bản ngoài phạm vi chuyên ngành CNTT (ví dụ: Nghị định 100 giao thông)
    if facts.out_of_scope_docs and not facts.article_refs and not _sanitize_fulltext_query(question):
        out_name = ", ".join(facts.out_of_scope_docs)
        guardrail_answer = (
            f"ℹ️ **THÔNG BÁO PHẠM VI TƯ VẤN:**\n\n"
            f"Văn bản **{out_name}** không nằm trong cơ sở dữ liệu chuyên ngành **Công nghệ thông tin & An toàn thông tin mạng**.\n\n"
            f"Hệ thống hiện tại tập trung tư vấn các văn bản nòng cốt:\n"
            f"- **Nghị định 15/2020/NĐ-CP** (Xử phạt vi phạm hành chính lĩnh vực CNTT, viễn thông, mạng xã hội).\n"
            f"- **Luật An ninh mạng 2018 (24/2018/QH14)**.\n"
            f"- **Luật Công nghệ thông tin 2006 (67/2006/QH11)**.\n"
            f"- **Luật Giao dịch điện tử 2023, Luật Viễn thông 2023, Luật Dữ liệu 2024, Bộ luật Hình sự 2015 (Tội phạm CNTT)**.\n\n"
            f"👉 Vui lòng đặt câu hỏi liên quan đến lĩnh vực CNTT, an ninh mạng hoặc mạng xã hội."
        )
        return {
            "answer": guardrail_answer,
            "naive_answer": guardrail_answer if request.comparison_mode else None,
            "symbolic_reasoning": {
                "facts": facts.to_dict(),
                "matched_actions": [],
                "penalty_calculations": [],
                "rule_steps": [{
                    "rule": "OUT_OF_SCOPE_GUARDRAIL",
                    "basis": "Phạm vi dữ liệu Đồ án",
                    "detail": f"Văn bản '{out_name}' nằm ngoài phạm vi chuyên môn CNTT & An ninh mạng.",
                }],
            },
            "graph_view": {"nodes": [], "edges": []},
            "sources": [],
        }

    # Nhúng câu hỏi 1 lần duy nhất để dùng chung cho cả PGVector và Neo4j Vector Index
    query_vector: list[float] | None = None
    try:
        query_vector = embeddings.embed_query(question)
    except Exception as e:
        print(f"[CẢNH BÁO Embed Query lỗi]: {e}")

    # 2. Luồng Neural: Truy vấn pgvector
    neural_docs = []
    if vector_db:
        try:
            if query_vector:
                neural_docs = vector_db.similarity_search_by_vector(query_vector, k=4)
            else:
                neural_docs = vector_db.similarity_search(question, k=4)
        except Exception as e:
            print(f"[CẢNH BÁO PGVector Search lỗi]: {e}")

    neural_context = (
        "\n\n---\n\n".join(
            [f"[{doc.metadata.get('doc_title', 'Luật')}] {doc.page_content}" for doc in neural_docs]
        )
        if neural_docs
        else "Không tìm thấy đoạn trích văn bản phù hợp trong vector database."
    )

    # Trích xuất danh sách article_id từ kết quả PGVector làm cầu nối sang Neo4j
    neural_article_ids = [
        str(doc.metadata["article_id"])
        for doc in neural_docs
        if doc.metadata and doc.metadata.get("article_id")
    ]

    # 3. Luồng Symbolic: Truy vấn Neo4j 4 tầng & Chạy Rule Engine
    graph_result = query_knowledge_graph(
        facts=facts,
        raw_question=question,
        neural_article_ids=neural_article_ids,
        query_vector=query_vector,
    )

    # Chuẩn bị context văn bản cho Symbolic Reasoning (Gồm Mức phạt + Biện pháp khắc phục + Quy phạm)
    symbolic_summary_lines = []
    if graph_result["penalty_calculations"]:
        symbolic_summary_lines.append("CÁC MỨC PHẠT VÀ CHẾ TÀI ĐÃ TÍNH TOÁN TẤT ĐỊNH THEO LUẬT:")
        for calc in graph_result["penalty_calculations"]:
            symbolic_summary_lines.append(f"- Hành vi: {calc['action']}")
            symbolic_summary_lines.append(f"  Căn cứ: {calc['clause']}, {calc['article']}")
            for res in calc["calculations"]:
                symbolic_summary_lines.append(
                    f"  + Chủ thể [{res['subject_label']}]: {res['display']} (Công thức: {res['formula']})"
                )
            if calc.get("sanctions"):
                symbolic_summary_lines.append(
                    f"  + Hình thức xử phạt bổ sung / Biện pháp khắc phục hậu quả: {'; '.join(calc['sanctions'])}"
                )
            if calc.get("conditions"):
                symbolic_summary_lines.append(f"  + Điều kiện áp dụng: {'; '.join(calc['conditions'])}")
            if calc.get("ref_articles"):
                symbolic_summary_lines.append(
                    f"  + Điều khoản liên đới tham chiếu: Điều {', '.join(map(str, calc['ref_articles']))}"
                )
    elif graph_result["matched_actions"]:
        # Trường hợp câu hỏi thuộc Luật An ninh mạng / Luật CNTT / BLHS (quy định cấm/nghĩa vụ/tội danh)
        symbolic_summary_lines.append("CÁC QUY PHẠM PHÁP LUẬT TRÍCH XUẤT TỪ ĐỒ THỊ TRI THỨC:")
        for act in graph_result["matched_actions"]:
            loc = f"Khoản {act['clause_number']} " if act.get("clause_number") else ""
            if act.get("point"):
                loc += f"Điểm {act['point']} "
            symbolic_summary_lines.append(
                f"- [{act['action_kind']}] {act['action_name']} "
                f"(Căn cứ: {loc}Điều {act['article_number']} - {act['doc_title']})"
            )
            if act.get("sanctions"):
                symbolic_summary_lines.append(f"  + Chế tài/Biện pháp: {'; '.join(act['sanctions'])}")

    if graph_result["rule_steps"]:
        symbolic_summary_lines.append("\nCĂN CỨ NGUYÊN TẮC SUY LUẬN (RULE TRACE):")
        for step in graph_result["rule_steps"]:
            symbolic_summary_lines.append(
                f"- Quy tắc [{step['rule']}]: {step['detail']} (Căn cứ: {step['basis']})"
            )

    symbolic_facts_text = (
        "\n".join(symbolic_summary_lines)
        if symbolic_summary_lines
        else "Không xác định được điều khoản vi phạm cụ thể trên đồ thị tri thức."
    )

    # 4. Sinh phản hồi Hybrid (Neuro-Symbolic)
    hybrid_prompt_text = prompt_neuro_symbolic.format(
        symbolic_facts=symbolic_facts_text,
        neural_context=neural_context,
        question=contextual_question,
    )

    try:
        hybrid_res = llm.invoke(hybrid_prompt_text)
        hybrid_answer = hybrid_res.content if hasattr(hybrid_res, "content") else str(hybrid_res)
    except Exception as e:
        print(f"[LỖI LLM Hybrid]: {e}")
        hybrid_answer = f"Lỗi gọi mô hình ngôn ngữ: {e}"

    # 5. Sinh phản hồi Naive RAG (để so sánh đối chứng A/B nếu bật comparison_mode)
    naive_answer = None
    if request.comparison_mode:
        try:
            naive_prompt_text = prompt_naive.format(
                neural_context=neural_context,
                question=contextual_question,
            )
            naive_res = llm.invoke(naive_prompt_text)
            naive_answer = naive_res.content if hasattr(naive_res, "content") else str(naive_res)
        except Exception as e:
            naive_answer = f"(Chế độ Naive RAG gặp sự cố: {e})"

    # Thu thập nguồn trích dẫn
    sources = []
    for doc in neural_docs:
        meta = doc.metadata or {}
        sources.append({
            "title": meta.get("doc_title") or meta.get("doc_code") or "Văn bản luật",
            "article": f"Điều {meta.get('article_number', '')}: {meta.get('article_title', '')}".strip(": "),
            "page": meta.get("page", 1),
            "snippet": doc.page_content[:200] + "...",
        })

    return {
        "answer": hybrid_answer,
        "naive_answer": naive_answer,
        "symbolic_reasoning": {
            "facts": facts.to_dict(),
            "matched_actions": graph_result["matched_actions"],
            "penalty_calculations": graph_result["penalty_calculations"],
            "rule_steps": graph_result["rule_steps"],
        },
        "graph_view": graph_result["graph_view"],
        "sources": sources,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)