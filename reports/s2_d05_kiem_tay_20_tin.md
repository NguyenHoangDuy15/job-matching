# S2-D05: Kiểm tay thẻ kỹ năng trên 20 tin đang mở

Ngày 11/11/2026 · Người kiểm: Duy (10 tin), Thịnh (10 tin) · Issue #449 (US-10)

Bộ tin lấy ngẫu nhiên bằng `scripts/check_job_skills.py` (seed 1). File đã điền có tiêu đề và link tin thật nên nằm trong `data/eval/`, không lên git. Báo cáo này chỉ ghi `job_id`.

## Kết quả

**Tiêu chí "xong" của issue:** ≥ 90% tin mở có thẻ kỹ năng.

```
$ uv run python scripts/label_skills.py --report
Tin đang mở: 284 · có thẻ kỹ năng: 264 (93.0%, mục tiêu ≥ 90%) · trung bình 6.2 thẻ/tin
```

**Kiểm tay** (`--merge` hai file rồi `--score`):

| Chỉ số | Giá trị | Cách tính |
|---|---|---|
| Tin lấy mẫu | 20 | |
| Bỏ qua | 6 | Trang tin lỗi lúc crawl (popup thanh toán TopCV); cả 6 tin hiện đã `closed` |
| Tin được chấm | 14 | |
| Thẻ máy gắn | 105 | |
| **Độ chính xác của thẻ** | **94,3%** (99/105) | Thẻ không bị đánh "sai" / tổng thẻ |
| **Đúng mức** bắt buộc/ưu tiên | **99,0%** (98/99) | Trong các thẻ đúng |
| Độ phủ xấp xỉ | 44,0% | Thẻ đúng / (thẻ đúng + mục người kiểm ghi "thiếu") |
| Tin không thiếu, không sai | 1/14 | |

**Kết luận:** thẻ máy gắn gần như luôn đúng, cả về kỹ năng lẫn mức. Điểm yếu là **độ phủ**, và phần lớn nguyên nhân nằm ngoài bộ trích kỹ năng (xem dưới).

## Vì sao thiếu: 126 mục người kiểm ghi "thiếu"

| Nhóm | Số mục | Ví dụ (job) | Nằm ở đâu |
|---|---|---|---|
| Chưa có trong từ điển | 80 (63%) | MES, SCADA, PLC (208); After Effects (249); ABAP Dictionary, CDS View (420); Sales, Telesales (295) | Từ điển. 5/14 tin không phải việc IT (4 tin bán hàng, 1 tin thiết kế đồ họa) |
| Nội dung VietnamWorks bị cắt | 22 (17%) | AWS, Docker, Kubernetes (427); RDBMS (409) | **Crawler.** 93/97 tin VietnamWorks đang mở lưu `jd_text` kết thúc bằng "...", trung bình 691 ký tự (TopCV: 3.049) |
| Đã gắn, nhưng dưới tên kỹ năng chuẩn khác | 14 (11%) | Routing → Networking, CCNA → Cisco, IPsec → VPN, MQTT → IoT, Microsoft 365 → Tin học văn phòng | Từ điển gộp alias; người xem không biết thẻ đó bao gồm kỹ năng nào |
| Nhận ra nhưng gắn mức `mentioned` (không hiện thẻ) | 5 (4%) | ERP, Data Warehouse (208); Node.js, TypeScript (427) | Luật mức: kỹ năng chỉ có ở phần Mô tả |
| Có trong nội dung nhưng bộ trích bỏ sót | 4 (3%) | Scrum trong "Agile/Scrum" (212); Windows Server (273) | Bộ trích |
| DB còn gắn bằng bản cũ | 1 | Leadership (427) | Chạy lại `label_skills.py --apply --stale` |

## Thẻ sai: 6/105, đều do alias quá rộng

| Job | Thẻ | Máy khớp từ | Vì sao sai |
|---|---|---|---|
| 420 | SOLID | "**Solid** understanding of SQL" | Tính từ "solid", không phải nguyên lý SOLID |
| 249 | System Design | "thiết kế hệ thống đồ họa" | Thiết kế đồ họa, không phải thiết kế hệ thống phần mềm |
| 191 | Cryptography | "VPN (IPsec/**SSL**)" | Nhắc SSL VPN, không yêu cầu mật mã học |
| 231 | Đàm phán | "kỹ năng thuyết phục" | Thuyết phục ≠ đàm phán |
| 309 | Tư duy logic | "kỹ năng phân tích" | Phân tích ≠ tư duy logic |
| 273 | Tin học văn phòng | "Microsoft 365" | Quản trị Microsoft 365 là việc IT, không phải dùng Office |

Sai mức: 1 thẻ (Tiếng Trung, job 212). JD ghi rõ là ưu tiên, máy gắn bắt buộc.

## Việc tiếp theo

| Việc | Người | Lý do |
|---|---|---|
| Lấy đủ mô tả tin VietnamWorks (trang chi tiết thay vì đoạn tóm tắt) | Tùng (crawler, S2-T03) | 17% mục thiếu; ảnh hưởng gần như mọi tin VietnamWorks |
| Thu hẹp alias gây sai: `Solid` phải viết hoa `SOLID`; bỏ "thiết kế hệ thống", "kỹ năng thuyết phục", "kỹ năng phân tích", "SSL", "Microsoft 365" khỏi các kỹ năng trên | Duy (S2-D08) | Toàn bộ 6 thẻ sai |
| Tách các kỹ năng đang bị gộp khác bản chất: Proxmox ≠ Hyper-V, Notion ≠ Trello, DHCP ≠ DNS | Duy (S2-D08) | Thẻ hiện tên khác với kỹ năng tin ghi |
| Quyết định phạm vi từ điển với tin không phải IT (bán hàng, thiết kế) | Cả nhóm | Lọc tin không phải IT ở crawler, hoặc chấp nhận độ phủ thấp ở nhóm tin này |
| Chạy `label_skills.py --apply --stale` trên Supabase | Duy | Gắn lại tin bằng bản luật mới nhất (PR #633) |

## Cách chạy lại

```bash
# Mỗi người điền phần của mình, rồi:
uv run python scripts/check_job_skills.py --merge data/eval/check_job_skills_duy.csv data/eval/check_job_skills_thinh.csv --score
```

`--merge` đọc được file Excel lưu có BOM, báo và sửa ô bị dán lặp. `--score` không tính tin ghi "bỏ qua", giữ nguyên tên kỹ năng có dấu phẩy ("Cẩn thận, chi tiết"), và cảnh báo khi một kỹ năng vừa được ghi "thiếu" vừa đã có thẻ.
