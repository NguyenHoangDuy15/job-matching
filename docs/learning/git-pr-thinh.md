# Vòng PR của Thịnh (TASK-H005, US-01.06/AC3)

Các bước cơ bản (nhánh, commit, push, mở PR) đã có ở [git-pr.md](git-pr.md).
File này ghi những gì tôi thực sự gặp trong S1: lỗi, cách sửa, một lần tự giải xung đột và một lần được review chéo.

## Quy ước nhóm

- 1 task = 1 issue = 1 nhánh = 1 PR.
- Tên nhánh: `feat/TASK-xxx-mo-ta` (task spike dùng `spike/TASK-xxx-mo-ta`), viết thường, không dấu, nối bằng gạch ngang.
- Tiêu đề PR: `[TASK-xxx] mô tả ngắn`, mô tả có `Closes #<số issue>` để issue tự đóng khi merge vào `main`.
- `main` có ruleset: không push thẳng, cần 1 approve của code owner, 3 check `lint`, `test`, `gitleaks` phải xanh.

## Lỗi đã gặp và cách sửa

| Lỗi                                                             | Nguyên nhân                                                              | Cách sửa                                                                                |
| --------------------------------------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| PowerShell báo lỗi ở `psql ... < file.sql` và `lệnh1 && lệnh2`  | PowerShell 5.1 không có `<` và `&&` như bash                             | `Get-Content -Raw file.sql \| docker compose exec -T db psql ...`; tách thành từng lệnh |
| `curl` trả lỗi lạ trong PowerShell                              | `curl` là alias của `Invoke-WebRequest`                                  | Gõ `curl.exe`                                                                           |
| `uv` không nhận sau khi cài                                     | Terminal cũ chưa nạp PATH mới                                            | Mở terminal mới, hoặc nạp lại `$env:Path`                                               |
| Job `lint` đỏ ở `ruff format --check` dù code chạy đúng         | Một file thiếu dòng trống cuối file                                      | `uv run ruff format .` trước khi commit                                                 |
| Job `gitleaks` đỏ: `403 Resource not accessible by integration` | Token CI chỉ có `contents: read`, action cần đọc danh sách commit của PR | Thêm `pull-requests: read` cho job `gitleaks` (PR #24)                                  |
| PR lỗi có nút Merge mờ nhưng chưa rõ do check nào               | Draft + chưa có approve + check đỏ cùng chặn                             | Bỏ Draft, nhờ approve, xem lại hộp merge chỉ còn lý do check đỏ                         |
| `warning: LF will be replaced by CRLF` khi commit               | Git trên Windows tự đổi kiểu xuống dòng                                  | Không ảnh hưởng, bỏ qua được                                                            |

## Tự tạo và giải 1 xung đột

**Cách tạo:** hai nhánh `practice/h-a` và `practice/h-b` tách từ cùng một commit, cùng sửa dòng "Tên nhánh".
`git merge practice/h-a` chạy êm (Fast-forward). `git merge practice/h-b` báo:

```
CONFLICT (content): Merge conflict in docs/learning/git-pr-thinh.md
Automatic merge failed; fix conflicts and then commit the result.
```

**Đọc dấu xung đột:** phần giữa `<<<<<<< HEAD` và `=======` là bản của nhánh đang đứng (đã có h-a),
phần giữa `=======` và `>>>>>>> practice/h-b` là bản của nhánh đang merge vào.
Hai bản bổ sung cho nhau nên tôi gộp thành một dòng và xóa cả 3 dấu.

**Sai lầm đã gặp:**

- `git diff --check` báo `leftover conflict marker` nhưng tôi vẫn `git add` và commit. Git không chặn,
  CI cũng không bắt (ruff chỉ kiểm `.py`). Sửa: xóa dấu trong file, rồi `git commit -a --amend --no-edit`
  (chỉ amend khi chưa push).
- Khi quét cả thư mục bằng `git grep "^<<<<<<<"`, tôi xóa nhầm dấu trong `git-pr.md` của Tùng.
  Ở đó dấu nằm trong khối code ví dụ, không phải xung đột thật. Đã khôi phục bằng `git checkout main -- docs/learning/git-pr.md`.

**Bài học:** dùng `git diff --check` (chỉ kiểm file đang xung đột) trước khi `git add`;
không phải dấu `<<<<<<<` nào cũng là xung đột.

## Review chéo

<!-- Thịnh điền sau khi PR được review: ai review, góp ý gì, đã sửa gì. -->

## Checklist trước khi mở PR

- [ ] `git switch main` và `git pull` trước khi tạo nhánh
- [ ] `uv run ruff check .`, `uv run ruff format .`, `uv run pytest -q` đều xanh
- [ ] `git status` chỉ có file mình định commit, không có `.env`, `data/`, CV thật
- [ ] Tiêu đề `[TASK-xxx] ...`, mô tả có `Closes #n`
- [ ] Chọn reviewer không phải chính mình, hoặc để CODEOWNERS tự mời
