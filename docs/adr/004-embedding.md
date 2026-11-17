# ADR-004: Model embedding cho JD và CV

- Trạng thái: đã chấp nhận, đang chạy production từ 17/11/2026
- Ngày: 20/11/2026
- Người viết / người duyệt: Duy / nhóm 5
- Thay cho spike S1-D10 (#435), làm thu nhỏ trong S3-D07 (#484)

## Bối cảnh

S3-D07 cần vector cho mọi đoạn JD (≤ 300 token) để S4-D02 tính điểm ngữ nghĩa E (EN-03: hiểu "xây
dựng pipeline dữ liệu" ↔ "ETL workflows"); S6-D03 dùng **cùng model** cho CV. Schema đã chốt
`core.job_chunks.embedding halfvec(1024)` + HNSW cosine. Nhóm không có thẻ thanh toán GCP (không
dùng được Cloud Run / Vertex); crawl chạy trên GitHub Actions, API CV trên Hugging Face Spaces.

## Các phương án

| Phương án | Ưu | Nhược |
| --- | --- | --- |
| **bge-m3 qua Cloudflare Workers AI** (`@cf/baai/bge-m3`) | 1024 chiều đúng schema; đa ngữ Việt–Anh; miễn phí 10.000 neurons/ngày, không cần GPU/thẻ; crawl và API CV gọi chung một endpoint nên vector luôn cùng model; web đã ở Cloudflare | Cần Account ID + API token; phụ thuộc dịch vụ ngoài (có thử lại, dừng gọn khi lỗi) |
| bge-m3 chạy tại chỗ (sentence-transformers, CPU) | Không phụ thuộc dịch vụ ngoài | Model 2,2 GB + torch: image API to, nạp lâu (đo: tải + nạp 268 giây lần đầu); 69 ms/đoạn trên CPU M1 |
| multilingual-e5-base / gte-multilingual-base (spike S1-D10) | Nhỏ, nhanh | **768 chiều**: không khớp schema 1024 |
| multilingual-e5-large | 1024 chiều | Không có trên Workers AI; chạy tại chỗ nặng như bge-m3 |

## Thử nghiệm (spike thu nhỏ, 20/11/2026)

bge-m3 (chạy tại chỗ, cùng trọng số với Workers AI), 10 bộ (truy vấn tiếng Việt, đoạn tiếng Anh
cùng ý, đoạn khác nghề):

| Truy vấn | cùng ý | khác ý | |
| --- | --- | --- | --- |
| xây dựng pipeline dữ liệu ↔ "Develop and maintain ETL workflows with Airflow" | 0,546 | 0,423 | ✓ |
| kiểm thử tự động ↔ "Write automation test scripts with Selenium" | 0,614 | 0,432 | ✓ |
| lập trình backend Java ↔ "Phát triển API bằng Spring Boot…" | 0,518 | 0,472 | ✓ |
| triển khai hạ tầng cloud ↔ "Provision AWS infrastructure with Terraform…" | 0,564 | 0,387 | ✓ |
| phân tích dữ liệu kinh doanh ↔ "Build Power BI dashboards…" | 0,554 | 0,461 | ✓ |
| thiết kế giao diện người dùng ↔ "Design UI/UX prototypes in Figma" | 0,624 | 0,441 | ✓ |
| bảo mật ứng dụng web ↔ "Perform penetration testing following OWASP Top 10" | 0,491 | 0,494 | ✗ |
| phát triển ứng dụng di động ↔ "Build cross-platform apps with Flutter" | 0,548 | 0,416 | ✓ |
| quản lý dự án phần mềm ↔ "Lead Agile/Scrum sprints…" | 0,522 | 0,387 | ✓ |
| học máy ↔ "Train machine learning models with scikit-learn and PyTorch" | 0,567 | 0,458 | ✓ |

**9/10 đúng**, khác Việt–Anh vẫn bắt được. Khoảng cách giữa "cùng ý" và "khác ý" nhỏ (0,05–0,18) với
truy vấn ngắn: S4-D02 không dùng cosine thô làm ngưỡng mà dùng max-cosine theo đoạn + **phân vị toàn
kho**, và cộng với điểm kỹ năng (từ điển); ca "bảo mật ↔ pentest/OWASP" đã có kỹ năng từ điển bù.

Chi phí: 1.451 tin mở → 6.173 đoạn, 834 nghìn token → khoảng 900 neurons Workers AI (< 10% quota
miễn phí/ngày); mỗi ngày crawl thêm khoảng 100–200 tin là không đáng kể.

## Quyết định

- Model **BAAI/bge-m3**, 1024 chiều, chuẩn hóa L2, cosine.
- Nơi chạy: **Cloudflare Workers AI** (`cf/baai/bge-m3` ghi ở cột `model`). Chạy tại chỗ
  (`hf/BAAI/bge-m3`) là phương án dự phòng khi không có Workers AI, **không trộn** hai nơi: đổi nơi
  chạy thì cột `model` đổi và toàn kho được làm lại tự động (đoạn khác model).
- Đoạn ≤ 300 token đếm bằng tokenizer bge-m3; CV (S6-D03) dùng chung `embedding.chunker`.

## Hệ quả

- Cần secret `CF_ACCOUNT_ID`, `CF_API_TOKEN` (quyền Workers AI: Read) cho GitHub Actions và API CV.
- Spike S1-D10 (#435) đóng với kết quả này; phần "20 cặp CV–JD" chuyển sang S4-D02 khi có điểm E.
