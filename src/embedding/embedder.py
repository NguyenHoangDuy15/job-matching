"""Nơi tính vector (S3-D07). Mọi vector 1024 chiều, chuẩn hóa L2 (cosine = tích vô hướng).

    embedder = from_env()          # EMBEDDER=workers_ai | local | fake
    vectors = embedder.embed(["…", "…"])

- WorkersAIEmbedder: Cloudflare Workers AI `@cf/baai/bge-m3`. Miễn phí 10.000 neurons/ngày, không
  cần GPU; crawl (GitHub Actions) và API CV (Hugging Face) gọi chung nên vector luôn cùng model.
  Cần CF_ACCOUNT_ID + CF_API_TOKEN (quyền Workers AI: Read).
- LocalEmbedder: BAAI/bge-m3 qua sentence-transformers trên CPU (khoảng 2,2 GB; cài riêng:
  `uv run --with sentence-transformers ...`). Dùng cho spike / khi không có Workers AI.
- FakeEmbedder: vector giả xác định từ hash, cho test (không mạng).

Cột core.job_chunks.model ghi `Embedder.model`; chỉ so vector cùng model (không trộn nơi chạy).
"""

import hashlib
import math
import os
import time
from typing import Protocol

import httpx

DIM = 1024


class EmbedderError(RuntimeError):
    """Không tính được vector (hết quota, mạng, cấu hình): dừng gọn, lượt sau làm tiếp."""


class Embedder(Protocol):
    model: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _normalize(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class FakeEmbedder:
    model = "fake/hash-1024"
    dim = DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            seed = hashlib.sha256(t.encode()).digest()
            raw = [((seed[i % 32] + i * 31) % 255) / 127.0 - 1.0 for i in range(DIM)]
            out.append(_normalize(raw))
        return out


class WorkersAIEmbedder:
    model = "cf/baai/bge-m3"
    dim = DIM

    def __init__(
        self,
        account_id: str,
        api_token: str,
        *,
        batch_size: int = 50,
        retries: int = 4,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.retries = retries
        self._http = httpx.Client(
            base_url=f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run",
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=60,
            transport=transport,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            out += self._batch(texts[i : i + self.batch_size])
        return out

    def _batch(self, texts: list[str]) -> list[list[float]]:
        delay = 2.0
        for attempt in range(self.retries + 1):
            try:
                r = self._http.post("/@cf/baai/bge-m3", json={"text": texts})
            except httpx.HTTPError as e:
                if attempt == self.retries:
                    raise EmbedderError(f"mạng: {type(e).__name__}") from None
            else:
                if r.status_code == 200:
                    data = r.json().get("result", {}).get("data")
                    if not isinstance(data, list) or len(data) != len(texts):
                        raise EmbedderError("Workers AI trả kết quả không đúng dạng")
                    if any(len(v) != DIM for v in data):
                        raise EmbedderError("Workers AI trả vector không phải 1024 chiều")
                    return [_normalize(v) for v in data]
                if r.status_code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise EmbedderError(f"Workers AI HTTP {r.status_code}")
            time.sleep(delay)
            delay *= 2
        raise EmbedderError("Workers AI: hết số lần thử")


class LocalEmbedder:
    model = "hf/BAAI/bge-m3"
    dim = DIM

    def __init__(self, batch_size: int = 16) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise EmbedderError(
                "chưa cài sentence-transformers: uv run --with sentence-transformers ..."
            ) from None
        self._model = SentenceTransformer("BAAI/bge-m3")
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False
        )
        return [list(map(float, v)) for v in vectors]


def from_env() -> Embedder | None:
    """Theo biến EMBEDDER (workers_ai | local | fake). None nếu chưa cấu hình (bước bị bỏ qua)."""
    kind = os.environ.get("EMBEDDER", "workers_ai" if os.environ.get("CF_API_TOKEN") else "")
    if kind == "workers_ai":
        account, token = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
        if not account or not token:
            raise EmbedderError("thiếu CF_ACCOUNT_ID / CF_API_TOKEN")
        return WorkersAIEmbedder(account, token)
    if kind == "local":
        return LocalEmbedder()
    if kind == "fake":
        return FakeEmbedder()
    return None
