"""S3-D06: tính độ đúng và gợi ý alias từ các file đã chấm tay."""

from scripts.eval_cv_real import score


def test_score_counts_and_alias_suggestions():
    skills = [
        {"cv": "cvr01", "skill_id": "java", "muc_may": "strong", "dung": "y", "muc_dung": ""},
        {
            "cv": "cvr01",
            "skill_id": "docker",
            "muc_may": "listed",
            "dung": "y",
            "muc_dung": "strong",
        },
        {"cv": "cvr01", "skill_id": "leadership", "muc_may": "listed", "dung": "n"},
        {"cv": "cvr02", "skill_id": "python", "muc_may": "strong", "dung": ""},  # chưa chấm: bỏ
    ]
    missing = [
        {"cv": "cvr01", "ky_nang": "Kubernetes", "cach_viet": "Kubernets", "muc": "strong"},
        {
            "cv": "cvr01",
            "ky_nang": "Kafka",
            "cach_viet": "Kafka",
            "muc": "strong",
        },  # có rồi: không gợi ý
        {"cv": "cvr02", "ky_nang": "Odoo ERP", "cach_viet": "Odoo", "muc": "listed"},
        {"cv": "cvr02", "ky_nang": "", "cach_viet": ""},  # dòng trống
    ]
    meta = [
        {
            "cv": "cvr01",
            "trang_thai": "parsed",
            "so_nam_may": "3.0",
            "so_nam_dung": "3.5",
            "chuc_danh_may": "Backend Developer",
            "chuc_danh_dung": "y",
            "section_dung": "y",
        },
        {"cv": "cvr02", "trang_thai": "failed:ocr_required"},
    ]
    r = score(skills, missing, meta)
    assert (r["ky_nang_may"], r["dung"], r["sai"], r["bo_sot"]) == (3, 2, 1, 3)
    assert r["precision"] == 0.667 and r["recall"] == 0.4
    assert r["dung_muc"] == 0.5  # docker máy để listed, đúng là strong
    assert r["so_nam_mae"] == 0.5 and r["so_nam_lech_le_0_5"] == 1
    assert r["chuc_danh_dung"] == "1/1" and r["doc_duoc"] == 1 and r["pii_lo"] == 0
    assert r["alias_thieu"] == [{"skill_id": "kubernetes", "cach_viet": "kubernets", "cv": "cvr01"}]
    assert r["ngoai_tu_dien"] == [("Odoo ERP", 1)]
    assert r["sai_hay_gap"] == [("leadership", 1)]
