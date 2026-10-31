"""HAR-RV reference for T_rv. OLS on log RV1, log RV5, log RV22.

The target is log realized vol, so the regressors are the logs of the
same three horizons. No penalty and no extra features.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LinearRegression

COLS = ["rv1", "rv5", "rv22"]


class Model:
    def _matrix(self, X):
        missing = [col for col in COLS if col not in X.columns]
        if missing:
            raise RuntimeError(f"HAR missing columns {missing}")
        return np.log(X[COLS].clip(lower=1e-8).to_numpy(dtype=float))

    def fit(self, X, y):
        self.est = LinearRegression()
        self.est.fit(self._matrix(X), np.asarray(y, dtype=float))
        return self

    def predict(self, X):
        return self.est.predict(self._matrix(X))


def make():
    return Model()
