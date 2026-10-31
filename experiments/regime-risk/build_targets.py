"""Targets for SPY and QQQ. T1.4.

T_down, T_volexp, and T_rv are known only after the next 5 sessions.
The threshold for T_volexp is the trailing 60-day median of backward-looking
5-day realized vol, which is known at the close. Rows whose 5-day window is
incomplete are left missing. Prices stop at 2021-12-31 unless HUMAN=1, so a
window cannot reach the holdout.
"""
from __future__ import annotations

import pickle

import numpy as np
import pandas as pd

from build_features import _pull_daily, realized_vol, total_return_price
from common import DATA, assert_no_holdout


def forward_rv(logret: pd.Series, n: int = 5) -> pd.Series:
    acc = None
    for k in range(1, n + 1):
        term = logret.shift(-k).pow(2)
        acc = term if acc is None else acc + term
    return np.sqrt(acc * (252.0 / n))


def build_symbol(symbol: str) -> pd.DataFrame:
    raw = _pull_daily(symbol)
    px = total_return_price(raw)
    logret = np.log(px / px.shift(1))
    fwd = px.shift(-5) / px - 1.0
    frv = forward_rv(logret, 5)
    back = realized_vol(logret, 5)
    med = back.rolling(60, min_periods=60).median()
    out = pd.DataFrame(index=raw.index)
    out["T_down"] = np.where(fwd.notna(), (fwd < -0.02).astype(float), np.nan)
    out["T_volexp"] = np.where(frv.notna() & med.notna(), (frv > med).astype(float), np.nan)
    out["T_rv"] = np.where(frv.notna() & (frv > 0), np.log(frv), np.nan)
    out["fwd_ret_5"] = fwd
    out["fwd_rv_5"] = frv
    assert_no_holdout(out.index, symbol)
    return out


def label_counts(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    rows = []
    for year, part in frame.groupby(frame.index.year):
        rows.append({
            "symbol": symbol,
            "year": int(year),
            "n": int(len(part)),
            "T_down_pos": int(part["T_down"].sum(skipna=True)),
            "T_down_n": int(part["T_down"].notna().sum()),
            "T_volexp_pos": int(part["T_volexp"].sum(skipna=True)),
            "T_volexp_n": int(part["T_volexp"].notna().sum()),
            "T_rv_n": int(part["T_rv"].notna().sum()),
        })
    return pd.DataFrame(rows)


def main() -> None:
    payload = {symbol: build_symbol(symbol) for symbol in ("spy", "qqq")}
    path = DATA / "targets.pkl"
    with path.open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    tables = [label_counts(frame, symbol) for symbol, frame in payload.items()]
    counts = pd.concat(tables, ignore_index=True)
    text = counts.to_string(index=False)
    print(text)
    (DATA.parent / "reports" / "T1.4_label_counts.txt").write_text(text + "\n")
    print(f"saved {path}")


if __name__ == "__main__":
    main()
