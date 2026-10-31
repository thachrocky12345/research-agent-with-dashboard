"""B0. Classification: base rate over the last 3 years of the training window.
Regression: predict log trailing RV20, which is already on the row.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _classification(y) -> bool:
    values = set(np.round(np.unique(np.asarray(y, dtype=float)), 6))
    return values.issubset({0.0, 1.0}) and len(values) <= 2


class Model:
    def fit(self, X, y):
        self.kind = "clf" if _classification(y) else "reg"
        if self.kind == "clf":
            cutoff = y.index.max() - pd.DateOffset(years=3)
            window = y.loc[y.index >= cutoff]
            self.rate = float(window.mean()) if len(window) else float(y.mean())
        return self

    def predict(self, X):
        if self.kind == "clf":
            return np.full(len(X), self.rate, dtype=float)
        return np.log(X["rv20"].clip(lower=1e-8).to_numpy(dtype=float))


def make():
    return Model()
