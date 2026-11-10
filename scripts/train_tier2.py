"""Train Tầng 2 "JEV-local" trên data/interim/silver_mentions.csv (S2-D04).

    uv run python scripts/train_tier2.py

- 25% mẫu đổi section thành NONE (seed 42) để model dùng được cho JD không heading.
- GroupKFold 5 fold theo jd_id: không JD nào vừa ở train vừa ở test.
- In báo cáo out-of-fold và bảng coverage / macro-F1 theo ngưỡng τ.
- Fit lại trên toàn bộ: models/jev_local_v1.joblib (không lên git, chạy lại ra cùng model)
  và reports/jev_local_v1.metrics.json.
KHÔNG dùng bộ gold để train.
"""

import csv
import json
import random
import sys
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import GroupKFold, cross_val_predict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skillkit.levels.tier2 import build_model, prep  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MODEL_VERSION = "jev_local_v1"
DROPOUT = 0.25


def main(csv_path: Path = ROOT / "data" / "interim" / "silver_mentions.csv") -> None:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    rng = random.Random(42)
    x = [
        prep("NONE" if rng.random() < DROPOUT else r["section"], r["sentence"], r["skill_text"])
        for r in rows
    ]
    y = np.array([r["label"] == "PREFERRED" for r in rows], dtype=int)
    groups = [r["jd_id"] for r in rows]
    print(f"{len(rows)} mẫu, {len(set(groups))} JD, preferred {y.mean():.1%}")

    oof = cross_val_predict(
        build_model(), x, y, groups=groups, cv=GroupKFold(n_splits=5), method="predict_proba"
    )[:, 1]
    report = classification_report(
        y, oof > 0.5, target_names=["REQUIRED", "PREFERRED"], digits=3, output_dict=True
    )
    print(classification_report(y, oof > 0.5, target_names=["REQUIRED", "PREFERRED"], digits=3))
    taus = {}
    for tau in (0.6, 0.7, 0.8, 0.9):
        ok = np.maximum(oof, 1 - oof) >= tau
        f1 = f1_score(y[ok], oof[ok] > 0.5, average="macro") if ok.any() else 0.0
        taus[str(tau)] = {"coverage": round(float(ok.mean()), 4), "macro_f1": round(float(f1), 4)}
        print(f"tau={tau}  coverage={ok.mean():.2f}  macroF1={f1:.3f}")

    model = build_model().fit(x, y)
    models, reports = ROOT / "models", ROOT / "reports"
    models.mkdir(exist_ok=True)
    reports.mkdir(exist_ok=True)
    joblib.dump(model, models / f"{MODEL_VERSION}.joblib")
    metrics = {
        "model_version": MODEL_VERSION,
        "sklearn": sklearn.__version__,
        "train_file": csv_path.name,
        "n_train": len(rows),
        "n_jd": len(set(groups)),
        "preferred_share": round(float(y.mean()), 4),
        "oof_macro_f1": round(report["macro avg"]["f1-score"], 4),
        "oof_preferred_recall": round(report["PREFERRED"]["recall"], 4),
        "cv_by_tau": taus,
        "note": "Nhãn silver do luật sinh ra: số liệu CV chỉ cho biết model học lại luật tốt đến "
        "đâu, KHÔNG phải độ chính xác thật. Độ chính xác thật đo bằng scripts/evaluate_levels.py.",
    }
    (reports / f"{MODEL_VERSION}.metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"→ {models / (MODEL_VERSION + '.joblib')}")


if __name__ == "__main__":
    main(
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "data" / "interim" / "silver_mentions.csv"
    )
