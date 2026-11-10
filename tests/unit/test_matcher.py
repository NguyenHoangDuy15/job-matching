"""S2-D03: trích kỹ năng tầng 1 trên từ điển thật, tập trung vào từ nhập nhằng."""

import pytest

from skillkit import load_taxonomy
from skillkit.matcher import SkillMatcher, prepare
from tests.unit.test_skill_seed import SKILLS_YAML


@pytest.fixture(scope="module")
def matcher() -> SkillMatcher:
    return SkillMatcher(load_taxonomy(SKILLS_YAML))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Java / JavaScript: cụm dài nhất thắng, không cần ngữ cảnh
        ("Thành thạo Java, JavaScript và TypeScript", ["java", "javascript", "typescript"]),
        ("Kinh nghiệm JavaScript (ES6+), ReactJS", ["javascript", "react"]),
        ("Biết Java Script cơ bản", ["javascript"]),
        # Go
        ("Backend bằng Go hoặc Golang, microservices", ["golang", "microservices"]),
        ("Python, Go, Rust", ["python", "golang", "rust"]),
        ("Dự án go live tháng 12, sẵn sàng go-to-market", []),
        ("Ready to go với khách hàng", []),
        ("Gõ văn bản nhanh", []),  # giữ dấu: "gõ" không thành "go"
        # R
        ("Biết Python, R, SQL để phân tích dữ liệu", ["python", "r_lang", "sql", "data_analysis"]),
        ("Phòng R&D của công ty", []),
        ("Thống kê bằng R và ggplot2", ["statistics", "r_lang"]),
        # C
        ("Lập trình C/C++ cho vi điều khiển STM32", ["c_lang", "cpp", "microcontroller"]),
        ("Bằng lái hạng C", []),
        ("Bổ sung vitamin C", []),
        ("Thành thạo C#.", ["csharp"]),
        ("Kiến thức C++17 và Rust", ["cpp", "rust"]),
        # .NET và lương Net
        ("Ưu tiên biết C#, .NET Core, ASP.NET MVC", ["csharp", "dotnet", "aspnet"]),
        ("Kinh nghiệm .NET.", ["dotnet"]),
        ("Lương Net 30 triệu, Gross 35 triệu", []),
        # Các từ nhập nhằng khác thấy trong dữ liệu thật
        ("Thành thạo Photoshop, AI, Illustrator", ["photoshop", "illustrator"]),
        (
            "Kinh nghiệm AI, Machine Learning, LLM",
            ["artificial_intelligence", "machine_learning", "llm"],
        ),
        ("React quickly to incidents", []),
        ("Kinh nghiệm React, Redux", ["react", "redux"]),
        ("Lập trình iOS bằng Swift, SwiftUI", ["ios", "swift", "swiftui"]),
        ("Cung cấp mã SWIFT ngân hàng", []),
        ("Spring Boot, Spring Security", ["spring_boot", "spring_security"]),
        ("Spring 2026 internship", []),
        ("Node.js, Express, MongoDB", ["nodejs", "expressjs", "mongodb"]),
        ("Express delivery service", []),
        ("Sử dụng thành thạo Excel, VBA", ["excel", "vba"]),
        ("We excel at problem solving", ["problem_solving"]),
        ("Docker, K8s, CI/CD trên AWS", ["docker", "kubernetes", "ci_cd", "aws"]),
    ],
)
def test_skills(matcher, text, expected):
    assert matcher.skills(text) == expected


def test_surface_keeps_original_case(matcher):
    [match] = matcher.find("Viết   backend bằng  Golang")
    assert (match.skill_id, match.surface, match.term) == ("golang", "Golang", "golang")


def test_prepare_keeps_length():
    cased, lower = prepare("  İstanbul\tGO  ")
    assert len(cased) == len(lower) and cased == "İstanbul GO"


def test_empty_text(matcher):
    assert matcher.find(None) == [] and matcher.skills("") == []


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        (["Python", "go", "R", "Unity"], [["python"], ["golang"], ["r_lang"], ["unity"]]),
        (["Photoshop", "AI", "Illustrator"], [["photoshop"], [], ["illustrator"]]),
        (["AI", "Machine Learning"], [["artificial_intelligence"], ["machine_learning"]]),
        ([".NET", ".NET Core", "Word"], [["dotnet"], ["dotnet"], []]),
    ],
)
def test_skill_list_mode(matcher, items, expected):
    assert matcher.match_list(items) == expected
