"""Lấy mô tả từ các trang tin TopCV do người dùng lưu tay bằng trình duyệt (Ctrl+S)."""

import argparse
import html
import json
import re
from pathlib import Path

from scripts.make_snapshot import DEFAULT_OUT as DEFAULT_SNAPSHOT
from scripts.make_snapshot import JOB_ID_PATTERN

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "topcv_2026"
DEFAULT_PAGES = RAW_DIR / "pages"
DEFAULT_OUT = RAW_DIR / "descriptions.jsonl"
DEFAULT_CHECKLIST = RAW_DIR / "checklist.html"
BLOCK_TAGS = r"br|div|h[1-6]|li|p|tr|ul|ol"
LD_JSON = re.compile(
    r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE
)
CANONICAL = re.compile(r"<link\b[^>]*rel=[\"']?canonical[\"']?[^>]*>", re.IGNORECASE)
HREF = re.compile(r"href=[\"']?([^\"'\s>]+)", re.IGNORECASE)
SAVED_FROM = re.compile(r"<!--\s*saved from url=\(\d+\)(\S+?)\s*-->", re.IGNORECASE)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<![\d.,])(?:\+?84|0)(?:[\s.-]?\d){8,10}(?![\d])")


def html_to_text(fragment: str) -> str:
    """Đổi HTML thành văn bản thuần, mỗi khối một dòng."""
    text = re.sub(rf"</?(?:{BLOCK_TAGS})\b[^>]*>", "\n", fragment, flags=re.IGNORECASE)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def mask_contacts(text: str) -> str:
    """Che email và số điện thoại để mô tả không mang PII sang bước embedding hay LLM."""
    return PHONE.sub("[phone]", EMAIL.sub("[email]", text))


def find_job_posting(page: str) -> dict | None:
    """Tìm khối JSON-LD JobPosting trong trang."""
    for block in LD_JSON.findall(page):
        try:
            data = json.loads(block, strict=False)
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


def find_jd_id(page: str) -> str | None:
    """Lấy jd_id từ link canonical; URL /brand/ khi mở cũng chuyển về canonical chứa cùng mã."""
    tag = CANONICAL.search(page)
    href = HREF.search(tag.group(0)) if tag else None
    url = href.group(1) if href else None
    if url is None:
        saved_from = SAVED_FROM.search(page)
        url = saved_from.group(1) if saved_from else ""
    match = re.search(JOB_ID_PATTERN, url)
    return f"topcv_{match.group(1)}" if match else None


def load_snapshot(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def import_pages(snapshot: list[dict], pages_dir: Path) -> tuple[dict[str, dict], list[str]]:
    """Trả về bản ghi theo jd_id và danh sách file không dùng được, kèm lý do."""
    wanted = {job["jd_id"] for job in snapshot}
    records: dict[str, dict] = {}
    problems: list[str] = []
    files = sorted(p for p in pages_dir.glob("*") if p.suffix.lower() in {".html", ".htm"})
    for file in files:
        page = file.read_text(encoding="utf-8", errors="replace")
        jd_id = find_jd_id(page)
        if jd_id is None:
            problems.append(f"{file.name}: không phải trang tin (có thể tin đã gỡ)")
        elif jd_id not in wanted:
            problems.append(f"{file.name}: {jd_id} không thuộc snapshot")
        elif jd_id in records:
            problems.append(f"{file.name}: trùng {jd_id}, đã bỏ qua")
        else:
            posting = find_job_posting(page)
            description = html_to_text(posting.get("description") or "") if posting else ""
            if not description:
                problems.append(f"{file.name}: {jd_id} không có mô tả trong trang")
                continue
            records[jd_id] = {
                "jd_id": jd_id,
                "status": "ok",
                "description": mask_contacts(description),
                "title_on_page": html_to_text(posting.get("title") or ""),
            }
    return records, problems


def write_records(records: dict[str, dict], path: Path) -> None:
    """Ghi JSONL sắp theo jd_id, LF, để cùng bộ trang luôn cho cùng một file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for jd_id in sorted(records):
            file.write(json.dumps(records[jd_id], ensure_ascii=False) + "\n")


def changed_titles(snapshot: list[dict], records: dict[str, dict]) -> list[str]:
    """Liệt kê tin có tiêu đề trên trang khác CSV: nội dung có thể đã được sửa sau khi crawl."""
    return [
        job["jd_id"]
        for job in snapshot
        if job["jd_id"] in records
        and records[job["jd_id"]]["title_on_page"].casefold() != job["title"].casefold()
    ]


def build_checklist(jobs: list[dict], people: int, total: int) -> str:
    """Tạo trang HTML chia link cho từng người; link đã mở sẽ đổi màu."""
    sections = []
    for person in range(people):
        items = "\n".join(
            f'<li><a href="{html.escape(job["source_url"])}" target="_blank" rel="noopener">'
            f"{html.escape(job['title'])}</a> <small>{html.escape(job['jd_id'])}</small></li>"
            for job in jobs[person::people]
        )
        count = len(jobs[person::people])
        sections.append(f"<h2>Người {person + 1} ({count} tin)</h2>\n<ol>\n{items}\n</ol>")
    body = "\n".join(sections)
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Checklist lưu tin</title>
<style>
body {{ font: 16px/1.6 system-ui, sans-serif; max-width: 860px; margin: 0 auto; padding: 16px; }}
a {{ color: #0b57d0; }}
a:visited {{ color: #7b1fa2; }}
small {{ color: #666; }}
.note {{ background: #f3f4f6; padding: 12px 16px; border-radius: 8px; }}
</style>
</head>
<body>
<h1>Còn {len(jobs)}/{total} tin cần lưu</h1>
<div class="note">
<p>Mở từng link, bấm <b>Ctrl+S</b>, chọn <b>Webpage, HTML Only</b>, lưu vào
<code>data\\raw\\topcv_2026\\pages\\</code>. Giữ nguyên tên file trình duyệt đặt.</p>
<p>Trang báo lỗi 404 hoặc chuyển về trang danh sách là tin đã gỡ: bỏ qua, không cần lưu.</p>
<p>Làm với tốc độ đọc bình thường. Nếu gặp trang xác minh chống bot thì dừng lại,
không cần tìm cách vượt qua.</p>
</div>
{body}
</body>
</html>
"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT, help="File snapshot")
    parser.add_argument("--pages", type=Path, default=DEFAULT_PAGES, help="Thư mục trang đã lưu")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="File kết quả JSONL")
    parser.add_argument(
        "--checklist", type=Path, default=DEFAULT_CHECKLIST, help="File HTML danh sách link"
    )
    parser.add_argument("--people", type=int, default=3, help="Số người chia việc")
    args = parser.parse_args(argv)

    snapshot = load_snapshot(args.snapshot)
    args.pages.mkdir(parents=True, exist_ok=True)
    records, problems = import_pages(snapshot, args.pages)
    write_records(records, args.out)

    remaining = [job for job in snapshot if job["jd_id"] not in records]
    args.checklist.parent.mkdir(parents=True, exist_ok=True)
    args.checklist.write_text(
        build_checklist(remaining, args.people, len(snapshot)), encoding="utf-8", newline="\n"
    )

    print(f"Có mô tả: {len(records)}/{len(snapshot)}")
    print(f"Còn thiếu: {len(remaining)} (xem {args.checklist})")
    changed = changed_titles(snapshot, records)
    if changed:
        print(f"Tiêu đề khác CSV, nên xem lại: {', '.join(changed)}")
    for problem in problems:
        print(f"Bỏ qua {problem}")


if __name__ == "__main__":
    main()
