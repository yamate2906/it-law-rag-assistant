# Trợ lý ảo tư vấn Luật Công nghệ thông tin ứng dụng kiến trúc Neuro-Symbolic AI

Hệ thống tư vấn pháp luật Công nghệ thông tin, Viễn thông và An toàn thông tin mạng Việt Nam, kết hợp giữa **Truy xuất Ngữ nghĩa Vector (Neural RAG)** và **Đồ thị Tri thức pháp lý + Bộ suy luận Luật tất định (Symbolic Knowledge Graph & Rule Engine)**.

---

## 1. Kiến trúc Hệ thống (Neuro-Symbolic Architecture)

```
Câu hỏi Người dùng
       │
       ├──► [1. Symbolic NLU & Guardrail] (backend/legal_rules.py)
       │      ├─ Nhận diện chủ thể (Tổ chức / Cá nhân), độ tuổi, số hiệu Điều, tên Luật
       │      └─ Chặn văn bản giả mạo (VD: Nghị định 9999/2025/NĐ-CP) & ngoài phạm vi
       │
       ├──► [2. Khối Neural: Vector Search] (PostgreSQL 16 + pgvector + Gemini Embedding)
       │      ├─ Tìm kiếm ngữ nghĩa trên các phân đoạn cấu trúc (Văn bản > Chương > Điều > Khoản)
       │      └─ Trích xuất `article_id` làm cầu nối sang Đồ thị Tri thức (Neural -> Symbolic Bridge)
       │
       ├──► [3. Khối Symbolic: Neo4j 5.26 + Deterministic Rule Engine]
       │      ├─ Truy vấn Đồ thị 4 tầng: Số hiệu Điều -> Vector Index ('action_embedding')
       │      │                          -> Full-text Index ('action_fulltext') -> Cầu nối PGVector
       │      └─ Tính toán tất định khung phạt tiền (Python Rule Engine):
       │           • Quy tắc chủ thể (Điều 4 Khoản 3 NĐ 15/2020: Cá nhân = 1/2 Tổ chức, trừ Điều 106)
       │           • Kiểm tra trần phạt lĩnh vực (Điều 4 Khoản 1, 2 NĐ 15/2020)
       │           • Quy tắc độ tuổi vị thành niên (<14 tuổi, 14–<16 tuổi, 16–<18 tuổi)
       │
       └──► [4. Hợp nhất (Neuro-Symbolic Fusion) & Giao diện XAI]
              ├─ Tổng hợp câu trả lời pháp lý chính xác kèm căn cứ Điểm, Khoản, Điều
              ├─ Đối chứng trực quan A/B: Naive Vector RAG vs. Neuro-Symbolic Hybrid RAG
              └─ Hiển thị Dấu vết suy luận (Rule Trace) & Đồ thị tri thức tương tác (SVG)
```

---

## 2. Cơ sở dữ liệu Văn bản Pháp luật (`data/`)

Hệ thống phân tích cấu trúc tự động (`backend/legal_parser.py`) cho các văn bản quy phạm pháp luật:
1. **Nghị định 15/2020/NĐ-CP** (Xử phạt VPHC trong lĩnh vực bưu chính, viễn thông, tần số vô tuyến điện, CNTT và giao dịch điện tử).
2. **Luật An ninh mạng 2018** (`24/2018/QH14`).
3. **Luật Công nghệ thông tin 2006** (`67/2006/QH11` - Văn bản hợp nhất).
4. **Luật Giao dịch điện tử 2023** (`20/2023/QH15`).
5. **Luật Viễn thông 2023** (`24/2023/QH15`).
6. **Luật Dữ liệu 2024** (`60/2024/QH15`).
7. **Luật Sở hữu trí tuệ sửa đổi 2022** (`07/2022/QH15`).
8. **Luật Bảo vệ quyền lợi người tiêu dùng 2023** (`19/2023/QH15`).
9. **Luật Tần số vô tuyến điện** (`42/2009/QH12` - VBHN `62/VBHN-VPQH`) & **Nghị định hợp nhất `26/2026/VBHN-BKHCN`**.
10. **Bộ luật Hình sự 2015 (sửa đổi, bổ sung 2017)** (`100/2015/QH13` - Nhóm tội phạm trong lĩnh vực CNTT, mạng viễn thông: Điều 285–294 và các điều liên đới).

---

## 3. Hướng dẫn Cài đặt & Vận hành

### Bước 1: Khởi chạy Cơ sở dữ liệu (PostgreSQL/pgvector & Neo4j)
```bash
docker compose up -d
```
- **PostgreSQL + pgvector**: `localhost:5433` (Database: `law_db`)
- **Neo4j Browser**: http://localhost:7474 (`bolt://localhost:7687`)

### Bước 2: Cài đặt thư viện Backend & Cấu hình `.env`
```bash
pip install -r backend/requirements.txt
```
Khai báo khóa API trong `backend/.env`:
```env
GEMINI_API_KEY=your_gemini_api_key
OPENROUTER_API_KEY=your_openrouter_or_deepseek_key
DATABASE_URL=postgresql+psycopg2://admin:admin2906@localhost:5433/law_db
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=lawgraph2906
```

### Bước 3: Nạp dữ liệu vào PGVector (Khối Neural) và Neo4j (Khối Symbolic)
```bash
# Đồng bộ metadata cấu trúc cho PGVector (hoặc chạy không cờ để nhúng mới toàn bộ)
python backend/ingest.py --sync-metadata

# Xây dựng Đồ thị tri thức trên Neo4j và tạo Vector Index cho các Điều trọng tâm
python backend/graph_ingest.py --no-llm --priority-only
```

### Bước 4: Khởi động Backend API & Frontend React
```bash
# Chạy FastAPI server tại http://localhost:8000
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Chạy giao diện React Vite tại http://localhost:5173
cd frontend
npm install
npm run dev
```

### Bước 5: Chạy Đánh giá Thực nghiệm Định lượng (Benchmark)
```bash
python backend/evaluate_benchmark.py
```

