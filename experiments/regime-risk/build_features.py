"""Daily features for the forward-risk sprint. T1.3a-d.

Prices end at 2021-12-31 unless HUMAN=1. Returns use adjclose where the
column is populated. Where it is null, the price is raw close times the
last known adjclose/close factor (held flat after the vendor stopped
writing adjclose). Symbols with no adjclose at all use raw close.

Usage:
  python build_features.py --set core|fred|breadth|etf|long|full
"""
from __future__ import annotations

import argparse
import json
import pickle
import time
from datetime import date

import numpy as np
import pandas as pd

from common import (
    DATA,
    LAST_ALLOWED,
    RAW,
    assert_no_holdout,
    human_allowed,
)

END = date(2021, 12, 31)
CORE_SYMBOLS = ("spy", "qqq")
ETF_SYMBOLS = ("iwm", "dia", "tlt", "hyg", "gld", "xlk", "xlf", "xle")
FRED_SERIES = ("VIXCLS", "BAMLH0A0HYM2", "DGS10", "DGS2", "DGS3MO", "T10Y2Y")
HY_SERIES = "BAMLH0A0HYM2"
BREADTH_N = 400
# Min/max scan budget. Full pulls of the chosen 400 are separate and cached.
SPAN_CAP = 2500


def _cache(name: str) -> pd.DataFrame | None:
    path = RAW / name
    if not path.exists():
        return None
    with path.open("rb") as handle:
        return pickle.load(handle)


def _save_cache(name: str, obj) -> None:
    path = RAW / name
    with path.open("wb") as handle:
        pickle.dump(obj, handle, protocol=pickle.HIGHEST_PROTOCOL)


def _save_frame(name: str, frame: pd.DataFrame) -> None:
    assert_no_holdout(frame.index, name)
    path = DATA / name
    frame.to_pickle(path)
    print(f"saved {path} rows={len(frame)} cols={len(frame.columns)} "
          f"{frame.index.min().date()} -> {frame.index.max().date()}")


def total_return_price(frame: pd.DataFrame) -> pd.Series:
    """adjclose where present, else close times a forward-filled adjustment factor."""
    close = pd.to_numeric(frame["close"], errors="coerce")
    adj = pd.to_numeric(frame["adjclose"], errors="coerce")
    factor = adj / close.replace(0, np.nan)
    # ffill only. bfill would copy a future adjustment factor onto earlier days.
    factor = factor.ffill()
    px = adj.where(adj.notna(), close * factor)
    return px.where(px.notna(), close).astype(float)


_MEM: dict[str, pd.DataFrame] = {}
_BUILT: dict[tuple, pd.DataFrame] = {}


def _asof_key(asof: pd.Timestamp | None):
    if asof is None:
        return None
    return pd.Timestamp(asof).normalize()


def _sessions(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop weekends and non-session copies of the previous bar.

    stockdb repeats the prior OHLC on some 2018-2021 weekends and holidays.
    The 2020-04-10 SPY copy matches open, low, and close, and the high is off by one cent.
    """
    out = frame.sort_index()
    prev = out.shift(1)
    copied = (
        (out["open"] == prev["open"])
        & (out["low"] == prev["low"])
        & (out["close"] == prev["close"])
        & ((out["high"] - prev["high"]).abs() <= 0.02)
    )
    weekend = out.index.dayofweek >= 5
    keep = ~(copied.fillna(False) | weekend)
    return out.loc[keep]


def _pull_daily(symbol: str) -> pd.DataFrame:
    if symbol in _MEM:
        return _MEM[symbol]
    cached = _cache(f"daily_{symbol}.pkl")
    if cached is None:
        from app.lib.stockdb_source import get_daily_bars

        raw = get_daily_bars(symbol, end=END)
        time.sleep(0.2)
        raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
        raw = raw.sort_values("date").drop_duplicates("date").set_index("date")
        assert_no_holdout(raw.index, symbol)
        _save_cache(f"daily_{symbol}.pkl", raw)
    else:
        raw = cached
    clean = _sessions(raw)
    assert_no_holdout(clean.index, symbol)
    _MEM[symbol] = clean
    return clean


_SPANS: dict | None = None


def _load_spans() -> dict:
    global _SPANS
    if _SPANS is not None:
        return _SPANS
    path = RAW / "breadth_spans.pkl"
    _SPANS = {}
    if path.exists() and path.stat().st_size > 0:
        try:
            loaded = _cache("breadth_spans.pkl")
            if isinstance(loaded, dict):
                _SPANS = loaded
        except Exception:
            _SPANS = {}
    return _SPANS


def _store_spans() -> None:
    path = RAW / "breadth_spans.pkl"
    tmp = path.with_suffix(".pkl.tmp")
    with tmp.open("wb") as handle:
        pickle.dump(_SPANS, handle, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(path)


def _span(symbol: str, cursor) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    cached = _load_spans()
    if symbol in cached:
        return cached[symbol]
    if not symbol.replace(".", "").replace("_", "").isalnum():
        return None
    cursor.execute(f'SELECT min(date), max(date) FROM "stock_data"."{symbol}"')
    row = cursor.fetchone()
    time.sleep(0.02)
    if row is None or row[0] is None:
        cached[symbol] = None
        return None
    span = (pd.Timestamp(row[0]), pd.Timestamp(row[1]))
    cached[symbol] = span
    if len(cached) % 100 == 0:
        _store_spans()
        print(f"spans cached {len(cached)}", flush=True)
    return span


def _connect():
    import psycopg2
    from app.config import settings

    conn = psycopg2.connect(
        host=settings.stockdb_host,
        port=settings.stockdb_port,
        dbname=settings.stockdb_db,
        user=settings.stockdb_user,
        password=settings.stockdb_password,
        connect_timeout=10,
        options="-c statement_timeout=30000",
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SET default_transaction_read_only = on")
    return conn


def choose_breadth_universe() -> list[str]:
    """400 names that still exist on 2024-09-27, preferring the longest histories.

    Row-count rank (pg reltuples) shortlists candidates. Scanning all 7,145
    tables for min/max does not fit the 10-minute kill rule. The shortlist is
    the names with the most daily rows, which for this schema is the history length.
    """
    path = RAW / "breadth_universe.json"
    if path.exists():
        return json.loads(path.read_text())
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'stock_data' AND c.relkind = 'r'
        ORDER BY c.reltuples DESC
        LIMIT %s
        """,
        (SPAN_CAP,),
    )
    names = [row[0] for row in cur.fetchall() if row[0].replace(".", "").isalnum()]
    accepted = []
    for name in names:
        span = _span(name, cur)
        if span is None:
            continue
        if span[1] >= pd.Timestamp("2024-09-27"):
            accepted.append((span[0], name))
    _store_spans()
    conn.close()
    accepted.sort()
    chosen = [name for _, name in accepted[:BREADTH_N]]
    if len(chosen) < BREADTH_N:
        raise SystemExit(f"breadth universe only found {len(chosen)} names with max date >= 2024-09-27")
    path.write_text(json.dumps(chosen, indent=2) + "\n")
    print(f"breadth universe {len(chosen)} earliest_start={accepted[0][0].date()} "
          f"latest_start_in_set={accepted[BREADTH_N - 1][0].date()}")
    return chosen


def realized_vol(logret: pd.Series, window: int) -> pd.Series:
    return np.sqrt(logret.pow(2).rolling(window, min_periods=window).sum() * (252.0 / window))


def rolling_pct_rank(series: pd.Series, window: int = 252) -> pd.Series:
    arr = series.to_numpy(dtype=float)
    out = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        window_values = arr[i + 1 - window:i + 1]
        finite = window_values[np.isfinite(window_values)]
        if len(finite) and np.isfinite(window_values[-1]):
            out[i] = np.mean(finite[-1] >= finite) if np.isfinite(arr[i]) else np.nan
            if not np.isfinite(arr[i]):
                out[i] = np.nan
    return pd.Series(out, index=series.index)


def _symbol_features(raw: pd.DataFrame) -> pd.DataFrame:
    px = total_return_price(raw)
    logret = np.log(px / px.shift(1))
    high = pd.to_numeric(raw["high"], errors="coerce")
    low = pd.to_numeric(raw["low"], errors="coerce")
    close = pd.to_numeric(raw["close"], errors="coerce")
    volume = pd.to_numeric(raw["volume"], errors="coerce")
    prev_close = close.shift(1)
    true_range = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr20 = true_range.rolling(20, min_periods=20).mean()
    ma50 = px.rolling(50, min_periods=50).mean()
    ma200 = px.rolling(200, min_periods=200).mean()
    rv5 = realized_vol(logret, 5)
    rv20 = realized_vol(logret, 20)
    rv60 = realized_vol(logret, 60)
    dollar = (close * volume).replace(0, np.nan)
    amihud = (logret.abs() / dollar).rolling(20, min_periods=20).mean()
    vol_mean = volume.rolling(20, min_periods=20).mean()
    vol_std = volume.rolling(20, min_periods=20).std()
    down = (logret < 0).astype(float)
    streak = down.groupby((down != down.shift()).cumsum()).cumsum()
    streak = streak.where(logret < 0, 0.0)
    daily_range = high - low
    out = pd.DataFrame({
        "logret_1": logret,
        "logret_5": np.log(px / px.shift(5)),
        "logret_20": np.log(px / px.shift(20)),
        "logret_60": np.log(px / px.shift(60)),
        "rv1": np.sqrt(logret.pow(2) * 252.0),
        "rv5": rv5,
        "rv20": rv20,
        "rv22": realized_vol(logret, 22),
        "rv60": rv60,
        "rv5_over_rv20": rv5 / rv20,
        "dist_ma50": px / ma50 - 1.0,
        "dist_ma200": px / ma200 - 1.0,
        "ma200_slope_20": ma200 / ma200.shift(20) - 1.0,
        "dd_252": px / px.rolling(252, min_periods=252).max() - 1.0,
        "vol_z20": (volume - vol_mean) / vol_std.replace(0, np.nan),
        "amihud_20": amihud,
        "range_atr": daily_range.rolling(5, min_periods=5).max() / atr20,
        "down_streak": streak,
        "px": px,
    }, index=raw.index)
    out["last_adj_date"] = pd.NaT
    return out


def build_core(asof: pd.Timestamp | None = None) -> pd.DataFrame:
    key = ("core", _asof_key(asof))
    if key in _BUILT:
        return _BUILT[key]
    frames = {}
    for symbol in CORE_SYMBOLS:
        raw = _pull_daily(symbol)
        if asof is not None:
            raw = raw.loc[:asof]
        feat = _symbol_features(raw)
        frames[symbol] = feat.drop(columns=["px", "last_adj_date"])
    spy = frames["spy"].add_prefix("spy__")
    qqq = frames["qqq"].add_prefix("qqq__")
    joined = spy.join(qqq, how="outer")
    joined["qqq_spy_ret20"] = joined["qqq__logret_20"] - joined["spy__logret_20"]
    joined = joined.sort_index()
    if asof is None:
        _print_warmup(joined)
    _BUILT[key] = joined
    return joined


def _print_warmup(frame: pd.DataFrame) -> None:
    warm = frame.iloc[260:]
    print(f"core date range {frame.index.min().date()} -> {frame.index.max().date()}")
    print("columns:", ", ".join(frame.columns))
    nan_counts = warm.isna().sum()
    print("NaN count per column after 260-row warmup:")
    for name, count in nan_counts.items():
        print(f"  {name} {int(count)}")


def _fred_client():
    from fredapi import Fred
    from app.config import settings
    return Fred(api_key=settings.fred_api_key)


def _pull_fred(series: str) -> pd.Series:
    cached = _cache(f"fred_{series}.pkl")
    if cached is not None:
        return cached
    raw = _fred_client().get_series(series, observation_end=END.isoformat())
    raw.index = pd.to_datetime(raw.index).tz_localize(None).normalize()
    raw = raw.sort_index()
    raw = raw.loc[:LAST_ALLOWED]
    _save_cache(f"fred_{series}.pkl", raw)
    time.sleep(0.2)
    return raw


def _changes(series: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({
        "level": series,
        "chg5": series.diff(5),
        "chg20": series.diff(20),
        "pct252": rolling_pct_rank(series, 252),
    })


def build_fred(asof: pd.Timestamp | None = None, spy_rv20: pd.Series | None = None) -> pd.DataFrame:
    key = ("fred", _asof_key(asof))
    if key in _BUILT:
        frame = _BUILT[key]
        if spy_rv20 is not None:
            frame = frame.copy()
            frame["vrp"] = frame["vixcls_level"] / 100.0 - spy_rv20.reindex(frame.index)
        return frame
    spy_index = _pull_daily("spy").index
    if asof is not None:
        spy_index = spy_index[spy_index <= asof]
    pieces = []
    for series in FRED_SERIES:
        raw = _pull_fred(series)
        if asof is not None:
            raw = raw.loc[:asof]
        aligned = raw.reindex(spy_index).ffill(limit=3)
        if series == HY_SERIES:
            aligned = aligned.shift(1)
        block = _changes(aligned)
        block.columns = [f"{series.lower()}_{col}" for col in block.columns]
        pieces.append(block)
    frame = pd.concat(pieces, axis=1)
    frame["s2s10"] = frame["dgs10_level"] - frame["dgs2_level"]
    frame["s2s10_chg20"] = frame["s2s10"].diff(20)
    if spy_rv20 is None:
        core = build_core(asof=asof)
        spy_rv20 = core["spy__rv20"].reindex(frame.index)
    frame["vrp"] = frame["vixcls_level"] / 100.0 - spy_rv20.reindex(frame.index)
    frame = frame.sort_index()
    _BUILT[key] = frame
    return frame


def _breadth_panel(asof: pd.Timestamp | None = None) -> pd.DataFrame:
    symbols = choose_breadth_universe()
    columns = {}
    for symbol in symbols:
        try:
            raw = _pull_daily(symbol)
        except Exception as exc:
            print(f"skip {symbol}: {exc}")
            continue
        if asof is not None:
            raw = raw.loc[:asof]
        columns[symbol] = total_return_price(raw)
    panel = pd.DataFrame(columns)
    spy_index = _pull_daily("spy").index
    if asof is not None:
        spy_index = spy_index[spy_index <= asof]
    panel = panel.reindex(spy_index).ffill(limit=3)
    return panel


def build_breadth(asof: pd.Timestamp | None = None) -> pd.DataFrame:
    key = ("breadth", _asof_key(asof))
    if key in _BUILT:
        return _BUILT[key]
    px = _breadth_panel(asof=asof)
    ma50 = px.rolling(50, min_periods=50).mean()
    ma200 = px.rolling(200, min_periods=200).mean()
    # A missing price is not a down day. Comparisons on NaN would count it as False.
    above50 = (px > ma50).where(px.notna() & ma50.notna())
    above200 = (px > ma200).where(px.notna() & ma200.notna())
    ret20 = px / px.shift(20) - 1.0
    roll_max = px.rolling(20, min_periods=20).max()
    roll_min = px.rolling(20, min_periods=20).min()
    hi = (px >= roll_max).where(px.notna() & roll_max.notna())
    lo = (px <= roll_min).where(px.notna() & roll_min.notna())
    n50 = above50.notna().sum(axis=1)
    n200 = above200.notna().sum(axis=1)
    nret = ret20.notna().sum(axis=1)
    nhi = hi.notna().sum(axis=1)
    # This database has 24 survivors with a start before 2000. A floor of 200
    # names would blank breadth until the 2014-03-10 listing wave. Twenty names
    # keeps a defined reading through the development window.
    min_names = 20
    frame = pd.DataFrame(index=px.index)
    frame["pct_above_ma50"] = above50.mean(axis=1).where(n50 >= min_names)
    frame["pct_above_ma200"] = above200.mean(axis=1).where(n200 >= min_names)
    frame["net_adv_20"] = ((ret20 > 0).sum(axis=1) - (ret20 < 0).sum(axis=1)) / nret.replace(0, np.nan)
    frame["hi_minus_lo"] = hi.mean(axis=1).where(nhi >= min_names) - lo.mean(axis=1).where(nhi >= min_names)
    for col in ("pct_above_ma50", "pct_above_ma200", "net_adv_20", "hi_minus_lo"):
        frame[f"{col}_chg10"] = frame[col].diff(10)
    frame = frame.sort_index()
    _BUILT[key] = frame
    return frame


def _ratio_slope(ratio: pd.Series, window: int = 20) -> pd.Series:
    x = np.arange(window, dtype=float)
    x = x - x.mean()
    varx = float(np.dot(x, x))
    values = ratio.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    for i in range(window - 1, len(values)):
        window_values = values[i + 1 - window:i + 1]
        if np.isfinite(window_values).all():
            out[i] = np.dot(x, window_values - window_values.mean()) / varx
    return pd.Series(out, index=ratio.index)


def build_etf(asof: pd.Timestamp | None = None) -> pd.DataFrame:
    key = ("etf", _asof_key(asof))
    if key in _BUILT:
        return _BUILT[key]
    spy = _pull_daily("spy")
    if asof is not None:
        spy = spy.loc[:asof]
    spy_px = total_return_price(spy)
    spy_ret20 = np.log(spy_px / spy_px.shift(20))
    frame = pd.DataFrame(index=spy.index)
    for symbol, col in (("iwm", "iwm_rel20"), ("xlk", "xlk_rel20"), ("xlf", "xlf_rel20"), ("xle", "xle_rel20")):
        raw = _pull_daily(symbol)
        if asof is not None:
            raw = raw.loc[:asof]
        px = total_return_price(raw).reindex(spy.index).ffill(limit=3)
        frame[col] = np.log(px / px.shift(20)) - spy_ret20
    hyg = total_return_price(_slice(_pull_daily("hyg"), asof)).reindex(spy.index).ffill(limit=3)
    tlt = total_return_price(_slice(_pull_daily("tlt"), asof)).reindex(spy.index).ffill(limit=3)
    gld = total_return_price(_slice(_pull_daily("gld"), asof)).reindex(spy.index).ffill(limit=3)
    iwm = total_return_price(_slice(_pull_daily("iwm"), asof)).reindex(spy.index).ffill(limit=3)
    ratio_hyg = hyg / tlt.replace(0, np.nan)
    frame["hyg_tlt_chg20"] = np.log(ratio_hyg / ratio_hyg.shift(20))
    frame["gld_ret20"] = np.log(gld / gld.shift(20))
    frame["iwm_spy_slope20"] = _ratio_slope(iwm / spy_px.replace(0, np.nan), 20)
    frame = frame.sort_index()
    _BUILT[key] = frame
    return frame


def _slice(raw: pd.DataFrame, asof: pd.Timestamp | None) -> pd.DataFrame:
    if asof is None:
        return raw
    return raw.loc[:asof]


def assemble(feature_set: str, symbol: str, asof: pd.Timestamp | None = None) -> pd.DataFrame:
    """One row per date for one symbol. feature_set is long or full."""
    if symbol not in CORE_SYMBOLS:
        raise SystemExit(f"symbol must be spy or qqq, got {symbol}")
    if feature_set not in ("long", "full", "core"):
        raise SystemExit(f"assemble set must be core, long, or full, got {feature_set}")
    core = build_core(asof=asof)
    prefix = f"{symbol}__"
    own = core[[c for c in core.columns if c.startswith(prefix)]].rename(columns=lambda c: c[len(prefix):])
    pieces = [own, core[["qqq_spy_ret20"]]]
    if feature_set in ("long", "full"):
        fred = build_fred(asof=asof, spy_rv20=core["spy__rv20"])
        pieces.append(fred.drop(columns=["vrp"], errors="ignore"))
        pieces.append(build_breadth(asof=asof))
    if feature_set == "full":
        pieces.append(build_etf(asof=asof))
    frame = pieces[0]
    for piece in pieces[1:]:
        frame = frame.join(piece, how="inner")
    frame["log_rv20"] = np.log(frame["rv20"].clip(lower=1e-8))
    if "vixcls_level" in frame.columns:
        frame["log_vix"] = np.log(frame["vixcls_level"].clip(lower=1e-8))
        frame["vrp"] = frame["vixcls_level"] / 100.0 - frame["rv20"]
    empty = [col for col in frame.columns if frame[col].isna().all()]
    if empty:
        print("dropping all-null columns:", ", ".join(empty))
        frame = frame.drop(columns=empty)
    frame = frame.sort_index()
    assert_no_holdout(frame.index, f"{feature_set}:{symbol}")
    return frame


def _nan_report(frame: pd.DataFrame, label: str) -> None:
    warm = frame.iloc[min(260, len(frame)):]
    print(f"{label} {frame.index.min().date()} -> {frame.index.max().date()} cols={len(frame.columns)}")
    counted = warm.isna().sum().sort_values(ascending=False)
    print(counted.head(12).to_string())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", required=True, choices=("core", "fred", "breadth", "etf", "long", "full"))
    args = parser.parse_args()
    if human_allowed():
        print("HUMAN=1 is set. This script still caps pulls at 2021-12-31.")
    started = time.time()
    if args.set == "core":
        frame = build_core()
        _save_frame("features_core.pkl", frame)
        for symbol in CORE_SYMBOLS:
            raw = _pull_daily(symbol)
            known = raw.index[pd.to_numeric(raw["adjclose"], errors="coerce").notna()]
            last = known.max() if len(known) else None
            print(f"{symbol} last_adjclose {last.date() if last is not None else 'none'} null_adj {int(raw['adjclose'].isna().sum())}")
    elif args.set == "fred":
        frame = build_fred()
        _save_frame("features_fred.pkl", frame)
        _nan_report(frame, "fred")
    elif args.set == "breadth":
        frame = build_breadth()
        _save_frame("features_breadth.pkl", frame)
        _nan_report(frame, "breadth")
        print("Survivorship caveat: the 400 names are survivors as of 2024-09-27, so breadth levels are biased upward. Prefer changes and percentile ranks in models.")
    elif args.set == "etf":
        frame = build_etf()
        _save_frame("features_etf.pkl", frame)
        _nan_report(frame, "etf")
    else:
        # long and full are stored per symbol so the evaluator does not rebuild.
        out = {}
        for symbol in CORE_SYMBOLS:
            out[symbol] = assemble(args.set, symbol)
            _nan_report(out[symbol], f"{args.set}:{symbol}")
        path = DATA / f"features_{args.set}.pkl"
        with path.open("wb") as handle:
            pickle.dump(out, handle, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"saved {path}")
    print(f"elapsed_sec {time.time() - started:.1f}")


if __name__ == "__main__":
    main()
