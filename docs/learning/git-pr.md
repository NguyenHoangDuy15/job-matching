# Làm 1 PR từ đầu đến cuối (job-matching)

Quy tắc repo: `main` được bảo vệ, không push thẳng. Mỗi việc một nhánh
`feat/<mã>-<mô-tả>`. PR cần 1 người approve, ruff và pytest xanh, dưới 400 dòng.

Ví dụ dưới đây là PR thêm file `docs/learning/git-pr.md`. Lệnh chạy trong CMD,
tại thư mục gốc repo.

## 7 bước

### 1. Lấy `main` mới nhất

```bat
git switch main
git pull
```

### 2. Tạo nhánh mới

```bat
git switch -c feat/docs-git-pr-guide
```

### 3. Sửa code hoặc thêm file

Ví dụ: chép `git-pr.md` vào `docs\learning\`.

### 4. Kiểm tra trước khi commit

```bat
uv run ruff check .
uv run ruff format .
uv run pytest -q
```

Cả ba phải chạy không lỗi. Nếu ruff báo lỗi, sửa rồi chạy lại.

### 5. Commit và push

```bat
git status
git add docs/learning/git-pr.md
git commit -m "docs: add git PR notes"
git push -u origin feat/docs-git-pr-guide
```

`git status` để chắc chắn chỉ add đúng file mình muốn (không có `.env`, không có `data/`).

### 6. Mở PR và xin approve

```bat
gh pr create --base main --title "docs: add git PR notes" --body "Them tai lieu git PR. Khong doi code."
```

Nếu có góp ý: sửa file, rồi `git add`, `git commit`, `git push`. PR tự cập nhật.

### 7. Merge và dọn dẹp

Khi PR có approve và CI xanh:

```bat
gh pr merge <số-PR> --squash --delete-branch
git switch main
git pull
```

## Khi có xung đột

PR báo "This branch has conflicts" nghĩa là `main` đã đổi cùng chỗ với nhánh của bạn.

```bat
git switch feat/docs-git-pr-guide
git fetch origin
git merge origin/main
```

Mở file bị báo `CONFLICT`, sẽ thấy:

```
<<<<<<< HEAD
bản của bạn
=======
bản từ main
>>>>>>> origin/main
```

Chọn giữ bản nào (hoặc gộp cả hai), xóa 3 dòng dấu `<<<<<<<`, `=======`, `>>>>>>>`, rồi:

```bat
uv run ruff check .
uv run pytest -q
git add <file-vừa-sửa>
git commit
git push
```

Muốn bỏ dở: `git merge --abort`.

## Lỗi đã gặp

| Lỗi                                  | Cách xử lý                               |
| ------------------------------------ | ---------------------------------------- |
| README hiện chữ lạ                   | Chạy `chcp 65001` rồi `type README.md`   |
| `403` / `Permission denied` khi push | Chưa có quyền ghi: xin quyền hoặc fork   |
| Push lên `main` bị từ chối           | `main` được bảo vệ: tạo nhánh `feat/...` |
| `no upstream branch`                 | `git push -u origin <tên-nhánh>`         |
| Không merge được dù CI xanh          | Thiếu approve: nhờ người khác duyệt      |

## Lệnh cứu hộ

```bat
git restore <file>             :: bỏ thay đổi chưa add
git restore --staged <file>    :: bỏ file khỏi staging
git log --oneline -5           :: xem 5 commit gần nhất
```
