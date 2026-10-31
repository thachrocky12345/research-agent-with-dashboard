"""Small LightGBM. Depth and leaves are fixed. n_estimators stops early on the last 2 train years, and never exceeds 400.

Drops rv1 and rv22. Fallback is 200 trees if the inner split cannot host early stopping.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor, early_stopping, log_evaluation

DROP = {"rv1", "rv22"}
PARAMS = dict(
    num_leaves=7,
    max_depth=3,
    learning_rate=0.03,
    min_child_samples=50,
    colsample_bytree=0.7,
    subsample=0.7,
    subsample_freq=1,
    n_estimators=400,
    n_jobs=1,
    verbosity=-1,
    importance_type="gain",
    random_state=20261029,
)


def _classification(y) -> bool:
    values = set(np.round(np.unique(np.asarray(y, dtype=float)), 6))
    return values.issubset({0.0, 1.0}) and len(values) <= 2


class Model:
    def fit(self, X, y):
        self.cols = [col for col in X.columns if col not in DROP]
        # Breadth shares are numeric values stored as object after a NaN mask.
        matrix = X[self.cols].apply(pd.to_numeric, errors="coerce").astype("float64")
        self.kind = "clf" if _classification(y) else "reg"
        target = np.asarray(y, dtype=float)
        cutoff = matrix.index.max() - pd.DateOffset(years=2)
        inner_val = np.asarray(matrix.index >= cutoff)
        inner_train = ~inner_val
        self.est = LGBMClassifier(**PARAMS) if self.kind == "clf" else LGBMRegressor(**PARAMS)
        fit_target = target.astype(int) if self.kind == "clf" else target
        can_stop = int(inner_train.sum()) >= 252 and int(inner_val.sum()) >= 100
        if self.kind == "clf":
            can_stop = can_stop and len(np.unique(fit_target[inner_train])) == 2 and len(np.unique(fit_target[inner_val])) == 2
        if can_stop:
            self.est.fit(
                matrix.loc[inner_train],
                fit_target[inner_train],
                eval_set=[(matrix.loc[inner_val], fit_target[inner_val])],
                callbacks=[early_stopping(50, verbose=False), log_evaluation(0)],
            )
        else:
            self.est.set_params(n_estimators=200)
            self.est.fit(matrix, fit_target)
        return self

    def predict(self, X):
        matrix = X[self.cols].apply(pd.to_numeric, errors="coerce").astype("float64")
        if self.kind == "clf":
            return self.est.predict_proba(matrix)[:, 1]
        return np.asarray(self.est.predict(matrix), dtype=float)


def make():
    return Model()
