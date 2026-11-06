import json

import pytest

from scripts.import_saved_pages import (
    build_checklist,
    changed_titles,
    find_jd_id,
    html_to_text,
    import_pages,
    main,
    mask_contacts,
)

SNAPSHOT = [
    {
        "jd_id": "topcv_111",
        "title": "Tester",
        "source_url": "https://www.topcv.vn/viec-lam/tester/111.html",
    },
    {
        "jd_id": "topcv_222",
        "title": "Fresher <Dev>",
        "source_url": "https://www.topcv.vn/brand/abc/tuyen-dung/dev-j222.html",
    },
]


def page(job_id: int, title: str = "Tester", description: str = "<p>Viết test</p>") -> str:
    data = {"@type": "JobPosting", "title": title, "description": description}
    return (
        f'<html><head><link rel="canonical" href="https://www.topcv.vn/viec-lam/x/{job_id}.html">'
        f'<script type="application/ld+json">{json.dumps(data)}</script></head></html>'
    )


def test_html_to_text_keeps_blocks_and_entities():
    fragment = "<h2>Mô tả công việc</h2>\n<p>A &amp; <b>B</b></p><ul><li>C  D</li><li>E</li></ul>"
    assert html_to_text(fragment) == "Mô tả công việc\nA & B\nC D\nE"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('<link rel="canonical" href="https://t.vn/viec-lam/a/123.html">', "topcv_123"),
        ('<link href="https://t.vn/viec-lam/a/123.html" rel="canonical" />', "topcv_123"),
        ("<!-- saved from url=(0029)https://t.vn/a/x-j456.html?a=1 -->", "topcv_456"),
        ('<link rel="canonical" href="https://t.vn/viec-lam">', None),
        ("<html></html>", None),
    ],
)
def test_find_jd_id(source, expected):
    assert find_jd_id(source) == expected


def test_import_reports_each_unusable_file(tmp_path):
    (tmp_path / "good.html").write_text(page(111), encoding="utf-8")
    (tmp_path / "copy.html").write_text(page(111), encoding="utf-8")
    (tmp_path / "other.html").write_text(page(999), encoding="utf-8")
    (tmp_path / "gone.html").write_text("<html>trang danh sách</html>", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text(page(222), encoding="utf-8")

    records, problems = import_pages(SNAPSHOT, tmp_path)

    assert records["topcv_111"]["description"] == "Viết test"
    assert list(records) == ["topcv_111"]
    joined = "\n".join(problems)
    assert "topcv_999 không thuộc snapshot" in joined
    assert "không phải trang tin" in joined
    assert "trùng topcv_111" in joined
    assert len(problems) == 3


def test_page_without_description_is_reported(tmp_path):
    (tmp_path / "empty.html").write_text(page(111, description=""), encoding="utf-8")
    records, problems = import_pages(SNAPSHOT, tmp_path)
    assert records == {}
    assert "không có mô tả" in problems[0]


def test_changed_titles_ignores_case_only():
    records = {
        "topcv_111": {"title_on_page": "TESTER"},
        "topcv_222": {"title_on_page": "Manual Tester"},
    }
    assert changed_titles(SNAPSHOT, records) == ["topcv_222"]


def test_checklist_escapes_titles_and_splits_people():
    result = build_checklist(SNAPSHOT, people=2, total=2)
    assert "Fresher &lt;Dev&gt;" in result
    assert "Người 1 (1 tin)" in result
    assert "Người 2 (1 tin)" in result


def test_main_is_repeatable_and_updates_checklist(tmp_path, capsys):
    snapshot = tmp_path / "snapshot.jsonl"
    snapshot.write_text(
        "".join(json.dumps(job, ensure_ascii=False) + "\n" for job in SNAPSHOT), encoding="utf-8"
    )
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "a.html").write_text(page(222, title="Khác"), encoding="utf-8")
    out = tmp_path / "descriptions.jsonl"
    checklist = tmp_path / "checklist.html"
    arguments = [
        "--snapshot",
        str(snapshot),
        "--pages",
        str(pages),
        "--out",
        str(out),
        "--checklist",
        str(checklist),
    ]

    main(arguments)
    first = out.read_bytes()
    main(arguments)

    printed = capsys.readouterr().out
    assert first == out.read_bytes()
    assert b"\r\n" not in first
    assert "Có mô tả: 1/2" in printed
    assert "topcv_222" in printed
    page_html = checklist.read_text(encoding="utf-8")
    assert "Còn 1/2 tin" in page_html
    assert "/tester/111.html" in page_html
    assert "dev-j222" not in page_html


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Gửi CV tới hr.team@example.com.vn", "Gửi CV tới [email]"),
        ("Liên hệ 0912 345 678 hoặc +84.912.345.678", "Liên hệ [phone] hoặc [phone]"),
        ("Lương 10.000.000 - 20.000.000 VND, 5 năm", "Lương 10.000.000 - 20.000.000 VND, 5 năm"),
    ],
)
def test_mask_contacts(text, expected):
    assert mask_contacts(text) == expected


def test_import_masks_contacts_in_description(tmp_path):
    posting = {
        "@type": "JobPosting",
        "title": "Tester",
        "description": "<p>Gửi CV tới hr@example.com</p>",
    }
    (tmp_path / "a.html").write_text(
        '<link rel="canonical" href="https://www.topcv.vn/viec-lam/tester/111.html">'
        f'<script type="application/ld+json">{json.dumps(posting)}</script>',
        encoding="utf-8",
    )

    records, _ = import_pages(SNAPSHOT, tmp_path)

    assert records["topcv_111"]["description"] == "Gửi CV tới [email]"
