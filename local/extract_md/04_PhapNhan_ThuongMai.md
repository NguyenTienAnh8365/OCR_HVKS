# Nhóm 4: Pháp Nhân Thương Mại Phạm Tội

> **Phạm vi cột:** Col 57 – Col 66  
> **Mã trường:** 26.1 → 26.6.4  
> **Áp dụng cho:** Trường hợp bị cáo là pháp nhân thương mại (doanh nghiệp, tổ chức tín dụng…) bị truy cứu trách nhiệm hình sự  
> **Lưu ý:** Nhóm này độc lập với Nhóm 2 và Nhóm 3 — có thể điền đồng thời khi vụ án có cả cá nhân và pháp nhân bị truy tố

---

## Danh sách trường

### 4.1 Thông tin pháp nhân

| STT | Mã trường | Tên trường | Cột (Excel) | Ghi chú / Ví dụ mẫu |
|-----|-----------|-----------|-------------|----------------------|
| 1 | 26.1 | Loại cơ quan/tổ chức | Col 57 | Sử dụng danh mục sheet `DB` cột `Quan hệ pháp luật` — VD: `694-1.1 Ngân hàng thương mại`, `688-2.2 Công ty Trách nhiệm hữu hạn`, `689-2.3 Công ty cổ phần`… |
| 2 | 26.2 | Tên cơ quan/tổ chức | Col 58 | Tên đầy đủ theo Giấy chứng nhận đăng ký doanh nghiệp |
| 3 | 26.3 | Số Giấy chứng nhận đăng ký doanh nghiệp | Col 59 | Mã số doanh nghiệp gồm 10 chữ số hoặc số đăng ký kinh doanh cũ |
| 4 | 26.4 | Mã số thuế | Col 60 | Mã số thuế của pháp nhân (thường trùng với mã số doanh nghiệp) |

---

### 4.2 Người đại diện pháp lý

| STT | Mã trường | Tên trường | Cột (Excel) | Ghi chú / Ví dụ mẫu |
|-----|-----------|-----------|-------------|----------------------|
| 5 | 26.5.1 | Họ và tên (người đại diện) | Col 61 | Họ tên đầy đủ của người đại diện theo pháp luật tại thời điểm xét xử |
| 6 | 26.5.2 | Số định danh (người đại diện) | Col 62 | Số CCCD/CMND của người đại diện pháp lý |

---

### 4.3 Địa chỉ trụ sở

| STT | Mã trường | Tên trường | Cột (Excel) | Ghi chú / Ví dụ mẫu |
|-----|-----------|-----------|-------------|----------------------|
| 7 | 26.6.1 | Địa chỉ trụ sở - Tỉnh/Thành phố | Col 63 | Sử dụng danh mục sheet `DB` cột `Tỉnh / Thành Phố` |
| 8 | 26.6.2 | Địa chỉ trụ sở - Quận/Huyện | Col 64 | |
| 9 | 26.6.3 | Địa chỉ trụ sở - Xã/Phường | Col 65 | |
| 10 | 26.6.4 | Địa chỉ trụ sở - Địa chỉ chi tiết | Col 66 | Số nhà, tên đường… |

---

## Quy tắc điền

- **Loại cơ quan/tổ chức** (Col 57): bắt buộc dùng đúng mã và tên trong danh mục `Quan hệ pháp luật` của sheet `DB`. Các loại phổ biến:
  - `682-1. Doanh nghiệp nhà nước`
  - `687-2.1 Doanh nghiệp tư nhân`
  - `688-2.2 Công ty Trách nhiệm hữu hạn`
  - `689-2.3 Công ty cổ phần`
  - `690-2.4 Công ty hợp danh`
  - `691-3. Doanh nghiệp 100% vốn đầu tư nước ngoài`
  - `693-1. Ngân hàng`, `694-1.1 Ngân hàng thương mại`, `699-2. Quỹ tín dụng nhân dân`…
- **Tên cơ quan/tổ chức** (Col 58): ghi đúng tên pháp lý đầy đủ, không viết tắt.
- **Số GCNĐKDN** (Col 59): không bỏ số 0 đầu nếu có; nếu chưa có mã số doanh nghiệp thì điền số đăng ký kinh doanh cũ.
- **Mã số thuế** (Col 60): có thể để trống nếu không xác định được.
- **Người đại diện** (Col 61, 62): là người đại diện theo pháp luật được xác định trong hồ sơ vụ án, không nhất thiết là Tổng Giám đốc/Giám đốc hiện tại.
- **Địa chỉ trụ sở** (Col 63–66): theo địa chỉ đăng ký kinh doanh tại thời điểm xét xử, không phải địa chỉ hoạt động thực tế (nếu khác).
- Nếu không có pháp nhân bị truy tố trong vụ án: **để trống toàn bộ nhóm này** (Col 57–66).
