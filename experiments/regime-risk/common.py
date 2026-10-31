"""Shared holdout guard, metrics, and manifest check for the regime-risk sprint.

Task scripts import this. It is not itself a scored model.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

EXP = Path(__file__).resolve().parent
BACKEND = Path(os.environ.get("STOCK_AI_BACKEND", "/Users/thachbui/Documents/ultimate-stock-ai/backend"))
DATA = EXP / "data"
RAW = DATA / "raw"
CONFIG = EXP / "config"
REPORTS = EXP / "reports"

sys.path.insert(0, str(EXP))
sys.path.insert(0, str(BACKEND))
if "app.services" not in sys.modules:
    _stub = types.ModuleType("app.services")
    _stub.__path__ = [str(BACKEND / "app" / "services")]
    sys.modules["app.services"] = _stub

# Last date an agent may put in a frame. Holdout starts 2022-01-03.
LAST_ALLOWED = pd.Timestamp("2021-12-31")
DEV_START = pd.Timestamp("2000-01-03")
DEV_END = pd.Timestamp("2018-12-31")
VAL_START = pd.Timestamp("2019-01-02")
VAL_END = pd.Timestamp("2021-12-31")
HOLDOUT_START = pd.Timestamp("2022-01-03")
HOLDOUT_END = pd.Timestamp("2024-09-27")
COST_BPS = 2
SEED = 20261029

# Columns a candidate model may see. rv1 and rv22 exist only so HAR/ridge can use them.
HAR_ONLY = ("rv1", "rv22")
B1_COLS = ("log_rv20", "log_vix", "rv5_over_rv20")

MANIFEST_FILES = (
    "check_features.py",
    "build_features.py",
    "build_targets.py",
    "evaluate_model.py",
)


def human_allowed() -> bool:
    return os.environ.get("HUMAN") == "1"


def assert_no_holdout(index, label: str) -> None:
    """Refuse any frame whose dates go past 2021-12-31 unless HUMAN=1."""
    if human_allowed() or len(index) == 0:
        return
    mx = pd.Timestamp(pd.DatetimeIndex(index).max())
    if mx > LAST_ALLOWED:
        raise SystemExit(
            f"REFUSED {label}: max date {mx.date()} is after 2021-12-31. "
            "Holdout dates load only when the human sets HUMAN=1."
        )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_paths() -> list[Path]:
    paths = [EXP / name for name in MANIFEST_FILES]
    paths.extend(sorted(p for p in CONFIG.glob("*.json") if p.name != "manifest.json"))
    return paths


def write_manifest() -> dict:
    body = {str(p.relative_to(EXP)): sha256_file(p) for p in manifest_paths()}
    path = CONFIG / "manifest.json"
    path.write_text(json.dumps(body, indent=2) + "\n")
    return body


def check_manifest() -> None:
    path = CONFIG / "manifest.json"
    if not path.exists():
        raise SystemExit("REFUSED: config/manifest.json is missing. Run check_features.py first.")
    locked = json.loads(path.read_text())
    bad = []
    for rel, digest in locked.items():
        file_path = EXP / rel
        if not file_path.exists() or sha256_file(file_path) != digest:
            bad.append(rel)
    if bad:
        raise SystemExit("REFUSED: manifest hash mismatch: " + ", ".join(bad))


def append_result(task, run_id, split, target, model, feature_set, metric, value, baseline, skill, n, note) -> None:
    """Append one results.tsv row. Never rewrites old rows. Locks so Tier A can append too."""
    import fcntl

    path = EXP / "results.tsv"
    fields = [task, run_id, split, target, model, feature_set, metric, value, baseline, skill, n, note]
    text = "\t".join("" if v is None else str(v) for v in fields)
    if "\n" in text or "\t" in str(note):
        raise ValueError("result note must be one line without tabs")
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(text + "\n")
        fcntl.flock(handle, fcntl.LOCK_UN)


def brier(y, p) -> float:
    return float(np.mean((p - y) ** 2))


def logloss(y, p) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def auc_score(y, p) -> float:
    y = np.asarray(y)
    if len(np.unique(y)) < 2:
        return float("nan")
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p))


def ece(y, p, n_bins: int = 10) -> float:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = 0.0
    n = len(y)
    if n == 0:
        return float("nan")
    for i in range(n_bins):
        right = p <= edges[i + 1] if i == n_bins - 1 else p < edges[i + 1]
        mask = (p >= edges[i]) & right
        count = int(mask.sum())
        if count == 0:
            continue
        total += (count / n) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(total)


def qlike(y_log, p_log) -> float:
    """Patton QLIKE on variance. y_log and p_log are log realized vol."""
    y = np.exp(2.0 * np.asarray(y_log, dtype=float))
    h = np.exp(2.0 * np.clip(np.asarray(p_log, dtype=float), -5.0, 2.0))
    h = np.clip(h, 1e-12, None)
    return float(np.mean(np.log(h) + y / h))


def skill(model_loss, baseline_loss) -> float:
    if baseline_loss == 0 or not np.isfinite(baseline_loss):
        return float("nan")
    return float(1.0 - model_loss / baseline_loss)


def qlike_skill(model_q, baseline_q) -> float:
    """Percent QLIKE reduction. Positive means the model loss is lower.

    Patton QLIKE is negative here because variance is far below 1.
    The ratio 1 - model/baseline then gives a positive score to a worse model.
    """
    if baseline_q == 0 or not np.isfinite(baseline_q) or not np.isfinite(model_q):
        return float("nan")
    return float((baseline_q - model_q) / abs(baseline_q))


def split_bounds(name: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    if name == "dev":
        return DEV_START, DEV_END
    if name == "val":
        return VAL_START, VAL_END
    if name == "holdout":
        return HOLDOUT_START, HOLDOUT_END
    raise SystemExit(f"unknown split {name}")
