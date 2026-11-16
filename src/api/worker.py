"""Nhóm tiến trình đọc CV có TIMEOUT CỨNG (S3-D05; việc S3-D01 để lại).

PDFium là thư viện C: thread không ngắt được, PDF độc hại có thể làm treo. Mỗi worker là một tiến
trình riêng đã nạp sẵn mô hình (warm_up), nhận việc qua Pipe. Quá `timeout` thì kill tiến trình đó,
tạo tiến trình mới thay, và báo TimeoutError: request vẫn trả lời đúng hạn, API không treo.

`size = 0`: chạy thẳng trong tiến trình hiện tại (test, máy yếu) — không có timeout cứng.
"""

import multiprocessing as mp
import queue
import threading
from datetime import date


def _serve(conn) -> None:  # chạy trong tiến trình con
    from cvparser.pipeline import parse_cv, warm_up

    warm_up()
    conn.send(("ready", None))
    while True:
        try:
            job = conn.recv()
        except EOFError:
            return
        try:
            conn.send(("ok", parse_cv(**job)))
        except Exception as e:  # lỗi lập trình: chỉ gửi tên lớp, không gửi nội dung
            conn.send(("error", type(e).__name__))


class _Worker:
    def __init__(self, ctx) -> None:
        self.conn, child = ctx.Pipe()
        self.proc = ctx.Process(target=_serve, args=(child,), daemon=True)
        self.proc.start()
        child.close()
        self.ready = False

    def wait_ready(self, timeout: float) -> bool:
        """True khi tiến trình đã nạp xong mô hình; False nếu chưa xong hoặc đã chết."""
        try:
            if not self.ready and self.conn.poll(timeout):
                self.ready = self.conn.recv()[0] == "ready"
        except (EOFError, OSError):
            self.ready = False
        return self.ready

    def kill(self) -> None:
        self.proc.kill()
        self.proc.join(timeout=2)
        self.conn.close()


class ParsePool:
    def __init__(self, size: int = 1, timeout: float = 10.0) -> None:
        self.size = size
        self.timeout = timeout
        self._ctx = mp.get_context("spawn")
        self._idle: queue.Queue[_Worker] = queue.Queue()
        self._lock = threading.Lock()
        for _ in range(size):
            self._idle.put(_Worker(self._ctx))

    def warm(self, timeout: float = 120.0) -> bool:
        """Chờ mọi worker nạp xong mô hình (gọi khi khởi động API)."""
        if self.size == 0:
            from cvparser.pipeline import warm_up

            warm_up()
            return True
        workers = [self._idle.get() for _ in range(self.size)]
        ok = all(w.wait_ready(timeout) for w in workers)
        for w in workers:
            self._idle.put(w)
        return ok

    def run(
        self, data: bytes, *, filename: str | None, known_names: tuple[str, ...], as_of: date
    ) -> dict:
        job = {"data": data, "filename": filename, "known_names": known_names, "as_of": as_of}
        if self.size == 0:
            from cvparser.pipeline import parse_cv

            return parse_cv(**job)
        worker = self._idle.get(timeout=self.timeout)  # đợi worker rảnh, cũng tính vào hạn
        if not worker.wait_ready(60):  # chết lúc nạp mô hình: thay worker, báo lỗi hệ thống
            worker.kill()
            self._idle.put(_Worker(self._ctx))
            raise RuntimeError("worker_unavailable")
        try:
            worker.conn.send(job)
            if not worker.conn.poll(self.timeout):
                raise TimeoutError
            kind, payload = worker.conn.recv()
        except (TimeoutError, EOFError, BrokenPipeError, OSError):
            worker.kill()
            worker = _Worker(self._ctx)  # thay worker hỏng / treo; nạp lại ở nền
            raise TimeoutError from None
        finally:
            self._idle.put(worker)
        if kind != "ok":
            raise RuntimeError(payload)
        return payload

    def close(self) -> None:
        while not self._idle.empty():
            self._idle.get_nowait().kill()
