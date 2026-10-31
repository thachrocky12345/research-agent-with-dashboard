"""Ridge on HAR terms plus the feature set. Alpha in {0.1, 1, 10} by MSE on the last 2 train years.

Fallback alpha=1 if the inner split is too small.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

GRID = (0.1, 1.0, 10.0)


class Model:
    def fit(self, X, y):
        self.cols = list(X.columns)
        target = np.asarray(y, dtype=float)
        cutoff = X.index.max() - pd.DateOffset(years=2)
        inner_val = X.index >= cutoff
        inner_train = ~inner_val
        self.alpha = 1.0
        if int(inner_train.sum()) >= 252 and int(inner_val.sum()) >= 100:
            best = None
            for alpha in GRID:
                scaler = StandardScaler()
                train = scaler.fit_transform(X.loc[inner_train, self.cols].to_numpy(dtype=float))
                val = scaler.transform(X.loc[inner_val, self.cols].to_numpy(dtype=float))
                est = Ridge(alpha=alpha)
                est.fit(train, target[np.asarray(inner_train)])
                pred = est.predict(val)
                score = float(np.mean((pred - target[np.asarray(inner_val)]) ** 2))
                if best is None or score < best[0]:
                    best = (score, alpha)
            self.alpha = best[1]
        self.scaler = StandardScaler()
        scaled = self.scaler.fit_transform(X[self.cols].to_numpy(dtype=float))
        self.est = Ridge(alpha=self.alpha)
        self.est.fit(scaled, target)
        return self

    def predict(self, X):
        scaled = self.scaler.transform(X[self.cols].to_numpy(dtype=float))
        return self.est.predict(scaled)


def make():
    return Model()
