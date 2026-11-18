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
from api.match import router as match_router
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
    if not hasattr(app.state, "match_engine"):  # test có thể gắn sẵn kho tin giả
        setup_matcher(app, settings)
    yield
    app.state.pool.close()


def setup_matcher(app: FastAPI, settings) -> None:
    """S4-D04: kho tin trong RAM (BM25 + ma trận vector) qua matcher_ro, nạp ở luồng nền ngay khi
    khởi động, dựng lại mỗi giờ. Chưa cấu hình MATCHER_DATABASE_URL thì /match/jobs trả 503."""
    if not settings.matcher_database_url:
        logging.getLogger("api").warning("chưa có MATCHER_DATABASE_URL: tắt /match/jobs")
        return
    from embedding.embedder import from_env
    from ranking.engine import MatcherDB
    from ranking.refresh import RefreshingIndex
    from ranking.semantic import CvVectorCache

    db = MatcherDB(settings.matcher_database_url)
    app.state.matcher_db = db
    app.state.match_engine = RefreshingIndex(db.build_snapshot, settings.match_refresh_seconds)
    embedder = from_env()
    app.state.cv_vectors = CvVectorCache(embedder) if embedder is not None else None
    app.state.match_engine.peek()  # bắt đầu nạp ở luồng nền


app = FastAPI(title="Job Matching API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().origins,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(cv_router)
app.include_router(match_router)


@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
    body = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
    return JSONResponse(body, status_code=exc.status_code)


@app.get("/health")
def health(request: Request) -> dict:
    engine = getattr(request.app.state, "match_engine", None)
    snapshot = engine.peek() if engine is not None else None
    return {
        "status": "ok",
        "warm": bool(getattr(request.app.state, "warm", False)),
        "matcher": None
        if engine is None
        else {
            "ready": snapshot is not None,
            "corpus_size": snapshot.corpus_size if snapshot else None,
            "load_seconds": round(snapshot.load_seconds, 1) if snapshot else None,
        },
    }
