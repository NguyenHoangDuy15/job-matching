# Docker Compose + pgvector (spike TH1.L1)

- Người học: Thịnh · Sprint: S1 · Ngày: 02/11/2026
- Mã nguồn: `sandbox/compose-demo/` (chỉ để học; compose thật của dự án là TH1.1)
- Môi trường đã thử: Windows 11, Docker Desktop 28.4.0, Compose v2.39.4, image `pgvector/pgvector:pg16` (pgvector 0.8.7)

## Chạy thử

    docker compose -f sandbox/compose-demo/compose.yaml up -d --wait
    docker compose -f sandbox/compose-demo/compose.yaml exec -T db psql -U demo -d demo < sandbox/compose-demo/demo.sql
    docker compose -f sandbox/compose-demo/compose.yaml down        # giữ dữ liệu
    docker compose -f sandbox/compose-demo/compose.yaml down -v     # xóa luôn volume

`--wait` chờ tới khi healthcheck báo `healthy`, nên lệnh sau không bị "connection refused".

## Điều rút ra

| Khái niệm | Ghi nhớ |
| --- | --- |
| Image | `pgvector/pgvector:pg16` = Postgres 16 có sẵn extension, không cần tự build. Vẫn phải `CREATE EXTENSION vector` trong từng database. |
| Named volume | `pgdata:/var/lib/postgresql/data`. `down` giữ volume, `down -v` xóa. Đã thử: thêm 1 dòng → `down` → `up` vẫn còn 6 dòng. |
| `docker-entrypoint-initdb.d` | File `.sql`/`.sh` trong đó chạy theo thứ tự tên, **chỉ khi volume trống**. Sau `down -v` thì log có `running /docker-entrypoint-initdb.d/01-init.sql` và bảng về lại 5 dòng. |
| Healthcheck | `pg_isready -h 127.0.0.1 ...`; trong compose phải viết `$${POSTGRES_USER}` (hai dấu `$`) để biến được container đọc, không bị Compose thay trước. |
| Kiểu `vector(n)` | Cố định số chiều; dự án dùng `vector(1024)` cho bge-m3. |

### Ba toán tử khoảng cách (càng nhỏ càng gần)

| Toán tử | Ý nghĩa | Đổi sang độ giống |
| --- | --- | --- |
| `<->` | Khoảng cách L2 | — |
| `<=>` | Khoảng cách cosine = 1 − cos | `1 - (a <=> b)` |
| `<#>` | Tích vô hướng **âm** (−a·b) | `-(a <#> b)` |

Kiểm tra tính tay: CV giả `[0.8, 0, 0.6]` với `data-engineer [0.6, 0, 0.8]`: a·b = 0,48 + 0,48 = 0,96, cả hai có độ dài 1 → cosine = 0,96. Truy vấn trả đúng `0.9600`.

Top-K luôn viết `ORDER BY embedding <=> :q LIMIT k` (tăng dần). Nếu đã chuẩn hóa vector về độ dài 1 (bge-m3 có `normalize_embeddings=True`) thì `<#>` cho cùng thứ tự với `<=>` và nhanh hơn một chút.

## 5 lỗi thường gặp

1. **Sửa `initdb/*.sql` mà không thấy thay đổi.** Script chỉ chạy khi volume trống. Cách sửa: `down -v` rồi `up` (mất dữ liệu demo), hoặc dùng migration (Alembic, TU1.L2) cho DB thật.
2. **`ERROR: type "vector" does not exist`.** Quên `CREATE EXTENSION vector`, hoặc chạy trên database khác với database đã bật extension. Kiểm tra: `SELECT extversion FROM pg_extension WHERE extname='vector';`
3. **`ERROR: expected 3 dimensions, not 2`.** Số chiều của vector chèn/truy vấn khác cột `vector(n)`. Với bge-m3 phải đúng 1024; đổi model là phải migration cột.
4. **Healthcheck báo healthy quá sớm, hoặc biến trong healthcheck rỗng.** Trong lúc init, Postgres tạm chỉ nghe unix socket nên `pg_isready` không có `-h` có thể qua sớm; thêm `-h 127.0.0.1`. Viết `$POSTGRES_USER` (một `$`) thì Compose thay bằng biến trên máy host (thường rỗng) → dùng `$$`.
5. **Cổng 5432 đã bị chiếm / không kết nối được trên Windows.** Máy có Postgres cài sẵn hoặc compose khác đang chạy → đổi cổng host (`5433:5432`, biến `DEMO_DB_PORT`). Nếu `docker` báo `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified` thì Docker Desktop chưa chạy: mở Docker Desktop rồi chờ engine lên.

## Mang sang TH1.1 (compose thật)

- Giữ: image `pgvector/pgvector:pg16`, named volume, healthcheck có `-h 127.0.0.1` và `$$`, `up --wait`.
- `api` và `ui` dùng `depends_on: db: condition: service_healthy`.
- Mật khẩu lấy từ `.env` (chép từ `.env.example`), không để mặc định trong compose như bản demo.
- Tạo bảng bằng Alembic, chỉ để `CREATE EXTENSION vector` ở init (hoặc trong migration đầu tiên).
- Nên ghim phiên bản image (ví dụ `pgvector/pgvector:0.8.x-pg16`) để 3 máy giống nhau; chốt trong ADR-003.
- Chưa cần index HNSW (ADR-003 hoãn); exact scan đủ nhanh cho vài nghìn JD.
