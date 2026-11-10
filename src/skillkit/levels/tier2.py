"""Tầng 2 "JEV-local": TF-IDF n-gram ký tự + Logistic Regression, đoán p(preferred).

Chỉ được gọi cho ca luật không chắc (xem cascade). `prep()` dùng chung cho train và chạy.
Interface `Tier2Classifier` để sau này thay bằng Jev API mà không đổi phần còn lại.
"""

from pathlib import Path
from typing import Protocol


class Tier2Classifier(Protocol):
    version: str

    def prob_preferred(self, section: str, sentence: str, skill_text: str) -> float: ...


def prep(section: str, sentence: str, skill_text: str) -> str:
    """Thay tên kỹ năng bằng <s> để model học ngữ cảnh, không học thuộc tên kỹ năng."""
    return f"[{section}] " + sentence.replace(skill_text, " <s> ")


def build_model():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    return make_pipeline(
        TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 5), lowercase=True, sublinear_tf=True, min_df=2
        ),
        LogisticRegression(C=4, class_weight="balanced", max_iter=2000),
    )


class JevLocal:
    def __init__(self, path: str | Path) -> None:
        import joblib

        self.model = joblib.load(path)
        self.version = Path(path).stem

    def prob_preferred(self, section: str, sentence: str, skill_text: str) -> float:
        return float(self.model.predict_proba([prep(section, sentence, skill_text)])[0, 1])


def load_tier2(path: str | Path) -> JevLocal | None:
    """Model đã train, hoặc None nếu chưa có file (pipeline vẫn chạy bằng luật)."""
    return JevLocal(path) if Path(path).exists() else None
