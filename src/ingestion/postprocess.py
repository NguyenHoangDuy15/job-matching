"""Bước sau khi tin vào DB, dùng chung cho MỌI đường nạp tin (crawl.py, TopCV sync, nạp JSONL…).

③ (S2-D06) gắn kỹ năng + mức (bắt buộc / ưu tiên / chỉ nhắc) cho tin mới / đổi nội dung trong
   lượt, cùng mọi tin đang mở chưa có thẻ hoặc gắn bằng từ điển / luật cũ.
④ (S3-D07) vector hóa theo đoạn cho tin mới / đổi, cùng mọi tin đang mở còn thiếu vector.

Hai bước chọn tin theo trạng thái trong DB chứ không theo nguồn, nên tin vào bằng đường nào
(kể cả đường chưa gọi hàm này) cũng được làm ở lượt chạy kế tiếp. Chạy riêng (lưới an toàn,
workflow `post-ingest`):

    uv run python scripts/postprocess.py                 # ③ + ④
    uv run python scripts/postprocess.py --skip-embed    # chỉ ③

Lỗi ở bước phụ không làm mất dữ liệu đã nạp: rollback, báo False để job báo thất bại.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS_YAML = ROOT / "config" / "skills.yaml"
SKILLS_SEED = ROOT / "db" / "seed" / "seed_skills.sql"


def _log(msg: str) -> None:
    print(msg, flush=True)


def yaml_skill_slugs(path: Path = SKILLS_YAML) -> set[str]:
    """Các kỹ năng (level 2–3) mà bộ gắn có thể trả về; level 1 là nhóm, không ghi vào DB."""
    from skillkit import load_taxonomy

    return {s.id for s in load_taxonomy(path) if s.level > 1}


def sync_skill_seed(conn, seed_path: Path = SKILLS_SEED, yaml_path: Path = SKILLS_YAML) -> int:
    """Từ điển trong repo đổi (thêm / bỏ kỹ năng) mà ref.skills chưa theo kịp thì nạp lại seed
    (sinh từ config/skills.yaml, chạy lại an toàn). Không làm thế, kỹ năng mới bị bỏ khi ghi
    (`thieu_trong_ref_skills`) và tin thiếu thẻ. Trả số kỹ năng lệch trước khi nạp (0 = khớp)."""
    want = yaml_skill_slugs(yaml_path)
    have = {r[0] for r in conn.execute("select slug from ref.skills where is_active").fetchall()}
    diff = len(want ^ have)
    if diff:
        conn.execute(seed_path.read_text(encoding="utf-8"))
        conn.commit()
        _log(
            f"== từ điển: ref.skills lệch {diff} kỹ năng so với config/skills.yaml "
            f"(thiếu {len(want - have)}, thừa {len(have - want)}) → đã nạp lại seed =="
        )
    return diff


def label_skills(store) -> bool:
    """Bước ③. Trả False nếu lỗi."""
    from skillkit.levels.db import has_levels_schema, label_and_write, select_jobs
    from skillkit.levels.pipeline import SkillLabeler

    conn = store.conn
    changed_ids = list(getattr(store, "changed_job_ids", []) or [])
    try:
        if not has_levels_schema(conn):
            conn.rollback()
            _log("! DB chưa chạy 0005_job_skill_levels.sql: bỏ qua bước gắn kỹ năng.")
            return True
        sync_skill_seed(conn)
        labeler = SkillLabeler.default()
        version = labeler.model_version
        rows = {
            r[0]: r for r in select_jobs(conn, model_version=version, only_open=True, stale=True)
        }
        if changed_ids:
            changed = select_jobs(conn, model_version=version, ids=changed_ids)
            rows.update({r[0]: r for r in changed})
        stats = label_and_write(conn, labeler, list(rows.values()))
        conn.commit()
    except Exception as exc:  # không để bước phụ làm hỏng lượt nạp tin
        conn.rollback()
        _log(f"  ✗ gắn kỹ năng lỗi: {exc!r}")
        return False
    tier2 = "có Tầng 2" if labeler.clf else "chỉ luật (không có file model)"
    _log(
        f"== kỹ năng ({version}, {tier2}) ==\n"
        f"  tin đổi trong lượt: {len(changed_ids)} · đã gắn: {stats.get('tin', 0)} tin · "
        f"bắt buộc {stats.get('required', 0)} · ưu tiên {stats.get('preferred', 0)} · "
        f"chỉ nhắc {stats.get('mentioned', 0)}"
    )
    return True


def embed(store) -> bool:
    """Bước ④. Chưa cấu hình model thì bỏ qua. Hết quota / lỗi mạng: dừng gọn, lượt sau làm tiếp."""
    from embedding.embedder import from_env
    from embedding.store import coverage_report, embed_jobs, prune_closed

    conn = store.conn
    try:
        embedder = from_env()
        if embedder is None:
            _log("== vector: chưa cấu hình EMBEDDER / CF_API_TOKEN, bỏ qua ==")
            return True
        stats = embed_jobs(conn, embedder)
        pruned = prune_closed(conn)
        report = coverage_report(conn, embedder.model)
    except Exception as exc:  # cả EmbedderError
        conn.rollback()
        _log(f"  ✗ vector hóa lỗi: {exc!r}")
        return False
    _log(
        f"== vector ({embedder.model}) ==\n"
        f"  cần làm {stats.get('can_lam', 0)} tin · đã ghi {stats.get('da_ghi_tin', 0)} tin "
        f"({stats.get('da_ghi_doan', 0)} đoạn) · dọn {pruned} đoạn tin đóng · "
        f"độ phủ {report['pct']}% ({report['with_vectors']}/{report['open_jobs']})"
        + (" · DỪNG GIỮA CHỪNG (lượt sau làm tiếp)" if stats.get("dung_vi") else "")
    )
    return not stats.get("dung_vi")


def run_post_steps(store, *, skills: bool = True, vectors: bool = True) -> bool:
    """③ rồi ④. Thẻ kỹ năng nằm trong đoạn tóm tắt nên ④ chạy sau ③. True nếu cả hai ổn."""
    ok = True
    if skills:
        ok = bool(label_skills(store)) and ok
    if vectors:
        ok = bool(embed(store)) and ok
    return ok


def main(argv: list[str] | None = None) -> int:
    from ingestion.crawl import _database_url, load_env_file
    from ingestion.store import PgStore

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-skills", action="store_true", help="không gắn kỹ năng")
    parser.add_argument("--skip-embed", action="store_true", help="không vector hóa")
    args = parser.parse_args(argv)
    load_env_file()
    dsn = _database_url()
    if not dsn:
        parser.error("thiếu DATABASE_URL (biến môi trường hoặc file .env)")
    store = PgStore(dsn)
    try:
        ok = run_post_steps(store, skills=not args.skip_skills, vectors=not args.skip_embed)
    finally:
        store.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
