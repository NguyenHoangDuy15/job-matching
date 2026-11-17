"""Gần trùng bằng MinHash/LSH (S3-T04, US-14): cùng tin đăng nhưng mỗi nơi viết khác vài chữ.

Chỉ so các tin chuẩn đang mở CÙNG CÔNG TY và CÓ CHUNG TỈNH (hoặc cả hai không có tỉnh).
Nội dung so là chức danh + mô tả đã chuẩn hóa (ingestion.dedup.normalize_description), cắt
thành cụm 3 từ liên tiếp (shingle).

  1. MinHash + LSH (datasketch) tìm nhanh các cặp có thể giống nhau ≥ 0,70
  2. Tính độ giống CHÍNH XÁC = Jaccard của hai tập shingle (MinHash chỉ là ước lượng)
  3. Quyết định:
     ≥ 0,85 và chức danh gần như trùng và đủ dài   → gộp tự động (core.merge_jobs)
     0,70–0,85, hoặc ≥ 0,85 nhưng chưa đủ chắc     → hàng chờ core.dedup_candidates cho admin
     < 0,70                                         → bỏ qua

Hai tin cùng mẫu mô tả của một công ty nhưng khác cấp bậc ("Java Developer" và "Senior Java
Developer") có thể giống nhau > 0,85; vì vậy gộp tự động còn đòi chức danh giống nhau.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from datasketch import MinHash, MinHashLSH

from ingestion.dedup import normalize_description
from ingestion.location import normalize_key

MERGE_THRESHOLD = 0.85
REVIEW_THRESHOLD = 0.70
TITLE_MERGE_THRESHOLD = 0.8  # Jaccard theo từ của chức danh, để gộp tự động
MIN_TOKENS_TO_MERGE = 30  # văn bản ngắn hơn: giống nhau là chuyện thường, chỉ đưa vào hàng chờ
SHINGLE_WORDS = 3
NUM_PERM = 128

Decision = Literal["merge", "review"]


@dataclass(frozen=True)
class JobDoc:
    id: int
    company_id: int | None
    provinces: frozenset[int]
    title: str
    text: str  # mô tả gốc (jd_text)


@dataclass(frozen=True)
class NearPair:
    job_a: int  # job_a < job_b, giống ràng buộc của core.dedup_candidates
    job_b: int
    similarity: float
    title_similarity: float
    decision: Decision


def tokens(text: str) -> list[str]:
    return normalize_description(text).split()


def shingles(words: Sequence[str], k: int = SHINGLE_WORDS) -> frozenset[str]:
    if len(words) < k:
        return frozenset([" ".join(words)]) if words else frozenset()
    return frozenset(" ".join(words[i : i + k]) for i in range(len(words) - k + 1))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _same_place(a: JobDoc, b: JobDoc) -> bool:
    return bool(a.provinces & b.provinces) or (not a.provinces and not b.provinces)


def decide(similarity: float, title_similarity: float, min_tokens: int) -> Decision | None:
    if similarity < REVIEW_THRESHOLD:
        return None
    sure = title_similarity >= TITLE_MERGE_THRESHOLD and min_tokens >= MIN_TOKENS_TO_MERGE
    return "merge" if similarity >= MERGE_THRESHOLD and sure else "review"


def find_near_duplicates(docs: Iterable[JobDoc]) -> list[NearPair]:
    """Cặp gần trùng trong danh sách tin, sắp theo độ giống giảm dần."""
    prepared: dict[int, tuple[JobDoc, frozenset[str], frozenset[str], int]] = {}
    for doc in docs:
        if doc.company_id is None:
            continue  # không biết công ty thì không đủ căn cứ
        words = tokens(f"{doc.title}\n{doc.text}")
        sh = shingles(words)
        if sh:
            prepared[doc.id] = (doc, sh, frozenset(normalize_key(doc.title).split()), len(words))

    # Mỗi công ty một chỉ mục LSH: chỉ so trong cùng công ty
    by_company: dict[int, list[int]] = {}
    for job_id, (doc, *_) in prepared.items():
        by_company.setdefault(doc.company_id, []).append(job_id)

    pairs: list[NearPair] = []
    for ids in by_company.values():
        if len(ids) < 2:
            continue
        lsh = MinHashLSH(threshold=REVIEW_THRESHOLD, num_perm=NUM_PERM)
        hashes: dict[int, MinHash] = {}
        for job_id in sorted(ids):
            mh = MinHash(num_perm=NUM_PERM)
            mh.update_batch(s.encode() for s in prepared[job_id][1])
            hashes[job_id] = mh
            lsh.insert(job_id, mh)
        for a in sorted(ids):
            doc_a, sh_a, title_a, n_a = prepared[a]
            for b in lsh.query(hashes[a]):
                if b <= a:
                    continue
                doc_b, sh_b, title_b, n_b = prepared[b]
                if not _same_place(doc_a, doc_b):
                    continue
                sim = jaccard(sh_a, sh_b)
                title_sim = jaccard(title_a, title_b)
                decision = decide(sim, title_sim, min(n_a, n_b))
                if decision:
                    pairs.append(NearPair(a, b, round(sim, 4), round(title_sim, 4), decision))
    pairs.sort(key=lambda p: (-p.similarity, p.job_a, p.job_b))
    return pairs
