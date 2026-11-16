# Image chung cho api, ui (TASK-H002) và pipeline crawl khi chạy trên Cloud Run Job
# (phương án GCP của S2-T05; lịch hằng ngày hiện chạy bằng GitHub Actions).
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src

# Cài thư viện trước, copy code sau: sửa code không phải cài lại thư viện (cache layer).
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY ui ./ui
COPY config ./config
# Bảng 34 tỉnh: ingestion.location và bộ che PII (S3-D03) đọc từ file seed khi không có DB.
COPY db/seed ./db/seed
# Pipeline crawl: python scripts/crawl.py run ... (lệnh đặt ở scripts/deploy_crawl_job.sh).
COPY scripts ./scripts
# Model Tầng 2 (models/jev_local_v1.joblib) không nằm trên git: có trên máy build thì vào image,
# không có thì bước gắn kỹ năng chỉ chạy bằng luật.
COPY models ./models

# Mặc định: API đọc CV (S3-D05). Cổng lấy từ $PORT: Cloud Run đặt sẵn; Hugging Face Spaces dùng
# app_port 7860. Pipeline crawl ghi đè lệnh này (--command python --args scripts/crawl.py,...).
EXPOSE 7860
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers"]
