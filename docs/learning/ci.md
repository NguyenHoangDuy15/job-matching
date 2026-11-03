# GitHub Actions + setup-uv (spike TASK-H003)

- Người học: Thịnh · Sprint: S1 · Ngày: 03/11/2026 · Story: US-01.06 (chuẩn bị cho AC1)
- Workflow thử: `.github/workflows/sandbox.yml` (đã xóa trước khi mở PR; xem lịch sử nhánh `spike/TASK-H003-gha`)
- Action dùng: `actions/checkout@v7`, `astral-sh/setup-uv@v7`

## Workflow đã thử

```yaml
name: sandbox
on:
  push:
    branches: ["spike/**"]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - id: setup-uv
        uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - run: echo "cache-hit = ${{ steps.setup-uv.outputs.cache-hit }}"
      - run: uv sync --locked
      - run: uv run pytest
```

## Cấu trúc workflow

- `on`: sự kiện kích hoạt. Ở đây là `push` vào nhánh khớp `spike/**`; push nhánh khác không chạy.
- `jobs`: mỗi job chạy trên một máy ảo mới, sạch (`runs-on: ubuntu-latest`); các job chạy song song nếu không khai báo `needs`.
- `steps`: chạy tuần tự trong job. `uses:` gọi action có sẵn, `run:` chạy lệnh shell.
- Một step đỏ → các step sau bị bỏ qua (trừ step có `if: always()`), cả job và cả run đỏ.
- `id:` đặt tên cho step để đọc output của nó: `${{ steps.setup-uv.outputs.cache-hit }}`.
- `uv sync --locked`: báo lỗi nếu `uv.lock` không khớp `pyproject.toml` (ai đó quên commit lock).

## Cache của uv

Số đo ngày 03/11/2026 (tab Actions, workflow `sandbox`, nhánh `spike/TASK-H003-gha`):

| Run | Commit | Kết quả | cache-hit | Thời gian job | "Cài thư viện" (`uv sync`) | "Chạy test" |
| --- | --- | --- | --- | --- | --- | --- |
| #1 – lần đầu | `097cf93` thêm workflow | xanh | false (chưa có cache) | 11s | 2s | 2s |
| #2 – có cache | `57e42e2` commit rỗng | xanh | true | 12s | 3s | 3s |
| #3 – cố ý đỏ | `19606ee` test sai | đỏ | true | 13s | – | đỏ (1 failed, 10 passed) |
| #4 – hoàn lại | `89b2888` bỏ test sai | xanh | true | 13s | 2s | 4s |

- Cache chỉ được **lưu** ở bước "Post Cài uv" khi job thành công. Ở run #3 bước này bị bỏ qua (⊘) → run đỏ không lưu cache.
- Khóa cache tính từ nội dung `uv.lock`: đổi thư viện → khóa mới → lần đầu lại phải tải.
- Cache của nhánh con đọc được cache của `main`, nhưng không đọc được cache của nhánh khác.
- Kết luận: với 56 package hiện tại, cache **gần như không làm nhanh hơn** (11s so với 12s), vì uv tải và cài
  rất nhanh ngay cả khi không có cache (~2s). Cache sẽ có ích khi thêm thư viện nặng (torch, sentence-transformers
  ở S4, hàng trăm MB). Vẫn bật `enable-cache` trong `ci.yml` thật vì không tốn gì.
- Thời gian job (11–13s) chủ yếu là dựng máy ảo, lấy code và chạy test; cả run chỉ khoảng 15s.

## Đọc log lỗi (run 3, commit `19606ee`)

- Tab Actions → run có ✗ đỏ → job `test` → step "uv run pytest" mở sẵn, các step sau bị bỏ qua.
- Dòng quan trọng: `FAILED tests/unit/test_fail_on_purpose.py::test_fail_on_purpose` và `AssertionError: cố ý đỏ để học cách đọc log CI`.
- Muốn xem lại log cũ: bấm biểu tượng ⚙ của step → "View raw logs", hoặc tải log về.
- Dòng tổng kết cuối log: `1 failed, 10 passed, 1 warning`, rồi `Error: Process completed with exit code 1.`
  → pytest trả mã khác 0 nên step đỏ.
- Mục "Annotations" ở đầu trang run tóm tắt lỗi (1 error) mà không cần mở log.
- Log còn có cảnh báo `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`:
  chỉ là cảnh báo, không làm đỏ job.
- Run #4 (commit `89b2888`, bỏ test đỏ) xanh trở lại.

## push khác pull_request thế nào

| | `push` | `pull_request` |
| --- | --- | --- |
| Chạy khi | Đẩy commit lên nhánh khớp bộ lọc | Mở PR, push thêm vào PR, mở lại PR |
| Code được chạy | Đúng commit vừa đẩy | Bản **ghép thử** nhánh PR với nhánh đích (merge commit tạm) |
| Bắt được | Lỗi trong nhánh | Cả lỗi chỉ lộ ra khi ghép với main mới nhất |
| Dùng làm required check | Không | Có (ruleset chặn merge) |

→ `ci.yml` thật (TASK-H004) chạy `on: pull_request` + `push` vào `main`.

## Lỗi gặp khi làm

- `uv.lock` trên `main` bị hỏng sau một lần giải xung đột merge (thiếu mục `annotated-doc`): `uv sync` báo
  `Failed to parse uv.lock ... has missing source field but has more than one matching package`.
  CI với `uv sync --locked` sẽ bắt được lỗi này ngay ở PR nếu đã có required check. Đã sửa ở nhánh `fix/uv-lock`.
- Bài học: khi xung đột ở `uv.lock`, **không sửa tay**; giữ bản của `main` rồi chạy `uv lock` để uv tự tính lại.
