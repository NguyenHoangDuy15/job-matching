"""Đo chất lượng khử trùng (S3-T05, US-14): lấy mẫu cặp tin, gán tay, tính precision/recall.

Đơn vị đo là CẶP TIN cùng công ty, có chung tỉnh (đúng phạm vi ingestion.near_dedup). Mỗi cặp
có 3 đặc trưng mà luật gộp dùng: độ giống nội dung (Jaccard cụm 3 từ), độ giống chức danh, số từ
của tin ngắn hơn. Vì giữ lại đặc trưng nên sau khi gán nhãn có thể thử lại MỌI bộ ngưỡng mà không
cần quay lại DB.

Lấy mẫu phân tầng theo độ giống, vì cặp gần trùng rất hiếm so với tổng số cặp:
    gop        ≥ 0,85        vùng gộp tự động (cần precision ≥ 0,95)
    hang_cho   0,70–0,85     vùng đưa vào hàng chờ admin
    duoi_nguong 0,40–0,70    dưới ngưỡng: ước lượng số cặp trùng bị BỎ SÓT (recall)
    thap       0,20–0,40     chỉ lấy khi các tầng trên không đủ cặp (kho nhỏ)
Mỗi cặp được gán trọng số = số cặp của tầng / số cặp lấy mẫu của tầng, nên precision/recall là
ước lượng cho TOÀN KHO chứ không chỉ cho 100 cặp. Cặp < 0,20 không lấy mẫu: recall là cận trên.
"""

from __future__ import annotations

import csv
import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ingestion.location import normalize_key
from ingestion.near_dedup import (
    MERGE_THRESHOLD,
    MIN_TOKENS_TO_MERGE,
    REVIEW_THRESHOLD,
    TITLE_MERGE_THRESHOLD,
    JobDoc,
    jaccard,
    shingles,
    tokens,
)

# (tên, độ giống từ, độ giống tới (không gồm), số cặp lấy mẫu mặc định)
STRATA: tuple[tuple[str, float, float, int], ...] = (
    ("gop", 0.85, 1.01, 45),
    ("hang_cho", 0.70, 0.85, 35),
    ("duoi_nguong", 0.40, 0.70, 20),
    ("thap", 0.20, 0.40, 0),  # chỉ tiêu 0: chỉ nhận phần dư
)
MIN_SIMILARITY = STRATA[-1][1]


@dataclass(frozen=True)
class Rule:
    """Một bộ ngưỡng của luật gộp tự động (giống ingestion.near_dedup.decide)."""

    merge: float = MERGE_THRESHOLD
    title: float = TITLE_MERGE_THRESHOLD
    min_tokens: int = MIN_TOKENS_TO_MERGE
    review: float = REVIEW_THRESHOLD

    def decide(self, similarity: float, title_similarity: float, min_tokens: int) -> str:
        sure = title_similarity >= self.title and min_tokens >= self.min_tokens
        if sure and similarity >= self.merge:
            return "merge"
        return "review" if similarity >= self.review else "none"

    def label(self) -> str:
        return f"gộp ≥ {self.merge:.2f} · chức danh ≥ {self.title:.2f} · ≥ {self.min_tokens} từ"


CURRENT_RULE = Rule()
BASELINE_RULE = Rule(merge=0.85)  # luật S3-T04, trước khi chỉnh ngưỡng ở S3-T05


@dataclass(frozen=True)
class Pair:
    job_a: int
    job_b: int
    similarity: float
    title_similarity: float
    min_tokens: int


@dataclass
class LabeledPair:
    pair: Pair
    weight: float
    stratum: str
    is_dup: bool


def stratum_of(similarity: float) -> str | None:
    for name, lo, hi, _ in STRATA:
        if lo <= similarity < hi:
            return name
    return None


def _same_place(a: JobDoc, b: JobDoc) -> bool:
    return bool(a.provinces & b.provinces) or (not a.provinces and not b.provinces)


def all_pairs(docs: Iterable[JobDoc], min_similarity: float = MIN_SIMILARITY) -> list[Pair]:
    """Mọi cặp cùng công ty, chung tỉnh, độ giống ≥ min_similarity (so đủ từng cặp, không LSH).

    Không dùng LSH để không bỏ sót cặp nào trong vùng đo; mỗi công ty chỉ vài chục tin nên so
    hết vẫn nhanh.
    """
    prepared = []
    for doc in docs:
        if doc.company_id is None:
            continue
        words = tokens(f"{doc.title}\n{doc.text}")
        sh = shingles(words)
        if sh:
            prepared.append((doc, sh, frozenset(normalize_key(doc.title).split()), len(words)))
    by_company: dict[int, list] = {}
    for item in prepared:
        by_company.setdefault(item[0].company_id, []).append(item)

    pairs: list[Pair] = []
    for items in by_company.values():
        items.sort(key=lambda it: it[0].id)
        for i, (doc_a, sh_a, title_a, n_a) in enumerate(items):
            for doc_b, sh_b, title_b, n_b in items[i + 1 :]:
                if not _same_place(doc_a, doc_b):
                    continue
                # Cận trên của Jaccard theo kích thước tập: bỏ nhanh cặp chắc chắn dưới ngưỡng
                small, big = sorted((len(sh_a), len(sh_b)))
                if small / big < min_similarity:
                    continue
                sim = jaccard(sh_a, sh_b)
                if sim < min_similarity:
                    continue
                pairs.append(
                    Pair(
                        doc_a.id,
                        doc_b.id,
                        round(sim, 4),
                        round(jaccard(title_a, title_b), 4),
                        min(n_a, n_b),
                    )
                )
    pairs.sort(key=lambda p: (-p.similarity, p.job_a, p.job_b))
    return pairs


def sample_pairs(
    pairs: Sequence[Pair], total: int = 100, seed: int = 20261118
) -> list[tuple[Pair, str, int, int]]:
    """Lấy mẫu phân tầng. Trả (cặp, tầng, số cặp của tầng, số cặp lấy của tầng).

    Tầng có ít cặp hơn chỉ tiêu thì lấy hết; phần dư chia cho các tầng còn cặp, ưu tiên tầng
    trên (vùng gộp quan trọng nhất cho precision).
    """
    groups: dict[str, list[Pair]] = {name: [] for name, *_ in STRATA}
    for p in pairs:
        name = stratum_of(p.similarity)
        if name:
            groups[name].append(p)
    base = sum(q for *_, q in STRATA)
    quota = {name: round(q * total / base) for name, _, _, q in STRATA}
    quota[STRATA[0][0]] += total - sum(quota.values())
    take = {name: min(quota[name], len(groups[name])) for name in quota}
    spare = total - sum(take.values())
    for name, *_ in STRATA:
        extra = min(spare, len(groups[name]) - take[name])
        take[name] += extra
        spare -= extra

    rng = random.Random(seed)
    out: list[tuple[Pair, str, int, int]] = []
    for name, *_ in STRATA:
        chosen = rng.sample(groups[name], take[name]) if take[name] else []
        chosen.sort(key=lambda p: (-p.similarity, p.job_a))
        out.extend((p, name, len(groups[name]), take[name]) for p in chosen)
    return out


# ---- Chấm điểm -----------------------------------------------------------------------------
@dataclass
class Metrics:
    rule: Rule
    precision: float | None  # ước lượng toàn kho (có trọng số)
    recall: float | None  # chỉ tính cặp gộp tự động
    recall_with_review: float | None  # gộp tự động + vào hàng chờ (admin duyệt)
    merged_sampled: int  # số cặp mẫu luật này gộp
    merged_wrong: int  # trong đó gộp nhầm (theo nhãn)
    precision_low: float | None  # cận dưới Wilson 95% trên các cặp mẫu bị gộp
    merged_est: float  # số cặp ước tính bị gộp trên toàn kho
    fp_examples: list[Pair] = field(default_factory=list)


def wilson_lower(success: int, n: int, z: float = 1.96) -> float | None:
    if n == 0:
        return None
    p = success / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / denom


def evaluate(rows: Sequence[LabeledPair], rule: Rule) -> Metrics:
    tp = fp = fn = caught = 0.0
    merged_n = merged_wrong = 0
    fps: list[Pair] = []
    for r in rows:
        p = r.pair
        d = rule.decide(p.similarity, p.title_similarity, p.min_tokens)
        if d == "merge":
            merged_n += 1
            if r.is_dup:
                tp += r.weight
            else:
                fp += r.weight
                merged_wrong += 1
                fps.append(p)
        elif r.is_dup:
            fn += r.weight
        if r.is_dup and d in ("merge", "review"):
            caught += r.weight
    dups = tp + fn
    return Metrics(
        rule=rule,
        precision=tp / (tp + fp) if tp + fp else None,
        recall=tp / dups if dups else None,
        recall_with_review=caught / dups if dups else None,
        merged_sampled=merged_n,
        merged_wrong=merged_wrong,
        precision_low=wilson_lower(merged_n - merged_wrong, merged_n),
        merged_est=tp + fp,
        fp_examples=fps,
    )


MERGE_GRID = (0.20, 0.30, 0.40, 0.45, 0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
TITLE_GRID = (1.0, 0.8, 0.5, 0.0)


def rule_grid() -> list[Rule]:
    return [
        Rule(merge=m, title=t, min_tokens=k)
        for m in MERGE_GRID
        for t in TITLE_GRID
        for k in (0, 30)
    ]


def best_rule(results: Sequence[Metrics], target: float = 0.95) -> Metrics | None:
    """Bộ ngưỡng recall cao nhất mà precision ≥ target; hòa thì chọn bộ chặt hơn (an toàn)."""
    ok = [m for m in results if m.precision is not None and m.precision >= target]
    if not ok:
        return None
    return max(
        ok,
        key=lambda m: (
            round(m.recall or 0, 4),
            m.rule.merge,
            m.rule.title,
            m.rule.min_tokens,
        ),
    )


# ---- File CSV ------------------------------------------------------------------------------
CSV_FIELDS = (
    "pair_id",
    "tang",
    "so_cap_tang",
    "so_cap_mau_tang",
    "job_a",
    "job_b",
    "do_giong",
    "do_giong_chuc_danh",
    "so_tu_it_hon",
    "quyet_dinh_hien_tai",
    "da_gop",
    "cong_ty",
    "chuc_danh_a",
    "chuc_danh_b",
    "nguon_a",
    "nguon_b",
    "url_a",
    "url_b",
    "nhan",  # 1 = cùng một tin tuyển dụng, 0 = hai tin khác nhau
    "ghi_chu",
)


def read_labels(path) -> tuple[list[LabeledPair], list[str]]:
    """Đọc CSV đã gán nhãn. Trả (cặp có nhãn, cảnh báo)."""
    rows: list[LabeledPair] = []
    warnings: list[str] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for rec in csv.DictReader(f):
            label = (rec.get("nhan") or "").strip()
            if label not in ("0", "1"):
                warnings.append(f"cặp {rec.get('pair_id')}: nhãn '{label}' không phải 0/1, bỏ qua")
                continue
            pair = Pair(
                int(rec["job_a"]),
                int(rec["job_b"]),
                float(rec["do_giong"]),
                float(rec["do_giong_chuc_danh"]),
                int(rec["so_tu_it_hon"]),
            )
            rows.append(LabeledPair(pair, float(rec["so_cap_tang"]), rec["tang"], label == "1"))
    # Trọng số = số cặp của tầng / số cặp ĐÃ CÓ NHÃN của tầng (bỏ trống vài nhãn vẫn đúng)
    labeled: dict[str, int] = {}
    for r in rows:
        labeled[r.stratum] = labeled.get(r.stratum, 0) + 1
    for r in rows:
        r.weight = r.weight / labeled[r.stratum]
    return rows, warnings
