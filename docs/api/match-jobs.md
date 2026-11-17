# API Top N việc phù hợp: `POST /match/jobs` (S4-D04, US-16)

Contract cho trang "Việc phù hợp với tôi" (S4-H01 mock, S4-H02 thẻ kết quả, S4-H04 nối API thật).
Schema chuẩn nằm ở `src/api/match.py` (`MatchRequest`, `MatchResponse`); test
`tests/unit/test_api_match.py` kiểm response khớp schema.

## Gọi

```ts
const { data: { session } } = await supabase.auth.getSession();
const res = await fetch(`${process.env.NEXT_PUBLIC_CV_API_URL}/match/jobs`, {
  method: "POST",
  headers: { Authorization: `Bearer ${session.access_token}`, "Content-Type": "application/json" },
  body: JSON.stringify({ cv_id, top_n: 10, filters: { provinces: [1, 79], work_modes: ["remote"] } }),
});
```

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `cv_id` | uuid | CV của chính người dùng, đã đọc xong (`parse_status = parsed`) |
| `top_n` | 5 \| 10 \| 20 \| 50 | Mặc định 10. Không đủ tin thì trả ít hơn |
| `filters.provinces` | số[] | Mã tỉnh mới (`ref.provinces.code`). Rỗng = mọi tỉnh. Tin **remote** và tin **không ghi tỉnh** luôn qua bộ lọc tỉnh |
| `filters.work_modes` | ("onsite" \| "hybrid" \| "remote")[] | Rỗng = mọi hình thức |

Tin hết hạn (`valid_through` < hôm nay) hoặc đã đóng không bao giờ có trong kết quả: API kiểm lại
Top N với DB ngay lúc trả.

## Kết quả 200

```json
{
  "request_id": 123,
  "cv_id": "2f0c…",
  "top_n": 10,
  "engine_version": "ranker-v1",
  "corpus_size": 1435,
  "candidates": 151,
  "latency_ms": 420,
  "note": "Điểm là mức phù hợp theo công thức, không phải xác suất trúng tuyển.",
  "results": [
    {
      "rank": 1,
      "job_id": 1484,
      "public_id": "6b1e…",
      "title": "Data Engineer",
      "company": "Công ty Cổ phần …",
      "provinces": ["Hà Nội"],
      "work_mode": "onsite",
      "valid_through": "2026-12-11",
      "apply_url": "https://…",
      "score": 82.4,
      "components": { "K": 0.94, "M": 0.75, "E": 0.89, "X": null },
      "weights_used": { "K": 0.2778, "M": 0.3889, "E": 0.3333 },
      "skills_matched": [
        { "skill_id": "python", "skill": "Python", "level": "required", "via": null,
          "relation": "exact", "evidence": "strong" },
        { "skill_id": "spark", "skill": "Spark", "level": "required", "via": "PySpark",
          "relation": "child", "evidence": "strong" }
      ],
      "skills_missing": [ { "skill_id": "kafka", "skill": "Kafka", "level": "preferred" } ],
      "explanation": "Khớp 4/5 kỹ năng bắt buộc · 0/1 kỹ năng ưu tiên · tin không ghi số năm kinh nghiệm · nội dung CV gần với tin này hơn 89% tin đang mở"
    }
  ]
}
```

| Trường | Ý nghĩa trên UI |
|---|---|
| `score` | Điểm H 0–100, 1 chữ số thập phân. Kèm `note` (bắt buộc hiện, AC US-16) |
| `components` | 4 thanh: **K** Từ khóa, **M** Kỹ năng, **E** Ngữ nghĩa, **X** Kinh nghiệm (0–1). `null` = không xác định (tin không ghi kỹ năng / số năm…): ẩn thanh hoặc ghi "không áp dụng" |
| `weights_used` | Trọng số sau khi chia lại (tổng 1), cho tooltip "điểm tính thế nào" |
| `skills_matched` | Kỹ năng khớp. `via` khác null: khớp qua kỹ năng liên quan, ví dụ "Spark (qua PySpark)" |
| `skills_missing` | Kỹ năng CV **chưa thể hiện**, bắt buộc trước |
| `explanation` | Một dòng giải thích ngắn |
| `request_id` | Id lượt chấm trong `app.match_requests`. `null` nếu ghi lịch sử lỗi (kết quả vẫn dùng được) |

Công thức: `H = 100 × (0,25 K + 0,35 M + 0,30 E + 0,10 X)` chỉ trên thành phần xác định
(`config/ranker_config.yaml`).

## Lỗi

| HTTP | `error` | Thông báo gợi ý cho người dùng |
|---|---|---|
| 401 | `unauthorized` | Phiên đăng nhập hết hạn, hãy đăng nhập lại. |
| 404 | `cv_not_found` | Không tìm thấy CV. |
| 409 | `cv_not_parsed` | CV chưa đọc xong, hãy đợi rồi thử lại. |
| 422 | (FastAPI `detail`) | Lỗi gửi dữ liệu (top_n hoặc bộ lọc sai). |
| 429 | `rate_limited` | Bạn thao tác quá nhanh, thử lại sau 1 phút (20 lượt/phút). |
| 502 | `supabase_error` | Có lỗi hệ thống, hãy thử lại. |
| 503 | `engine_warming` | Hệ thống đang khởi động (khoảng 15 giây), thử lại sau ít phút. |
| 503 | `matcher_not_configured` | Tính năng chưa bật trên máy chủ này. |

## Cấu hình máy chủ

| Biến môi trường | Bắt buộc | Ghi chú |
|---|---|---|
| `MATCHER_DATABASE_URL` | Có | Chuỗi kết nối role **chỉ đọc** `matcher_ro` (migration 0012), Session pooler. Bí mật: đặt ở Secret của Render, không commit |
| `CF_ACCOUNT_ID`, `CF_API_TOKEN` | Nên có | Vector hóa CV (bge-m3, Workers AI). Thiếu thì E = null, các điểm khác vẫn tính |
| `MATCH_REFRESH_SECONDS` | Không | Làm mới kho tin trong RAM, mặc định 3600 |
| `MATCH_RATE_LIMIT_PER_MINUTE` | Không | Mặc định 20 |

Cần migration `db/migrations/0013_match_jobs_api.sql` (RPC `api.get_cv_for_match`, `api.save_match`).
Nên có `0014_cv_match_input.sql` (S4-D05): đọc hồ sơ + vector CV trong một lượt gọi, nhanh hơn
khoảng 85 ms; thiếu thì API tự dùng lại hai RPC cũ.

Header `Server-Timing` của response ghi thời gian từng bước (`cv_read`, `cv_embed`, `rank`,
`still_open`, `save`, `total`, đơn vị ms): xem trong DevTools → Network → Timing, hoặc đọc
`response.headers.get("server-timing")` để hiện thời gian phản hồi (S4-H04).
`/health` có thêm `matcher.ready`, `matcher.corpus_size`.
