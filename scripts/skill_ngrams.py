"""Đếm n-gram trong phần yêu cầu của JD để lập danh sách kỹ năng ứng viên."""

import argparse
import csv
import re
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Repo không cài thành package, nên chạy trực tiếp script phải tự thêm đường dẫn.
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from scripts.profile_dataset import load_dataset  # noqa: E402
from skillkit import normalize_text  # noqa: E402

DEFAULT_INPUT = ROOT / "data" / "raw" / "topcv_2026"
DEFAULT_OUT = ROOT / "data" / "interim" / "skill_candidates.csv"
# Trường raw_job trong config/column_map.yaml; CSV TopCV hiện chưa có cột này.
DEFAULT_COLUMN = "description"
MAX_N = 3

STOPWORDS = frozenset(
    """
    và hoặc của có các những một là với cho trong về được khi từ theo để đã sẽ này đó như
    tại trên dưới không rất cần phải ít nhất năm
    a an the and or of to in on for with at by from as is are be this that it you we our your
    """.split()  # noqa: SIM905
)

# Dấu câu chia đoạn: n-gram không được vắt qua, ví dụ "java, python" không tạo "java python".
SEGMENT_BREAK = re.compile(r"[\n\r,;:!?•()]|\.\s")
TOKEN_EDGE = "-–—*\"'“”‘’[]{}|/"


def tokenize(text: str) -> list[list[str]]:
    """Chia văn bản thành các đoạn, mỗi đoạn là danh sách từ; giữ nguyên c++, c#, .net."""
    segments = []
    for segment in SEGMENT_BREAK.split(text):
        tokens = [token.strip(TOKEN_EDGE).rstrip(".") for token in normalize_text(segment).split()]
        tokens = [token for token in tokens if token]
        if tokens:
            segments.append(tokens)
    return segments


def is_candidate(gram: tuple[str, ...]) -> bool:
    """Bỏ n-gram mở đầu hoặc kết thúc bằng stopword, và n-gram có từ chỉ gồm chữ số."""
    if gram[0] in STOPWORDS or gram[-1] in STOPWORDS:
        return False
    return not any(token.isdigit() for token in gram)


def count_ngrams(texts: Iterable[str], max_n: int = MAX_N) -> Counter[tuple[str, ...]]:
    counts: Counter[tuple[str, ...]] = Counter()
    for text in texts:
        for tokens in tokenize(text):
            for n in range(1, max_n + 1):
                for i in range(len(tokens) - n + 1):
                    gram = tuple(tokens[i : i + n])
                    if is_candidate(gram):
                        counts[gram] += 1
    return counts


def to_rows(counts: Counter[tuple[str, ...]], min_freq: int) -> list[tuple[str, int, int]]:
    """Trả về (ngram, n, freq), freq giảm dần; cùng freq thì theo ngram để kết quả cố định."""
    rows = [(" ".join(gram), len(gram), freq) for gram, freq in counts.items() if freq >= min_freq]
    return sorted(rows, key=lambda row: (-row[2], row[0]))


def write_csv(rows: list[tuple[str, int, int]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["ngram", "n", "freq"])
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="File CSV hoặc thư mục")
    parser.add_argument("--column", default=DEFAULT_COLUMN, help="Cột chứa phần yêu cầu của JD")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="File CSV kết quả")
    parser.add_argument("--min-freq", type=int, default=2, help="Bỏ n-gram có tần suất nhỏ hơn")
    args = parser.parse_args(argv)

    try:
        df = load_dataset(args.input)
    except FileNotFoundError as e:
        raise SystemExit(f"Không đọc được dữ liệu: {e}") from e
    if args.column not in df.columns:
        raise SystemExit(f"Không có cột '{args.column}'. Các cột hiện có: {list(df.columns)}")

    rows = to_rows(count_ngrams(df[args.column].dropna()), args.min_freq)
    write_csv(rows, args.out)
    print(f"{len(df)} JD -> {len(rows)} n-gram -> {args.out}")


if __name__ == "__main__":
    main()
