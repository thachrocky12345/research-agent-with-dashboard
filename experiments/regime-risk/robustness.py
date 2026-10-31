"""T4.2 robustness on validation only.

Block bootstrap of the frozen LightGBM full-feature scores, costs at 4 bps,
and one refit where every feature is lagged an extra day. This script refuses
the holdout and does not choose a new model.
"""
from __future__ import annotations

import sys
from datetime import datetime

import numpy as np
import pandas as pd

from common import (
    COST_BPS,
    LAST_ALLOWED,
    REPORTS,
    SEED,
    append_result,
    brier,
    check_manifest,
    human_allowed,
    skill,
)
from evaluate_model import load_xy, walk_forward
from exposure import OOS_PATH, align, mapped_exposures, market, path_stats, split_mask

BLOCK = 21
DRAWS = 1000
COST2 = (COST_BPS * 2) / 10000.0


def refuse_holdout() -> None:
    if len(sys.argv) > 1 and "holdout" in sys.argv:
        print("BANNER: final holdout 2022-01-03 through 2024-09-27. Human only, one run.")
        print("REFUSED: robustness stays on validation.")
        sys.exit(2)
    if human_allowed():
        print("HUMAN=1 is set. This script still refuses dates after 2021-12-31.")


def load_oos() -> dict:
    if not OOS_PATH.exists():
        raise SystemExit(f"missing {OOS_PATH}")
    import pickle

    with OOS_PATH.open("rb") as handle:
        oos = pickle.load(handle)
    for symbol, targets in oos.items():
        for target, frame in targets.items():
            if frame.index.max() > LAST_ALLOWED:
                raise SystemExit(f"REFUSED: {symbol} {target} crosses 2021-12-31")
    return oos


def block_indices(n: int, rng: np.random.Generator) -> np.ndarray:
    if n <= BLOCK:
        raise SystemExit(f"series length {n} is shorter than the {BLOCK}-day block")
    n_blocks = int(np.ceil(n / BLOCK))
    starts = rng.integers(0, n - BLOCK + 1, size=n_blocks)
    pieces = [np.arange(start, start + BLOCK) for start in starts]
    return np.concatenate(pieces)[:n]


def bootstrap_bss(y: np.ndarray, p: np.ndarray, base: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    out = np.empty(DRAWS)
    for draw in range(DRAWS):
        idx = block_indices(len(y), rng)
        out[draw] = skill(brier(y[idx], p[idx]), brier(y[idx], base[idx]))
    return out


def daily_net(simple: pd.Series, exposure: pd.Series, cost: float) -> pd.Series:
    pos = exposure.shift(1).fillna(0.0)
    turn = pos.diff().abs()
    turn.iloc[0] = abs(float(pos.iloc[0]))
    return pos * simple - turn * cost


def sharpe(net: np.ndarray) -> float:
    vol = float(np.std(net, ddof=0))
    if vol <= 0 or len(net) == 0:
        return float("nan")
    return float(np.mean(net) / vol * np.sqrt(252.0))


def bootstrap_sharpe_diff(left: np.ndarray, right: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    out = np.empty(DRAWS)
    for draw in range(DRAWS):
        idx = block_indices(len(left), rng)
        out[draw] = sharpe(left[idx]) - sharpe(right[idx])
    return out


def ci(draws: np.ndarray) -> tuple[float, float]:
    finite = draws[np.isfinite(draws)]
    if len(finite) == 0:
        return float("nan"), float("nan")
    low, high = np.quantile(finite, [0.025, 0.975])
    return float(low), float(high)


def b1_val(symbol: str, target: str, X: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
    pred, _fitted = walk_forward("baseline_b1", X, y, "val")
    if pred.index.max() > LAST_ALLOWED:
        raise SystemExit("REFUSED: baseline dates cross 2021-12-31")
    return pred


def match_bss(oos: dict, symbol: str, target: str, expected: float | None) -> tuple[pd.DataFrame, float]:
    X, y = load_xy(symbol, "full", target)
    base = b1_val(symbol, target, X, y)
    model = oos[symbol][target]
    model = model[model["split"] == "val"][["y", "p"]]
    merged = model.join(base["p"].rename("b1"), how="inner")
    if len(merged) != len(model) or len(merged) != len(base):
        raise SystemExit(f"{symbol} {target} val rows model={len(model)} b1={len(base)} joined={len(merged)}")
    point = skill(brier(merged["y"], merged["p"]), brier(merged["y"], merged["b1"]))
    if not np.isfinite(point):
        raise SystemExit(f"{symbol} {target} BSS is not finite")
    if expected is not None and abs(point - expected) > 1e-4:
        raise SystemExit(f"{symbol} {target} BSS {point:.6f} does not match the stored {expected:.6f}")
    print(f"match {symbol} {target} bss {point:.6f} n={len(merged)}", flush=True)
    return merged, point


def val_books(oos: dict, symbol: str) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    prices = market(symbol)
    mapped = mapped_exposures(oos[symbol]["T_down"]["p"])
    exposures = {name: expo[split_mask(expo.index, "val")] for name, expo in mapped.items()}
    exposures = {name: expo for name, expo in exposures.items() if len(expo)}
    first = exposures["binary"]
    for name, expo in exposures.items():
        if not expo.index.equals(first.index):
            raise SystemExit(f"{symbol} {name} dates differ")
    sl = align(prices, first)
    books = {name: expo.reindex(sl.index).ffill() for name, expo in exposures.items()}
    books["BH"] = pd.Series(1.0, index=sl.index)
    books["VT"] = pd.Series(np.minimum(1.0, 0.15 / sl["rv20"].clip(lower=1e-4)), index=sl.index)
    check, _yearly = path_stats(sl["simple"], books["binary"])
    expected = 0.940654 if symbol == "spy" else 0.932889
    if abs(check["sharpe"] - expected) > 1e-4:
        raise SystemExit(f"{symbol} binary sharpe {check['sharpe']:.6f} does not match {expected:.6f}")
    print(f"match {symbol} binary sharpe {check['sharpe']:.6f} n={check['n']}", flush=True)
    return sl, books


def lagged_predictions(symbol: str, target: str) -> dict[str, pd.DataFrame]:
    X, y = load_xy(symbol, "full", target)
    lagged = X.shift(1)
    keep = lagged.notna().all(axis=1)
    lagged = lagged.loc[keep]
    y = y.loc[keep]
    out = {}
    splits = ("dev", "val") if target == "T_down" else ("val",)
    for split in splits:
        print(f"lag walk {symbol} {target} {split}", flush=True)
        pred, _fitted = walk_forward("lgbm", lagged, y, split)
        if pred.index.max() > LAST_ALLOWED:
            raise SystemExit("REFUSED: lagged predictions cross 2021-12-31")
        pred = pred.copy()
        pred["split"] = split
        out[split] = pred
    if target in ("T_down", "T_volexp"):
        print(f"lag baseline {symbol} {target} val", flush=True)
        base, _fitted = walk_forward("baseline_b1", lagged, y, "val")
        out["b1"] = base
    return out


def fmt(value: float) -> str:
    if not np.isfinite(value):
        return "nan"
    return f"{value:.4f}"


def markdown_table(rows: list[dict], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    rule = "|" + "|".join("---:" if col not in ("symbol", "target", "book") else "---" for col in columns) + "|"
    lines = [header, rule]
    for row in rows:
        cells = []
        for col in columns:
            value = row[col]
            cells.append(fmt(value) if isinstance(value, float) else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    refuse_holdout()
    check_manifest()
    oos = load_oos()
    rng = np.random.default_rng(SEED)
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    expected_bss = {("spy", "T_down"): 0.004752, ("spy", "T_volexp"): 0.415123}
    bss_rows = []
    for symbol in ("spy", "qqq"):
        for target in ("T_down", "T_volexp"):
            merged, point = match_bss(oos, symbol, target, expected_bss.get((symbol, target)))
            draws = bootstrap_bss(merged["y"].to_numpy(), merged["p"].to_numpy(), merged["b1"].to_numpy(), rng)
            low, high = ci(draws)
            bss_rows.append({
                "symbol": symbol,
                "target": target,
                "bss": point,
                "ci_low": low,
                "ci_high": high,
                "n": len(merged),
                "p_positive": float(np.mean(draws > 0)),
            })
            append_result(
                "T4.2", f"{run_id}_{symbol}", "val", target, "lgbm", "full", "bss_vs_b1",
                f"{point:.6f}", f"{low:.6f}", f"{high:.6f}", len(merged),
                "block bootstrap 21d 1000 seed 20261029; baseline is p2.5 and skill is p97.5",
            )
            print(f"bss {symbol} {target} {point:.4f} ci {low:.4f} {high:.4f}", flush=True)

    sharpe_rows = []
    cost_rows = []
    year_rows = []
    for symbol in ("spy", "qqq"):
        sl, books = val_books(oos, symbol)
        net2 = {book: daily_net(sl["simple"], expo, COST_BPS / 10000.0) for book, expo in books.items()}
        net4 = {book: daily_net(sl["simple"], expo, COST2) for book, expo in books.items()}
        bh4 = summarize(net4["BH"])
        _bh_pooled, bh_yearly = path_stats(sl["simple"], books["BH"])
        bh_years = {year: stats for year, stats in bh_yearly}
        for book, expo in books.items():
            pooled2, yearly = path_stats(sl["simple"], expo)
            pooled4 = summarize(net4[book])
            cost_rows.append({
                "symbol": symbol, "book": book,
                "sharpe_2bps": pooled2["sharpe"], "max_dd_2bps": pooled2["max_dd"],
                "sharpe_4bps": pooled4["sharpe"], "max_dd_4bps": pooled4["max_dd"],
                "n": pooled2["n"],
            })
            append_result(
                "T4.2", f"{run_id}_{symbol}", "val", "T_down", "lgbm", "full", "sharpe",
                f"{pooled4['sharpe']:.6f}", f"{bh4['sharpe']:.6f}",
                f"{pooled4['sharpe'] - bh4['sharpe']:.6f}",
                int(pooled4["n"]), f"book={book} cost=4bps baseline=BH",
            )
            if book == "BH":
                continue
            for year, stats in yearly:
                base = bh_years[year]
                year_rows.append({
                    "symbol": symbol, "year": year, "book": book,
                    "sharpe": stats["sharpe"], "bh_sharpe": base["sharpe"],
                    "max_dd": stats["max_dd"], "bh_max_dd": base["max_dd"],
                    "sharpe_ge": int(stats["sharpe"] >= base["sharpe"]),
                    "dd_less_severe": int(stats["max_dd"] > base["max_dd"]),
                })
        for book in ("binary", "linear", "tercile"):
            diff = bootstrap_sharpe_diff(net2[book].to_numpy(dtype=float), net2["BH"].to_numpy(dtype=float), rng)
            low, high = ci(diff)
            point = sharpe(net2[book].to_numpy(dtype=float)) - sharpe(net2["BH"].to_numpy(dtype=float))
            sharpe_rows.append({
                "symbol": symbol, "book": book, "sharpe_diff": point,
                "ci_low": low, "ci_high": high, "p_nonneg": float(np.mean(diff >= 0)),
                "n": len(net2[book]),
            })
            append_result(
                "T4.2", f"{run_id}_{symbol}", "val", "T_down", "lgbm", "full", "sharpe_minus_bh",
                f"{point:.6f}", f"{low:.6f}", f"{high:.6f}", len(net2[book]),
                f"book={book}; block bootstrap 21d 1000; baseline p2.5 skill p97.5",
            )
            print(f"sharpe diff {symbol} {book} {point:.4f} ci {low:.4f} {high:.4f}", flush=True)

    corr_rows = []
    for target in ("T_down", "T_volexp"):
        spy = oos["spy"][target]
        qqq = oos["qqq"][target]
        spy = spy[spy["split"] == "val"]["p"]
        qqq = qqq[qqq["split"] == "val"]["p"]
        joined = pd.concat([spy.rename("spy"), qqq.rename("qqq")], axis=1, join="inner").dropna()
        corr_rows.append({"target": target, "corr": float(joined["spy"].corr(joined["qqq"])), "n": len(joined)})

    lag_rows = []
    lag_expo_rows = []
    for symbol in ("spy", "qqq"):
        lagged_down = None
        for target in ("T_down", "T_volexp"):
            lagged = lagged_predictions(symbol, target)
            if target == "T_down":
                lagged_down = lagged
            val = lagged["val"].join(lagged["b1"]["p"].rename("b1"), how="inner")
            point = skill(brier(val["y"], val["p"]), brier(val["y"], val["b1"]))
            raw = next(row["bss"] for row in bss_rows if row["symbol"] == symbol and row["target"] == target)
            lag_rows.append({"symbol": symbol, "target": target, "bss_lag1": point, "bss_raw": raw, "n": len(val)})
            append_result(
                "T4.2", f"{run_id}_{symbol}", "val", target, "lgbm", "full", "bss_vs_b1",
                f"{point:.6f}", f"{raw:.6f}", f"{point - raw:.6f}", len(val),
                "features lagged one extra day; baseline is the unlagged validation BSS",
            )
            print(f"lag {symbol} {target} bss {point:.4f} raw {raw:.4f}", flush=True)
        frame = pd.concat([lagged_down["dev"], lagged_down["val"]]).sort_index()
        mapped = mapped_exposures(frame["p"])
        exposures = {name: expo[split_mask(expo.index, "val")] for name, expo in mapped.items()}
        sl = align(market(symbol), exposures["binary"])
        bh_pooled, _bh_years = path_stats(sl["simple"], pd.Series(1.0, index=sl.index))
        for name, expo in exposures.items():
            filled = expo.reindex(sl.index).ffill()
            pooled, _yearly = path_stats(sl["simple"], filled)
            lag_expo_rows.append({
                "symbol": symbol, "book": name, "sharpe": pooled["sharpe"],
                "bh_sharpe": bh_pooled["sharpe"], "max_dd": pooled["max_dd"],
                "bh_max_dd": bh_pooled["max_dd"], "n": pooled["n"],
            })

    lines = [
        "# T4.2 Robustness on validation",
        "",
        "Frozen model: LightGBM, feature set `full`. Validation only. "
        "The block bootstrap resamples 21-day blocks, 1,000 draws, seed 20261029. "
        "It does not refit the trees. Holdout dates were not loaded.",
        "",
        "## BSS intervals",
        "",
        markdown_table(bss_rows, ["symbol", "target", "bss", "ci_low", "ci_high", "p_positive", "n"]),
        "",
        "## Sharpe minus buy-and-hold",
        "",
        markdown_table(sharpe_rows, ["symbol", "book", "sharpe_diff", "ci_low", "ci_high", "p_nonneg", "n"]),
        "",
        "## Costs at 2 bps and 4 bps",
        "",
        markdown_table(cost_rows, ["symbol", "book", "sharpe_2bps", "max_dd_2bps", "sharpe_4bps", "max_dd_4bps", "n"]),
        "",
        "## Features lagged one extra day",
        "",
        markdown_table(lag_rows, ["symbol", "target", "bss_lag1", "bss_raw", "n"]),
        "",
        "Lagged `P(T_down)` uses the same three mappings. Cuts come from the lagged model's prior calendar year.",
        "",
        markdown_table(lag_expo_rows, ["symbol", "book", "sharpe", "bh_sharpe", "max_dd", "bh_max_dd", "n"]),
        "",
        "## Per-year stability at 2 bps",
        "",
        markdown_table(year_rows, ["symbol", "year", "book", "sharpe", "bh_sharpe", "max_dd", "bh_max_dd", "sharpe_ge", "dd_less_severe"]),
        "",
        "## SPY and QQQ probability agreement",
        "",
        markdown_table(corr_rows, ["target", "corr", "n"]),
        "",
        "- Intervals are percentiles of the block bootstrap. The trees are not refit inside each draw.",
        "- `p_positive` is the share of draws with BSS above zero. `p_nonneg` is the share with Sharpe at least buy-and-hold.",
        "- `dd_less_severe` is 1 when the stored drawdown is closer to zero than buy-and-hold.",
        "- Lagged BSS is the same walk-forward rule on the previous row's features. `bss_raw` is the unlagged validation BSS.",
        "- Holdout dates were not loaded. This file does not pick a model and does not decide a gate.",
        "",
        "What I am unsure about: the bootstrap misses training noise because LightGBM stays fixed inside each draw.",
        "",
    ]
    text = "\n".join(lines)
    (REPORTS / "w4_robustness.md").write_text(text)
    print(f"wrote {REPORTS / 'w4_robustness.md'}", flush=True)


def summarize(net: pd.Series) -> dict:
    equity = (1.0 + net).cumprod()
    peak = equity.cummax()
    drawdown = float((equity / peak - 1.0).min())
    return {"sharpe": sharpe(net.to_numpy(dtype=float)), "max_dd": drawdown, "n": int(len(net))}


if __name__ == "__main__":
    main()
