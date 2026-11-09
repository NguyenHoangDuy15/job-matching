# Nguồn JD được phê duyệt (TASK-U008)

Ngày kiểm: 06/11/2026. Phục vụ US-02.06/AC1. Đây là ghi chú kỹ thuật của nhóm, không phải tư vấn pháp lý.

## Bảng tổng hợp

| Nguồn | robots.txt | Điều khoản | Giới hạn tốc độ | Được phép? | Cách lấy |
|---|---|---|---|---|---|
| TopCV | [Có](https://www.topcv.vn/robots.txt). Không chặn `/viec-lam/`, không có `Crawl-delay` | [Điều khoản](https://www.topcv.vn/terms-of-service), cập nhật 01/04/2025. Mục 6 hạn chế sao chép, phân phối và khai thác Nội dung TopCV | Không công bố | Có, đã được người phụ trách dự án xác nhận | Crawler có guard `allowed` và giới hạn request chủ động theo config |
| ITviec | [Có](https://itviec.com/robots.txt). Chỉ chặn `/subscriptions/new`, không có `Crawl-delay` | [Thỏa thuận sử dụng](https://itviec.com/blog/terms-conditions-vn/), hiệu lực 01/07/2023. Mục 2.2 hạn chế lấy, sao chép và tải nội dung | Không công bố | Có, đã được người phụ trách dự án xác nhận | Chỉ vận hành trong phạm vi phê duyệt và khi `allowed: true` |
| VietnamWorks | [Không có](https://www.vietnamworks.com/robots.txt) (HTTP 404) | [Terms of Use](https://www.vietnamworks.com/terms-of-use), không ghi ngày cập nhật. Mục VietnamWorks Website Content hạn chế sao chép và khai thác thương mại | Không công bố | Có, đã được người phụ trách dự án xác nhận | API ingestion có guard `allowed` và rate limit theo config |

## Kết luận

Người phụ trách dự án đã xác nhận cả ba nguồn được phép thu thập cho phạm vi dự án. Bằng chứng, phạm vi URL/dữ liệu, điều kiện lưu trữ và thời hạn phê duyệt phải được lưu theo quy trình nội bộ; không đưa nội dung nhạy cảm vào repo công khai. Trạng thái vận hành hiện được phản ánh bằng `allowed: true` trong `config/sources.yaml`.

- `robots.txt` chỉ cho biết quy ước truy cập, không phải giấy phép dùng nội dung.
- Theo RFC 9309, `robots.txt` trả về 404 thì crawler được phép truy cập. Việc này không thay đổi điều khoản của VietnamWorks.
- Không điều khoản nào trong ba văn bản nhắc trực tiếp đến robot, spider, scraping hay crawl. Việc vận hành dựa trên phạm vi phê duyệt riêng của dự án.
- Không nguồn nào công bố giới hạn tốc độ. Sau khi TopCV trả HTTP 429 với khoảng nghỉ 15 giây ngày 07/11/2026, cấu hình TopCV được nâng lên `rate_limit_s: 30`. Đây là khoảng cách tối thiểu nhóm tự áp dụng giữa các điều hướng chủ động; nó không kiểm soát mọi asset/XHR do trình duyệt tải.
- `allowed: true` không được dùng để bỏ qua guard. Nếu nguồn chuyển về `false`, thiếu khóa hoặc cấu hình sai kiểu, ingestion phải fail closed trước khi mở kết nối.

## Kiểm tra trước khi vận hành

1. Đối chiếu phạm vi và thời hạn phê duyệt đã lưu nội bộ; nếu hết hạn hoặc không khớp nguồn, đổi `allowed: false`.
2. Chạy test offline/mocked trước. Smoke test live phải chạy riêng, không nằm trong CI mặc định.
3. Kiểm tra lại `robots.txt` và điều khoản vì các văn bản có thể đổi. Gặp 403, 429 hoặc trang xác minh chống bot thì dừng, không tìm cách vượt.

## Thiết lập TopCV crawler

```powershell
uv sync --locked
uv run python src/ingestion/topcv.py --pages 1 --limit 2
```

Để thu thập tới một tổng mục tiêu cố định mà không xử lý vượt quá, dùng
`--target-total`. Ví dụ, mỗi lượt xử lý tối đa 2 JD và tự dừng khi SQLite có đủ
1.000 JD `COMPLETED`:

```powershell
uv run python src/ingestion/topcv.py --details-only --limit 2 --delay 15 --target-total 1000
```

Khi đã đủ mục tiêu, crawler không đọc chính sách nguồn và không mở trình duyệt.
Nếu số JD còn thiếu nhỏ hơn `--limit`, crawler chỉ xử lý đúng số còn thiếu.

Nếu đã có CSV danh sách TopCV với tối thiểu hai cột `title,url`, có thể đưa các URL
chưa có vào hàng đợi hoàn toàn offline. Các trạng thái hiện có không bị reset:

```powershell
uv run python src/ingestion/topcv.py --import-listing-csv data/raw/topcv_2026/topcv_jobs.csv
```

Crawler dùng Nodriver với Chrome đã cài trên máy, lưu hàng đợi trong
`data/state/topcv_jobs.db` và mặc định xuất `data/raw/topcv_nodriver.jsonl`.
Crawler đọc phê duyệt nội bộ và `rate_limit_s` từ `config/sources.yaml`; `--delay`
nếu dùng chỉ có thể tăng khoảng nghỉ tối thiểu, không thể hạ thấp giá trị cấu hình.
`allowed: true` không thay thế quyền truy cập hoặc điều khoản của TopCV.

### Nhập JD TopCV từ HTML đã lưu

Nếu tài liệu chính trả `401`, `403`, `429` hoặc trang challenge, crawler ghi job
`BLOCKED`, khóa nguồn trong bảng `source_state` và dừng cả phiên. `Retry-After`
(nếu có) được giữ cả giá trị gốc lẫn thời điểm UTC đã parse. Crawler không tự mở
khóa và `--details-only` không thử lại các job `BLOCKED`. Chỉ dùng
`--clear-source-block` sau khi quyền/chính sách truy cập đã được xác minh; lệnh này
không reset các job `BLOCKED`.

Có thể mở JD được phép truy cập bằng Chrome, nhấn `Ctrl+S`, chọn **Webpage, HTML Only** hoặc **Webpage, Complete** và lưu vào `data/raw/saved_jd/`. Sau đó nhập hoàn toàn offline:

```powershell
uv run python src/ingestion/topcv.py `
  --import-html "data/raw/saved_jd/senior-qa.html" `
  --job-url "https://www.topcv.vn/viec-lam/senior-qa-engineer/2345138.html"
```

Chế độ này không đọc cấu hình nguồn, không khởi tạo browser và không gửi request
HTTP. JD hợp lệ được lưu transactionally vào SQLite, sau đó JSONL được sao lưu và
atomic replace. Crawler từ chối ghi vào `data/raw/topcv.jsonl` cũ và từ chối export
nếu tập mới làm mất job ID đã xuất.

Các lệnh chẩn đoán offline:

```powershell
uv run python src/ingestion/topcv.py --report-only
uv run python src/ingestion/topcv.py --export-only
```
