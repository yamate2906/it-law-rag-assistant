# Nguồn án lệ và bản án đã tuyển chọn

Chỉ thêm tài liệu đã công bố công khai và được người phụ trách kiểm tra. Hệ thống
không tự tải toàn bộ hồ sơ Tòa án và không coi mọi bản án là án lệ.

Tạo file JSON theo `precedents.example.json`, rồi nạp bằng:

```powershell
python backend/precedents.py data/precedents/your-reviewed-records.json
```

Yêu cầu cho mỗi bản ghi:

- `id` là mã ổn định; `source_url` phải thuộc tên miền `toaan.gov.vn`.
- Ghi riêng tình tiết trọng yếu, vấn đề pháp lý, kết luận và lập luận; không trộn
  nhận định của người nhập với nội dung của quyết định.
- Mỗi liên kết văn bản phải có `supporting_quote` nguyên văn đủ để kiểm tra. Dùng
  `INTERPRETS` khi quyết định diễn giải điều khoản; `APPLIES` khi áp dụng; còn lại
  dùng `CITES`.
- Chỉ đặt `status` thành `ACTIVE` hoặc `WITHDRAWN` khi có nguồn chính thức trong
  `status_source`; nếu chưa xác minh, giữ `UNKNOWN`.
- Không thêm dữ liệu định danh cá nhân đã được ẩn danh trong nguồn công bố.

Importer kiểm tra schema, lưu nguồn và chỉ liên kết tới Điều đã có trong Neo4j.
Những liên kết chưa khớp Điều sẽ không được tự suy ra; chúng cần được sửa trong
manifest trước khi nạp.
