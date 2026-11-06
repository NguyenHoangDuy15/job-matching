# Nguồn JD đang mở (TASK-U008)

Ngày kiểm: 06/11/2026. Phục vụ US-02.06/AC1. Đây là ghi chú kỹ thuật của nhóm, không phải tư vấn pháp lý.

## Bảng tổng hợp

| Nguồn | robots.txt | Điều khoản | Giới hạn tốc độ | Được phép? | Cách lấy |
|---|---|---|---|---|---|
| TopCV | [Có](https://www.topcv.vn/robots.txt). Không chặn `/viec-lam/`, không có `Crawl-delay` | [Điều khoản](https://www.topcv.vn/terms-of-service), cập nhật 01/04/2025. Mục 6 cấm sao chép, phân phối và khai thác Nội dung TopCV | Không công bố | Chưa, cần xin phép | Dùng bộ Kaggle đã có. Chỉ crawl sau khi TopCV đồng ý bằng văn bản |
| ITviec | [Có](https://itviec.com/robots.txt). Chỉ chặn `/subscriptions/new`, không có `Crawl-delay` | [Thỏa thuận sử dụng](https://itviec.com/blog/terms-conditions-vn/), hiệu lực 01/07/2023. Mục 2.2 cấm lấy, sao chép, tải về nội dung nếu chưa có đồng ý bằng văn bản, trừ trường hợp cần thiết trong chừng mực | Không công bố | Chưa, cần xin phép | Chỉ crawl sau khi ITviec đồng ý bằng văn bản |
| VietnamWorks | [Không có](https://www.vietnamworks.com/robots.txt) (HTTP 404) | [Terms of Use](https://www.vietnamworks.com/terms-of-use), không ghi ngày cập nhật. Mục VietnamWorks Website Content cấm sao chép và khai thác thương mại; chỉ cho một số bản sao hợp lý, bao gồm bản dùng nội bộ, kèm ghi nguồn | Không công bố | Chưa, cần xin phép | Chỉ crawl sau khi VietnamWorks đồng ý bằng văn bản |

## Kết luận

Chưa nguồn nào đủ điều kiện để bật crawl. `robots.txt` của cả ba nguồn không chặn trang việc làm, nhưng điều khoản của cả ba đều hạn chế sao chép nội dung.

- `robots.txt` chỉ cho biết quy ước truy cập, không phải giấy phép dùng nội dung.
- Theo RFC 9309, `robots.txt` trả về 404 thì crawler được phép truy cập. Việc này không thay đổi điều khoản của VietnamWorks.
- Không điều khoản nào trong ba văn bản nhắc trực tiếp đến robot, spider, scraping hay crawl. Các kết luận trên dựa trên điều khoản chung về sao chép nội dung.
- Không nguồn nào công bố giới hạn tốc độ. `rate_limit_s: 5` trong `config/sources.yaml` là mức nhóm tự đặt để nháp.

## Việc tiếp theo

1. Nhóm chọn nguồn ưu tiên và gửi yêu cầu cho phép, nêu rõ mục đích đồ án, số tin và tốc độ truy cập.
2. Chỉ đổi `allowed: true` khi có đồng ý bằng văn bản, và lưu link hoặc bản sao phản hồi trong issue của US-02.06.
3. Khi crawl phải kiểm tra lại `robots.txt` và điều khoản, vì các văn bản này có thể đổi. Gặp 403, 429 hoặc trang xác minh chống bot thì dừng, không tìm cách vượt.
