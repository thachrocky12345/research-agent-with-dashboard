"""Tier A diagnostic (T1.2). Forward return of existing signals vs a matched random entry.

A signal at bar i enters at open[i+1]. Signed return at horizon h:
    r_h = (close[i+h] / open[i+1] - 1) * (+1 if bullish else -1)
Neutral signals are dropped (a -1 sign would call them bearish). Horizons are
15-minute bars: 2, 4, 8, 26, 78, 130.

Does not write the holdout ranking into config/tier_a_preregistered.json.
Holdout runs only with --only, and only the combos listed there.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
import types
import warnings
from collections import defaultdict, namedtuple
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message="Pyarrow will become", category=DeprecationWarning)

EXP = Path(__file__).resolve().parent
COMBO = EXP.parent / "indicator-combo"
CELL_DIR = COMBO / "data" / "cells"
POOL_DIR = COMBO / "data" / "pools"
CELLS_JSON = COMBO / "config" / "cells.json"

# Unpickle PoolSignal without importing indicator-combo's evaluate stack.
_bt = types.ModuleType("backtester")
_bt.PoolSignal = namedtuple("PoolSignal", "bar_index direction confidence magnitude signal_type")
sys.modules["backtester"] = _bt

HORIZONS = (2, 4, 8, 26, 78, 130)
N_BOOT = 1000
BASELINE_MULT = 200
SEED = 20261029
COST_PER_SHARE = 0.01  # one cent each way; round trip is 2 * this / close

TSV_HEADER = (
    "source\thash\tsignal_type\tdirection\th\tn_signals\tn_cells\t"
    "excess\tci_lo\tci_hi\texcess_bps\texcess_atr\tmean_cost\t"
    "hit_signal\thit_base\tfrac_cells_positive\tci_excludes_0"
)


def load_pickle(path: Path):
    with open(path, "rb") as f:
        return pickle.load(f)


def cell_ids(split: str) -> list[str]:
    spec = json.loads(CELLS_JSON.read_text())
    return [row["id"] for row in spec[split]]


def full_coverage_sources() -> list[tuple[str, str]]:
    """VSA lives on the cell. Pools: every hash directory that has all 55 cells."""
    found = [("vsa", "cell")]
    n_cells = len(list(CELL_DIR.glob("*.pkl")))
    for src in sorted(p for p in POOL_DIR.iterdir() if p.is_dir()):
        for hdir in sorted(p for p in src.iterdir() if p.is_dir()):
            n = len(list(hdir.glob("*.pkl")))
            if n == n_cells:
                found.append((src.name, hdir.name))
    return found


def load_signals(cell: dict, cell_id: str, source: str, pool_hash: str) -> list:
    if source == "vsa":
        return list(cell["vsa"])
    path = POOL_DIR / source / pool_hash / f"{cell_id}.pkl"
    if not path.exists():
        return []
    return list(load_pickle(path))


def bar_arrays(bars: list[dict]):
    n = len(bars)
    open_ = np.empty(n, np.float64)
    high = np.empty(n, np.float64)
    low = np.empty(n, np.float64)
    close = np.empty(n, np.float64)
    day = np.empty(n, np.int32)
    hour = np.empty(n, np.int16)
    for i, b in enumerate(bars):
        open_[i] = b["open"]
        high[i] = b["high"]
        low[i] = b["low"]
        close[i] = b["close"]
        dt = b["dt"]
        day[i] = dt.date().toordinal()
        hour[i] = dt.hour
    return open_, high, low, close, day, hour


def atr14(high, low, close):
    prev = np.empty_like(close)
    prev[0] = close[0]
    prev[1:] = close[:-1]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    csum = np.cumsum(tr)
    atr = np.full(len(close), np.nan)
    if len(close) >= 14:
        atr[13] = csum[13] / 14.0
    if len(close) > 14:
        atr[14:] = (csum[14:] - csum[:-14]) / 14.0
    return atr


def forward_return(open_, close, h: int) -> np.ndarray:
    """r[i] = close[i+h] / open[i+1] - 1. NaN when i+h leaves the cell."""
    out = np.full(len(close), np.nan)
    if len(close) <= h:
        return out
    i = np.arange(0, len(close) - h)
    entry = open_[i + 1]
    good = entry > 0
    out[i[good]] = close[i[good] + h] / entry[good] - 1.0
    return out


def day_reduce(values: np.ndarray, days: np.ndarray):
    if len(values) == 0:
        return np.empty(0, np.int32), np.empty(0), np.empty(0, np.int32)
    order = np.argsort(days, kind="mergesort")
    days = days[order]
    values = values[order]
    uniq, start = np.unique(days, return_index=True)
    sums = np.add.reduceat(values, start)
    counts = np.diff(np.append(start, len(values))).astype(np.int32)
    return uniq.astype(np.int32), sums.astype(np.float64), counts


def bootstrap_excess(sig_sum, sig_cnt, base_sum, base_cnt, rng: np.random.Generator):
    """Two-sample day-block bootstrap of mean(signal) - mean(baseline)."""
    if len(sig_sum) < 2 or len(base_sum) < 2 or sig_cnt.sum() == 0 or base_cnt.sum() == 0:
        return np.nan, np.nan, np.nan
    point = sig_sum.sum() / sig_cnt.sum() - base_sum.sum() / base_cnt.sum()
    ns, nb = len(sig_sum), len(base_sum)
    si = rng.integers(0, ns, size=(N_BOOT, ns))
    bi = rng.integers(0, nb, size=(N_BOOT, nb))
    s_mean = sig_sum[si].sum(axis=1) / sig_cnt[si].sum(axis=1)
    b_mean = base_sum[bi].sum(axis=1) / base_cnt[bi].sum(axis=1)
    lo, hi = np.quantile(s_mean - b_mean, [0.025, 0.975])
    return float(point), float(lo), float(hi)


def hour_index(hour: np.ndarray, valid: np.ndarray) -> dict[int, np.ndarray]:
    hv = hour[valid]
    out = {}
    for h in np.unique(hv):
        out[int(h)] = valid[hv == h]
    return out


def matched_baseline(sig_idx: np.ndarray, hour: np.ndarray, by_hour: dict[int, np.ndarray], rng):
    """200 draws per signal, from bars in the same hour. With replacement."""
    if len(sig_idx) == 0:
        return np.empty(0, np.int32)
    hours = hour[sig_idx]
    parts = []
    for h, count in zip(*np.unique(hours, return_counts=True)):
        pool = by_hour.get(int(h))
        if pool is None or len(pool) == 0:
            continue
        parts.append(rng.choice(pool, size=int(count) * BASELINE_MULT, replace=True))
    if not parts:
        return np.empty(0, np.int32)
    return np.concatenate(parts)


def sign_of(direction: str) -> float:
    return 1.0 if direction == "bullish" else -1.0


class Agg:
    """Day-sum bags for one (source, hash, type, direction, horizon), pooled later."""

    def __init__(self):
        self.sig_day = []
        self.sig_sum = []
        self.sig_cnt = []
        self.base_day = []
        self.base_sum = []
        self.base_cnt = []
        self.sig_hit_sum = []
        self.base_hit_sum = []
        self.sig_atr_sum = []
        self.sig_atr_cnt = []
        self.base_atr_sum = []
        self.base_atr_cnt = []
        self.cost_sum = []
        self.cost_cnt = []
        self.cell_excess = []
        self.n_signals = 0
        self.cell_ids = []


def score_group(sig_idx, base_idx, ret, atr_ret, cost, day, cell_key, rng) -> dict | None:
    if len(sig_idx) == 0 or len(base_idx) == 0:
        return None
    sig_ret = ret[sig_idx]
    base_ret = ret[base_idx]
    sig_day = day[sig_idx] + cell_key
    base_day = day[base_idx] + cell_key
    sd, ss, sc = day_reduce(sig_ret, sig_day)
    bd, bs, bc = day_reduce(base_ret, base_day)
    excess = float(sig_ret.mean() - base_ret.mean())
    sig_hit = day_reduce((sig_ret > 0).astype(np.float64), sig_day)
    base_hit = day_reduce((base_ret > 0).astype(np.float64), base_day)
    sig_atr = atr_ret[sig_idx]
    base_atr = atr_ret[base_idx]
    sig_atr_ok = np.isfinite(sig_atr)
    base_atr_ok = np.isfinite(base_atr)
    sig_cost = cost[sig_idx]
    return {
        "n": int(len(sig_idx)),
        "excess": excess,
        "lo": np.nan,
        "hi": np.nan,
        "sig_day": sd,
        "sig_sum": ss,
        "sig_cnt": sc,
        "base_day": bd,
        "base_sum": bs,
        "base_cnt": bc,
        "sig_hit_sum": sig_hit[1],
        "base_hit_sum": base_hit[1],
        "sig_atr_sum": float(np.nansum(sig_atr)),
        "sig_atr_n": int(sig_atr_ok.sum()),
        "base_atr_sum": float(np.nansum(base_atr)),
        "base_atr_n": int(base_atr_ok.sum()),
        "cost_sum": float(np.nansum(sig_cost)),
        "cost_n": int(np.isfinite(sig_cost).sum()),
        "hit_signal": float(np.mean(sig_ret > 0)),
        "hit_base": float(np.mean(base_ret > 0)),
    }


def combine_days(days, sums, cnts):
    """Add sums that landed on the same day (two directions, or two hashes)."""
    if len(days) == 0:
        return days, sums, cnts
    order = np.argsort(days, kind="mergesort")
    days, sums, cnts = days[order], sums[order], cnts[order]
    uniq, start = np.unique(days, return_index=True)
    return uniq, np.add.reduceat(sums, start), np.add.reduceat(cnts, start)


def add_cell(agg: Agg, scored: dict, cell_id: str):
    agg.sig_day.append(scored["sig_day"])
    agg.sig_sum.append(scored["sig_sum"])
    agg.sig_cnt.append(scored["sig_cnt"])
    agg.base_day.append(scored["base_day"])
    agg.base_sum.append(scored["base_sum"])
    agg.base_cnt.append(scored["base_cnt"])
    agg.sig_hit_sum.append(scored["sig_hit_sum"])
    agg.base_hit_sum.append(scored["base_hit_sum"])
    agg.sig_atr_sum.append(scored["sig_atr_sum"])
    agg.sig_atr_cnt.append(scored["sig_atr_n"])
    agg.base_atr_sum.append(scored["base_atr_sum"])
    agg.base_atr_cnt.append(scored["base_atr_n"])
    agg.cost_sum.append(scored["cost_sum"])
    agg.cost_cnt.append(scored["cost_n"])
    if np.isfinite(scored["excess"]):
        agg.cell_excess.append(scored["excess"])
    agg.n_signals += scored["n"]
    agg.cell_ids.append(cell_id)


def finalize(agg: Agg, rng) -> dict:
    sig_day = np.concatenate(agg.sig_day) if agg.sig_day else np.empty(0, np.int32)
    sig_sum = np.concatenate(agg.sig_sum) if agg.sig_sum else np.empty(0)
    sig_cnt = np.concatenate(agg.sig_cnt) if agg.sig_cnt else np.empty(0, np.int32)
    base_day = np.concatenate(agg.base_day) if agg.base_day else np.empty(0, np.int32)
    base_sum = np.concatenate(agg.base_sum) if agg.base_sum else np.empty(0)
    base_cnt = np.concatenate(agg.base_cnt) if agg.base_cnt else np.empty(0, np.int32)
    sig_day, sig_sum, sig_cnt = combine_days(sig_day, sig_sum, sig_cnt)
    base_day, base_sum, base_cnt = combine_days(base_day, base_sum, base_cnt)
    excess, lo, hi = bootstrap_excess(sig_sum, sig_cnt, base_sum, base_cnt, rng)
    hit_s_num = float(sum(float(np.sum(x)) for x in agg.sig_hit_sum)) if agg.sig_hit_sum else 0.0
    hit_b_num = float(sum(float(np.sum(x)) for x in agg.base_hit_sum)) if agg.base_hit_sum else 0.0
    hit_s = hit_s_num / float(sig_cnt.sum()) if len(sig_cnt) and sig_cnt.sum() else np.nan
    hit_b = hit_b_num / float(base_cnt.sum()) if len(base_cnt) and base_cnt.sum() else np.nan
    atr_n_s = int(np.sum(agg.sig_atr_cnt))
    atr_n_b = int(np.sum(agg.base_atr_cnt))
    excess_atr = np.nan
    if atr_n_s and atr_n_b:
        excess_atr = float(np.sum(agg.sig_atr_sum) / atr_n_s - np.sum(agg.base_atr_sum) / atr_n_b)
    cost_n = int(np.sum(agg.cost_cnt))
    mean_cost = float(np.sum(agg.cost_sum) / cost_n) if cost_n else np.nan
    cells_pos = float(np.mean(np.array(agg.cell_excess) > 0)) if agg.cell_excess else np.nan
    excludes = bool(np.isfinite(lo) and np.isfinite(hi) and (lo > 0 or hi < 0))
    return {
        "n_signals": agg.n_signals,
        "n_cells": len(set(agg.cell_ids)),
        "excess": excess,
        "ci_lo": lo,
        "ci_hi": hi,
        "excess_bps": excess * 1e4 if np.isfinite(excess) else np.nan,
        "excess_atr": excess_atr,
        "mean_cost": mean_cost,
        "hit_signal": hit_s,
        "hit_base": hit_b,
        "frac_cells_positive": cells_pos,
        "ci_excludes_0": excludes,
    }


def prepare_cell(cell_id: str):
    cell = load_pickle(CELL_DIR / f"{cell_id}.pkl")
    open_, high, low, close, day, hour = bar_arrays(cell["bars"])
    atr = atr14(high, low, close)
    return cell, open_, high, low, close, day, hour, atr


def group_real_signals(signals, n: int) -> dict[tuple[str, str], np.ndarray]:
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    for s in signals:
        direction = s.direction
        if direction not in ("bullish", "bearish"):
            continue
        i = int(s.bar_index)
        if i < 0 or i >= n:
            continue
        buckets[(s.signal_type, direction)].append(i)
    return {k: np.asarray(v, np.int32) for k, v in buckets.items()}


def score_index_map(groups, ret_h, atr_h, cost, day, hour, by_hour, cell_key, rng, aggs, source, pool_hash, cell_id, horizons):
    for (stype, direction), idx0 in groups.items():
        sign = sign_of(direction)
        for h in horizons:
            valid = idx0[np.isfinite(ret_h[h][idx0])]
            if len(valid) == 0:
                continue
            base = matched_baseline(valid, hour, by_hour[h], rng)
            base = base[np.isfinite(ret_h[h][base])] if len(base) else base
            scored = score_group(valid, base, ret_h[h] * sign, atr_h[h] * sign, cost, day, cell_key, rng)
            if scored is None:
                continue
            key = (source, pool_hash, stype, direction, h)
            add_cell(aggs[key], scored, cell_id)


def cheat_indices(ret4: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    pos = np.flatnonzero(np.isfinite(ret4) & (ret4 > 0))
    if len(pos) == 0:
        return pos.astype(np.int32)
    k = max(1, int(round(0.10 * len(pos))))
    k = min(k, len(pos))
    return np.sort(rng.choice(pos, size=k, replace=False).astype(np.int32))


def random_indices(n_bars: int, n_real: int, ret_long, rng) -> np.ndarray:
    eligible = np.flatnonzero(np.isfinite(ret_long))
    if len(eligible) == 0 or n_real <= 0:
        return np.empty(0, np.int32)
    # Density = n_real / n_bars, applied to bars that can complete the longest horizon.
    k = int(round(n_real * len(eligible) / max(n_bars, 1)))
    k = max(1, k)
    replace = k > len(eligible)
    return rng.choice(eligible, size=k, replace=replace).astype(np.int32)


def assign_directions(n: int, real_dirs: list[str], rng) -> np.ndarray:
    dirs = [d for d in real_dirs if d in ("bullish", "bearish")]
    if not dirs:
        dirs = ["bullish", "bearish"]
    vals, counts = np.unique(dirs, return_counts=True)
    p = counts / counts.sum()
    return rng.choice(vals, size=n, p=p)


def count_real(cell, cell_id, sources) -> tuple[int, list[str]]:
    n = 0
    dirs = []
    for source, pool_hash in sources:
        for s in load_signals(cell, cell_id, source, pool_hash):
            if s.direction not in ("bullish", "bearish"):
                continue
            n += 1
            dirs.append(s.direction)
    return n, dirs


def fmt(x, nd=6):
    if x is None or not np.isfinite(x):
        return ""
    return f"{x:.{nd}f}"


def row_tsv(source, pool_hash, stype, direction, h, fin) -> str:
    return "\t".join([
        source, pool_hash, stype, direction, str(h),
        str(fin["n_signals"]), str(fin["n_cells"]),
        fmt(fin["excess"]), fmt(fin["ci_lo"]), fmt(fin["ci_hi"]),
        fmt(fin["excess_bps"], 2), fmt(fin["excess_atr"]), fmt(fin["mean_cost"]),
        fmt(fin["hit_signal"], 4), fmt(fin["hit_base"], 4),
        fmt(fin["frac_cells_positive"], 4),
        "1" if fin["ci_excludes_0"] else "0",
    ])


def append_results(rows: list[str]):
    path = EXP / "results.tsv"
    with open(path, "a") as f:
        for row in rows:
            f.write(row + "\n")


def _extend_agg(dest: Agg, src: Agg):
    dest.sig_day.extend(src.sig_day)
    dest.sig_sum.extend(src.sig_sum)
    dest.sig_cnt.extend(src.sig_cnt)
    dest.base_day.extend(src.base_day)
    dest.base_sum.extend(src.base_sum)
    dest.base_cnt.extend(src.base_cnt)
    dest.sig_hit_sum.extend(src.sig_hit_sum)
    dest.base_hit_sum.extend(src.base_hit_sum)
    dest.sig_atr_sum.extend(src.sig_atr_sum)
    dest.sig_atr_cnt.extend(src.sig_atr_cnt)
    dest.base_atr_sum.extend(src.base_atr_sum)
    dest.base_atr_cnt.extend(src.base_atr_cnt)
    dest.cost_sum.extend(src.cost_sum)
    dest.cost_cnt.extend(src.cost_cnt)
    dest.cell_excess.extend(src.cell_excess)
    dest.n_signals += src.n_signals
    dest.cell_ids.extend(src.cell_ids)


def _collapse_horizons(cell_aggs: dict, kind: str) -> dict:
    if kind == "cheat":
        return {key[4]: agg for key, agg in cell_aggs.items() if key[3] == "bullish"}
    merged: dict[int, Agg] = defaultdict(Agg)
    for key, agg in cell_aggs.items():
        _extend_agg(merged[key[4]], agg)
    return merged


def run_control(split: str, kind: str):
    t0 = time.time()
    ids = cell_ids(split)
    sources = full_coverage_sources()
    print(f"sources {sources}", flush=True)
    # Per cell, per horizon, for the acceptance test. Cheat is bullish only.
    # Random is scored per horizon on all random fires (directions mixed, baseline matched within direction).
    per_cell = []
    aggs: dict[tuple, Agg] = defaultdict(Agg)
    for ci, cell_id in enumerate(ids):
        cell, open_, high, low, close, day, hour, atr = prepare_cell(cell_id)
        n = len(close)
        ret = {h: forward_return(open_, close, h) for h in HORIZONS}
        atr_unit = {}
        for h, r in ret.items():
            scaled = np.full(n, np.nan)
            ok = np.isfinite(r) & np.isfinite(atr) & (atr > 0) & (close > 0)
            scaled[ok] = r[ok] * close[ok] / atr[ok]
            atr_unit[h] = scaled
        cost = np.full(n, np.nan)
        pos = close > 0
        cost[pos] = 2.0 * COST_PER_SHARE / close[pos]
        if kind == "random":
            # Random fires are drawn only from bars that can finish the longest
            # horizon. The baseline has to use that same set.
            long_ok = np.isfinite(ret[max(HORIZONS)])
            by_hour = {
                h: hour_index(hour, np.flatnonzero(np.isfinite(ret[h]) & long_ok))
                for h in HORIZONS
            }
        else:
            by_hour = {h: hour_index(hour, np.flatnonzero(np.isfinite(ret[h]))) for h in HORIZONS}
        rng = np.random.default_rng(SEED + ci * 17 + (1 if kind == "random" else 0))
        cell_key = (ci + 1) * 1_000_000
        if kind == "cheat":
            idx = cheat_indices(ret[4], rng)
            groups = {("CHEAT", "bullish"): idx}
            horizons = HORIZONS
        else:
            n_real, dirs = count_real(cell, cell_id, sources)
            idx = random_indices(n, n_real, ret[max(HORIZONS)], rng)
            chosen_dir = assign_directions(len(idx), dirs, rng) if len(idx) else np.array([])
            groups = {}
            for direction in ("bullish", "bearish"):
                take = idx[chosen_dir == direction] if len(idx) else np.empty(0, np.int32)
                if len(take):
                    groups[(f"RANDOM", direction)] = take
            horizons = HORIZONS
            print(f"{cell_id} random_fires={len(idx)} real_signals={n_real}", flush=True)
        if kind == "cheat":
            print(f"{cell_id} cheat_fires={len(idx)}", flush=True)
        cell_aggs: dict[tuple, Agg] = defaultdict(Agg)
        score_index_map(groups, ret, atr_unit, cost, day, hour, by_hour, cell_key, rng, cell_aggs, "control", kind, cell_id, horizons)
        for key, agg in cell_aggs.items():
            dest = aggs[key]
            _extend_agg(dest, agg)
        rng_cell = np.random.default_rng(SEED + 1000 + ci)
        for h, agg in sorted(_collapse_horizons(cell_aggs, kind).items()):
            fin = finalize(agg, rng_cell)
            per_cell.append({"cell": cell_id, "h": h, **fin})
    rng_pool = np.random.default_rng(SEED + 99)
    finished = []
    lines = [TSV_HEADER]
    for key in sorted(aggs, key=lambda k: (k[0], k[1], k[2], k[3], k[4])):
        fin = finalize(aggs[key], rng_pool)
        source, pool_hash, stype, direction, h = key
        lines.append(row_tsv(source, pool_hash, stype, direction, h, fin))
        finished.append((key, fin))
    out_tsv = EXP / "reports" / f"tier_a_{kind}_{split}.tsv"
    out_tsv.write_text("\n".join(lines) + "\n")

    acceptance = _acceptance_text(kind, split, per_cell)
    print(acceptance, flush=True)
    elapsed = time.time() - t0
    print(f"elapsed_sec {elapsed:.1f}", flush=True)
    report = _control_report(kind, split, per_cell, finished, acceptance, elapsed)
    (EXP / "reports" / f"T1.2a_{kind}.md").write_text(report)
    n_cells = len(cell_ids(split))
    metric = "cheat_h4_all_exclude_0" if kind == "cheat" else "random_min_frac_include_0"
    value = "1" if "PASS" in acceptance else "0"
    append_results([
        f"T1.2a\t{kind}-{split}\t{split}\tnone\tcontrol_{kind}\tnone\t{metric}\t{value}\t0\t\t{n_cells}\t{acceptance.splitlines()[-1]}"
    ])
    if "FAIL" in acceptance:
        return 1
    return 0


def _per_cell_from_pass(split: str, kind: str, sources) -> list[dict]:
    """Second, cell-local pass so the acceptance test is per cell, not pooled."""
    ids = cell_ids(split)
    rows = []
    for ci, cell_id in enumerate(ids):
        cell, open_, high, low, close, day, hour, atr = prepare_cell(cell_id)
        n = len(close)
        ret = {h: forward_return(open_, close, h) for h in HORIZONS}
        atr_unit = {h: np.full(n, np.nan) for h in HORIZONS}
        cost = np.full(n, np.nan)
        pos = close > 0
        cost[pos] = 2.0 * COST_PER_SHARE / close[pos]
        by_hour = {h: hour_index(hour, np.flatnonzero(np.isfinite(ret[h]))) for h in HORIZONS}
        rng = np.random.default_rng(SEED + ci * 17 + (1 if kind == "random" else 0))
        if kind == "cheat":
            groups = {("CHEAT", "bullish"): cheat_indices(ret[4], rng)}
        else:
            n_real, dirs = count_real(cell, cell_id, sources)
            idx = random_indices(n, n_real, ret[max(HORIZONS)], rng)
            chosen = assign_directions(len(idx), dirs, rng) if len(idx) else np.array([])
            groups = {}
            for direction in ("bullish", "bearish"):
                take = idx[chosen == direction] if len(idx) else np.empty(0, np.int32)
                if len(take):
                    groups[("RANDOM", direction)] = take
        cell_aggs: dict[tuple, Agg] = defaultdict(Agg)
        score_index_map(groups, ret, atr_unit, cost, day, hour, by_hour, 0, rng, cell_aggs, "control", kind, cell_id, HORIZONS)
        rng_f = np.random.default_rng(SEED + 1000 + ci)
        # Collapse directions within a horizon for the random acceptance line.
        by_h: dict[int, Agg] = {}
        if kind == "cheat":
            for key, agg in cell_aggs.items():
                h = key[4]
                if key[3] != "bullish":
                    continue
                by_h[h] = agg
        else:
            merged: dict[int, Agg] = defaultdict(Agg)
            for key, agg in cell_aggs.items():
                dest = merged[key[4]]
                dest.sig_day.extend(agg.sig_day)
                dest.sig_sum.extend(agg.sig_sum)
                dest.sig_cnt.extend(agg.sig_cnt)
                dest.base_day.extend(agg.base_day)
                dest.base_sum.extend(agg.base_sum)
                dest.base_cnt.extend(agg.base_cnt)
                dest.sig_hit_sum.extend(agg.sig_hit_sum)
                dest.base_hit_sum.extend(agg.base_hit_sum)
                dest.sig_atr_sum.extend(agg.sig_atr_sum)
                dest.sig_atr_cnt.extend(agg.sig_atr_cnt)
                dest.base_atr_sum.extend(agg.base_atr_sum)
                dest.base_atr_cnt.extend(agg.base_atr_cnt)
                dest.cost_sum.extend(agg.cost_sum)
                dest.cost_cnt.extend(agg.cost_cnt)
                dest.cell_excess.extend(agg.cell_excess)
                dest.n_signals += agg.n_signals
                dest.cell_ids.extend(agg.cell_ids)
            by_h = merged
        for h, agg in sorted(by_h.items()):
            fin = finalize(agg, rng_f)
            rows.append({"cell": cell_id, "h": h, **fin})
    return rows


def _acceptance_text(kind: str, split: str, rows: list[dict]) -> str:
    cells = sorted({r["cell"] for r in rows})
    lines = [f"CONTROL {kind} split={split} cells={len(cells)}"]
    if kind == "cheat":
        h4 = [r for r in rows if r["h"] == 4]
        flags = []
        min_bps = np.inf
        for r in h4:
            ok = bool(r["ci_excludes_0"] and np.isfinite(r["excess"]) and r["excess"] > 0 and r["ci_lo"] > 0)
            flags.append(ok)
            if np.isfinite(r["excess_bps"]):
                min_bps = min(min_bps, r["excess_bps"])
            lines.append(
                f"cell {r['cell']} h=4 n={r['n_signals']} excess_bps={r['excess_bps']:.2f} "
                f"ci_lo_bps={r['ci_lo']*1e4:.2f} ci_hi_bps={r['ci_hi']*1e4:.2f} excludes_0={int(ok)}"
            )
        passed = bool(h4) and all(flags) and len(h4) == len(cells)
        lines.append(
            f"ACCEPTANCE cheat_all_cells_h4_excludes_0={int(passed)} min_excess_bps={min_bps:.2f} "
            f"{'PASS' if passed else 'FAIL'}"
        )
        return "\n".join(lines)
    # Per horizon: fraction of cells whose CI includes 0. Every horizon must be >= 0.90.
    fracs = []
    joint_ok = 0
    for cell in cells:
        mine = [r for r in rows if r["cell"] == cell]
        by_h = {r["h"]: r for r in mine}
        cell_all = True
        for h in HORIZONS:
            r = by_h.get(h)
            includes = bool(r and np.isfinite(r["ci_lo"]) and r["ci_lo"] <= 0 <= r["ci_hi"])
            if not includes:
                cell_all = False
        if cell_all:
            joint_ok += 1
    for h in HORIZONS:
        mine = [r for r in rows if r["h"] == h]
        n_in = sum(1 for r in mine if np.isfinite(r["ci_lo"]) and r["ci_lo"] <= 0 <= r["ci_hi"])
        frac = n_in / len(mine) if mine else 0.0
        fracs.append(frac)
        lines.append(f"horizon {h} cells={len(mine)} frac_ci_includes_0={frac:.3f}")
        for r in mine:
            includes = bool(np.isfinite(r["ci_lo"]) and r["ci_lo"] <= 0 <= r["ci_hi"])
            if not includes:
                lines.append(
                    f"  exclude {r['cell']} h={h} excess_bps={r['excess_bps']:.2f} "
                    f"ci_lo_bps={r['ci_lo']*1e4:.2f} ci_hi_bps={r['ci_hi']*1e4:.2f}"
                )
    min_frac = min(fracs) if fracs else 0.0
    joint = joint_ok / len(cells) if cells else 0.0
    passed = min_frac >= 0.90
    lines.append(
        f"ACCEPTANCE random_per_horizon_min_frac_ci_includes_0={min_frac:.3f} "
        f"joint_frac_cells_all_horizons_include_0={joint:.3f} "
        f"{'PASS' if passed else 'FAIL'}"
    )
    return "\n".join(lines)


def _control_report(kind, split, per_cell, finished, acceptance, elapsed) -> str:
    h4 = [r for r in per_cell if r["h"] == 4]
    h4_sorted = sorted(h4, key=lambda r: r["excess_bps"] if np.isfinite(r["excess_bps"]) else -1e9, reverse=True)
    show = h4_sorted[:5]
    table = ["| cell | h | n | excess bps | CI lo bps | CI hi bps | hit | hit base |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in show:
        table.append(
            f"| {r['cell']} | {r['h']} | {r['n_signals']} | {r['excess_bps']:.2f} | "
            f"{r['ci_lo']*1e4:.2f} | {r['ci_hi']*1e4:.2f} | {r['hit_signal']:.3f} | {r['hit_base']:.3f} |"
        )
    bullets = [
        f"Control `{kind}` on the `{split}` split, {len({r['cell'] for r in per_cell})} cells, {elapsed:.1f}s.",
        "Matched baseline: 200 bars per signal, same hour of day, same sign. Day-block bootstrap, 1000 draws, 95% percentile CI.",
        "Cheat fires on a random 10% of bars whose 4-bar forward return is positive, signed bullish.",
        "Random fires at the real signals' density (VSA plus every 55-cell pool hash) and is signed from that direction mix.",
        "Neutral pool rows are ignored. Round-trip cost line is 2 * $0.01 / close, reported on the real-signal run.",
    ]
    return (
        f"# T1.2a {kind} control ({split})\n\n"
        + "\n".join(table)
        + "\n\n"
        + "\n".join(f"- {b}" for b in bullets)
        + "\n\nWhat I am unsure about: the acceptance uses, for the random control, the fraction of cells whose CI includes 0 at each horizon separately (every horizon must clear 90%). A cell that must clear all six horizons at once is a harder bar and is printed as joint_frac.\n\n"
        + "```\n" + acceptance + "\n```\n"
    )


def load_only(path: str) -> list[dict]:
    payload = json.loads((EXP / path).read_text()) if not Path(path).is_absolute() else json.loads(Path(path).read_text())
    # allow path relative to experiment
    if not payload.get("combos") and not Path(path).is_absolute():
        payload = json.loads((EXP / path).read_text())
    return payload.get("combos") or []


def combo_allows(combo_list: list[dict], source, pool_hash, stype, direction, h) -> bool:
    if not combo_list:
        return True
    for c in combo_list:
        if c.get("source") not in (None, source):
            continue
        if c.get("hash") not in (None, pool_hash):
            continue
        if c.get("signal_type") not in (None, stype):
            continue
        if c.get("direction") not in (None, direction):
            continue
        if c.get("h") not in (None, h):
            continue
        return True
    return False


def run_real(split: str, only_path: str | None):
    t0 = time.time()
    ids = cell_ids(split)
    sources = full_coverage_sources()
    combos = load_only(only_path) if only_path else []
    if split == "holdout":
        if not only_path:
            raise SystemExit("refusing holdout without --only config/tier_a_preregistered.json")
        if not combos:
            raise SystemExit("refusing holdout: tier_a_preregistered.json has no combos")
    print(f"split={split} cells={len(ids)} sources={sources} only={len(combos)}", flush=True)
    aggs: dict[tuple, Agg] = defaultdict(Agg)
    for ci, cell_id in enumerate(ids):
        cell, open_, high, low, close, day, hour, atr = prepare_cell(cell_id)
        n = len(close)
        ret = {h: forward_return(open_, close, h) for h in HORIZONS}
        atr_unit = {}
        for h, r in ret.items():
            scaled = np.full(n, np.nan)
            ok = np.isfinite(r) & np.isfinite(atr) & (atr > 0) & (close > 0)
            scaled[ok] = r[ok] * close[ok] / atr[ok]
            atr_unit[h] = scaled
        cost = np.full(n, np.nan)
        pos = close > 0
        cost[pos] = 2.0 * COST_PER_SHARE / close[pos]
        by_hour = {h: hour_index(hour, np.flatnonzero(np.isfinite(ret[h]))) for h in HORIZONS}
        rng = np.random.default_rng(SEED + 50 + ci)
        cell_key = (ci + 1) * 1_000_000
        n_groups = 0
        for source, pool_hash in sources:
            signals = load_signals(cell, cell_id, source, pool_hash)
            groups = group_real_signals(signals, n)
            if combos:
                groups = {
                    k: v for k, v in groups.items()
                    if any(combo_allows([c], source, pool_hash, k[0], k[1], h) for h in HORIZONS for c in [c])
                    and any(combo_allows(combos, source, pool_hash, k[0], k[1], h) for h in HORIZONS)
                }
            before = len(aggs)
            score_index_map(
                groups, ret, atr_unit, cost, day, hour, by_hour, cell_key, rng, aggs,
                source, pool_hash, cell_id, HORIZONS,
            )
            n_groups += max(0, len(aggs) - before)
        print(f"{cell_id} bars={n} new_keys={n_groups} total_keys={len(aggs)}", flush=True)
    if combos:
        # Drop keys the human did not list (horizon-specific).
        aggs = {
            k: v for k, v in aggs.items()
            if combo_allows(combos, k[0], k[1], k[2], k[3], k[4])
        }
    rng_pool = np.random.default_rng(SEED + 7)
    lines = [TSV_HEADER]
    finished = []
    for key in sorted(aggs):
        fin = finalize(aggs[key], rng_pool)
        source, pool_hash, stype, direction, h = key
        lines.append(row_tsv(source, pool_hash, stype, direction, h, fin))
        finished.append((key, fin))
    tag = "holdout" if split == "holdout" else "train"
    out_tsv = EXP / "reports" / f"tier_a_{tag}.tsv"
    out_tsv.write_text("\n".join(lines) + "\n")
    report = _train_report(split, finished, time.time() - t0)
    (EXP / "reports" / f"tier_a_{tag}.md").write_text(report)
    n_excl = sum(1 for _, fin in finished if fin["ci_excludes_0"])
    append_results([
        f"T1.2b\t{tag}\t{split}\tnone\ttier_a\tall\tn_combos\t{len(finished)}\t\t\t{len(finished)}\t",
        f"T1.2b\t{tag}\t{split}\tnone\ttier_a\tall\tn_ci_excludes_0\t{n_excl}\t{0.05 * len(finished):.1f}\t\t{len(finished)}\tchance_about_5pct",
    ])
    print(report, flush=True)
    print(f"ACCEPTANCE rows={len(finished)} ci_excludes_0={n_excl} of {len(finished)} chance_about_{0.05 * len(finished):.1f}", flush=True)
    return 0


def _train_report(split: str, finished, elapsed: float) -> str:
    def width(fin):
        if not (np.isfinite(fin["ci_lo"]) and np.isfinite(fin["ci_hi"])):
            return np.nan
        return fin["ci_hi"] - fin["ci_lo"]

    ranked = []
    for key, fin in finished:
        w = width(fin)
        ratio = fin["excess"] / w if np.isfinite(w) and w > 0 and np.isfinite(fin["excess"]) else np.nan
        cost_bps = fin["mean_cost"] * 1e4 if np.isfinite(fin["mean_cost"]) else np.nan
        ranked.append((ratio, key, fin, cost_bps))
    valid = [r for r in ranked if np.isfinite(r[0])]
    valid.sort(key=lambda r: r[0], reverse=True)
    best = valid[:15]
    worst = sorted(valid, key=lambda r: r[0])[:5]
    n_excl = sum(1 for _, fin in finished if fin["ci_excludes_0"])
    chance = 0.05 * len(finished)

    def table(rows):
        head = [
            "| source | hash | type | dir | h | n | excess bps | CI lo | CI hi | ratio | hit | hit base | frac cells + | cost bps |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for ratio, key, fin, cost_bps in rows:
            source, pool_hash, stype, direction, h = key
            head.append(
                f"| {source} | {pool_hash} | {stype} | {direction} | {h} | {fin['n_signals']} | "
                f"{fin['excess_bps']:.2f} | {fin['ci_lo']*1e4:.2f} | {fin['ci_hi']*1e4:.2f} | {ratio:.2f} | "
                f"{fin['hit_signal']:.3f} | {fin['hit_base']:.3f} | {fin['frac_cells_positive']:.2f} | {cost_bps:.2f} |"
            )
        return "\n".join(head)

    bullets = [
        f"Train-cell Tier A, {len(finished)} combos (source, hash, signal type, direction, horizon), {elapsed:.1f}s. This is a ranking for reading, not a selection.",
        f"{n_excl} of {len(finished)} combos have a 95% CI that excludes 0. Pure chance at 5% would be about {chance:.1f}.",
        "Excess is signal mean minus matched-random mean, in bps of the underlying. Cost bps is the mean of 2 * $0.01 / close at the signal bar (slippage line from the card, not the 2 bps economic cost).",
        "A combo is not marked alive here. Alive requires the cost test on train and a holdout CI, and the holdout list is still empty.",
        "Hashes are the pool directories that contain all 55 cells. VSA uses hash `cell` because those signals are stored on the cell.",
    ]
    return (
        f"# Tier A {split}\n\n"
        "## 15 highest excess / CI width\n\n"
        + table(best)
        + "\n\n## 5 lowest excess / CI width\n\n"
        + table(worst)
        + "\n\n"
        + "\n".join(f"- {b}" for b in bullets)
        + "\n\nWhat I am unsure about: several pool hashes for the same source are different generator settings, so the same signal type can appear more than once. Overlapping horizons share days; the day-block bootstrap is the dependence control, and it does not remove the multiple-comparison problem in this table.\n"
    )


def main():
    p = argparse.ArgumentParser(description="Tier A forward-return diagnostic")
    p.add_argument("--split", choices=("train", "holdout"), required=True)
    p.add_argument("--only", default=None, help="JSON file of pre-registered combos")
    p.add_argument("--control", choices=("cheat", "random"), default=None)
    args = p.parse_args()
    if args.split == "holdout" and args.control is None and not args.only:
        raise SystemExit("refusing holdout without --only")
    if args.control:
        code = run_control(args.split, args.control)
    else:
        code = run_real(args.split, args.only)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
