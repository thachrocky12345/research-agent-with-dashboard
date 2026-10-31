"""T3.2 risk-gated exposure. Out-of-sample P(T_down) only.

The chosen model is LightGBM on the full feature set, the SPY development
winner from T2.4. Three mappings use the previous calendar year's out-of-sample
probabilities as the cut points. The first scored year has no trailing year and
is not traded. A T_rv forecast is sized as min(1, 0.15 / forecast vol).

This script does not load the holdout.
"""
from __future__ import annotations

import pickle
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from build_features import _pull_daily, total_return_price
from common import (
    COST_BPS,
    DATA,
    LAST_ALLOWED,
    REPORTS,
    VAL_END,
    VAL_START,
    append_result,
    assert_no_holdout,
    human_allowed,
)
from evaluate_model import load_xy, walk_forward

COST = COST_BPS / 10000
CHOSEN = ("lgbm", "full")
OOS_PATH = DATA / "oos_chosen.pkl"
TARGETS = ("T_down", "T_volexp", "T_rv")


def collect_oos() -> dict:
    """Walk dev and val once per symbol and target. Cache the out-of-sample frame."""
    out = {}
    for symbol in ("spy", "qqq"):
        out[symbol] = {}
        for target in TARGETS:
            parts = []
            for split in ("dev", "val"):
                print(f"walk {symbol} {target} {split}", flush=True)
                _x, _y = load_xy(symbol, CHOSEN[1], target)
                pred, _fitted = walk_forward(CHOSEN[0], _x, _y, split)
                frame = pred.copy()
                frame["split"] = split
                parts.append(frame)
            joined = pd.concat(parts).sort_index()
            if joined.index.has_duplicates:
                raise SystemExit(f"duplicate OOS dates for {symbol} {target}")
            assert_no_holdout(joined.index, f"oos {symbol} {target}")
            out[symbol][target] = joined
    with OOS_PATH.open("wb") as handle:
        pickle.dump(out, handle, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"saved {OOS_PATH}", flush=True)
    return out


def market(symbol: str) -> pd.DataFrame:
    raw = _pull_daily(symbol)
    px = total_return_price(raw)
    core = pd.read_pickle(DATA / "features_core.pkl")
    frame = pd.DataFrame(
        {
            "simple": px.pct_change(),
            "px": px,
            "ma200": px.rolling(200, min_periods=200).mean(),
            "rv20": core[f"{symbol}__rv20"].reindex(px.index),
        }
    )
    assert_no_holdout(frame.index, f"market {symbol}")
    return frame


def mapped_exposures(prob: pd.Series) -> dict[str, pd.Series]:
    """Cut points come from the prior calendar year's out-of-sample probabilities."""
    prob = prob.sort_index()
    built = {"binary": [], "linear": [], "tercile": []}
    for year in sorted(set(prob.index.year)):
        prior = prob[prob.index.year == year - 1]
        current = prob[prob.index.year == year]
        if len(prior) < 100 or len(current) == 0:
            print(f"skip thresholds {year} prior={len(prior)} current={len(current)}")
            continue
        p25, p75 = np.quantile(prior.to_numpy(dtype=float), [0.25, 0.75])
        p33, p66 = np.quantile(prior.to_numpy(dtype=float), [1.0 / 3.0, 2.0 / 3.0])
        values = current.to_numpy(dtype=float)
        binary = pd.Series(np.where(values > p75, 0.0, 1.0), index=current.index)
        span = float(p75 - p25)
        if span <= 1e-12:
            linear = pd.Series(1.0, index=current.index)
        else:
            linear = pd.Series(1.0 - np.clip((values - p25) / span, 0.0, 1.0), index=current.index)
        tercile = np.full(len(current), 0.5)
        tercile[values <= p33] = 1.0
        tercile[values > p66] = 0.0
        built["binary"].append(binary)
        built["linear"].append(linear)
        built["tercile"].append(pd.Series(tercile, index=current.index))
        print(
            f"thresholds {year} n_prior={len(prior)} p25={p25:.4f} p75={p75:.4f} "
            f"p33={p33:.4f} p66={p66:.4f}"
        )
    return {name: pd.concat(parts).sort_index() for name, parts in built.items() if parts}


def rv_exposure(log_rv: pd.Series) -> pd.Series:
    """min(1, 0.15 / forecast vol). Forecast vol is exp(log next-5-day RV)."""
    vol = np.exp(log_rv.to_numpy(dtype=float))
    vol = np.where(np.isfinite(vol), vol, np.inf)
    expo = np.minimum(1.0, 0.15 / np.maximum(vol, 1e-8))
    expo = np.where(np.isfinite(expo), expo, 0.0)
    return pd.Series(expo, index=log_rv.index)


def align(prices: pd.DataFrame, exposure: pd.Series) -> pd.DataFrame:
    exposure = exposure.sort_index()
    sl = prices.loc[exposure.index.min():exposure.index.max()].copy()
    sl["model"] = exposure.reindex(sl.index).ffill()
    sl = sl.dropna(subset=["simple", "px", "ma200", "rv20", "model"])
    if sl.index.max() > LAST_ALLOWED:
        raise SystemExit("REFUSED: exposure path crosses 2021-12-31")
    return sl


def pack(net: pd.Series, pos: pd.Series, turn: pd.Series) -> dict:
    equity = (1.0 + net).cumprod()
    years = max(len(net) / 252.0, 1e-9)
    peak = equity.cummax()
    drawdown = float((equity / peak - 1.0).min()) if len(equity) else float("nan")
    vol = float(net.std(ddof=0)) if len(net) else float("nan")
    sharpe = float(net.mean() / vol * np.sqrt(252.0)) if vol > 0 else float("nan")
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if len(equity) and equity.iloc[-1] > 0 else float("nan")
    return {
        "cagr": cagr,
        "sharpe": sharpe,
        "max_dd": drawdown,
        "turnover": float(turn.mean() * 252.0) if len(turn) else float("nan"),
        "time_in_market": float((pos > 0.05).mean()) if len(pos) else float("nan"),
        "n": int(len(net)),
    }


def path_stats(simple: pd.Series, exposure: pd.Series) -> tuple[dict, list[tuple[int, dict]]]:
    """Same cost math as benchmarks._stats. Exposure at close t earns the next simple return."""
    pos = exposure.shift(1).fillna(0.0)
    turn = pos.diff().abs()
    turn.iloc[0] = abs(float(pos.iloc[0]))
    net = pos * simple - turn * COST
    pooled = pack(net, pos, turn)
    yearly = []
    for year, part in net.groupby(net.index.year):
        yearly.append((int(year), pack(part, pos.reindex(part.index), turn.reindex(part.index))))
    return pooled, yearly


def panel(prices: pd.DataFrame, exposures: dict[str, pd.Series]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score model books and BH, DMA, VT on the dates of the first model book."""
    first = next(iter(exposures.values()))
    for name, expo in exposures.items():
        if not expo.index.equals(first.index):
            raise SystemExit(f"{name} dates differ from the panel dates")
    sl = align(prices, first)
    books = {}
    for name, expo in exposures.items():
        filled = expo.reindex(sl.index).ffill()
        if filled.isna().any():
            raise SystemExit(f"{name} has a gap with no prior exposure")
        books[name] = filled
    books["BH"] = pd.Series(1.0, index=sl.index)
    books["DMA"] = (sl["px"] > sl["ma200"]).astype(float)
    books["VT"] = pd.Series(np.minimum(1.0, 0.15 / sl["rv20"].clip(lower=1e-4)), index=sl.index)
    pooled_rows = []
    year_rows = []
    for name, expo in books.items():
        pooled, yearly = path_stats(sl["simple"], expo.astype(float))
        pooled.update({"book": name, "start": sl.index.min().date().isoformat(), "end": sl.index.max().date().isoformat()})
        pooled_rows.append(pooled)
        for year, stats in yearly:
            stats.update({"book": name, "year": year})
            year_rows.append(stats)
    return pd.DataFrame(pooled_rows), pd.DataFrame(year_rows)


def split_mask(index: pd.DatetimeIndex, split: str) -> pd.Series:
    if split == "dev":
        return index <= pd.Timestamp("2018-12-31")
    if split == "val":
        return (index >= VAL_START) & (index <= VAL_END)
    raise SystemExit(split)


def fmt(value: float) -> str:
    if value is None or not np.isfinite(value):
        return "nan"
    return f"{value:.4f}"


def table(frame: pd.DataFrame, columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    rule = "|" + "|".join("---:" if col != "book" else "---" for col in columns) + "|"
    lines = [header, rule]
    for rec in frame.itertuples(index=False):
        cells = []
        for col in columns:
            value = getattr(rec, col)
            cells.append(fmt(value) if isinstance(value, float) else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def gate_lines(pooled: pd.DataFrame) -> list[str]:
    bh = pooled.loc[pooled["book"] == "BH"].iloc[0]
    lines = []
    for book in ("binary", "linear", "tercile"):
        row = pooled.loc[pooled["book"] == book].iloc[0]
        dd_ok = row["max_dd"] < bh["max_dd"]
        sharpe_ok = row["sharpe"] >= bh["sharpe"]
        lines.append(
            f"{book} sharpe {row['sharpe']:.6f} vs BH {bh['sharpe']:.6f} "
            f"max_dd {row['max_dd']:.6f} vs BH {bh['max_dd']:.6f} "
            f"both {bool(dd_ok and sharpe_ok)}"
        )
    return lines


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--split" and len(sys.argv) > 2 and sys.argv[2] == "holdout":
        print("BANNER: final holdout 2022-01-03 through 2024-09-27. Human only, one run.")
        if not human_allowed():
            print("REFUSED: holdout requires HUMAN=1")
            sys.exit(2)
        print("REFUSED: the one holdout exposure run is T4.1. This week-3 call stops.")
        sys.exit(2)
    oos = collect_oos()
    spy_val = oos["spy"]["T_down"]
    spy_val = spy_val[spy_val["split"] == "val"]
    if len(spy_val) != 721:
        raise SystemExit(f"REFUSED: SPY T_down validation rows are {len(spy_val)}, expected 721")
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    report = [
        "# T3.2 Risk-gated exposure",
        "",
        "Chosen model: LightGBM, feature set `full`. Probabilities are walk-forward and out of sample. "
        "Cut points are the previous calendar year's out-of-sample `P(T_down)`. "
        "Cost is 2 bps per side on the notional changed. "
        "BH, DMA, and VT are scored on the same dates as the book in that panel. "
        "T3.1 is skipped: `config/tier_a_preregistered.json` has no combo.",
        "",
    ]
    acceptance = ["Acceptance, validation, same dates, after costs:", ""]
    for symbol in ("spy", "qqq"):
        prices = market(symbol)
        down = oos[symbol]["T_down"]["p"]
        mapped = mapped_exposures(down)
        rv_book = rv_exposure(oos[symbol]["T_rv"]["p"])
        for split in ("dev", "val"):
            split_mapped = {name: expo[split_mask(expo.index, split)] for name, expo in mapped.items()}
            split_mapped = {name: expo for name, expo in split_mapped.items() if len(expo)}
            pooled, yearly = panel(prices, split_mapped)
            pooled.insert(0, "symbol", symbol)
            pooled.insert(1, "split", split)
            pooled.insert(2, "panel", "p_down")
            yearly.insert(0, "symbol", symbol)
            yearly.insert(1, "split", split)
            yearly.insert(2, "panel", "p_down")
            report.append(f"## {symbol} {split} P(T_down) mappings")
            report.append("")
            report.append(table(pooled, ["book", "cagr", "sharpe", "max_dd", "turnover", "time_in_market", "n", "start", "end"]))
            report.append("")
            report.append(table(yearly, ["year", "book", "cagr", "sharpe", "max_dd", "turnover", "time_in_market", "n"]))
            report.append("")
            rv_split = rv_book[split_mask(rv_book.index, split)]
            rv_pooled, rv_yearly = panel(prices, {"rv_vt": rv_split})
            rv_pooled.insert(0, "symbol", symbol)
            rv_pooled.insert(1, "split", split)
            rv_yearly.insert(0, "symbol", symbol)
            rv_yearly.insert(1, "split", split)
            report.append(f"## {symbol} {split} T_rv vol sizing")
            report.append("")
            report.append(table(rv_pooled, ["book", "cagr", "sharpe", "max_dd", "turnover", "time_in_market", "n", "start", "end"]))
            report.append("")
            report.append(table(rv_yearly, ["year", "book", "cagr", "sharpe", "max_dd", "turnover", "time_in_market", "n"]))
            report.append("")
            if split == "val":
                acceptance.append(f"{symbol}")
                acceptance.extend(gate_lines(pooled))
                acceptance.append("")
            for frame, target in ((pooled, "T_down"), (rv_pooled, "T_rv")):
                bh = frame.loc[frame["book"] == "BH"].iloc[0]
                for rec in frame.itertuples(index=False):
                    if rec.book in {"DMA", "VT", "BH"}:
                        continue
                    for metric in ("sharpe", "max_dd", "cagr"):
                        value = getattr(rec, metric)
                        base = float(bh[metric])
                        append_result(
                            "T3",
                            f"{run_id}_{symbol}",
                            split,
                            target,
                            CHOSEN[0],
                            CHOSEN[1],
                            metric,
                            f"{float(value):.6f}",
                            f"{base:.6f}",
                            f"{float(value) - base:.6f}",
                            int(rec.n),
                            f"book={rec.book} baseline=BH same dates",
                        )
    report.extend(acceptance)
    text = "\n".join(report) + "\n"
    (REPORTS / "w3_exposure.md").write_text(text)
    print("\n".join(acceptance))
    print(f"wrote {REPORTS / 'w3_exposure.md'}")


if __name__ == "__main__":
    main()
