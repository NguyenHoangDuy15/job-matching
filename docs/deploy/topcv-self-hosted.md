# TopCV automation trên GitHub Actions self-hosted Windows

Workflow `.github/workflows/topcv-self-hosted.yml` chạy crawler TopCV trên chính máy Windows,
giữ SQLite/profile ngoài Git checkout và chỉ đồng bộ các JD mới lên Supabase.

## Nguyên tắc an toàn

- Chỉ chạy khi `config/sources.yaml` vẫn có `topcv.allowed: true`.
- Giữ khoảng nghỉ tối thiểu 30 giây; workflow không thể hạ giới hạn này.
- Dừng ngay khi gặp HTTP 403/429 hoặc trang chống bot.
- Không tự chạy `--clear-source-block`.
- Không commit SQLite, JSONL, Chrome profile hoặc `DATABASE_URL`.
- Workflow không chạy từ pull request và chỉ có quyền `contents: read`.

## 1. Bootstrap checkpoint hiện tại

Mở PowerShell bằng tài khoản Windows sẽ chạy GitHub runner:

```powershell
New-Item -ItemType Directory -Force C:\topcv-automation\state | Out-Null
New-Item -ItemType Directory -Force C:\topcv-automation\raw | Out-Null
New-Item -ItemType Directory -Force C:\topcv-automation\chrome-profile | Out-Null
New-Item -ItemType Directory -Force C:\topcv-automation\logs | Out-Null

Copy-Item -LiteralPath C:\FU\job-matching\data\state\topcv_jobs.db `
  -Destination C:\topcv-automation\state\topcv_jobs.db
Copy-Item -LiteralPath C:\FU\job-matching\data\raw\topcv_nodriver.jsonl `
  -Destination C:\topcv-automation\raw\topcv_nodriver.jsonl
```

Không copy state trong khi crawler đang chạy. Chrome profile có thể để trống; nó chỉ nằm trên máy này và
không được upload lên GitHub.

Kiểm tra checkpoint:

```powershell
uv run python scripts\run_topcv_automation.py `
  --state-root C:\topcv-automation --sync-only
```

Lệnh trên không truy cập TopCV. Nó upsert các JD chưa được đánh dấu sync vào Supabase rồi ghi báo cáo tại
`C:\topcv-automation\logs\latest-summary.json`.

## 2. Đăng ký self-hosted runner

1. GitHub repository → **Settings** → **Actions** → **Runners**.
2. Chọn **New self-hosted runner** → **Windows** → **x64**.
3. Tạo thư mục riêng, ví dụ `C:\actions-runner`.
4. Chạy đúng các lệnh download/configure GitHub hiển thị. Registration token chỉ dùng một lần; không ghi
   token vào repo hoặc tài liệu.
5. Khi trình cài đặt hỏi chạy runner như Windows service, chọn **Yes**. Dùng tài khoản Windows có quyền đọc/
   ghi `C:\topcv-automation` và chạy Chrome.
6. Trong GitHub, runner phải hiện **Idle** với các label `self-hosted`, `Windows`, `X64`.

Máy phải bật, có mạng và không sleep. Màn hình có thể tắt hoặc Windows có thể lock. Nếu runner offline,
job chờ tối đa 24 giờ rồi GitHub hủy.

## 3. Cấu hình GitHub secret và variable

Repository → **Settings** → **Secrets and variables** → **Actions**:

1. Tab **Secrets** → **New repository secret**:
   - Name: `DATABASE_URL`
   - Value: chuỗi Supabase **Session pooler** dùng được với psycopg.
2. Tab **Variables**: chưa cần tạo `TOPCV_SCHEDULE_ENABLED`, hoặc đặt giá trị `false`.

Không dùng URL public/anon key thay cho `DATABASE_URL`. Workflow không in secret ra log.

## 4. Nghiệm thu trước khi bật lịch

Merge workflow vào default branch, rồi vào **Actions** → **topcv-self-hosted** → **Run workflow**.

### Lần 1: chỉ sync

- `sync_only`: bật
- `limit`: 1
- `target_total`: 1000

Kỳ vọng: không mở TopCV, workflow xanh và summary báo số `synced_to_supabase` bằng số JD completed.

### Lần 2: thử đúng một JD

- `sync_only`: tắt
- `limit`: 1
- `target_total`: 1000

Kỳ vọng:

- Chrome chạy headless.
- Một JD được xử lý hoặc crawler báo không còn JD chờ.
- JSONL được export vào `C:\topcv-automation\raw`.
- JD mới được upsert Supabase và `synced_to_pg=1`.
- `PROCESSING=0` khi kết thúc.

Nếu gặp 403/429, workflow đỏ và source giữ `BLOCKED`. Không bật lịch và không tự mở khóa; cần xác minh lại
quyền/chính sách trước.

## 5. Bật lịch

Sau khi hai lần chạy tay thành công, tạo hoặc sửa repository variable:

```text
TOPCV_SCHEDULE_ENABLED=true
```

Lịch mặc định chạy mỗi 2 giờ vào phút 17 theo `Asia/Ho_Chi_Minh`, mỗi lượt tối đa 20 JD và dừng chính xác
khi `COMPLETED` đạt 1000. `concurrency` ngăn hai lượt chạy chồng nhau; mỗi job có timeout 30 phút.

Tạm dừng mà không sửa code: đặt `TOPCV_SCHEDULE_ENABLED=false`. Chạy tay vẫn hoạt động.

## Lệnh vận hành hữu ích

Chỉ xem checkpoint cục bộ:

```powershell
uv run python src\ingestion\topcv.py `
  --db C:\topcv-automation\state\topcv_jobs.db --report-only
```

Chỉ sync Supabase, không vào TopCV:

```powershell
uv run python scripts\sync_topcv_supabase.py `
  --db C:\topcv-automation\state\topcv_jobs.db `
  --jsonl C:\topcv-automation\raw\topcv_nodriver.jsonl
```

Chạy tay một batch giống GitHub Actions:

```powershell
uv run python scripts\run_topcv_automation.py `
  --state-root C:\topcv-automation --limit 20 --target-total 1000 --headless
```

Mỗi thư mục backup chỉ giữ 10 file gần nhất. Không xóa thủ công database hiện tại khi workflow đang chạy.
