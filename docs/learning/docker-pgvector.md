# Docker Compose + pgvector (spike TASK-H001)

- Người học: Thịnh · Sprint: S1 · Ngày: 02–03/11/2026 · Story: US-01.05 (AC1, AC2)
- Mã nguồn: `sandbox/compose-demo/` (chỉ để học; compose thật của dự án là TASK-H002)
- Môi trường đã thử: Windows 11, Docker Desktop 28.4.0, Compose v2.39.4, image `pgvector/pgvector:pg16` (pgvector 0.8.7)

## Kiểm tra "xong"

    cd sandbox/compose-demo
    docker compose up -d --wait
    docker compose ps                     # db ... (healthy)
    docker compose exec -T db psql -U demo -d demo -c "SELECT id, name FROM demo_item ORDER BY embedding <=> '[1,0,0]' LIMIT 3;"

Kết quả đã chạy (03/11): `1 backend-python`, `2 backend-java`, `3 data-engineer`.

## Chạy thử từ gốc repo

    docker compose -f sandbox/compose-demo/compose.yaml up -d --wait
    docker compose -f sandbox/compose-demo/compose.yaml exec -T db psql -U demo -d demo < sandbox/compose-demo/demo.sql
    docker compose -f sandbox/compose-demo/compose.yaml down        # giữ dữ liệu
    docker compose -f sandbox/compose-demo/compose.yaml down -v     # xóa luôn volume

`--wait` chờ tới khi healthcheck báo `healthy`, nên lệnh sau không bị "connection refused".

PowerShell không có toán tử `<` (báo `The '<' operator is reserved for future use`). Thay dòng chạy `demo.sql` bằng:

    Get-Content -Raw sandbox/compose-demo/demo.sql | docker compose -f sandbox/compose-demo/compose.yaml exec -T db psql -U demo -d demo

hoặc chép file vào container rồi dùng `psql -f` (chạy được trên mọi shell):

    docker compose -f sandbox/compose-demo/compose.yaml cp sandbox/compose-demo/demo.sql db:/tmp/demo.sql
    docker compose -f sandbox/compose-demo/compose.yaml exec -T db psql -U demo -d demo -f /tmp/demo.sql

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

Cả 5 lỗi dưới đây đã được cố ý gây ra và sửa thử ngày 03/11; thông báo lỗi chép nguyên văn.

### 1. Trùng cổng

- Dấu hiệu: `Bind for 0.0.0.0:5433 failed: port is already allocated`
- Nguyên nhân: cổng host đã có container khác (hoặc Postgres cài sẵn trên máy, thường là 5432) chiếm. Thử bằng cách chạy compose thứ hai cùng cổng khi demo đang chạy.
- Cách sửa: tắt cái đang chiếm (`docker ps` để tìm), hoặc đổi cổng host: `DEMO_DB_PORT=5434 docker compose up -d` (PowerShell: `$env:DEMO_DB_PORT=5434; docker compose up -d`). Cổng trong container (5432) giữ nguyên.

### 2. Đổi mật khẩu sau khi volume đã có dữ liệu

- Dấu hiệu: container vẫn `healthy` nhưng đăng nhập báo `FATAL: password authentication failed for user "demo"`; log có `PostgreSQL Database directory appears to contain a database; Skipping initialization`.
- Nguyên nhân: `POSTGRES_PASSWORD` chỉ dùng **lúc khởi tạo volume lần đầu**. Đổi biến sau đó không đổi mật khẩu thật; mật khẩu cũ vẫn vào được.
- Cách sửa: dùng lại mật khẩu cũ, hoặc đổi trong DB (`ALTER USER demo PASSWORD '...'`), hoặc `down -v` rồi `up` (mất dữ liệu).

### 3. Dùng image `postgres` thường (không có pgvector)

- Dấu hiệu: `ERROR: extension "vector" is not available` / `Could not open extension control file ".../vector.control"`
- Nguyên nhân: image `postgres:16` không cài sẵn extension; tên extension đúng nhưng file không có trong container.
- Cách sửa: dùng `pgvector/pgvector:pg16`. Nếu báo `type "vector" does not exist` thì là đã có image đúng nhưng quên `CREATE EXTENSION vector` trong database đang dùng.

### 4. Quên healthcheck

- Dấu hiệu: service phụ thuộc có `depends_on: db: condition: service_healthy` không chạy: `dependency failed to start: container ... has no healthcheck configured`. Nếu bỏ luôn điều kiện thì `api` khởi động trước khi DB sẵn sàng và báo `connection refused` ngẫu nhiên.
- Cách sửa: thêm healthcheck `pg_isready -h 127.0.0.1 -U $${POSTGRES_USER} -d $${POSTGRES_DB}`. `-h 127.0.0.1` vì trong lúc init Postgres tạm chỉ nghe unix socket (không có `-h` có thể báo sẵn sàng quá sớm); `$$` để Compose không thay biến bằng giá trị rỗng trên máy host.

### 5. Đường dẫn bind mount sai

- Dấu hiệu: **không có lỗi lúc khởi động**, container vẫn `healthy`, nhưng truy vấn báo `ERROR: relation "demo_item" does not exist`. Trên máy xuất hiện thư mục rỗng mới (ví dụ `init-db/`).
- Nguyên nhân: gõ sai `./init-db` thay vì `./initdb`; Docker tự tạo thư mục rỗng ở đường dẫn sai và mount vào, nên không có script init nào chạy. Đường dẫn tương đối tính từ thư mục chứa `compose.yaml`, không phải thư mục đang đứng.
- Cách sửa: kiểm `docker compose config` (in đường dẫn tuyệt đối đã giải), sửa đường dẫn, xóa thư mục rỗng lỡ tạo, rồi `down -v` và `up` để init chạy lại.

### Lỗi khác gặp khi làm

- Sửa `initdb/*.sql` mà không thấy thay đổi: script chỉ chạy khi volume trống → `down -v` rồi `up`, hoặc dùng migration (Alembic) cho DB thật.
- `ERROR: expected 3 dimensions, not 2`: số chiều khác cột `vector(n)`; với bge-m3 phải đúng 1024.
- `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`: Docker Desktop chưa chạy.

## Mang sang TASK-H002 (compose thật)

- Giữ: image `pgvector/pgvector:pg16`, named volume, healthcheck có `-h 127.0.0.1` và `$$`, `up --wait`.
- `api` và `ui` dùng `depends_on: db: condition: service_healthy`.
- Mật khẩu lấy từ `.env` (chép từ `.env.example`), không để mặc định trong compose như bản demo.
- Tạo bảng bằng Alembic, chỉ để `CREATE EXTENSION vector` ở init (hoặc trong migration đầu tiên).
- Nên ghim phiên bản image (ví dụ `pgvector/pgvector:0.8.x-pg16`) để 3 máy giống nhau; chốt trong ADR-003.
- Chưa cần index HNSW (ADR-003 hoãn); exact scan đủ nhanh cho vài nghìn JD.
