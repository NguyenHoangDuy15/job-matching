-- Migration 0020 — bổ sung cho 0019: role api_metrics_writer thiếu quyền USAGE trên schema app,
-- nên phép ép kiểu %s::app.app_role trong INSERT của middleware (src/api/metrics.py) bị
-- "permission denied for schema app" và mọi số đo bị bỏ. Chỉ cấp USAGE (thấy được kiểu app_role),
-- không cấp quyền đọc/ghi bảng nào trong app. Chạy lại nhiều lần được. Cần 0019.

grant usage on schema app to api_metrics_writer;
