"""Tính vector tin tuyển dụng theo đoạn → core.job_chunks (S3-D07, EN-03).

    uv run python scripts/embed_jobs.py --report                  # độ phủ hiện tại (AC: 100%)
    uv run python scripts/embed_jobs.py                           # chạy thử: đếm tin / đoạn cần làm
    uv run python scripts/embed_jobs.py --apply --prune           # lấp đầy toàn kho + dọn tin đóng

Khóa Workers AI: trên máy để CF_ACCOUNT_ID, CF_API_TOKEN trong .env (đã gitignore); trên GitHub
Actions là secret cùng tên. Biến môi trường luôn được ưu tiên hơn .env.
    uv run python scripts/embed_jobs.py --knn "xây dựng pipeline dữ liệu"   # thử truy vấn top-10

Tin mới crawl được làm tự động ở bước ④ sau crawl (ingestion.crawl). Chạy lại nhiều lần được:
đoạn không đổi thì không gọi model.
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from embedding.embedder import EmbedderError, FakeEmbedder, from_env  # noqa: E402
from embedding.store import coverage_report, embed_jobs, prune_closed  # noqa: E402
from ingestion.crawl import _database_url, load_env_file  # noqa: E402


def knn(conn, embedder, query: str, k: int = 10) -> tuple[list[tuple], float]:
    """Top-k tin gần nhất theo cosine (index HNSW), mỗi tin lấy đoạn gần nhất."""
    from embedding.store import _vector_literal

    vec = _vector_literal(embedder.embed([query])[0])
    t = time.perf_counter()
    dist = "c.embedding OPERATOR(extensions.<=>) %(v)s::extensions.halfvec"  # cosine, index HNSW
    rows = conn.execute(
        f"""select j.id, j.title, c.section, round((1 - ({dist}))::numeric, 3)
              from (select c.job_id, c.section, c.embedding from core.job_chunks c
                     where c.model = %(m)s order by {dist} limit %(n)s) c
              join core.jobs j on j.id = c.job_id""",
        {"v": vec, "m": embedder.model, "n": k * 3},
    ).fetchall()
    ms = (time.perf_counter() - t) * 1000
    seen, out = set(), []
    for row in rows:
        if row[0] not in seen:
            seen.add(row[0])
            out.append(row)
    return out[:k], ms


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="tính vector và ghi DB")
    parser.add_argument("--limit", type=int, help="chỉ làm N tin (thử)")
    parser.add_argument("--prune", action="store_true", help="xóa đoạn của tin đóng quá 30 ngày")
    parser.add_argument("--report", action="store_true", help="chỉ in độ phủ")
    parser.add_argument("--knn", help="thử truy vấn top-10 bằng câu này")
    args = parser.parse_args(argv)
    load_env_file()  # trên máy: đọc CF_ACCOUNT_ID / CF_API_TOKEN từ .env (gitignore)
    dsn = _database_url()
    if not dsn:
        parser.error("thiếu DATABASE_URL")
    try:
        embedder = from_env()
    except EmbedderError as e:
        parser.error(str(e))

    import psycopg

    with psycopg.connect(dsn.replace("+psycopg", ""), prepare_threshold=None) as conn:
        if args.knn:
            if embedder is None or isinstance(embedder, FakeEmbedder):
                parser.error("--knn cần model thật (EMBEDDER=workers_ai hoặc local)")
            times = []
            for _ in range(5):
                rows, ms = knn(conn, embedder, args.knn)
                times.append(ms)
            print(f"top-10 cho {args.knn!r} · truy vấn DB p50 {statistics.median(times):.0f} ms")
            for jid, title, section, sim in rows:
                print(f"  {sim}  {jid:>6}  [{section}] {title[:70]}")
            return 0
        if not args.report:
            if embedder is None:
                print("Chưa cấu hình EMBEDDER (workers_ai cần CF_ACCOUNT_ID + CF_API_TOKEN).")
                if args.apply:
                    return 2
                embedder = FakeEmbedder()  # chạy thử chỉ để đếm tin / đoạn cần làm
            stats = embed_jobs(conn, embedder, limit=args.limit, apply=args.apply)
            print(f"model: {embedder.model} · {dict(stats)}")
            if args.prune and args.apply:
                print(f"đã dọn {prune_closed(conn)} đoạn của tin đóng quá 30 ngày")
            if not args.apply:
                print("Chưa ghi gì (chạy lại với --apply).")
        report = coverage_report(conn, embedder.model if embedder else None)
        print(
            f"Tin đang mở: {report['open_jobs']} · có vector: {report['with_vectors']} "
            f"({report['pct']}%, mục tiêu 100%) · {report['chunks_open']} đoạn "
            f"(trung bình {report['avg_chunks']}/tin) · bảng {report['table_mb']} MB · "
            f"model {report['models']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
