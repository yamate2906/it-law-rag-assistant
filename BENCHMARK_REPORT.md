# BÁO CÁO THỰC NGHIỆM ĐỐI CHỨNG: NAIVE VECTOR RAG vs. NEURO-SYMBOLIC HYBRID RAG

> **Đề tài:** Nghiên cứu và xây dựng Trợ lý ảo tư vấn Luật Công nghệ thông tin ứng dụng kiến trúc Neuro-Symbolic AI  
> **Phiên bản hệ thống:** LexIT Neuro-Symbolic 2.2 Hybrid  
> **Thời điểm đánh giá:** 26/10/2026  
> **Đối tượng đánh giá:** Tập kiểm thử chuẩn vàng (*Gold-Standard Benchmark*) mở rộng gồm 40 ca do chuyên gia gán nhãn, bao phủ toàn bộ 5 chuyên đề trọng yếu của Pháp luật CNTT Việt Nam:
> 1. Mạng xã hội, Trang thông tin điện tử & Nội dung mạng (TC01-TC05, TC16-TC20)
> 2. Bảo vệ Dữ liệu Cá nhân & An ninh mạng (TC06, TC09, TC21-TC26)
> 3. Viễn thông & Tần số vô tuyến điện (TC27-TC32)
> 4. Giao dịch điện tử & Chữ ký số (TC10, TC33-TC36)
> 5. Tội phạm Công nghệ cao & Chuyển hóa Hình sự (TC07, TC08, TC37-TC40)
> Kèm nhóm Chốt chặn Kiểm duyệt & Xử lý Yêu cầu Không hợp lệ (TC11-TC15).

---

## 1. Phương pháp & Tiêu chuẩn Đánh giá Khoa học

Hệ thống được kiểm thử đối chứng trực tiếp giữa hai kiến trúc:
1. **Naive Vector RAG (Baseline):** Mô hình RAG truyền thống dựa trên độ tương đồng cosine của vector embeddings kết hợp Prompt Engineering đơn thuần để mô hình ngôn ngữ (LLM) tự đọc và tự suy diễn mức phạt.
2. **Neuro-Symbolic Hybrid RAG (Đề xuất):** Hợp nhất truy xuất ngữ nghĩa (PGVector HNSW) với Đồ thị tri thức (Neo4j) và Động cơ suy luận quy tắc tất định (*Deterministic Symbolic Engine*) có chốt chặn kiểm duyệt đầu vào (*Guardrails*).

### 5 Thước đo Khoa học Độc lập (Independent Scientific Metrics)

| Thước đo | Định nghĩa & Ý nghĩa Khoa học |
| :--- | :--- |
| **Citation Accuracy** | Tỷ lệ trích dẫn chính xác số hiệu Điều, Khoản, Điểm và Tên văn bản quy phạm pháp luật làm căn cứ xử lý. |
| **Rule & Penalty Accuracy** | Độ chính xác tuyệt đối của khung tiền phạt (áp dụng đúng nguyên tắc x2 với tổ chức, 1/2 với cá nhân theo Điều 4 NĐ 15/2020 và trần phạt độ tuổi vị thành niên theo Điều 5, Điều 22 và Điều 134 Luật XLVPHC). |
| **Subject & Guardrail Accuracy** | Khả năng phân định chủ thể và kích hoạt chốt chặn từ chối khi câu hỏi ngoài phạm vi, thiếu căn cứ, giả mạo văn bản hoặc bằng chứng không hợp lệ. |
| **Temporal Validity Accuracy** | Tính đúng đắn theo mốc thời gian áp dụng (phân định chính xác văn bản lịch sử trước 01/07/2026 vs văn bản mới có hiệu lực Nghị định 174/2026 & 330/2026). |
| **Evidence Groundedness** | Tỷ lệ câu trả lời có viện dẫn nguyên văn đoạn trích hoặc chứng cứ nguồn xác thực từ kho dữ liệu, không sinh câu trả lời vô căn cứ. |

---

## 2. Bảng Kết quả Chi tiết theo 40 Kịch bản Kiểm thử Chuẩn vàng

| Mã Ca | Kịch bản Pháp lý | Căn cứ Luật (N/H) | Khung phạt (N/H) | Guardrail (N/H) | Hiệu lực (N/H) | Bằng chứng (N/H) | Thời gian |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **TC01** | Quy tắc chủ thể lịch sử Điều 101 NĐ 15/2020 (Cá nhân = 1/2 Tổ chức) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC02** | Độ tuổi vị thành niên 14 - dưới 16 tuổi (Điều 5, 22 Luật XLVPHC: Chỉ cảnh cáo) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC03** | Độ tuổi vị thành niên 16 - dưới 18 tuổi (Điều 134 Luật XLVPHC: Max 1/2 cá nhân) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC04** | Ngoại lệ chủ thể gốc là Cá nhân (Điều 106 NĐ 15/2020: Người chơi game) | ❌ / **✅** | ❌ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | 0.12s |
| **TC05** | Quy định mới Nghị định 174/2026/NĐ-CP (Hiệu lực từ 01/07/2026: Điều 95) | ✅ / **✅** | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | 0.12s |
| **TC06** | Quy định mới Nghị định 330/2026/NĐ-CP (Hiệu lực từ 19/08/2026: Điều 50) | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC07** | Suy luận đa chặng: Vi phạm mạng -> Hình sự Điều 288 BLHS 2015 | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC08** | Suy luận đa chặng: Tấn công mạng -> Hình sự Điều 289 BLHS 2015 | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC09** | Quy phạm cấm đoán: Điều 8 Luật An ninh mạng 2018 | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC10** | Luật Giao dịch điện tử 2023: Giá trị pháp lý chữ ký điện tử | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC11** | Câu hỏi thiếu tên văn bản (Ambiguous Article Guardrail) | ❌ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ❌ / **✅** | 0.12s |
| **TC12** | Khoảng tuổi mơ hồ cần xác định tuổi chính xác (Ambiguous Age) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | 0.12s |
| **TC13** | Chặn văn bản ngoài phạm vi CNTT (Nghị định 100/2019 giao thông) | ❌ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ❌ / **✅** | 0.12s |
| **TC14** | Chặn văn bản không có trong kho / giả mạo (Nghị định 9999 giả mạo) | ❌ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ❌ / **✅** | 0.12s |
| **TC15** | Chặn câu hỏi ngoài lề không liên quan pháp luật (Irrelevant Query) | ❌ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ❌ / **✅** | 0.12s |
| **TC16** | Vi phạm quy định về trang thông tin điện tử (Khoản 3 Điều 99 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC17** | Cung cấp trò chơi điện tử G1 không phép (Điều 103 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC18** | Livestream xúc phạm danh dự trên mạng xã hội (Điều 101 NĐ 15/2020) | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC19** | Không gỡ bỏ thông tin vi phạm theo yêu cầu cơ quan có thẩm quyền (Khoản 2 Điểm b Điều 100 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC20** | Tiết lộ bí mật đời tư cá nhân trên mạng (Điều 102 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC21** | Thu thập thông tin cá nhân trái phép (Điều 84 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC22** | Mua bán dữ liệu cá nhân trái phép (Điều 84 NĐ 15/2020 & NĐ 13/2023) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC23** | An toàn hệ thống thông tin theo 5 cấp độ (Nghị định 85/2016/NĐ-CP) | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC24** | Nghĩa vụ lưu trữ dữ liệu người dùng tại Việt Nam (Điều 26 Luật ANM 2018) | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC25** | Phát tán tin nhắn rác quảng cáo không được sự đồng ý (Điều 94 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC26** | Không bảo đảm an toàn làm lộ lọt dữ liệu khách hàng (Điều 84 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC27** | Nhập sẵn thông tin thuê bao di động (SIM rác) (Điều 33 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC28** | Sử dụng thiết bị kích sóng, phá sóng gây can nhiễu tần số (Điều 68 NĐ 15) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC29** | Đăng ký thông tin thuê bao di động không chính chủ (Khoản 2 Điểm a Điều 33 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC30** | Quảng cáo dịch vụ nội dung qua tin nhắn ngoài khung giờ (Khoản 3 Điều 94 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC31** | Cung cấp dịch vụ viễn thông không có giấy phép (Điều 15 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC32** | Cản trở, trì hoãn kết nối mạng viễn thông (Khoản 2 Điều 20 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC33** | Vi phạm về thông điệp dữ liệu (Khoản 2 Điều 107 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC34** | Cung cấp dịch vụ chứng thực chữ ký số không phép (Điều 108 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC35** | Giá trị pháp lý của thông điệp dữ liệu (Luật Giao dịch điện tử 2023) | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC36** | Giả mạo thông điệp dữ liệu trong giao dịch điện tử (Điều 107 NĐ 15/2020) | ✅ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ✅ / **✅** | 0.12s |
| **TC37** | Hình sự Điều 285 BLHS: Sản xuất, mua bán công cụ tấn công mạng | ❌ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ❌ / **✅** | 0.12s |
| **TC38** | Hình sự Điều 286 BLHS: Phát tán virus, ransomware gây thiệt hại lớn | ❌ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ❌ / **✅** | 0.12s |
| **TC39** | Hình sự Điều 287 BLHS: Tấn công DDoS làm tê liệt cổng thông tin | ❌ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ❌ / **✅** | 0.12s |
| **TC40** | Hình sự Điều 290 BLHS: Lừa đảo, chiếm đoạt tài sản qua mạng viễn thông | ❌ / **✅** | ❌ / **✅** | ❌ / **✅** | ✅ / **✅** | ❌ / **✅** | 0.12s |

*Ghi chú:* Ký hiệu `(N / H)` thể hiện: Kết quả của **Naive Vector RAG** / Kết quả của **Neuro-Symbolic Hybrid RAG**. Thời gian phản hồi đo đạc trên môi trường máy trạm thử nghiệm.

---

## 3. Tổng hợp Định lượng 5 Thước đo Khoa học

```
+-------------------------------------------------------------+------------------+-----------------------------+---------------+
| Tiêu chí Đánh giá Khoa học                                  | Naive Vector RAG | Neuro-Symbolic Hybrid RAG   | Độ Cải thiện  |
+-------------------------------------------------------------+------------------+-----------------------------+---------------+
| 1. Citation Accuracy (Căn cứ pháp lý)                       |      77.5%       |           100.0%            |    +22.5%     |
| 2. Rule & Penalty Accuracy (Khung phạt & Độ tuổi tất định)   |      22.5%       |           100.0%            |    +77.5%     |
| 3. Subject & Guardrail Accuracy (Chủ thể & Kiểm duyệt)       |      20.0%       |           100.0%            |    +80.0%     |
| 4. Temporal Validity Accuracy (Tính đúng theo mốc thời gian)|      92.5%       |           100.0%            |     +7.5%     |
| 5. Evidence Groundedness (Căn cứ trích dẫn chứng minh)       |      80.0%       |           100.0%            |    +20.0%     |
+-------------------------------------------------------------+------------------+-----------------------------+---------------+
```

---

## 4. Ghi chú Phương pháp luận & Khuyến cáo Phạm vi (Methodological Note & Scope)

1. **Về Tập Dữ liệu Kiểm thử (Test Set Coverage):**
   * Bộ dữ liệu 40 ca là bộ kiểm thử quy chuẩn có định hướng (*curated regression suite*), được thiết kế chuyên biệt để kiểm thử các lỗ hổng đã biết của mô hình ngôn ngữ lớn (LLM) và RAG truyền thống (như tính toán số học, suy luận bắc cầu giữa Luật và Nghị định, phân tầng trách nhiệm theo độ tuổi và phân định chủ thể).
   * Kết quả đạt 100% trên bộ test này thể hiện hệ thống Neuro-Symbolic đã hoàn thành trọn vẹn các quy tắc thiết kế định trước, nhưng chưa đồng nghĩa với việc hệ thống có thể bao phủ hoàn toàn mọi tình huống pháp lý phức tạp ngoài thực tế nếu chưa được mở rộng kiểm thử độc lập.

2. **Về Thời gian Đáp ứng (Response Latency):**
   * Thời gian đo đạc thể hiện thời gian xử lý của các thành phần cục bộ (Parser, Rule Engine, Graph Traversal) trên máy trạm thử nghiệm. Khi kết nối API mô hình sinh ngôn ngữ bên ngoài (như Google Gemini API), độ trễ thực tế sẽ dao động từ 1.5s đến 3.5s phụ thuộc vào băng thông mạng và tải của máy chủ AI.
