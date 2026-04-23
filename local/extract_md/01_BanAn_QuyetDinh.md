# Nhóm 1: Bản án / Quyết định

> **Phạm vi cột:** Col 0 – Col 19  
> **Mã trường:** 1 → 23  
> **Ngữ cảnh chung:** Mã tòa án: `D01.20-Tòa án nhân dân cấp cao tại Hà Nội` | Loại án: `1-Hình sự`

---

## Danh sách trường

| STT | Mã trường | Tên trường | Cột (Excel) | Ghi chú / Ví dụ mẫu |
|-----|-----------|-----------|-------------|----------------------|
| 1 | 1 | Số Bản án/Quyết định | Col 0 | VD: `05/2015/HS-PT` |
| 2 | _(phụ)_ | Số (dạng số thuần) | Col 1 | VD: `052015` — cột phụ không có header riêng |
| 3 | 2 | Ngày ban hành Bản án/Quyết định | Col 2 | VD: `07/01/2015` — định dạng dd/mm/yyyy |
| 4 | 3 | Ngày hiệu lực Bản án/Quyết định | Col 3 | Có thể để trống |
| 5 | 4,5 | Tên đơn vị ban hành Bản án/Quyết định | Col 4 | VD: `D01.20-Tòa án nhân dân cấp cao tại Hà Nội` |
| 6 | 6 | Số Bản án/Quyết định liên quan | Col 5 | VD: `31/2014/HS-ST` |
| 7 | 7 | Ngày ban hành Bản án/Quyết định liên quan | Col 6 | VD: `20/08/2014` |
| 8 | 8 | Ngày hiệu lực Bản án/Quyết định liên quan | Col 7 | Có thể để trống |
| 9 | 9 | Đơn vị ban hành Bản án/Quyết định liên quan | Col 8 | VD: `D01.49-Tòa án nhân dân Thành phố Hà Nội` |
| 10 | 10 | Trạng thái Bản án/Quyết định | Col 9 | Có thể để trống |
| 11 | 11 | Thông tin về án tích và tình trạng án tích | Col 10 | Có thể để trống |
| 12 | 12 | Ghi chú | Col 11 | Có thể để trống |
| 13 | 13,14 | Tên tội danh | Col 12 | Nhiều tội danh phân cách bằng `;` — VD: `Tội giết người trong trạng thái tinh thần bị kích động mạnh;Tội hành hạ người khác` |
| 14 | 15 | Điều khoản luật được áp dụng | Col 13 | Có thể để trống |
| 15 | 16,17 | Tên hình phạt chính | Col 14 | VD: `5-Tù có thời hạn` |
| 16 | 18 | Thời hạn/giá trị hình phạt chính | Col 15 | VD: `1 năm` |
| 17 | 19,20 | Tên hình phạt bổ sung | Col 16 | VD: `2-Phạt tiền; 1-Cảnh cáo` |
| 18 | 21 | Thời hạn/giá trị hình phạt bổ sung | Col 17 | VD: `VNĐ` |
| 19 | 22 | Án phí | Col 18 | Có thể để trống |
| 20 | 23 | Miễn phí (án phí/lệ phí) | Col 19 | Có thể để trống |

---

## Quy tắc điền

- **Số Bản án/Quyết định** (Col 0): nhập đúng ký hiệu gốc, bao gồm dấu `/` và ký hiệu loại án (HS-PT, HS-ST, DS…).
- **Col 1** (không có tên header riêng): là dạng rút gọn số bản án, chỉ gồm chữ số — hệ thống tự sinh hoặc nhập thủ công.
- **Ngày tháng**: luôn định dạng `dd/mm/yyyy`.
- **Tên tội danh** (Col 12): nếu nhiều tội, phân cách bằng dấu chấm phẩy `;`, không xuống dòng.
- **Hình phạt chính/bổ sung**: sử dụng mã danh mục từ sheet `DB` (cột `Hình phạt`).
- **Tên đơn vị**: sử dụng mã danh mục `D01.xx-...` theo danh sách tòa án hệ thống.
- Các trường có thể để trống: Col 3, 7, 9, 10, 11, 13, 18, 19.
