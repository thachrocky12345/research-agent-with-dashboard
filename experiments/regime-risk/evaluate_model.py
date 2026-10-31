"""Locked walk-forward evaluator. T1.5.

  python evaluate_model.py --model NAME --target T_down|T_volexp|T_rv \
      --features long|full --split dev|val --symbol spy|qqq

Holdout exits unless HUMAN=1. A changed file in config/manifest.json exits.
One expanding window, refit each January on rows dated before that January.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import pickle
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from common import (
    EXP,
    LAST_ALLOWED,
    append_result,
    auc_score,
    brier,
    check_manifest,
    ece,
    human_allowed,
    logloss,
    qlike,
    qlike_skill,
    skill,
    split_bounds,
)

CLASS_TARGETS = {"T_down", "T_volexp"}


def load_model(name: str):
    path = EXP / "models" / f"{name}.py"
    if not path.exists():
        raise SystemExit(f"no model file {path}")
    spec = importlib.util.spec_from_file_location(f"regime_model_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.make()


def load_xy(symbol: str, feature_set: str, target: str) -> tuple[pd.DataFrame, pd.Series]:
    feature_path = EXP / "data" / f"features_{feature_set}.pkl"
    target_path = EXP / "data" / "targets.pkl"
    if not feature_path.exists() or not target_path.exists():
        raise SystemExit(f"missing {feature_path.name} or targets.pkl. Build them first.")
    with feature_path.open("rb") as handle:
        loaded = pickle.load(handle)
    features = loaded[symbol] if isinstance(loaded, dict) else loaded
    features = features.dropna(axis=1, how="all")
    with target_path.open("rb") as handle:
        y = pickle.load(handle)[symbol][target]
    frame = features.join(y.rename("y"), how="inner").dropna()
    if frame.index.max() > LAST_ALLOWED and not human_allowed():
        raise SystemExit("REFUSED: feature or target dates cross 2021-12-31")
    if "y" in features.columns or target in features.columns:
        raise SystemExit("REFUSED: target column leaked into X")
    return frame.drop(columns=["y"]), frame["y"]


def walk_forward(model_name: str, X: pd.DataFrame, y: pd.Series, split: str):
    start, end = split_bounds(split)
    rows = []
    last = None
    for year in range(start.year, end.year + 1):
        test = (X.index.year == year) & (X.index >= start) & (X.index <= end)
        train = X.index < pd.Timestamp(year=year, month=1, day=1)
        if int(test.sum()) < 20 or int(train.sum()) < 252:
            print(f"skip {year} test={int(test.sum())} train={int(train.sum())}")
            continue
        model = load_model(model_name)
        model.fit(X.loc[train], y.loc[train])
        pred = np.asarray(model.predict(X.loc[test]), dtype=float)
        rows.append(pd.DataFrame({"y": y.loc[test].to_numpy(), "p": pred, "year": year}, index=X.index[test]))
        last = model
    if not rows:
        raise SystemExit(f"no walk-forward years for {model_name} {split}")
    return pd.concat(rows).sort_index(), last


def report_classification(model_name, symbol, feature_set, target, split, pred, base) -> None:
    merged = pred.join(base["p"].rename("b1"), how="inner")
    y = merged["y"].to_numpy()
    p = merged["p"].to_numpy()
    b1 = merged["b1"].to_numpy()
    model_brier = brier(y, p)
    base_brier = brier(y, b1)
    bss = skill(model_brier, base_brier)
    print(f"bss_vs_b1: {bss:.6f}")
    print(f"brier: {model_brier:.6f}")
    print(f"logloss: {logloss(y, p):.6f}")
    print(f"auc: {auc_score(y, p):.6f}")
    print(f"ece: {ece(y, p):.6f}")
    print(f"n: {len(merged)}")
    print("year\tn\tbrier\tbss\tauc")
    year_rows = []
    for year, part in merged.groupby("year"):
        yb = brier(part["y"], part["p"])
        bb = brier(part["y"], part["b1"])
        year_bss = skill(yb, bb)
        year_auc = auc_score(part["y"], part["p"])
        print(f"{int(year)}\t{len(part)}\t{yb:.6f}\t{year_bss:.6f}\t{year_auc:.6f}")
        year_rows.append((int(year), len(part), bb, year_bss))
    run_id = datetime.now().strftime("%Y%m%d%H%M%S") + f"_{symbol}"
    note = "walk-forward yearly refit"
    append_result("T1.5" if model_name.startswith("baseline") or model_name == "har_rv" else "T2",
                  run_id, split, target, model_name, feature_set, "bss_vs_b1", f"{bss:.6f}",
                  f"{base_brier:.6f}", f"{bss:.6f}", len(merged), note)
    for year, n, yb, year_bss in year_rows:
        append_result("T2" if not model_name.startswith("baseline") else "T1.5",
                      run_id, split, target, model_name, feature_set, "bss_vs_b1",
                      f"{year_bss:.6f}", f"{yb:.6f}", f"{year_bss:.6f}", n, f"year={year}")


def report_regression(model_name, symbol, feature_set, target, split, pred, har) -> None:
    merged = pred.join(har["p"].rename("har"), how="inner")
    y = merged["y"].to_numpy()
    p = merged["p"].to_numpy()
    h = merged["har"].to_numpy()
    model_q = qlike(y, p)
    har_q = qlike(y, h)
    qskill = qlike_skill(model_q, har_q)
    mse = float(np.mean((p - y) ** 2))
    print(f"qlike_skill_vs_har: {qskill:.6f}")
    print(f"qlike: {model_q:.6f}")
    print(f"mse: {mse:.6f}")
    print(f"n: {len(merged)}")
    print("year\tn\tqlike\tskill\tmse")
    run_id = datetime.now().strftime("%Y%m%d%H%M%S") + f"_{symbol}"
    for year, part in merged.groupby("year"):
        yq = qlike(part["y"], part["p"])
        hq = qlike(part["y"], part["har"])
        year_skill = qlike_skill(yq, hq)
        year_mse = float(np.mean((part["p"] - part["y"]) ** 2))
        print(f"{int(year)}\t{len(part)}\t{yq:.6f}\t{year_skill:.6f}\t{year_mse:.6f}")
        append_result("T2" if model_name != "har_rv" else "T1.5", run_id, split, target, model_name,
                      feature_set, "qlike_skill_vs_har", f"{year_skill:.6f}", f"{hq:.6f}",
                      f"{year_skill:.6f}", len(part), f"year={year}")
    append_result("T2" if model_name != "har_rv" else "T1.5", run_id, split, target, model_name,
                  feature_set, "qlike_skill_vs_har", f"{qskill:.6f}", f"{har_q:.6f}",
                  f"{qskill:.6f}", len(merged), "walk-forward yearly refit")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--target", required=True, choices=("T_down", "T_volexp", "T_rv"))
    parser.add_argument("--features", required=True, choices=("long", "full", "core"))
    parser.add_argument("--split", required=True, choices=("dev", "val", "holdout"))
    parser.add_argument("--symbol", default="spy", choices=("spy", "qqq"))
    args = parser.parse_args()
    if args.split == "holdout":
        print("BANNER: final holdout 2022-01-03 through 2024-09-27. Human only, one run.")
        if not human_allowed():
            print("REFUSED: holdout requires HUMAN=1")
            sys.exit(2)
    check_manifest()
    X, y = load_xy(args.symbol, args.features, args.target)
    pred, fitted = walk_forward(args.model, X, y, args.split)
    if args.model == "lgbm" and fitted is not None and hasattr(fitted, "est"):
        gain = np.asarray(fitted.est.feature_importances_, dtype=float)
        order = np.argsort(gain)[::-1][:10]
        print("top_gain\tfeature\tgain")
        for i in order:
            print(f"top_gain\t{fitted.cols[i]}\t{gain[i]:.6f}")
    if args.target in CLASS_TARGETS:
        base, _ = walk_forward("baseline_b1", X, y, args.split)
        report_classification(args.model, args.symbol, args.features, args.target, args.split, pred, base)
    else:
        har, _ = walk_forward("har_rv", X, y, args.split)
        report_regression(args.model, args.symbol, args.features, args.target, args.split, pred, har)


if __name__ == "__main__":
    main()
