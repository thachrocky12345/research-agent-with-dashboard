"""Causality check, then lock the manifest. T1.3e.

For 20 development dates, rebuild each feature set from rows dated <= t and
compare to the full-sample row. Also flag any feature whose development
correlation with the next-day SPY return exceeds 0.5.
"""
from __future__ import annotations

import pickle

import numpy as np
import pandas as pd

from build_features import assemble, build_breadth, build_core, build_etf, build_fred
from common import DATA, DEV_END, DEV_START, SEED, write_manifest

SETS = ("core", "fred", "breadth", "etf", "long", "full")


def _row(frame: pd.DataFrame, day: pd.Timestamp) -> pd.Series:
    return frame.loc[day].drop(labels=["px"], errors="ignore")


def build_set(name: str, asof: pd.Timestamp | None) -> pd.DataFrame:
    if name == "core":
        return build_core(asof=asof)
    if name == "fred":
        return build_fred(asof=asof)
    if name == "breadth":
        return build_breadth(asof=asof)
    if name == "etf":
        return build_etf(asof=asof)
    return assemble(name, "spy", asof=asof)


def main() -> None:
    full = {name: build_set(name, None) for name in SETS}
    dev = full["long"]
    dev = dev.loc[(dev.index >= DEV_START) & (dev.index <= DEV_END)].dropna(how="all")
    candidates = dev.index[dev.index >= pd.Timestamp("2005-01-03")]
    rng = np.random.default_rng(SEED)
    positions = rng.choice(len(candidates), size=20, replace=False)
    pick = list(pd.DatetimeIndex(candidates[positions]).sort_values())
    failed = []
    for name in SETS:
        base = full[name]
        ok = True
        for day in pick:
            if day not in base.index:
                continue
            rebuilt = build_set(name, day)
            if day not in rebuilt.index:
                ok = False
                failed.append(f"{name} {day.date()} missing")
                continue
            left = _row(base, day).astype(float)
            right = _row(rebuilt, day).reindex(left.index).astype(float)
            if not np.allclose(left.to_numpy(), right.to_numpy(), atol=1e-9, rtol=1e-9, equal_nan=True):
                ok = False
                gap = (left - right).abs()
                failed.append(f"{name} {day.date()} max_abs={gap.max():.3e} col={gap.idxmax()}")
        print(f"{name} {'PASS' if ok else 'FAIL'}")
    spy_ret_next = full["core"]["spy__logret_1"].shift(-1)
    aligned = full["long"].join(spy_ret_next.rename("next_ret"), how="inner")
    aligned = aligned.loc[(aligned.index >= DEV_START) & (aligned.index <= DEV_END)]
    leaks = []
    for col in full["long"].columns:
        pair = aligned[[col, "next_ret"]].dropna()
        if len(pair) < 100:
            continue
        corr = float(pair[col].corr(pair["next_ret"]))
        if corr > 0.5:
            leaks.append((col, corr))
    if leaks:
        print("LEAK FLAGS")
        for col, corr in leaks:
            print(f"  {col} {corr:.4f}")
    else:
        print("leak check PASS (no feature corr with next-day return > 0.5)")
    if failed:
        print("CAUSALITY FAIL")
        for line in failed:
            print(" ", line)
        raise SystemExit(1)
    saved = DATA / "features_long.pkl"
    if saved.exists():
        with saved.open("rb") as handle:
            on_disk = pickle.load(handle)["spy"]
        fresh = full["long"]
        shared = fresh.columns.intersection(on_disk.columns)
        left, right = fresh[shared].align(on_disk[shared], join="inner")
        if not np.allclose(left.to_numpy(dtype=float), right.to_numpy(dtype=float), atol=1e-9, rtol=1e-9, equal_nan=True):
            raise SystemExit("features_long.pkl does not match a fresh assemble. Rebuild it.")
        print("features_long.pkl matches fresh assemble")
    manifest = write_manifest()
    print(f"manifest locked {len(manifest)} files")


if __name__ == "__main__":
    main()
