# Vòng PR của Duy (TASK-D004, US-01.02)

Hướng dẫn đầy đủ ở [git-pr.md](git-pr.md); file này là bản tóm tắt để tra nhanh.

1. Tạo nhánh từ `main` mới: `git switch main && git pull && git switch -c feat/TASK-xxx-mo-ta`.
2. Commit đúng file: `git status`, `git add <file>`, `git commit -m "..."`.
3. Push: `git push -u origin <nhánh>`.
4. Mở PR: `gh pr create --base main --title "[TASK-xxx] ..."`, mô tả có `Closes #<issue>`.
5. Issue chỉ tự đóng khi PR merge vào `main`; PR merge vào nhánh khác thì phải đóng bằng tay.
6. Giải xung đột: `git fetch origin && git merge origin/main`, sửa file, chạy `git diff --check`, rồi `git add` và `git commit`.
7. Muốn giữ commit giải xung đột trên `main` thì merge bằng `gh pr merge --merge`; squash sẽ gộp mất commit đó.
