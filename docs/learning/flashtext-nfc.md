# Unicode NFC + flashtext (spike TASK-D006)

- Người học: Duy · Sprint: S1 · Ngày: 05/11/2026
- Mã nguồn: `src/skillkit/normalize.py` (dùng thật), `tests/unit/test_normalize.py` (cấu hình flashtext ở đây chỉ để thử)
- Môi trường: Python 3.11, flashtext 2.7

## Chạy thử

    uv run pytest tests/unit/test_normalize.py    # 10 passed

`normalize_text` làm theo thứ tự: NFC → chữ thường → gộp khoảng trắng. Văn bản và từ khóa phải đi qua cùng một hàm: `lập trình` dạng NFD không khớp từ khóa dạng NFC.

## Kết quả thử `non_word_boundaries`

Mọi văn bản đã qua `normalize_text`.

| Văn bản | Mặc định | Thêm `+ # .` | Thêm `+ #` + chữ có dấu |
| --- | --- | --- | --- |
| `c++, c#, .net, go, google` | đúng 4 kỹ năng | đúng 4 kỹ năng | đúng 4 kỹ năng |
| `biết c++ và c#.` | `c++`, `c#` | mất `c#` | `c++`, `c#` |
| `go.` | `go` | mất `go` | `go` |
| `cơ sở dữ liệu` | nhầm `c` | nhầm `c` | không khớp (đúng) |
| `rất tốt` | nhầm `r` | nhầm `r` | không khớp (đúng) |
| `c+ a+` | nhầm `c` | không khớp (đúng) | không khớp (đúng) |

## Bẫy

1. **Chữ có dấu là ranh giới từ.** Mặc định flashtext chỉ coi chữ ASCII, số và `_` là thuộc về từ, nên `cơ` khớp `c`, `rất` khớp `r`.
2. **Thêm `.` làm mất kỹ năng cuối câu.** Không cần thêm: `node.js` và `.net` vẫn khớp vì dấu chấm nằm trong từ khóa.
3. **`c++17` không khớp `c++`,** vì chữ số thuộc về từ. Bỏ chữ số khỏi `non_word_boundaries` thì khớp, nhưng `c4`, `r2`, `go1` cũng thành `c`, `r`, `go`.
4. **`split()` gộp được NBSP nhưng không bỏ ký tự zero-width** (`a` + `U+200B` + `b` vẫn là một từ). Chưa xử lý; thêm khi gặp trong dữ liệu thật.

## Quyết định

- `non_word_boundaries` = mặc định + `+`, `#` + chữ có dấu (`U+00C0` đến `U+1EFF`). Không thêm `.`.
- Phiên bản viết liền khai báo bằng alias trỏ về tên chuẩn: `add_keyword("c++17", "c++")`, trong `skills.yaml` là `aliases: [c++, c++11, c++14, c++17, c++20, c++23]`. Cách viết chưa khai báo (`c++2a`) vẫn bị bỏ sót.
- Việc còn lại khi viết phần trích kỹ năng thật: đưa cấu hình trên vào `src/skillkit`, và cho `_norm` trong `taxonomy.py` dùng `normalize_text`.
