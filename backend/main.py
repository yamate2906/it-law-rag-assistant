import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_core.prompts import PromptTemplate

# 1. Load configuration relative to this file so startup works from any cwd.
BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")

# 2. Khởi tạo ứng dụng FastAPI
app = FastAPI()

# Cấu hình CORS để Frontend (React) sau này có thể gọi được API mà không bị chặn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Keep database and embedding settings aligned with ingest.py/docker-compose.yml.
CONNECTION_STRING = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://admin:admin2906@localhost:5433/law_db",
)
COLLECTION_NAME = "it_law_documents"
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.8-flash")

# 4. Khởi tạo AI và Kết nối Database
embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
db = PGVector(
    collection_name=COLLECTION_NAME,
    connection_string=CONNECTION_STRING,
    embedding_function=embeddings,
)
llm = ChatGoogleGenerativeAI(model=CHAT_MODEL, temperature=0.2)

# 5. Định dạng dữ liệu đầu vào
class ChatRequest(BaseModel):
    question: str

# 6. Tạo prompt "ép" AI phải trả lời dựa trên luật
PROMPT_TEMPLATE = """
Bạn là một trợ lý pháp lý ảo chuyên nghiệp, am hiểu Luật Công nghệ thông tin và An toàn thông tin mạng của Việt Nam.
Dựa vào các trích đoạn tài liệu pháp luật sau đây, hãy trả lời câu hỏi của người dùng một cách chính xác, ngắn gọn và dễ hiểu.
Tuyệt đối KHÔNG tự bịa ra thông tin. Nếu trong tài liệu không có câu trả lời, hãy nói: "Dựa trên dữ liệu hiện tại, tôi không tìm thấy thông tin cụ thể cho vấn đề này."

Trích đoạn tài liệu:
{context}

Câu hỏi của người dùng:
{question}

Trả lời (Nhớ trích dẫn rõ Điều, Khoản nếu có trong tài liệu):
"""
prompt = PromptTemplate(template=PROMPT_TEMPLATE, input_variables=["context", "question"])

# 7. Viết API xử lý câu hỏi
@app.post("/chat")
async def chat_with_bot(request: ChatRequest):
    # Bước A: Chuyển câu hỏi thành Vector và tìm 4 đoạn luật giống nhất trong Database
    try:
        docs = db.similarity_search(request.question, k=4)
    except Exception as exc:
        error_text = str(exc).upper()
        if "RESOURCE_EXHAUSTED" in error_text or "429" in error_text:
            raise HTTPException(
                status_code=429,
                detail="Gemini API đã hết quota. Hãy thử lại sau khi quota reset hoặc dùng project có quota phù hợp.",
            ) from exc
        raise HTTPException(
            status_code=503,
            detail="Không truy cập được vector database. Kiểm tra PostgreSQL và DATABASE_URL.",
        ) from exc
    if not docs:
        raise HTTPException(
            status_code=503,
            detail="Chưa có tài liệu trong vector database. Hãy chạy python ingest.py sau khi Gemini API có quota.",
        )
    
    # Bước B: Ghép 4 đoạn luật đó lại thành một đoạn văn bản dài
    context_text = "\n\n---\n\n".join([doc.page_content for doc in docs])
    
    # Bước C: Nhét câu hỏi và luật vào khung Prompt, gửi cho Gemini
    final_prompt = prompt.format(context=context_text, question=request.question)
    try:
        response = llm.invoke(final_prompt)
    except Exception as exc:
        error_text = str(exc).upper()
        if "RESOURCE_EXHAUSTED" in error_text or "429" in error_text:
            raise HTTPException(
                status_code=429,
                detail="Gemini API đã hết quota. Hãy thử lại sau khi quota reset hoặc dùng project có quota phù hợp.",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail="Gemini không thể tạo câu trả lời. Kiểm tra GEMINI_API_KEY và tên model.",
        ) from exc
    
    # Bước D: Trả kết quả về
    return {
        "answer": response.content,
        "sources": [doc.metadata for doc in docs]
    }
