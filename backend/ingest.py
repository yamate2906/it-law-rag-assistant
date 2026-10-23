import argparse
import hashlib
import json
import os
import re
import sys
import time
import warnings
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

warnings.filterwarnings("ignore", category=DeprecationWarning)
try:
    from langchain_core._api.deprecation import LangChainDeprecationWarning, LangChainPendingDeprecationWarning
    warnings.filterwarnings("ignore", category=LangChainDeprecationWarning)
    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
except Exception:
    pass

import psycopg2
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
)

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent

# Load cấu hình từ file .env (override=True để luôn nhận key mới nhất)
load_dotenv(BACKEND_DIR / ".env", override=True)

CONNECTION_STRING = DATABASE_URL
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
        header = f"[{document.short}] Chương {article.chapter or '-'} - {article.heading()}"
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
    docs = load_corpus(PROJECT_DIR / "data", core_only=True)
    by_code = {d.code: d for d in docs}

    dsn = CONNECTION_STRING.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("SELECT uuid, document, cmetadata FROM langchain_pg_embedding;")
    rows = cur.fetchall()

    updated = 0
    for row_uuid, raw_text, meta in rows:
        meta = dict(meta or {})
        src_name = Path(str(meta.get("source", ""))).name.lower()
        doc_code = meta.get("doc_code")
        if not doc_code:
            if "15-2020" in src_name:
                doc_code = "15/2020/NĐ-CP"
            elif "24-2018" in src_name:
                doc_code = "24/2018/QH14"
            elif "67-2006" in src_name:
                doc_code = "67/2006/QH11"

        doc_obj = by_code.get(doc_code)
        if not doc_obj or not doc_obj.articles:
            continue

        norm_chunk = normalize_text(raw_text or "")
        raw_page = int(meta.get("page", 0))
        page_1based = int(meta.get("page_label") or (raw_page + 1))

        # Tìm Điều khớp theo tiêu đề "Điều X." trong chunk hoặc theo trang gần nhất
        matched_art = None
        art_match = re.search(r"(?m)^\s*Điều\s+(\d{1,3})\s*\.", norm_chunk)
        if art_match:
            art_num = int(art_match.group(1))
            matched_art = next((a for a in doc_obj.articles if a.number == art_num), None)

        if matched_art is None:
            snippet = " ".join(norm_chunk.split())[:120]
            if len(snippet) > 25:
                matched_art = next((a for a in doc_obj.articles if snippet[:60] in a.text), None)

        if matched_art is None:
            candidates = [a for a in doc_obj.articles if a.page <= page_1based]
            matched_art = candidates[-1] if candidates else doc_obj.articles[0]

        new_meta = {
            **meta,
            "source": Path(str(meta.get("source", matched_art.source))).name,
            "page": page_1based,
            "doc_code": doc_obj.code,
            "doc_title": doc_obj.short,
            "article_id": matched_art.id,
            "article_number": matched_art.number,
            "article_title": matched_art.title,
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
    """Kiểm tra bảng rag_ingest_manifest và langchain_pg_embedding TRƯỚC khi đọc/OCR file.
    Trả về (skip_sources, pending_sources).
    """
    dsn = CONNECTION_STRING.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rag_ingest_manifest (
            collection_name TEXT NOT NULL,
            source TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (collection_name, source)
        );
    """)
    cur.execute(
        "SELECT source, sha256 FROM rag_ingest_manifest WHERE collection_name = %s",
        (COLLECTION_NAME,),
    )
    known: dict[str, str] = dict(cur.fetchall())

    # Các mã văn bản đã hoàn tất 100% trong rag_ingest_manifest
    completed_doc_codes: set[str] = set()
    for done_src, done_sha in known.items():
        if fingerprints.get(done_src) == done_sha:
            info = identify_document_by_name(done_src)
            if info:
                completed_doc_codes.add(info["code"])

    # Backfill manifest CHỈ cho file bản sao trùng doc_code đã hoàn tất 100% trong manifest
    # (Không backfill theo existing_sources vì file dừng giữa chừng chỉ mới có một phần batch trong DB)
    if not force:
        for source, digest in fingerprints.items():
            if source in known and known[source] == digest:
                continue
            doc_info = identify_document_by_name(source)
            doc_code = doc_info["code"] if doc_info else None
            if (
                doc_code
                and doc_code in completed_doc_codes
                and "15-2020" not in source.lower()
                and "91" not in source.lower()
                and "100-2015" not in source.lower()
            ):
                known[source] = digest
                cur.execute(
                    """
                    INSERT INTO rag_ingest_manifest (collection_name, source, sha256)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (collection_name, source)
                    DO UPDATE SET sha256 = EXCLUDED.sha256, ingested_at = NOW()
                    """,
                    (COLLECTION_NAME, source, digest),
                )
        conn.commit()

    cur.close()
    conn.close()

    if force:
        return set(), set(fingerprints.keys())

    skip_sources = {
        source for source, digest in fingerprints.items()
        if known.get(source) == digest
    }
    pending_sources = set(fingerprints.keys()) - skip_sources
    return skip_sources, pending_sources


def finalize_sources(sources: set[str], fingerprints: dict[str, str]) -> None:
    """Sau khi thêm vector mới thành công, dọn vector phiên bản cũ và cập nhật manifest."""
    if not sources:
        return
    dsn = CONNECTION_STRING.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    for source in sources:
        digest = fingerprints.get(source)
        if not digest:
            continue
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
    conn.commit()
    cur.close()
    conn.close()


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
    dsn = CONNECTION_STRING.replace("postgresql+psycopg2://", "postgresql://")
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
                old_key = getattr(embeddings, "google_api_key", None)
                load_dotenv(BACKEND_DIR / ".env", override=True)
                new_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                if new_key and str(old_key) != str(new_key):
                    print("   🔄 Phát hiện GEMINI_API_KEY mới trong .env -> Chuyển sang key mới ngay lập tức!")
                    get_embeddings.cache_clear()
                    embeddings = get_embeddings()
                    _usage_window.clear()
                    continue
                # Chỉ dừng hẳn khi hết hạn mức THEO NGÀY; giới hạn theo phút thì chờ rồi thử lại.
                # Google đôi khi không ghi rõ "PerDay": nếu đã chờ >1 phút mà vẫn 429 liên tiếp 3 lần
                # thì chắc chắn là hết hạn mức theo ngày -> dừng êm, không in traceback.
                if (
                    "PERDAY" in message
                    or "PER_DAY" in message
                    or re.search(r"RETRY IN \d+H", message)
                    or attempt >= 3
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

    finalize_sources(set(document.sources), fingerprints)
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
        help="Chỉ nhúng 3 văn bản cốt lõi (NĐ 15/2020, Luật ANM 2018, Luật CNTT 2006)",
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
        core_codes = {"15/2020/NĐ-CP", "24/2018/QH14", "67/2006/QH11"}
        fingerprints = {
            name: digest
            for name, digest in fingerprints.items()
            if (info := identify_document_by_name(name)) and info["code"] in core_codes
        }
    if args.file:
        target_name = Path(args.file).name
        if target_name not in fingerprints:
            print(f"❌ Không tìm thấy file '{target_name}' trong thư mục {data_dir}.")
            return
        fingerprints = {target_name: fingerprints[target_name]}

    print("🔍 BƯỚC 1: Kiểm tra manifest & dữ liệu đã nạp trong PostgreSQL...")
    skip_sources, pending_sources = get_ingested_state(fingerprints, force=args.force)
    if skip_sources:
        print(f"⏭  Bỏ qua {len(skip_sources)} file đã nạp (tiết kiệm 100% thời gian đọc/OCR và token API):")
        for src in sorted(skip_sources):
            print(f"   • {src} (đã nạp)")

    if not pending_sources:
        print("✅ Tất cả file mục tiêu đều đã được nạp vào PostgreSQL. Không tốn thêm token nào!")
        return

    only_sources = {Path(args.file).name} if args.file else None
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

    print(f"\n🎉 Hoàn tất! Đã nạp thêm {total_docs} văn bản ({total_chunks} chunks). Các file đã nạp trước đó được giữ nguyên.")


if __name__ == "__main__":
    main()
