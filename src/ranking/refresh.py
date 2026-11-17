"""Giữ một index trong RAM của API, dựng lại định kỳ ở luồng nền (K: S4-D01, E: S4-D02)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class RefreshingIndex(Generic[T]):
    """Dựng lại khi quá `refresh_seconds`; request luôn dùng bản đang có (đổi con trỏ khi bản
    mới xong), không chờ dựng lại; dựng lỗi thì giữ bản cũ, lần get sau thử lại."""

    def __init__(
        self,
        build: Callable[[], T],
        refresh_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._build = build
        self._every = refresh_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._index: T | None = None
        self._at = 0.0
        self._building = False

    def get(self) -> T:
        if self._index is None:
            with self._lock:
                if self._index is None:
                    self._index, self._at = self._build(), self._clock()
            return self._index
        if self._clock() - self._at >= self._every:
            self._refresh_in_background()
        return self._index

    def peek(self) -> T | None:
        """Bản đang có, KHÔNG chặn: chưa dựng xong lần đầu → None (API trả 503 engine_warming)
        và bắt đầu dựng ở luồng nền; quá hạn → trả bản cũ và dựng lại ở luồng nền."""
        if self._index is None or self._clock() - self._at >= self._every:
            self._refresh_in_background()
        return self._index

    @property
    def ready(self) -> bool:
        return self._index is not None

    def _refresh_in_background(self) -> None:
        with self._lock:
            if self._building:
                return
            self._building = True

        def run():
            try:
                index = self._build()
                with self._lock:
                    self._index, self._at = index, self._clock()
            except Exception:
                with self._lock:
                    self._at = self._clock()
            finally:
                with self._lock:
                    self._building = False

        threading.Thread(target=run, daemon=True).start()
