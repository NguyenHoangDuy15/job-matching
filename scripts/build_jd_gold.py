"""Dựng bộ 50 JD gán nhãn section cho S2-D03 (và S2-D07 gán thêm nhãn kỹ năng).

Nội dung: dòng thật của VietJobs (data/interim/vietjobs_it.csv: description, requirements_text,
benefits). Heading: ghép theo 8 kiểu trình bày thường gặp (TopCV, ITviec Việt/Anh,
VietnamWorks, đánh số viết hoa, markdown/emoji, heading cùng dòng, heading không có trong
config/jd_headings.yaml để đo giới hạn). Chưa crawl trang thật vì docs/data_sources.md
chưa cho phép.

Nhãn mặc định theo cột gốc; câu khác mặc định được gán tay theo nghĩa trong
tests/fixtures/jd_gold/labels.yaml (chỉ chứa số dòng + nhãn, không có nội dung JD).
Đầu ra data/eval/jd_gold.jsonl chứa nội dung JD nên KHÔNG lên git; ai có
data/interim/vietjobs_it.csv chạy lại là ra cùng một file (random_state cố định).

Chạy: uv run python scripts/build_jd_gold.py
"""

import ast
import json
import random
from pathlib import Path

import pandas as pd
import yaml

from skillkit.sections import explode

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "interim" / "vietjobs_it.csv"
LABELS = ROOT / "tests" / "fixtures" / "jd_gold" / "labels.yaml"  # chỉ số dòng + nhãn, lên git
OUT = ROOT / "data" / "eval"  # có nội dung JD → không lên git (data/README.md)
N = 50

STYLES = {
    "topcv": ("Mô tả công việc", "Yêu cầu ứng viên", "Quyền lợi", None),
    "itviec_en": (
        "Job description",
        "Your skills and experience",
        "Why you'll love working here",
        "Nice to have",
    ),
    "itviec_vi": ("Mô tả công việc", "Yêu cầu", "Tại sao bạn sẽ yêu thích làm việc tại đây", None),
    "vietnamworks": (
        "Mô tả Công việc",
        "Yêu Cầu Công Việc",
        "Các phúc lợi dành cho bạn",
        "Ưu tiên",
    ),
    "numbered_caps": ("1. MÔ TẢ CÔNG VIỆC:", "2. YÊU CẦU:", "3. QUYỀN LỢI:", "4. ƯU TIÊN:"),
    "markdown": (
        "🎯 **Responsibilities**",
        "✅ **Requirements**",
        "🎁 **Benefits**",
        "⭐ **Preferred qualifications**",
    ),
    "inline": ("Nhiệm vụ:", "Yêu cầu:", "Quyền lợi:", None),
    "unseen": ("Bạn sẽ làm gì", "Chúng tôi cần bạn", "Bạn nhận được gì", None),
}
STYLE_PLAN = (
    ["topcv"] * 9
    + ["itviec_en"] * 7
    + ["itviec_vi"] * 7
    + ["vietnamworks"] * 8
    + ["numbered_caps"] * 6
    + ["markdown"] * 5
    + ["inline"] * 5
    + ["unseen"] * 3
)


def _lines(text: object) -> list[str]:
    """Các câu của một cột VietJobs (đoạn dài được cắt câu giống bộ tách)."""
    if not isinstance(text, str) or not text.strip():
        return []
    if text.startswith("["):
        try:
            return [f"- {item}" for item in ast.literal_eval(text) if str(item).strip()]
        except (ValueError, SyntaxError):
            pass
    return [part for line in text.splitlines() if line.strip() for part in explode(line.strip())]


def pick_rows(df: pd.DataFrame) -> pd.DataFrame:
    ok = df[df.description.notna() & df.requirements_text.notna() & df.benefits.notna()]
    ok = ok[
        ok.description.str.len().between(150, 2500)
        & ok.requirements_text.str.len().between(80, 2000)
    ]
    # Lấy cả tin có heading con thật bên trong nội dung (khó hơn cho bộ tách).
    inner = ok[ok.description.str.contains(r"\n[^\n]{3,40}:\s*\n", regex=True)]
    rest = ok.drop(inner.index)
    chosen = pd.concat(
        [
            inner.sample(min(8, len(inner)), random_state=7),
            rest.sample(N - min(8, len(inner)), random_state=7),
        ]
    )
    return chosen.sample(frac=1, random_state=11)


def render(row: pd.Series, style: str, fix: dict, idx: int) -> dict:
    """fix: nhãn gán tay theo nghĩa, {"description"|"requirements": {chỉ số câu: nhãn}}."""
    desc_h, req_h, ben_h, pref_h = STYLES[style]
    out: list[tuple[str, str]] = [(f"Tuyển dụng {row.job_title}", "other")]
    desc, req, ben = _lines(row.description), _lines(row.requirements_text), _lines(row.benefits)
    desc_fix, req_fix = fix.get("description", {}), fix.get("requirements", {})
    desc_labeled = [(line, desc_fix.get(i, "description")) for i, line in enumerate(desc)]
    req_labeled = [(line, req_fix.get(i, "requirements")) for i, line in enumerate(req)]
    has_pref = any(label == "preferred" for _, label in req_labeled)

    physical: list[str] = []  # các dòng của văn bản JD
    items: list[tuple[str, str]] = []  # (nội dung, nhãn) để chấm, cùng thứ tự bộ tách trả về

    def emit(line: str, label: str) -> None:
        physical.append(line)
        items.append((line, label))

    def block(heading: str, lines: list[tuple[str, str]]) -> None:
        if not lines:
            return
        if style == "inline":  # "Yêu cầu: <câu đầu>" trên cùng một dòng
            first, label = lines[0]
            physical.append(f"{heading} {first}")
            items.extend([(heading, "heading"), (first, label)])
            lines = lines[1:]
        else:
            emit(heading, "heading")
        for line, label in lines:
            emit(line, label)

    for line, label in out:
        emit(line, label)
    block(desc_h, desc_labeled)
    if pref_h and has_pref:  # kiểu có mục Ưu tiên riêng: dồn câu ưu tiên vào đó
        # bỏ heading con của cột gốc ("Ưu tiên:") vì heading của kiểu trình bày thay thế
        block(req_h, [x for x in req_labeled if x[1] not in ("preferred", "heading")])
        block(pref_h, [x for x in req_labeled if x[1] == "preferred"])
    else:
        block(req_h, req_labeled)
    block(ben_h, [(line, "benefits") for line in ben])
    if style in ("topcv", "vietnamworks"):
        emit("Địa điểm làm việc", "heading")
        emit(f"- {row.location}", "other")
    return {
        "id": f"vj_{idx:03d}",
        "source_row": int(row.name),
        "style": style,
        "text": "\n".join(physical),
        "items": items,
    }


def main() -> None:
    df = pd.read_csv(SRC)
    rows = pick_rows(df)
    # Thiếu file nhãn là lỗi: bỏ qua âm thầm sẽ ra bộ mẫu chỉ có nhãn theo cột gốc.
    overrides = yaml.safe_load(LABELS.read_text(encoding="utf-8")) or {}
    styles = STYLE_PLAN[:]
    random.Random(3).shuffle(styles)
    samples = [
        render(row, styles[i], overrides.get(int(row.name), {}), i)
        for i, (_, row) in enumerate(rows.iterrows())
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "jd_gold.jsonl").open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"{len(samples)} JD → {OUT / 'jd_gold.jsonl'}")


if __name__ == "__main__":
    main()
