"""S4-D05: đo p95 của POST /match/jobs với 2.000 tin và 5 CV, tách thời gian từng bước.

    uv run python scripts/perf_match.py           # MATCHER_DATABASE_URL + khóa Workers AI
    uv run python scripts/perf_match.py --rpc-ms 80 --tls-ms 60 --repeat 20 --concurrency 5

Chạy endpoint thật (FastAPI TestClient → api.match): kho tin thật qua matcher_ro nhân lên
--target tin, Workers AI thật để vector hóa CV, kiểm tin còn mở bằng SQL thật. Supabase
(PostgREST, JWT người dùng) là bản giả có độ trễ đo thật: --rpc-ms mỗi lượt gọi RPC, --tls-ms
mỗi lần mở kết nối HTTPS mới (máy dev → Supabase Singapore: RTT 44 ms, bắt tay TLS 366 ms).

Kịch bản: "lần đầu" (CV chưa có vector, phải gọi model) và "lần sau" (đã lưu), N = 5/10/20/50,
có / không bộ lọc, tuần tự và --concurrency người gọi cùng lúc. In p50/p95/max tổng và từng bước
(header Server-Timing của API). Không ghi DB.
"""

import argparse
import json
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from api import match as match_module  # noqa: E402
from api import supabase as supabase_module  # noqa: E402
from api.main import app  # noqa: E402
from api.settings import Settings, get_settings  # noqa: E402
from api.worker import ParsePool  # noqa: E402
from cvparser.pipeline import parse_cv  # noqa: E402
from embedding.embedder import from_env  # noqa: E402
from ingestion.crawl import load_env_file  # noqa: E402
from ranking.engine import MatcherDB, Snapshot, load_snapshot  # noqa: E402
from ranking.semantic import CvVectorCache, SemanticIndex  # noqa: E402
from retrieval.bm25 import KeywordIndex, load_open_jobs  # noqa: E402

SAMPLES = ROOT / "tests" / "fixtures" / "cv" / "samples"
CV_FILES = ["cv01.pdf", "cv02.pdf", "cv04.pdf", "cv06.pdf", "cv09.docx"]  # 5 nghề khác nhau


def padded_snapshot(db: MatcherDB, target: int) -> tuple[Snapshot, dict[int, int]]:
    """Kho thật nhân bản lên `target` tin (id mới); trả thêm bản đồ id giả → id thật."""
    with db.connect() as conn:
        snap = load_snapshot(conn)
        docs = {d.id: d for d in load_open_jobs(conn)}
    real = sorted(snap.jobs)
    jobs, alias = dict(snap.jobs), {j: j for j in real}
    sem = snap.semantic
    ends = np.append(sem.starts[1:], sem.n_chunks)
    chunk_ids, rows = [], []
    for i, j in enumerate(sem.ids):
        chunk_ids += [int(j)] * int(ends[i] - sem.starts[i])
        rows.append(sem.matrix[sem.starts[i] : ends[i]])
    pos = {int(j): i for i, j in enumerate(sem.ids)}
    next_id, k = max(real) + 1, 0
    all_docs = [docs[j] for j in real if j in docs]
    while len(jobs) < target:
        src = real[k % len(real)]
        new = next_id + k
        jobs[new] = replace(snap.jobs[src], id=new)
        alias[new] = src
        if src in docs:
            all_docs.append(replace(docs[src], id=new))
        if src in pos:
            i = pos[src]
            chunk_ids += [new] * int(ends[i] - sem.starts[i])
            rows.append(sem.matrix[sem.starts[i] : ends[i]])
        k += 1
    semantic = SemanticIndex(chunk_ids, np.vstack(rows), sem.model)
    return Snapshot(jobs, KeywordIndex.build(all_docs), semantic), alias


class Holder:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def peek(self):
        return self.snapshot


class AliasDB:
    """Kiểm tin còn mở bằng SQL thật; id nhân bản dùng trạng thái của tin gốc."""

    def __init__(self, db: MatcherDB, alias: dict[int, int]):
        self.db, self.alias = db, alias

    def still_open(self, ids):
        real = self.db.still_open(sorted({self.alias[i] for i in ids}))
        return {i for i in ids if self.alias[i] in real}


class FakeSupabase:
    """PostgREST giả có độ trễ: mỗi RPC `rpc_ms`; dữ liệu CV từ parse_cv của CV mẫu."""

    def __init__(self, cvs: dict[str, dict], rpc_ms: float):
        self.cvs = cvs
        self.rpc_ms = rpc_ms
        self.chunks: dict[str, list] = {}
        self.lock = threading.Lock()
        self.next_id = 1

    def handler(self, request: httpx.Request) -> httpx.Response:
        time.sleep(self.rpc_ms / 1000)
        name = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content or b"{}")
        cv_id = body.get("p_cv_id")
        if name == "get_cv_for_match":
            return httpx.Response(200, json=self.cvs[cv_id])
        if name == "get_cv_chunks":
            return httpx.Response(200, json=self.chunks.get(cv_id, []))
        if name == "get_cv_match_input":
            return httpx.Response(
                200, json={**self.cvs[cv_id], "chunks": self.chunks.get(cv_id, [])}
            )
        if name == "save_cv_chunks":
            with self.lock:
                self.chunks[cv_id] = [
                    {**c, "embedding": json.dumps(c["embedding"])} for c in body["p_chunks"]
                ]
            return httpx.Response(200, json=len(body["p_chunks"]))
        if name == "save_match":
            with self.lock:
                self.next_id += 1
                return httpx.Response(200, json=self.next_id)
        return httpx.Response(404)


def pct(values, p):
    v = sorted(values)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))]


def parse_server_timing(header: str) -> dict[str, float]:
    out = {}
    for part in (header or "").split(","):
        name, _, rest = part.strip().partition(";dur=")
        if name and rest:
            out[name] = float(rest)
    return out


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--target", type=int, default=2000)
    p.add_argument("--repeat", type=int, default=20, help="số lượt 'lần sau' mỗi CV")
    p.add_argument("--rpc-ms", type=float, default=80)
    p.add_argument("--tls-ms", type=float, default=60)
    p.add_argument("--concurrency", type=int, default=5)
    p.add_argument("--json", type=Path, help="ghi kết quả ra file")
    p.add_argument("--cvs", type=int, default=5, help="số CV mẫu (≤ 5)")
    p.add_argument(
        "--cv-json",
        type=Path,
        help="hồ sơ CV đã đọc sẵn (không nạp Presidio/spaCy: đo API so khớp chạy riêng)",
    )
    p.add_argument("--dump-cvs", type=Path, help="đọc 5 CV mẫu, ghi hồ sơ ra file rồi thoát")
    args = p.parse_args(argv)

    load_env_file()
    settings = Settings()
    if not settings.matcher_database_url:
        p.error("thiếu MATCHER_DATABASE_URL")
    embedder = from_env()
    if embedder is None:
        p.error("thiếu CF_ACCOUNT_ID / CF_API_TOKEN")

    import resource

    def rss_mb():
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return r / 1e6 if sys.platform == "darwin" else r / 1e3

    t = time.perf_counter()
    db = MatcherDB(settings.matcher_database_url)
    snapshot, alias = padded_snapshot(db, args.target)
    match_module.warm_rank(snapshot)  # như api.main.setup_matcher: làm nóng trước khi sẵn sàng
    print(
        f"Kho: {snapshot.corpus_size} tin ({sum(a == j for j, a in alias.items())} thật) · "
        f"{snapshot.semantic.n_chunks} đoạn · nạp {time.perf_counter() - t:.1f} s"
    )

    if args.cv_json:
        cvs = json.loads(args.cv_json.read_text(encoding="utf-8"))
    else:
        cvs = {}
        for i, name in enumerate(CV_FILES[: args.cvs], start=1):
            parsed = parse_cv((SAMPLES / name).read_bytes(), filename=name, as_of=date.today())
            prof = parsed["profile"]
            cv_id = f"00000000-0000-0000-0000-{i:012d}"
            cvs[cv_id] = {
                "cv_id": cv_id, "parse_status": "parsed", "target_title": prof["target_title"],
                "years_exp": prof["years_exp"], "profile_confirmed_at": None,
                "sections": parsed["sections"],
                "skills": [{"skill_id": s["skill_id"], "name": s["name"],
                            "evidence_level": s["evidence_level"]} for s in prof["skills"]],
            }  # fmt: skip
    if args.dump_cvs:
        args.dump_cvs.write_text(json.dumps(cvs, ensure_ascii=False), encoding="utf-8")
        print(f"đã ghi {len(cvs)} hồ sơ CV ra {args.dump_cvs}")
        return 0
    fake = FakeSupabase(cvs, args.rpc_ms)

    # Mỗi lần mở kết nối HTTPS mới tới Supabase tốn --tls-ms (MockTransport không có TLS).
    original_init = supabase_module.SupabaseClient.__init__

    def slow_init(self, *a, **kw):
        original_init(self, *a, **kw)
        if getattr(self, "_new_connection", True):
            time.sleep(args.tls_ms / 1000)

    supabase_module.SupabaseClient.__init__ = slow_init

    from datetime import UTC, datetime, timedelta

    import jwt
    from cryptography.hazmat.primitives.asymmetric import ec
    from fastapi.testclient import TestClient

    url = "https://perf.supabase.co"
    key = ec.generate_private_key(ec.SECP256R1())

    class _FakeJwks:  # JWT tự ký (image chạy thật không có pytest/tests)
        def get_signing_key_from_jwt(self, tok):
            return type("K", (), {"key": key.public_key()})()

    def token():
        claims = {"sub": "00000000-0000-0000-0000-00000000000a", "aud": "authenticated",
                  "iss": f"{url}/auth/v1", "exp": datetime.now(UTC) + timedelta(hours=2),
                  "user_role": "seeker", "account_status": "active"}  # fmt: skip
        return jwt.encode(claims, key, algorithm="ES256")

    URL = url

    s = Settings(supabase_url=URL, supabase_publishable_key="sb_publishable_test",
                 parse_workers=0, match_rate_limit_per_minute=10_000)  # fmt: skip
    app.dependency_overrides[get_settings] = lambda: s
    app.state.pool = ParsePool(size=0)
    app.state.jwks = _FakeJwks()
    app.state.supabase_transport = httpx.MockTransport(fake.handler)
    app.state.match_engine = Holder(snapshot)
    db.warm()  # như api.main.setup_matcher: mở sẵn kết nối lúc khởi động
    app.state.matcher_db = AliasDB(db, alias)
    app.state.cv_vectors = CvVectorCache(embedder)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token()}"}

    def call(cv_id, top_n, filters):
        t = time.perf_counter()
        r = client.post("/match/jobs", headers=headers,
                        json={"cv_id": cv_id, "top_n": top_n, "filters": filters})  # fmt: skip
        ms = (time.perf_counter() - t) * 1000
        assert r.status_code == 200, r.text
        assert len(r.json()["results"]) == top_n
        return ms, parse_server_timing(r.headers.get("server-timing", ""))

    variants = [
        (5, {}), (10, {}), (20, {}), (50, {}),
        (10, {"provinces": [1]}), (10, {"provinces": [79], "work_modes": ["onsite", "hybrid"]}),
    ]  # fmt: skip
    results: dict[str, list] = {"lần đầu": [], "lần sau": [], "đồng thời": []}
    steps: dict[str, dict[str, list]] = {k: {} for k in results}

    def record(kind, ms, timing):
        results[kind].append(ms)
        for k, v in timing.items():
            steps[kind].setdefault(k, []).append(v)

    for cv_id in cvs:  # lần đầu: CV chưa có vector
        record("lần đầu", *call(cv_id, 10, {}))
    for _ in range(args.repeat):
        for cv_id in cvs:
            top_n, flt = variants[len(results["lần sau"]) % len(variants)]
            record("lần sau", *call(cv_id, top_n, flt))
    jobs = [(cv_id, *variants[i % len(variants)]) for i in range(args.repeat) for cv_id in cvs]
    with ThreadPoolExecutor(args.concurrency) as pool:
        for ms, timing in pool.map(lambda a: call(*a), jobs):
            record("đồng thời", ms, timing)

    print(
        f"\nRPC {args.rpc_ms:.0f} ms · TLS {args.tls_ms:.0f} ms · {len(cvs)} CV · "
        "N 5/10/20/50 ± lọc"
    )
    summary = {}
    for kind, values in results.items():
        if not values:
            continue
        summary[kind] = {"n": len(values), "p50": statistics.median(values),
                         "p95": pct(values, 0.95), "max": max(values)}  # fmt: skip
        print(
            f"{kind:10} n={len(values):3} · p50 {summary[kind]['p50']:6.0f} ms · "
            f"p95 {summary[kind]['p95']:6.0f} ms · max {summary[kind]['max']:6.0f} ms"
        )
        for step, v in sorted(steps[kind].items(), key=lambda kv: -statistics.median(kv[1])):
            print(f"    {step:16} p50 {statistics.median(v):6.0f} · p95 {pct(v, 0.95):6.0f} ms")
    print(f"RAM đỉnh của tiến trình: {rss_mb():.0f} MB")
    worst = max(s["p95"] for s in summary.values())
    print(
        f"\nAC p95 ≤ 3000 ms: {'ĐẠT' if worst <= 3000 else 'CHƯA ĐẠT'} "
        f"(p95 xấu nhất {worst:.0f} ms)"
    )
    if args.json:
        out = {"args": {k: str(v) for k, v in vars(args).items()}, "summary": summary}
        args.json.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    match_module.limiter._hits.clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
