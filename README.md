# Job Matching – Team 5

Matching CV–JD hai chiều: ứng viên nhận K JD phù hợp nhất, HR lọc N CV phù hợp nhất; giải thích được, có benchmark.

| Thành viên | Vai trò |
| --- | --- |
| Nguyễn Hoàng Duy | Tech lead, Ranking, Backend API |
| Đào Việt Tùng | Data, Retrieval |
| Nguyễn Xuân Thịnh | Đánh giá, UI, QA, DevOps |

## Bắt đầu

Cần Python 3.11 và uv.

    uv sync
    cp .env.example .env
    uv run pytest

## Cấu trúc

- `config/` cấu hình: skills.yaml, ranker_config.yaml, sources.yaml
- `src/` mỗi thư mục là một module; module chỉ gọi nhau qua hàm công khai trong `__init__.py`
- `dbt/`, `dags/`, `ui/` – F2, Airflow, Streamlit
- `tests/` unit, integration, perf
- `docs/adr/` quyết định kiến trúc
- `data/` KHÔNG lên git

## Quy ước

- `main` được bảo vệ. Mỗi hạng mục một nhánh `feat/<mã>-<mô-tả>`, ví dụ `feat/D1.1-skillkit-schema`.
- PR cần 1 người duyệt, test và ruff xanh, nên dưới 400 dòng.
- Không commit `.env`, `kaggle.json`, API key, CV thật. Không log nội dung CV. Không gửi PII cho LLM.
- Trọng số, ngưỡng, nguồn nằm trong `config/*.yaml`, không viết cứng trong code.
