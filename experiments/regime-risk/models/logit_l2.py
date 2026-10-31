"""L2 logistic regression. C in {0.01, 0.1, 1} chosen by Brier on the last 2 train years.

Drops rv1 and rv22. Those columns exist only for the HAR reference.
Fallback C=0.1 if the inner split is too small or has one class.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

GRID = (0.01, 0.1, 1.0)
DROP = {"rv1", "rv22"}


def _brier(y, p) -> float:
    return float(np.mean((p - y) ** 2))


class Model:
    def fit(self, X, y):
        self.cols = [col for col in X.columns if col not in DROP]
        matrix = X[self.cols]
        target = np.asarray(y, dtype=int)
        cutoff = matrix.index.max() - pd.DateOffset(years=2)
        inner_val = matrix.index >= cutoff
        inner_train = ~inner_val
        self.C = 0.1
        if int(inner_train.sum()) >= 252 and int(inner_val.sum()) >= 100 and len(np.unique(target[inner_train])) == 2:
            best = None
            for C in GRID:
                scaler = StandardScaler()
                train = scaler.fit_transform(matrix.loc[inner_train].to_numpy(dtype=float))
                val = scaler.transform(matrix.loc[inner_val].to_numpy(dtype=float))
                est = LogisticRegression(C=C, solver="lbfgs", max_iter=1000)
                est.fit(train, target[inner_train])
                score = _brier(target[inner_val], est.predict_proba(val)[:, 1])
                if best is None or score < best[0]:
                    best = (score, C)
            self.C = best[1]
        self.scaler = StandardScaler()
        scaled = self.scaler.fit_transform(matrix.to_numpy(dtype=float))
        self.est = LogisticRegression(C=self.C, solver="lbfgs", max_iter=1000)
        self.est.fit(scaled, target)
        return self

    def predict(self, X):
        scaled = self.scaler.transform(X[self.cols].to_numpy(dtype=float))
        return self.est.predict_proba(scaled)[:, 1]


def make():
    return Model()
