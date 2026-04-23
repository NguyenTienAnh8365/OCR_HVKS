# Nhóm 3: Thông tin Bị Cáo là Người Nước Ngoài

> **Phạm vi cột:** Col 50 – Col 56  
> **Mã trường:** 25.1 → 25.7  
> **Áp dụng cho:** Bị cáo mang quốc tịch nước ngoài hoặc không quốc tịch  
> **Lưu ý:** Nhóm này thay thế cho Nhóm 2 (Thông tin bị cáo) khi bị cáo là người nước ngoài — **không điền đồng thời cả hai nhóm**

---

## Danh sách trường

| STT | Mã trường | Tên trường | Cột (Excel) | Ghi chú / Ví dụ mẫu |
|-----|-----------|-----------|-------------|----------------------|
| 1 | 25.1 | Số định danh | Col 50 | Mã định danh cá nhân hoặc số ID tương đương theo nước sở tại |
| 2 | 25.2 | Loại giấy tờ XNC | Col 51 | Giấy tờ xuất nhập cảnh — VD: `Hộ chiếu`, `Thẻ tạm trú`, `Visa`… |
| 3 | 25.3 | Số giấy tờ | Col 52 | Số hộ chiếu hoặc số giấy tờ XNC tương ứng |
| 4 | 25.4 | Họ tên | Col 53 | Họ tên đầy đủ theo giấy tờ (có thể gồm cả ký tự Latin) |
| 5 | 25.5 | Quốc tịch | Col 54 | VD: `Trung Quốc`, `Hàn Quốc`, `Mỹ`… — sử dụng danh mục sheet `DB` cột `Quốc tịch / Quốc gia` |
| 6 | 25.6 | Ngày sinh | Col 55 | Định dạng `dd/mm/yyyy` |
| 7 | 25.7 | Giới tính | Col 56 | `Nam` hoặc `Nữ` — sử dụng danh mục sheet `DB` cột `Giới tính` |

---

## Quy tắc điền

- **Họ tên** (Col 53): ghi đúng theo giấy tờ tùy thân hợp lệ; nếu tên nước ngoài thì giữ nguyên ký tự gốc, không phiên âm tự ý.
- **Loại giấy tờ XNC** (Col 51): ưu tiên hộ chiếu; nếu không có hộ chiếu thì ghi loại giấy tờ được chấp nhận tại cửa khẩu hoặc theo quyết định của tòa.
- **Quốc tịch** (Col 54): bắt buộc dùng đúng giá trị trong danh mục sheet `DB`. Danh mục gồm toàn bộ quốc gia/vùng lãnh thổ chuẩn quốc tế (Aruba, Afghanistan, Angola…).
- **Số định danh** (Col 50): nếu không có thì để trống — không được điền giá trị giả.
- **Ngày sinh** (Col 55): định dạng `dd/mm/yyyy`; nếu không xác định được ngày/tháng thì ghi năm sinh có thể, phần còn lại để trống.
- **Giới tính** (Col 56): chỉ nhận `Nam` hoặc `Nữ`.
- Nhóm này **chỉ điền** khi bị cáo là người nước ngoài; không điền đồng thời với Nhóm 2.
