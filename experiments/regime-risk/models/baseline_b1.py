"""B1 gate baseline. Logistic (C=1) or ridge (alpha=1) on log RV20, log VIX, RV5/RV20.

Fixed parameters. This file is the gate, not a search.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

COLS = ["log_rv20", "log_vix", "rv5_over_rv20"]


def _classification(y) -> bool:
    values = set(np.round(np.unique(np.asarray(y, dtype=float)), 6))
    return values.issubset({0.0, 1.0}) and len(values) <= 2


class Model:
    def fit(self, X, y):
        missing = [col for col in COLS if col not in X.columns]
        if missing:
            raise RuntimeError(f"B1 missing columns {missing}")
        self.kind = "clf" if _classification(y) else "reg"
        self.scaler = StandardScaler()
        matrix = self.scaler.fit_transform(X[COLS].to_numpy(dtype=float))
        target = np.asarray(y, dtype=float)
        if self.kind == "clf":
            self.est = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
            self.est.fit(matrix, target.astype(int))
        else:
            self.est = Ridge(alpha=1.0)
            self.est.fit(matrix, target)
        return self

    def predict(self, X):
        matrix = self.scaler.transform(X[COLS].to_numpy(dtype=float))
        if self.kind == "clf":
            return self.est.predict_proba(matrix)[:, 1]
        return self.est.predict(matrix)


def make():
    return Model()
