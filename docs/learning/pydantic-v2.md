# Pydantic v2 + PyYAML (spike TASK-D001)

- Người học: Duy · Sprint: S1 · Ngày: 03/11/2026 · Issue: #9
- Mã nguồn: `tests/learning/test_pydantic.py` (chỉ để học; taxonomy thật là D1.1)
- Môi trường: macOS, Python 3.11, Pydantic 2.14.2, PyYAML 6.0.3

## Chạy thử

    uv run pytest tests/learning/test_pydantic.py -v    # 3 passed

Ba test nạp YAML bằng `yaml.safe_load` → `Skill.model_validate` và chờ `ValidationError`: level ngoài {1, 2, 3}, `ambiguous: true` thiếu `context`, `id` toàn khoảng trắng. Đã thử tắt từng validator: đúng một test tương ứng đỏ.

## Bảng v1 → v2

| v1 | v2 |
| --- | --- |
| `m.dict()` / `m.json()` | `m.model_dump()` / `m.model_dump_json()` |
| `Model.parse_obj(d)` | `Model.model_validate(d)` |
| `@validator("x")` | `@field_validator("x")` + `@classmethod` |
| `@root_validator` | `@model_validator(mode="before" \| "after")` |
| `class Config: extra = "forbid"` | `model_config = ConfigDict(extra="forbid")` |
| `Optional[X]` tự có mặc định `None` | Phải viết `X \| None = None`, không thì là bắt buộc |
| Gán lại field: `allow_mutation = False` | `ConfigDict(frozen=True)` |

## Bẫy đã gặp

1. **`field_validator` không chạy với giá trị mặc định.** Viết luật "ambiguous thì phải có context" bằng `field_validator("context")` thì YAML thiếu hẳn `context` vẫn qua (đã thử: `ambiguous=True context=[]`). Dùng `model_validator(mode="after")`, hoặc `Field(validate_default=True)`.
2. **`model_validator(mode="after")` không chạy nếu field đã lỗi.** `{"level": 9, "ambiguous": True}` chỉ báo 1 lỗi (level); sửa level xong mới thấy lỗi context.
3. **YAML 1.1 tự đổi kiểu:** `no`/`yes`/`on`/`off` → bool, `1.10` → `1.1`, `C #sharp` → `'C'` (sau ` #` là comment; `C#` liền thì không sao). Alias kiểu này phải để trong ngoặc kép.
4. **Lax mode tự ép kiểu:** `level: "2"` thành `2`. Muốn chặn: `model_validate(..., strict=True)` → lỗi `int_type`.
5. **`yaml.load` không có `Loader` thì lỗi** (PyYAML 6). Luôn dùng `yaml.safe_load`: chỉ tạo dict/list/str/số, không dựng object Python tùy ý.
6. Default `[]` trong model **không** dùng chung giữa các instance như default của hàm (Pydantic copy), nên viết thẳng được.

## Quyết định mang sang D1.1 (taxonomy.py)

- `yaml.safe_load` + `Skill.model_validate`; `ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)` để bắt gõ sai tên trường và không sửa skill sau khi nạp.
- Luật một trường → `field_validator`; luật nhiều trường → `model_validator(mode="after")`. Thông điệp lỗi luôn kèm `id`.
- Luật level/parent: level 1 không có parent; level 2, 3 bắt buộc có parent. Kiểm "parent tồn tại và đúng level ngay trên", trùng id/alias, vòng lặp phải làm ở mức cả cây trong taxonomy.py, không làm được trong một `Skill`.
- Đề xuất (chốt ở D1.1): nạp `skills.yaml` với `strict=True` để YAML ghi `level: "2"` bị báo thay vì âm thầm ép kiểu.
