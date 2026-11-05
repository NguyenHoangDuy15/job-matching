"""Spike TASK-D008: nDCG@k bằng numpy, đối chiếu với số tính tay trong docs/notes/ndcg.md."""

import numpy as np
import pytest


def dcg_at_k(rels: list[int], k: int) -> float:
    top = np.asarray(rels[:k], dtype=float)
    gains = 2**top - 1  # gain Burges, như ranx ndcg_burges
    discounts = np.log2(np.arange(1, top.size + 1) + 1)
    return float(np.sum(gains / discounts))


def ndcg_at_k(ranked: list[int], all_rels: list[int], k: int) -> float:
    # IDCG sắp lại từ mọi nhãn của truy vấn, gồm cả tài liệu hệ thống xếp ngoài top-k.
    idcg = dcg_at_k(sorted(all_rels, reverse=True), k)
    return dcg_at_k(ranked, k) / idcg if idcg > 0 else 0.0


@pytest.mark.parametrize(
    ("ranked", "expected"),
    [
        ([3, 2, 3, 0, 1, 2], 0.9488),
        ([0, 0, 1, 3], 0.4606),
        ([2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 3], 0.3866),  # nhãn 3 ở vị trí 11 bị cắt khỏi DCG@10
    ],
)
def test_ndcg_matches_hand_calculation(ranked, expected):
    assert ndcg_at_k(ranked, ranked, 10) == pytest.approx(expected, abs=1e-4)
