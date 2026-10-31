"""B0, B1, HAR, and the economic benchmarks. T1.4.

Walk-forward: each January the model is fit on every row before that January
and scored on that calendar year. Development is 2000-2018. Validation is
2019-2021. This script does not load the holdout.
"""
from __future__ import annotations

import pickle

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from build_features import _pull_daily, total_return_price
from common import DATA, DEV_END, DEV_START, REPORTS, VAL_END, VAL_START, brier, qlike, skill

COST = 2 / 10000  # 2 bps per side


def _frame(symbol: str) -> pd.DataFrame:
    core = pd.read_pickle(DATA / "features_core.pkl")
    fred = pd.read_pickle(DATA / "features_fred.pkl")
    with (DATA / "targets.pkl").open("rb") as handle:
        targets = pickle.load(handle)[symbol]
    prefix = f"{symbol}__"
    own = core[[c for c in core.columns if c.startswith(prefix)]].rename(columns=lambda c: c[len(prefix):])
    frame = own.join(fred[["vixcls_level"]], how="inner").join(targets, how="inner")
    frame["log_rv20"] = np.log(frame["rv20"].clip(lower=1e-8))
    frame["log_vix"] = np.log(frame["vixcls_level"].clip(lower=1e-8))
    frame["log_rv1"] = np.log(frame["rv1"].clip(lower=1e-8))
    frame["log_rv5"] = np.log(frame["rv5"].clip(lower=1e-8))
    frame["log_rv22"] = np.log(frame["rv22"].clip(lower=1e-8))
    return frame.sort_index()


def _years(index: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp) -> list[int]:
    sl = index[(index >= start) & (index <= end)]
    return sorted(set(sl.year))


def _fit_predict_class(train: pd.DataFrame, test: pd.DataFrame, cols: list[str], ycol: str, kind: str) -> np.ndarray:
    if kind == "b0":
        # Rolling 3-year base rate, known before the test year.
        start = test.index.min() - pd.DateOffset(years=3)
        window = train[train.index >= start]
        rate = float(window[ycol].mean()) if len(window) else float(train[ycol].mean())
        return np.full(len(test), rate)
    xtr = train[cols].to_numpy(dtype=float)
    ytr = train[ycol].to_numpy(dtype=float)
    xte = test[cols].to_numpy(dtype=float)
    scaler = StandardScaler().fit(xtr)
    model = LogisticRegression(C=1.0, max_iter=400)
    model.fit(scaler.transform(xtr), ytr)
    return model.predict_proba(scaler.transform(xte))[:, 1]


def _fit_predict_reg(train: pd.DataFrame, test: pd.DataFrame, kind: str) -> np.ndarray:
    if kind == "b0":
        return test["log_rv20"].to_numpy(dtype=float)
    if kind == "har":
        # OLS on log RV1, log RV5, log RV22. The target is a log, so the
        # regressors are logs too. Levels blew up in 2008 (MSE 0.66 vs 0.27).
        cols = ["log_rv1", "log_rv5", "log_rv22"]
        model = LinearRegression()
        model.fit(train[cols].to_numpy(dtype=float), train["T_rv"].to_numpy(dtype=float))
        return model.predict(test[cols].to_numpy(dtype=float))
    cols = ["log_rv20", "log_vix", "rv5_over_rv20"]
    xtr = train[cols].to_numpy(dtype=float)
    ytr = train["T_rv"].to_numpy(dtype=float)
    xte = test[cols].to_numpy(dtype=float)
    scaler = StandardScaler().fit(xtr)
    # B1 is ridge, as pre-registered. HAR is ordinary regression, so no penalty.
    model = Ridge(alpha=1.0) if kind == "b1" else LinearRegression()
    model.fit(scaler.transform(xtr), ytr)
    return model.predict(scaler.transform(xte))


def walk(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, ycol: str, kind: str) -> pd.DataFrame:
    rows = []
    preds = []
    b1_cols = ["log_rv20", "log_vix", "rv5_over_rv20"]
    for year in _years(frame.index, start, end):
        test_mask = (frame.index.year == year) & (frame.index >= start) & (frame.index <= end)
        train = frame[frame.index < pd.Timestamp(year=year, month=1, day=1)]
        test = frame.loc[test_mask]
        if ycol == "T_rv":
            need = ["T_rv", "log_rv20", "log_rv1", "log_rv5", "log_rv22", "log_vix", "rv5_over_rv20"]
            train = train.dropna(subset=need)
            test = test.dropna(subset=need)
            if len(train) < 50 or len(test) == 0:
                continue
            pred = _fit_predict_reg(train, test, kind)
        else:
            need = [ycol, *b1_cols]
            train = train.dropna(subset=need)
            test = test.dropna(subset=need)
            if train[ycol].nunique() < 2 or len(test) == 0:
                continue
            pred = _fit_predict_class(train, test, b1_cols, ycol, kind)
        part = pd.DataFrame({"y": test[ycol].to_numpy(dtype=float), "p": pred}, index=test.index)
        preds.append(part)
        if ycol == "T_rv":
            rows.append({"year": year, "n": len(part), "qlike": qlike(part["y"], part["p"]), "mse": float(np.mean((part["y"] - part["p"]) ** 2))})
        else:
            rows.append({"year": year, "n": len(part), "brier": brier(part["y"], part["p"]), "base_rate": float(part["y"].mean())})
    detail = pd.DataFrame(rows)
    pooled = pd.concat(preds) if preds else pd.DataFrame(columns=["y", "p"])
    return detail, pooled


def _stats(simple: pd.Series, exposure: pd.Series) -> dict:
    pos = exposure.shift(1).fillna(0.0)
    turn = pos.diff().abs()
    turn.iloc[0] = abs(pos.iloc[0])
    net = pos * simple - turn * COST
    equity = (1.0 + net).cumprod()
    years = max(len(net) / 252.0, 1e-9)
    peak = equity.cummax()
    dd = float((equity / peak - 1.0).min())
    vol = float(net.std(ddof=0))
    sharpe = float(net.mean() / vol * np.sqrt(252)) if vol > 0 else float("nan")
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if equity.iloc[-1] > 0 else float("nan")
    return {
        "cagr": cagr,
        "sharpe": sharpe,
        "max_dd": dd,
        "turnover": float(turn.mean() * 252),
        "time_in_market": float((pos > 0.05).mean()),
        "n": int(len(net)),
    }


def economics(symbol: str) -> pd.DataFrame:
    raw = _pull_daily(symbol)
    px = total_return_price(raw)
    simple = px.pct_change()
    ma200 = px.rolling(200, min_periods=200).mean()
    core = pd.read_pickle(DATA / "features_core.pkl")
    rv20 = core[f"{symbol}__rv20"]
    frame = pd.DataFrame({"simple": simple, "px": px, "ma200": ma200, "rv20": rv20}).dropna()
    out = []
    for label, start, end in (("development", DEV_START, DEV_END), ("validation", VAL_START, VAL_END)):
        sl = frame[(frame.index >= start) & (frame.index <= end)]
        exposures = {
            "BH": pd.Series(1.0, index=sl.index),
            "DMA": (sl["px"] > sl["ma200"]).astype(float),
            "VT": np.minimum(1.0, 0.15 / sl["rv20"].clip(lower=1e-4)),
        }
        for name, expo in exposures.items():
            stats = _stats(sl["simple"], expo)
            stats.update({"split": label, "symbol": symbol, "book": name})
            out.append(stats)
    return pd.DataFrame(out)


def main() -> None:
    lines = ["# Benchmarks", ""]
    gate = []
    for symbol in ("spy", "qqq"):
        frame = _frame(symbol)
        lines.append(f"## {symbol}")
        lines.append("")
        for ycol in ("T_down", "T_volexp"):
            for split_name, start, end in (("development", DEV_START, DEV_END), ("validation", VAL_START, VAL_END)):
                for kind in ("b0", "b1"):
                    detail, pooled = walk(frame, start, end, ycol, kind)
                    loss = brier(pooled["y"], pooled["p"]) if len(pooled) else float("nan")
                    lines.append(f"{ycol} {split_name} {kind} brier={loss:.6f} n={len(pooled)}")
                    if len(detail):
                        lines.append(detail.to_string(index=False))
                    lines.append("")
                    if split_name == "development" and symbol == "spy":
                        gate.append((ycol, kind, loss, len(pooled)))
        for split_name, start, end in (("development", DEV_START, DEV_END), ("validation", VAL_START, VAL_END)):
            losses = {}
            for kind in ("b0", "har", "b1"):
                detail, pooled = walk(frame, start, end, "T_rv", kind)
                loss = qlike(pooled["y"], pooled["p"]) if len(pooled) else float("nan")
                losses[kind] = loss
                lines.append(f"T_rv {split_name} {kind} qlike={loss:.6f} n={len(pooled)}")
                if len(detail):
                    lines.append(detail.to_string(index=False))
                lines.append("")
            if split_name == "development" and symbol == "spy":
                gate.append(("T_rv", "b0", losses["b0"], 0))
                gate.append(("T_rv", "har", losses["har"], 0))
        eco = economics(symbol)
        lines.append(eco.to_string(index=False))
        lines.append("")
    # Acceptance uses SPY development.
    by = {(a, b): c for a, b, c, _ in gate}
    checks = []
    for ycol in ("T_down", "T_volexp"):
        ok = by[(ycol, "b1")] < by[(ycol, "b0")]
        checks.append(f"{ycol} B1 {by[(ycol, 'b1')]:.6f} < B0 {by[(ycol, 'b0')]:.6f} {ok}")
    har_ok = by[("T_rv", "har")] < by[("T_rv", "b0")]
    checks.append(f"T_rv HAR {by[('T_rv', 'har')]:.6f} < B0 {by[('T_rv', 'b0')]:.6f} {har_ok}")
    passed = all("True" in row for row in checks)
    lines.append("## Acceptance")
    lines.extend(checks)
    lines.append("PASS" if passed else "FAIL")
    text = "\n".join(lines) + "\n"
    (REPORTS / "benchmarks.md").write_text(text)
    print("\n".join(checks))
    print("PASS" if passed else "FAIL")


if __name__ == "__main__":
    main()
