import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import PGVector

from legal_parser import load_corpus, normalize_text

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent

# Load cấu hình từ file .env
load_dotenv(BACKEND_DIR / ".env")

CONNECTION_STRING = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://admin:admin2906@localhost:5433/law_db",
)
COLLECTION_NAME = "it_law_documents"
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
MAX_CHUNK_CHARS = 1800


def build_structured_chunks(core_only: bool = False) -> list[Document]:
    """Cắt theo Điều/Khoản và gắn ngữ cảnh phân cấp (Văn bản > Chương > Điều) vào từng chunk.

    Metadata `article_id` trùng với id của node (:Article) trong Neo4j, nhờ đó kết quả tìm
    kiếm vector có thể "nhảy" sang đồ thị tri thức (cầu nối Neural -> Symbolic).
    """
    fallback_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=150)
    chunks: list[Document] = []
    for document in load_corpus(PROJECT_DIR / "data", core_only=core_only):
        for article in document.articles:
            header = f"[{document.short}] Chương {article.chapter or '-'} - {article.heading()}"
            metadata = {
                "source": article.source,
                "page": article.page,
                "doc_code": document.code,
                "doc_title": document.short,
                "article_id": article.id,
                "article_number": article.number,
                "article_title": article.title,
            }
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
                if group and sum(len(g) for g in group) + len(text) > MAX_CHUNK_CHARS:
                    flush()
                    group, numbers = [], []
                for piece in (
                    [text] if len(text) <= MAX_CHUNK_CHARS else fallback_splitter.split_text(text)
                ):
                    group.append(piece)
                    numbers.append(clause.number)
            flush()
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
            # Đối chiếu đoạn văn bản con hoặc trang của Điều
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
    args = parser.parse_args()

    if args.sync_metadata:
        sync_existing_pgvector_metadata()
        return

    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("LỖI: Không tìm thấy GEMINI_API_KEY trong backend/.env!")

    print("📥 BƯỚC 1-2: Đọc PDF và cắt theo cấu trúc Điều/Khoản (Structure-aware Chunking)...")
    chunks = build_structured_chunks(core_only=args.core_only)
    print(f"✅ Đã cắt văn bản thành {len(chunks)} đoạn (chunks) có ngữ cảnh phân cấp.\n")

    print("🧠 BƯỚC 3: Khởi tạo mô hình AI nhúng (Embedding) của Google Gemini...")
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)

    print("💾 BƯỚC 4: Đang tạo embedding trước khi cập nhật PostgreSQL...")
    print("⏳ Quá trình này có thể mất vài phút tùy hạn mức API và tốc độ mạng...")

    text_embeddings = []
    batch_size = 100
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        for attempt in range(5):
            try:
                vectors = embeddings.embed_documents([document.page_content for document in batch])
                break
            except Exception as exc:
                message = str(exc).upper()
                rate_limited = "429" in message or "RESOURCE_EXHAUSTED" in message
                daily_limit = "PERDAY" in message or re.search(r"RETRY IN \d+H", message)

                if rate_limited and daily_limit:
                    raise SystemExit(
                        "Gemini đã hết quota miễn phí theo ngày. Hãy chạy lại sau khi quota reset "
                        "hoặc dùng project có quota phù hợp. Collection chưa bị thay đổi."
                    ) from exc

                if not rate_limited or attempt == 4:
                    raise

                print("Gemini đang giới hạn tốc độ; chờ 60 giây rồi thử lại batch...")
                time.sleep(60)

        text_embeddings.extend(
            (document.page_content, vector) for document, vector in zip(batch, vectors)
        )
        print(f"Đã tạo embedding cho {min(start + len(batch), len(chunks))}/{len(chunks)} đoạn.")

    print("Đang thay collection cũ bằng dữ liệu mới...")
    PGVector.from_embeddings(
        text_embeddings=text_embeddings,
        embedding=embeddings,
        metadatas=[document.metadata for document in chunks],
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
        pre_delete_collection=True,
    )
    print("🎉 HOÀN TẤT! Toàn bộ văn bản luật đã được nhúng vào Database bằng Gemini.")


if __name__ == "__main__":
    main()

    main()