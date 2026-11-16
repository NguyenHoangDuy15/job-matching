"""API đọc CV (S3-D05). Chạy: uvicorn api.main:app --host 0.0.0.0 --port $PORT

Khởi động: tạo nhóm tiến trình đọc CV và nạp sẵn mô hình (Presidio/spaCy, từ điển kỹ năng) để
request đầu không phải chờ. /health báo `warm` khi đã sẵn sàng.
"""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.cv import router as cv_router
from api.settings import get_settings
from api.worker import ParsePool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not hasattr(app.state, "pool"):  # test có thể gắn sẵn pool riêng
        app.state.pool = ParsePool(settings.parse_workers, settings.parse_timeout_s)
    app.state.warm = False

    def warm() -> None:
        app.state.warm = app.state.pool.warm()

    threading.Thread(target=warm, daemon=True).start()  # không chặn cổng mở (Cloud Run/HF đợi)
    yield
    app.state.pool.close()


app = FastAPI(title="Job Matching API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().origins,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(cv_router)


@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
    body = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
    return JSONResponse(body, status_code=exc.status_code)


@app.get("/health")
def health(request: Request) -> dict:
    return {"status": "ok", "warm": bool(getattr(request.app.state, "warm", False))}
