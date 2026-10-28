import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import psycopg2
from sqlalchemy import create_engine
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import PGVector

from config import COLLECTION_NAME, DATABASE_URL, EMBEDDING_PROVIDER, get_embeddings
from legal_parser import (
    SUPPORTED_SUFFIXES,
    LegalDocument,
    identify_document_by_name,
    load_corpus,
    normalize_text,
    related_document_codes,
)
from vector_index import ensure_halfvec_hnsw_index

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent

# Load cấu hình từ file .env (override=True để luôn nhận key mới nhất)
load_dotenv(BACKEND_DIR / ".env", override=True)

CONNECTION_STRING = DATABASE_URL


def _psycopg2_dsn() -> str:
    return CONNECTION_STRING.replace("postgresql+psycopg2://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )
MAX_CHUNK_CHARS = 1800


def build_chunks_for_document(
    document: LegalDocument,
    fingerprints: dict[str, str],
    fallback_splitter: RecursiveCharacterTextSplitter | None = None,
) -> list[Document]:
    """Cắt 1 văn bản theo Điều/Khoản và gắn ngữ cảnh phân cấp (Văn bản > Chương > Điều) vào từng chunk.

    Metadata `article_id` trùng với id của node (:Article) trong Neo4j, nhờ đó kết quả tìm
    kiếm vector có thể "nhảy" sang đồ thị tri thức (cầu nối Neural -> Symbolic).
    """
    if fallback_splitter is None:
        fallback_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=150)

    chunks: list[Document] = []
    for article in document.articles:
        effective_label = ""
        effective_from = article.effective_from or document.effective_from
        effective_to = article.effective_to or document.effective_to
        if effective_from or effective_to:
            effective_label = (
                f" (hiệu lực {effective_from or 'không rõ'}"
                f" đến {effective_to or 'hiện chưa ghi nhận ngày kết thúc'})"
            )
        header = f"[{document.short}{effective_label}] Chương {article.chapter or '-'} - {article.heading()}"
        source_name = Path(str(article.source)).name
        digest = fingerprints.get(source_name, "")
        metadata = {
            "source": source_name,
            "page": article.page,
            "doc_code": document.code,
            "doc_title": document.short,
            "article_id": article.id,
            "article_number": article.number,
            "article_title": article.title,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "source_url": article.source_url or document.source_url,
        }
        if digest:
            metadata["file_sha256"] = digest

        if len(article.text) <= MAX_CHUNK_CHARS or not article.clauses:
            pieces = (
                [article.text]
                if len(article.text) <= MAX_CHUNK_CHARS
                else fallback_splitter.split_text(article.text)
            )
            for piece in pieces:
                chunks.append(
                    Document(page_content=f"{header}\n{piece}", metadata={**metadata, "clauses": ""})
                )
            continue

        # Điều dài: gom các Khoản liền nhau vào chunk ≤ MAX_CHUNK_CHARS, mỗi chunk đều có header
        group: list[str] = []
        numbers: list[int] = []

        def flush():
            if group:
                label = f"{numbers[0]}-{numbers[-1]}" if len(numbers) > 1 else str(numbers[0])
                chunks.append(
                    Document(
                        page_content=f"{header}\n" + "\n".join(group),
                        metadata={**metadata, "clauses": label},
                    )
                )

        for clause in article.clauses:
            text = f"{clause.number}. {clause.text}"
            for piece in (
                [text] if len(text) <= MAX_CHUNK_CHARS else fallback_splitter.split_text(text)
            ):
                if group and sum(len(g) for g in group) + len(piece) > MAX_CHUNK_CHARS:
                    flush()
                    group, numbers = [], []
                group.append(piece)
                numbers.append(clause.number)
        flush()
    return chunks


def build_structured_chunks(
    core_only: bool = False,
    skip_sources: set[str] | None = None,
    only_sources: set[str] | None = None,
) -> list[Document]:
    """Hàm tương thích ngược: đọc toàn bộ corpus (trừ các file trong skip_sources) và tạo danh sách chunks."""
    data_dir = PROJECT_DIR / "data"
    fingerprints = file_fingerprints(data_dir)
    fallback_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=150)
    chunks: list[Document] = []
    for document in load_corpus(
        data_dir,
        core_only=core_only,
        skip_sources=skip_sources,
        only_sources=only_sources,
    ):
        chunks.extend(build_chunks_for_document(document, fingerprints, fallback_splitter))
    return chunks


def sync_existing_pgvector_metadata() -> int:
    """Đồng bộ và chuẩn hóa metadata (doc_code, doc_title, article_id, article_number, article_title)
    cho các bản ghi đã nhúng trong bảng langchain_pg_embedding để kích hoạt cầu nối Neural -> Symbolic."""
    dsn = _psycopg2_dsn()
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT e.uuid, e.document, e.cmetadata
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON c.uuid = e.collection_id
        WHERE c.name = %s
        """,
        (COLLECTION_NAME,),
    )
    rows = cur.fetchall()

    docs = load_corpus(
        PROJECT_DIR / "data",
        core_only=False,
    )
    by_code = {d.code: d for d in docs}

    updated = 0
    for row_uuid, raw_text, meta in rows:
        meta = dict(meta or {})
        src_name = Path(str(meta.get("source", ""))).name.lower()
        doc_code = meta.get("doc_code")
        source_info = identify_document_by_name(src_name)
        if not doc_code and source_info:
            doc_code = source_info["code"]

        doc_obj = by_code.get(doc_code)
        if not doc_obj or not doc_obj.articles:
            continue

        norm_chunk = normalize_text(raw_text or "")

        # Tìm Điều khớp theo tiêu đề "Điều X." trong chunk hoặc theo trang gần nhất
        matched_art = None
        chunk_header = norm_chunk.splitlines()[0] if norm_chunk else ""
        art_match = re.search(r"\bĐiều\s+(\d{1,3}[a-z]?)\s*\.", chunk_header, re.IGNORECASE)
        if art_match:
            raw_number = art_match.group(1)
            art_num = int(raw_number) if raw_number.isdigit() else raw_number.lower()
            matched_art = next((a for a in doc_obj.articles if a.number == art_num), None)

        if matched_art is None:
            snippet = " ".join(norm_chunk.split())[:120]
            if len(snippet) > 25:
                matched_art = next((a for a in doc_obj.articles if snippet[:60] in a.text), None)

        if matched_art is None:
            # Keep unresolvable rows unlinked; page proximity is not reliable enough for a legal citation.
            continue

        new_meta = {
            **meta,
            "source": Path(str(meta.get("source", matched_art.source))).name,
            "doc_code": doc_obj.code,
            "doc_title": doc_obj.short,
            "article_id": matched_art.id,
            "article_number": matched_art.number,
            "article_title": matched_art.title,
            "effective_from": matched_art.effective_from or doc_obj.effective_from,
            "effective_to": matched_art.effective_to or doc_obj.effective_to,
            "source_url": matched_art.source_url or doc_obj.source_url,
        }
        cur.execute(
            "UPDATE langchain_pg_embedding SET cmetadata = %s::json WHERE uuid = %s;",
            (json.dumps(new_meta, ensure_ascii=False), row_uuid),
        )
        updated += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Đã đồng bộ metadata (article_id, doc_code, doc_title) cho {updated}/{len(rows)} vector trong PGVector.")
    return updated


def file_fingerprints(data_dir: Path) -> dict[str, str]:
    """SHA-256 theo tên file để chỉ nạp file mới hoặc file đã thay đổi (hỗ trợ cả PDF, DOCX, TXT, MD và ảnh)."""
    fingerprints = {}
    for path in sorted(data_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            fingerprints[path.name] = digest
    return fingerprints


def get_ingested_state(fingerprints: dict[str, str], force: bool = False) -> tuple[set[str], set[str]]:
    """Read the existing manifest before parsing files; do not create or mutate it here.
    Trả về (skip_sources, pending_sources).
    """
    known: dict[str, str] = {}
    try:
        with psycopg2.connect(_psycopg2_dsn()) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT source, sha256 FROM rag_ingest_manifest WHERE collection_name = %s",
                (COLLECTION_NAME,),
            )
            known = dict(cur.fetchall())
    except psycopg2.errors.UndefinedTable:
        # A fresh database has no manifest yet; the first successful ingest creates it.
        pass

    if force:
        return set(), set(fingerprints.keys())

    skip_sources = {
        source for source, digest in fingerprints.items()
        if known.get(source) == digest
    }
    pending_sources = set(fingerprints.keys()) - skip_sources
    return skip_sources, pending_sources


def finalize_sources(
    sources: set[str],
    fingerprints: dict[str, str],
    replace_doc_code: str | None = None,
    expected_doc_code: str | None = None,
    expected_ids_by_source: dict[str, list[str]] | None = None,
) -> None:
    """Sau khi thêm vector mới thành công, dọn vector phiên bản cũ và cập nhật manifest."""
    if not sources:
        return
    dsn = _psycopg2_dsn()
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rag_ingest_manifest (
                collection_name TEXT NOT NULL,
                source TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (collection_name, source)
            );
        """)
        if replace_doc_code and sources:
            current_sources = sorted(sources)
            cur.execute(
                """
                SELECT DISTINCT e.cmetadata->>'source'
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                WHERE c.name = %s
                  AND e.cmetadata->>'doc_code' = %s
                  AND COALESCE(e.cmetadata->>'source', '') <> ALL(%s)
                """,
                (COLLECTION_NAME, replace_doc_code, current_sources),
            )
            stale_sources = [row[0] for row in cur.fetchall() if row[0]]
            cur.execute(
                """
                DELETE FROM langchain_pg_embedding e
                USING langchain_pg_collection c
                WHERE e.collection_id = c.uuid AND c.name = %s
                  AND e.cmetadata->>'doc_code' = %s
                  AND COALESCE(e.cmetadata->>'source', '') <> ALL(%s)
                """,
                (COLLECTION_NAME, replace_doc_code, current_sources),
            )
            if stale_sources:
                cur.execute(
                    "DELETE FROM rag_ingest_manifest WHERE collection_name = %s AND source = ANY(%s)",
                    (COLLECTION_NAME, stale_sources),
                )
        for source in sources:
            digest = fingerprints.get(source)
            if digest:
                cur.execute("""
                    DELETE FROM langchain_pg_embedding e
                    USING langchain_pg_collection c
                    WHERE e.collection_id = c.uuid AND c.name = %s
                      AND e.cmetadata->>'source' = %s
                      AND COALESCE(e.cmetadata->>'file_sha256', '') <> %s
                """, (COLLECTION_NAME, source, digest))
                cur.execute("""
                    INSERT INTO rag_ingest_manifest (collection_name, source, sha256)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (collection_name, source)
                    DO UPDATE SET sha256 = EXCLUDED.sha256, ingested_at = NOW()
                """, (COLLECTION_NAME, source, digest))

            if expected_doc_code:
                expected_ids = (expected_ids_by_source or {}).get(source, [])
                if expected_ids:
                    cur.execute(
                        """
                        DELETE FROM langchain_pg_embedding e
                        USING langchain_pg_collection c
                        WHERE e.collection_id = c.uuid AND c.name = %s
                          AND e.cmetadata->>'doc_code' = %s
                          AND e.cmetadata->>'source' = %s
                          AND COALESCE(e.custom_id, '') <> ALL(%s)
                        """,
                        (COLLECTION_NAME, expected_doc_code, source, expected_ids),
                    )
                else:
                    cur.execute(
                        """
                        DELETE FROM langchain_pg_embedding e
                        USING langchain_pg_collection c
                        WHERE e.collection_id = c.uuid AND c.name = %s
                          AND e.cmetadata->>'doc_code' = %s
                          AND e.cmetadata->>'source' = %s
                        """,
                        (COLLECTION_NAME, expected_doc_code, source),
                    )


# Hạn mức Free tier của gemini-embedding-001: ~30.000 token/phút và 100 request/phút
# (mỗi đoạn trong batch tính là 1 request). Giữ dưới ngưỡng để không bị 429.
EMBED_TPM_LIMIT = int(os.getenv("EMBED_TPM_LIMIT", "24000"))
EMBED_RPM_LIMIT = int(os.getenv("EMBED_RPM_LIMIT", "80"))
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "8"))
_usage_window: list[tuple[float, int, int]] = []  # (thời điểm, token ước lượng, số request)


def _estimate_tokens(texts: list[str]) -> int:
    # Tiếng Việt ~2.5 ký tự/token với tokenizer của Gemini (ước lượng an toàn)
    return int(sum(len(t) for t in texts) / 2.5) + 1


def _throttle(tokens: int, requests: int) -> None:
    """Chờ chủ động để tổng token/request trong 60 giây gần nhất không vượt hạn mức theo phút."""
    while True:
        now = time.time()
        while _usage_window and now - _usage_window[0][0] >= 60:
            _usage_window.pop(0)
        used_tokens = sum(t for _, t, _ in _usage_window)
        used_reqs = sum(r for _, _, r in _usage_window)
        if not _usage_window or (
            used_tokens + tokens <= EMBED_TPM_LIMIT and used_reqs + requests <= EMBED_RPM_LIMIT
        ):
            _usage_window.append((now, tokens, requests))
            return
        wait = 60 - (now - _usage_window[0][0]) + 0.5
        print(f"   ⏸  Giữ tốc độ dưới hạn mức Free tier: chờ {wait:.0f} giây...")
        time.sleep(max(wait, 1))


def _retry_delay(message: str) -> float:
    match = re.search(r"RETRY(?:_DELAY| IN)[^0-9]*(\d+(?:\.\d+)?)\s*S", message)
    return min(float(match.group(1)) + 2, 120) if match else 65


def _chunk_id(doc: Document) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"{doc.metadata.get('source')}:{doc.metadata.get('file_sha256')}:{hashlib.sha256(doc.page_content.encode('utf-8')).hexdigest()}",
        )
    )


def _existing_chunk_ids(ids: list[str]) -> set[str]:
    """Các đoạn đã được lưu ở lần chạy trước (bị dừng giữa chừng) -> không nhúng lại, tiết kiệm token."""
    if not ids:
        return set()
    dsn = _psycopg2_dsn()
    try:
        with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT custom_id FROM langchain_pg_embedding WHERE custom_id = ANY(%s)", (ids,)
            )
            return {row[0] for row in cur.fetchall()}
    except psycopg2.Error:
        return set()


def embed_and_commit_document(
    document: LegalDocument,
    chunks: list[Document],
    embeddings,
    fingerprints: dict[str, str],
    batch_size: int = EMBED_BATCH_SIZE,
) -> int:
    """Nhúng và lưu NGAY từng batch vào PostgreSQL; chỉ ghi manifest khi xong cả văn bản.

    Nếu bị dừng giữa chừng, lần chạy sau tự bỏ qua các đoạn đã lưu (theo custom_id tất định).
        """
    if not chunks:
        return 0

    ids = [_chunk_id(doc) for doc in chunks]
    expected_ids_by_source: dict[str, list[str]] = {}
    for doc, chunk_id in zip(chunks, ids):
        source = Path(str(doc.metadata.get("source", ""))).name
        expected_ids_by_source.setdefault(source, []).append(chunk_id)
    done_ids = _existing_chunk_ids(ids)
    pending = [(doc, cid) for doc, cid in zip(chunks, ids) if cid not in done_ids]
    if done_ids:
        print(f"   ↪ Đã có sẵn {len(chunks) - len(pending)}/{len(chunks)} đoạn từ lần chạy trước, chỉ nhúng phần còn lại.")

    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        texts = [doc.page_content for doc, _ in batch]
        for attempt in range(8):
            load_dotenv(BACKEND_DIR / ".env", override=True)
            _throttle(_estimate_tokens(texts), len(texts))
            try:
                vectors = embeddings.embed_documents(texts)
                break
            except Exception as exc:
                message = str(exc).upper()
                rate_limited = "429" in message or "RESOURCE_EXHAUSTED" in message
                if not rate_limited or attempt == 7:
                    raise
                # Thử nạp lại .env phòng trường hợp người dùng vừa đổi GEMINI_API_KEY khi script đang chạy
                old_raw = getattr(embeddings, "google_api_key", None)
                old_key_val = (
                    old_raw.get_secret_value()
                    if hasattr(old_raw, "get_secret_value")
                    else str(old_raw or "")
                ).strip()
                load_dotenv(BACKEND_DIR / ".env", override=True)
                new_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
                if new_key and old_key_val != new_key:
                    print("   🔄 Phát hiện GEMINI_API_KEY mới trong .env -> Chuyển sang key mới ngay lập tức!")
                    get_embeddings.cache_clear()
                    embeddings = get_embeddings()
                    _usage_window.clear()
                    continue
                # Chỉ dừng hẳn khi hết hạn mức THEO NGÀY hoặc đã thử lại 6 lần liên tiếp không qua được.
                if (
                    "PERDAY" in message
                    or "PER_DAY" in message
                    or "PER DAY" in message
                    or re.search(r"RETRY IN \d+H", message)
                    or attempt >= 6
                ):
                    raise SystemExit(
                        "\n⚠ Đã hết hạn mức embedding THEO NGÀY của project Google chứa API key này.\n"
                        "   Các đoạn/văn bản đã lưu được bảo toàn; khi hạn mức reset (khoảng 14h-15h giờ VN) "
                        "hoặc đổi sang key của project khác, chạy lại `python ingest.py` sẽ tiếp tục từ chỗ dừng."
                    ) from None
                delay = _retry_delay(message)
                print(f"   ⏳ Vượt hạn mức theo phút (429); chờ {delay:.0f} giây rồi thử lại...")
                time.sleep(delay)

        PGVector.from_embeddings(
            text_embeddings=list(zip(texts, vectors)),
            embedding=embeddings,
            metadatas=[doc.metadata for doc, _ in batch],
            collection_name=COLLECTION_NAME,
            connection_string=CONNECTION_STRING,
            pre_delete_collection=False,
            ids=[cid for _, cid in batch],
        )
        print(f"   → Đã nhúng & lưu {len(chunks) - len(pending) + start + len(batch)}/{len(chunks)} đoạn của [{document.code}].")

    has_canonical_source = any("vbhn" in source.lower() for source in document.sources)
    finalize_sources(
        set(document.sources),
        fingerprints,
        replace_doc_code=document.code if has_canonical_source else None,
        expected_doc_code=document.code,
        expected_ids_by_source=expected_ids_by_source,
    )
    return len(chunks)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    parser = argparse.ArgumentParser(description="Nạp hoặc đồng bộ Vector Database (PGVector)")
    parser.add_argument(
        "--sync-metadata",
        action="store_true",
        help="Đồng bộ metadata cấu trúc (article_id, doc_code) cho các vector hiện có trong PostgreSQL",
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="Chỉ nhúng văn bản cốt lõi cùng NĐ 211/2025 sửa đổi NĐ 15",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Nạp lại toàn bộ file hiện có; thay vector cũ theo từng file, không xóa collection khác.",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Chỉ nạp 1 file cụ thể trong thư mục data/ (ví dụ: --file 13nd.signed.pdf)",
    )
    args = parser.parse_args()

    if args.sync_metadata:
        sync_existing_pgvector_metadata()
        return

    data_dir = PROJECT_DIR / "data"
    fingerprints = file_fingerprints(data_dir)
    if args.core_only:
        core_codes = {
            "15/2020/NĐ-CP", "24/2018/QH14", "67/2006/QH11", "211/2025/NĐ-CP"
        }
        fingerprints = {
            name: digest
            for name, digest in fingerprints.items()
            if (info := identify_document_by_name(name)) and info["code"] in core_codes
        }
    only_sources = None
    if args.file:
        target_name = Path(args.file).name
        if target_name not in fingerprints:
            print(f"❌ Không tìm thấy file '{target_name}' trong thư mục {data_dir}.")
            return
        target_info = identify_document_by_name(target_name)
        if target_info:
            related_codes = related_document_codes(target_info["code"])
            only_sources = {
                name
                for name in fingerprints
                if (info := identify_document_by_name(name)) and info["code"] in related_codes
            }
        else:
            only_sources = {target_name}
        fingerprints = {name: fingerprints[name] for name in only_sources}

    print("🔍 BƯỚC 1: Kiểm tra manifest & dữ liệu đã nạp trong PostgreSQL...")
    skip_sources, pending_sources = get_ingested_state(fingerprints, force=args.force)
    # A changed amendment or consolidated edition requires its sibling sources
    # so the parser can build the complete current document before replacing data.
    pending_related_codes: set[str] = set()
    for source in pending_sources:
        info = identify_document_by_name(source)
        if info:
            pending_related_codes.update(related_document_codes(info["code"]))
    if pending_related_codes:
        skip_sources = {
            source
            for source in skip_sources
            if not (info := identify_document_by_name(source)) or info["code"] not in pending_related_codes
        }
    if skip_sources:
        print(f"⏭  Bỏ qua {len(skip_sources)} file đã nạp (tiết kiệm 100% thời gian đọc/OCR và token API):")
        for src in sorted(skip_sources):
            print(f"   • {src} (đã nạp)")

    if not pending_sources:
        print("✅ Tất cả file mục tiêu đều đã được nạp vào PostgreSQL. Không tốn thêm token nào!")
        return

    print(f"\n📥 BƯỚC 2: Đọc/OCR và cắt cấu trúc Điều/Khoản cho {len(pending_sources)} file chưa nạp...")
    documents = load_corpus(
        data_dir,
        core_only=args.core_only,
        skip_sources=skip_sources,
        only_sources=only_sources,
    )
    if not documents:
        print("✅ Không có văn bản nào cần nạp thêm.")
        return

    print(f"\n🧠 BƯỚC 3: Khởi tạo embedding API ({EMBEDDING_PROVIDER})...")
    embeddings = get_embeddings()
    fallback_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=150)

    print("\n💾 BƯỚC 4: Nhúng và lưu cuốn chiếu từng văn bản vào PostgreSQL...")
    total_chunks = 0
    total_docs = 0
    for idx, document in enumerate(documents, start=1):
        doc_chunks = build_chunks_for_document(document, fingerprints, fallback_splitter)
        if not doc_chunks:
            continue
        print(
            f"\n[{idx}/{len(documents)}] Đang nạp {document.code} ({document.short}) "
            f"- {len(doc_chunks)} chunks từ {', '.join(document.sources)}..."
        )
        embedded_count = embed_and_commit_document(
            document, doc_chunks, embeddings, fingerprints
        )
        total_chunks += embedded_count
        total_docs += 1
        print(f"   ✅ Đã lưu an toàn {embedded_count} vector của [{document.code}] vào PGVector & manifest.")

    engine = create_engine(CONNECTION_STRING, pool_pre_ping=True)
    try:
        indexed_dimension = ensure_halfvec_hnsw_index(engine, COLLECTION_NAME)
        if indexed_dimension:
            print(f"✅ Đã tạo/kiểm tra HNSW halfvec index ({indexed_dimension} chiều).")
    except Exception as exc:
        print(f"⚠ Không tạo được HNSW index (vẫn có thể tìm kiếm chính xác): {exc}")
    finally:
        engine.dispose()

    print(f"\n🎉 Hoàn tất! Đã nạp thêm {total_docs} văn bản ({total_chunks} chunks). Các file đã nạp trước đó được giữ nguyên.")


if __name__ == "__main__":
    main()
