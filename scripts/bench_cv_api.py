"""Đo thời gian POST /cv/parse (S3-D05: "API trả hồ sơ ≤ 15 giây").

    # Tại máy: API thật (FastAPI + tiến trình đọc CV thật, nạp sẵn mô hình), Supabase giả
    uv run python scripts/bench_cv_api.py local --rounds 3

    # API đã triển khai: CV đã tải lên qua web, JWT của tài khoản thử (KHÔNG commit token)
    API_URL=https://... CV_TOKEN=eyJ... uv run python scripts/bench_cv_api.py url <cv_id> <cv_id>...

In thời gian khởi động (nạp mô hình), từng request, p50/p95/max. Không in nội dung CV.
"""

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SAMPLES = ROOT / "tests" / "fixtures" / "cv" / "samples"
LIMIT_S = 15.0


def summary(name: str, seconds: list[float]) -> dict:
    s = sorted(seconds)
    p95 = s[min(len(s) - 1, round(0.95 * (len(s) - 1)))]
    out = {
        "n": len(s),
        "p50_s": round(statistics.median(s), 3),
        "p95_s": round(p95, 3),
        "max_s": round(s[-1], 3),
        "under_15s": sum(x <= LIMIT_S for x in s),
    }
    print(f"{name}: {json.dumps(out)}")
    return out


def cmd_local(args) -> int:
    from datetime import UTC, datetime, timedelta

    import httpx
    import jwt
    from cryptography.hazmat.primitives.asymmetric import ec
    from fastapi.testclient import TestClient

    from api import cv as cv_module
    from api.main import app
    from api.settings import Settings, get_settings
    from api.worker import ParsePool

    url, uid = "https://bench.supabase.co", "00000000-0000-0000-0000-00000000000a"
    key = ec.generate_private_key(ec.SECP256R1())
    files = {p.stem: p.read_bytes() for p in sorted(SAMPLES.iterdir())}
    current = {"file": b""}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/claim_cv_parse"):
            row = {"storage_path": f"u/{uid}/x.pdf", "mime": "", "size_bytes": 0}
            return httpx.Response(200, json=[row])
        if path.endswith("/save_cv_profile"):
            return httpx.Response(200, json=len(json.loads(request.content)["p_skills"]))
        if "/storage/" in path:
            time.sleep(args.network_ms / 1000)  # giả lập tải file từ Storage
            return httpx.Response(200, content=current["file"])
        return httpx.Response(204)

    settings = Settings(
        supabase_url=url, supabase_publishable_key="x", rate_limit_per_minute=10_000
    )
    app.dependency_overrides[get_settings] = lambda: settings

    class _Jwks:
        def get_signing_key_from_jwt(self, _token):
            return type("K", (), {"key": key.public_key()})()

    app.state.jwks = _Jwks()
    app.state.supabase_transport = httpx.MockTransport(handler)
    t = time.perf_counter()
    app.state.pool = ParsePool(size=args.workers, timeout=10)
    app.state.pool.warm()
    startup = time.perf_counter() - t
    print(f"khởi động + nạp mô hình ({args.workers} tiến trình): {startup:.2f} giây")
    token = jwt.encode(
        {"sub": uid, "aud": "authenticated", "iss": f"{url}/auth/v1",
         "exp": datetime.now(UTC) + timedelta(hours=1), "account_status": "active"},
        key, algorithm="ES256",
    )  # fmt: skip
    client = TestClient(app)
    cv_module.limiter._hits.clear()
    seconds = []
    for _ in range(args.rounds):
        for name, data in files.items():
            current["file"] = data
            t = time.perf_counter()
            r = client.post(
                "/cv/parse",
                json={"cv_id": "11111111-1111-1111-1111-111111111111"},
                headers={"Authorization": f"Bearer {token}"},
            )
            seconds.append(time.perf_counter() - t)
            if r.status_code != 200:
                print(f"  {name}: HTTP {r.status_code} {r.json().get('error')}")
    app.state.pool.close()
    result = summary(f"POST /cv/parse ({len(files)} CV × {args.rounds} lượt)", seconds)
    return 0 if result["under_15s"] == result["n"] else 1


def cmd_url(args) -> int:
    import httpx

    api, token = os.environ.get("API_URL"), os.environ.get("CV_TOKEN")
    if not api or not token:
        print("cần API_URL và CV_TOKEN (JWT của tài khoản thử)")
        return 2
    t = time.perf_counter()
    health = httpx.get(f"{api.rstrip('/')}/health", timeout=180).json()
    print(f"/health: {health} sau {time.perf_counter() - t:.1f} giây (gồm khởi động nếu đang ngủ)")
    seconds = []
    for cv_id in args.cv_ids:
        t = time.perf_counter()
        r = httpx.post(
            f"{api.rstrip('/')}/cv/parse",
            json={"cv_id": cv_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        seconds.append(time.perf_counter() - t)
        body = r.json()
        skills = len((body.get("profile") or {}).get("skills", []))
        outcome = body.get("error") or body.get("status")
        print(f"  {cv_id[:8]}… HTTP {r.status_code} {outcome} {seconds[-1]:.2f}s skills={skills}")
    result = summary("POST /cv/parse (triển khai thật)", seconds)
    return 0 if result["under_15s"] == result["n"] else 1


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    local = sub.add_parser("local")
    local.add_argument("--rounds", type=int, default=3)
    local.add_argument("--workers", type=int, default=1)
    local.add_argument("--network-ms", type=int, default=300, help="độ trễ giả lập tải file")
    remote = sub.add_parser("url")
    remote.add_argument("cv_ids", nargs="+")
    args = parser.parse_args(argv)
    return cmd_local(args) if args.cmd == "local" else cmd_url(args)


if __name__ == "__main__":
    sys.exit(main())
