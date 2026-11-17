"""Phân vị trên toàn kho tin đang mở, dùng chung cho K (S4-D01) và E (S4-D02).

    P_j = (số tin có điểm < s_j + 0,5 × số tin có điểm = s_j) / N

N là MỌI tin đang mở (không phải tập sau bộ lọc), nên điểm cùng thang khi đổi bộ lọc, khi chấm
1 JD và phía HR (proposal mục 4).
"""

from __future__ import annotations

import numpy as np


def percentile_rank(scores: np.ndarray, *, zero_is_zero: bool = False) -> np.ndarray:
    """Phân vị (0–1) của từng điểm trong chính mảng đó. `zero_is_zero`: điểm ≤ 0 → 0 (K: tin
    không khớp từ nào không được nhận "phân vị giữa" của nhóm điểm 0)."""
    n = len(scores)
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    ordered = np.sort(scores)
    below = np.searchsorted(ordered, scores, side="left")
    at_or_below = np.searchsorted(ordered, scores, side="right")
    p = (below + 0.5 * (at_or_below - below)) / n
    if zero_is_zero:
        p[scores <= 0] = 0.0
    return p
