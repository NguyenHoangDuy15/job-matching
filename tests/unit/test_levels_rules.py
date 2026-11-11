"""S2-D04: lớp luật (21 ca của spec) và chuẩn hóa giữ độ dài."""

import pytest

from skillkit.levels.norm import norm
from skillkit.levels.rules import decide

CASES = [  # (section, câu, kỹ năng, mức mong đợi | None)
    ("REQ", "Must have Java; Docker is a plus", "Java", "REQUIRED"),
    ("REQ", "Must have Java; Docker is a plus", "Docker", "PREFERRED"),
    ("REQ", "Thành thạo Java, ưu tiên biết thêm Kotlin", "Java", "REQUIRED"),
    ("REQ", "Thành thạo Java, ưu tiên biết thêm Kotlin", "Kotlin", "PREFERRED"),
    ("REQ", "Ưu tiên ứng viên biết Docker, Kubernetes", "Docker", "PREFERRED"),
    ("REQ", "Ưu tiên ứng viên biết Docker, Kubernetes", "Kubernetes", "PREFERRED"),
    ("REQ", "Strong SQL skills, experience with AWS would be great", "SQL", "REQUIRED"),
    ("REQ", "Strong SQL skills, experience with AWS would be great", "AWS", "PREFERRED"),
    ("REQ", "Tiếng Nhật N3 không bắt buộc", "Tiếng Nhật", "PREFERRED"),
    ("REQ", "Uu tien ung vien biet Docker", "Docker", "PREFERRED"),
    ("PREF", "Ít nhất 1 năm kinh nghiệm React", "React", "PREFERRED"),
    ("BEN", "Được đào tạo AWS miễn phí", "AWS", "DROP"),
    ("REQ", "Biết Java là bắt buộc, Spring Boot là một lợi thế", "Java", "REQUIRED"),
    ("REQ", "Biết Java là bắt buộc, Spring Boot là một lợi thế", "Spring Boot", "PREFERRED"),
    ("REQ", "Có kinh nghiệm với Spring Boot là lợi thế", "Spring Boot", "PREFERRED"),
    ("REQ", "Kinh nghiệm làm việc với Python", "Python", "REQUIRED"),
    ("DESC", "Xử lý ưu tiên các ticket Jira", "Jira", None),
    ("NONE", "Tối thiểu 2 năm kinh nghiệm Node.js", "Node.js", "REQUIRED"),
    ("NONE", "Knowledge of Kafka is a plus", "Kafka", "PREFERRED"),
    ("NONE", "Experience with Redis is not required", "Redis", "PREFERRED"),
    ("DESC", "Hiểu biết về Kubernetes sẽ giúp ích nhiều", "Kubernetes", None),
    # Thêm cho repo này: gạch đầu dòng trước "Ưu tiên".
    ("REQ", "- Ưu tiên biết Docker", "Docker", "PREFERRED"),
    ("REQ", "1. Ưu tiên biết Docker", "Docker", "PREFERRED"),
    # Lỗi tìm ra khi chạy trên 48 JD gold.
    ("REQ", "Có kinh nghiệm về Vmware, Hyper-V, Docker, .. là một lợi thế.", "Docker", "PREFERRED"),
    ("REQ", "Kinh nghiệm làm việc với Kubernetes, ưu tiên đã dùng RKE2", "Kubernetes", "REQUIRED"),
    ("REQ", "Kinh nghiệm làm việc với Docker, ưu tiên đã dùng RKE2", "RKE2", "PREFERRED"),
    ("REQ", "Kinh nghiệm DevOps, ITSM,… là một lợi thế.", "DevOps", "PREFERRED"),
    ("REQ", "Có kỹ năng phân tích (ưu tiên thành thạo Odoo).", "kỹ năng phân tích", "REQUIRED"),
    ("REQ", "Có kỹ năng phân tích (ưu tiên thành thạo Odoo).", "Odoo", "PREFERRED"),
    ("REQ", "Biết Node.js là lợi thế", "Node.js", "PREFERRED"),
    # Lỗi tìm ra khi chấm gold lần 2 (S2-D04).
    ("DESC", "Công ty với hơn 17 năm chuyên môn về AI và IoT", "AI", None),
    ("DESC", "Có 3 năm kinh nghiệm Java", "Java", "REQUIRED"),
    ("NONE", "3+ years of experience with Go", "Go", "REQUIRED"),
    ("NONE", "Kinh nghiệm làm việc với Docker tối thiểu 2 năm", "Docker", "REQUIRED"),
    ("DESC", "Nghiên cứu cổ phiếu, phái sinh và đưa ra product roadmap", "product roadmap", None),
    ("NONE", "Phải biết Java", "Java", "REQUIRED"),
    (
        "REQ",
        "Biết ít nhất một ngôn ngữ (ưu tiên Python, JavaScript) hoặc scripting (Bash)",
        "Python",
        "PREFERRED",
    ),
    (
        "REQ",
        "Biết ít nhất một ngôn ngữ (ưu tiên Python, JavaScript) hoặc scripting (Bash)",
        "JavaScript",
        "PREFERRED",
    ),
    (
        "REQ",
        "Biết ít nhất một ngôn ngữ (ưu tiên Python, JavaScript) hoặc scripting (Bash)",
        "Bash",
        "REQUIRED",
    ),
    ("REQ", "Có kinh nghiệm backend (ưu tiên Python)", "Python", "PREFERRED"),
]


@pytest.mark.parametrize("section,sent,skill,expected", CASES)
def test_rules(section, sent, skill, expected):
    s = sent.index(skill)
    d = decide(section, sent, s, s + len(skill))
    assert (d.level if d else None) == expected


@pytest.mark.parametrize("text", ["Đã làm việc ở Gò Vấp", "ỨNG VIÊN ưu tiên", "İstanbul đ"])
def test_norm_keeps_length(text):
    assert len(norm(text)) == len(text)


def test_norm_folds_vietnamese():
    assert norm("Ưu Tiên Đạt") == "uu tien dat"
