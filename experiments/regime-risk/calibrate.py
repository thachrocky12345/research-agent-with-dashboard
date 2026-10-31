"""T3.3 calibration of the chosen classification models.

Reliability and ECE use the out-of-sample walk from exposure.py.
Isotonic regression is fit on development out-of-sample scores only and applied to validation.
This script does not load the holdout and does not refit the LightGBM.
"""
from __future__ import annotations

import pickle
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from common import DATA, REPORTS, append_result, assert_no_holdout, brier, ece
from exposure import OOS_PATH

BINS = np.linspace(0.0, 1.0, 11)


def reliability(y: np.ndarray, p: np.ndarray) -> pd.DataFrame:
    rows = []
    for i in range(10):
        right = p <= BINS[i + 1] if i == 9 else p < BINS[i + 1]
        mask = (p >= BINS[i]) & right
        count = int(mask.sum())
        rows.append(
            {
                "bin": i,
                "lo": BINS[i],
                "hi": BINS[i + 1],
                "n": count,
                "mean_p": float(p[mask].mean()) if count else float("nan"),
                "obs": float(y[mask].mean()) if count else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---:" for _ in columns) + "|"]
    for rec in frame.itertuples(index=False):
        cells = []
        for value in rec:
            if isinstance(value, float):
                cells.append("nan" if not np.isfinite(value) else f"{value:.4f}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    if not OOS_PATH.exists():
        raise SystemExit(f"missing {OOS_PATH}. Run exposure.py first.")
    with OOS_PATH.open("rb") as handle:
        oos = pickle.load(handle)
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    lines = [
        "# T3.3 Calibration",
        "",
        "Chosen classification models: LightGBM on `full`, out-of-sample walk. "
        "Ten equal-width bins. Isotonic regression is fit on development scores only.",
        "",
    ]
    acceptance = []
    for symbol in ("spy", "qqq"):
        for target in ("T_down", "T_volexp"):
            frame = oos[symbol][target]
            assert_no_holdout(frame.index, f"cal {symbol} {target}")
            dev = frame[frame["split"] == "dev"]
            val = frame[frame["split"] == "val"]
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(dev["p"].to_numpy(dtype=float), dev["y"].to_numpy(dtype=float))
            val_hat = iso.predict(val["p"].to_numpy(dtype=float))
            lines.append(f"## {symbol} {target}")
            lines.append("")
            for split, part in (("dev", dev), ("val", val)):
                y = part["y"].to_numpy(dtype=float)
                p = part["p"].to_numpy(dtype=float)
                lines.append(f"### {split} raw reliability n={len(part)} ECE {ece(y, p):.6f} Brier {brier(y, p):.6f}")
                lines.append("")
                lines.append(table(reliability(y, p)))
                lines.append("")
                year_rows = []
                for year, grp in part.groupby("year"):
                    year_rows.append(
                        {
                            "year": int(year),
                            "n": len(grp),
                            "ece": ece(grp["y"], grp["p"]),
                            "brier": brier(grp["y"], grp["p"]),
                        }
                    )
                lines.append(table(pd.DataFrame(year_rows)))
                lines.append("")
            yv = val["y"].to_numpy(dtype=float)
            pv = val["p"].to_numpy(dtype=float)
            raw_ece, raw_brier = ece(yv, pv), brier(yv, pv)
            new_ece, new_brier = ece(yv, val_hat), brier(yv, val_hat)
            lines.append(
                f"Validation after dev-only isotonic: ECE {raw_ece:.6f} -> {new_ece:.6f}, "
                f"Brier {raw_brier:.6f} -> {new_brier:.6f}."
            )
            lines.append("")
            acceptance.append(
                f"{symbol} {target} val ECE {raw_ece:.6f} -> {new_ece:.6f} "
                f"Brier {raw_brier:.6f} -> {new_brier:.6f} "
                f"ece_improved {new_ece < raw_ece} brier_improved {new_brier < raw_brier}"
            )
            for metric, before, after in (("ece", raw_ece, new_ece), ("brier", raw_brier, new_brier)):
                append_result(
                    "T3",
                    f"{run_id}_{symbol}",
                    "val",
                    target,
                    "lgbm",
                    "full",
                    metric,
                    f"{after:.6f}",
                    f"{before:.6f}",
                    f"{before - after:.6f}",
                    len(val),
                    "isotonic fit on dev OOS only; value is calibrated val, baseline is raw val",
                )
    lines.append("T_rv is a log-vol forecast. It has no probability reliability table.")
    lines.append("")
    lines.append("Acceptance:")
    lines.append("")
    lines.append("```")
    lines.extend(acceptance)
    lines.append("```")
    text = "\n".join(lines) + "\n"
    (REPORTS / "w3_calibration.md").write_text(text)
    print("\n".join(acceptance))
    print(f"wrote {REPORTS / 'w3_calibration.md'}")


if __name__ == "__main__":
    main()
