import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import PGVector

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent

# Load configuration relative to this file so the command works from any cwd.
load_dotenv(BACKEND_DIR / ".env")

# Keep these defaults aligned with docker-compose.yml and backend/main.py.
CONNECTION_STRING = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://admin:admin2906@localhost:5433/law_db",
)
COLLECTION_NAME = "it_law_documents"
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

def main():
    # Windows consoles may use a legacy code page that cannot print Vietnamese
    # text or emoji. Keep progress messages from aborting the ingestion run.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("LỖI: Không tìm thấy GEMINI_API_KEY trong backend/.env!")

    print("📥 BƯỚC 1: Đang đọc các file PDF văn bản luật từ thư mục data...")
    loader = PyPDFDirectoryLoader(str(PROJECT_DIR / "data"))
    docs = loader.load()
    print(f"✅ Đã đọc thành công {len(docs)} trang tài liệu.\n")

    print("✂️ BƯỚC 2: Đang cắt nhỏ văn bản (Chunking)...")
    # Sử dụng bộ cắt chuyên dụng, ưu tiên cắt theo từ khóa "Điều", "Chương" của luật pháp
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\nĐiều ", "\nChương ", "\n\n", "\n", " ", ""]
    )
    chunks = text_splitter.split_documents(docs)
    print(f"✅ Đã cắt văn bản thành {len(chunks)} đoạn (chunks) nhỏ.\n")

    print("🧠 BƯỚC 3: Khởi tạo mô hình AI nhúng (Embedding) của Google Gemini...")
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)

    print("💾 BƯỚC 4: Đang tạo embedding trước khi cập nhật PostgreSQL...")
    print("⏳ Quá trình này có thể mất vài phút tùy hạn mức API và tốc độ mạng...")

    # Build all vectors before replacing the collection. If Gemini rejects a
    # batch because of its free-tier rate limit, the existing collection stays
    # intact and the failed batch is retried after the quota window resets.
    text_embeddings = []
    batch_size = 100
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        for attempt in range(5):
            try:
                vectors = embeddings.embed_documents(
                    [document.page_content for document in batch]
                )
                break
            except Exception as exc:
                message = str(exc).upper()
                rate_limited = "429" in message or "RESOURCE_EXHAUSTED" in message
                daily_limit = "PERDAY" in message or re.search(r"RETRY IN \d+H", message)
                if rate_limited and daily_limit:
                    raise SystemExit(
                        "Gemini đã hết quota miễn phí theo ngày. Hãy chạy lại sau khi quota reset "
                        "hoặc dùng project có quota/billing phù hợp. Collection chưa bị thay đổi."
                    ) from exc
                if not rate_limited or attempt == 4:
                    raise
                print("Gemini đang giới hạn tốc độ; chờ 60 giây rồi thử lại batch...")
                time.sleep(60)

        text_embeddings.extend(
            (document.page_content, vector)
            for document, vector in zip(batch, vectors)
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
    print("🎉 HOÀN TẤT! Toàn bộ văn bản luật đã được nhúng vào Database, sẵn sàng cho Trợ lý AI tra cứu.")

if __name__ == "__main__":
    main()
