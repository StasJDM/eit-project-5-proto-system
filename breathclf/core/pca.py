"""PCA transformer used by breathclf 0.0.4 serialized pipelines."""

from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


class PCAApproximator(TransformerMixin, BaseEstimator):
    """Keep the original import path and behavior required by joblib."""

    def __init__(self, n_components: int = 10, whiten: bool = False):
        self.n_components = n_components
        self.whiten = whiten

    def fit(self, X, y=None):
        X = np.asarray(X, float)
        n = max(1, min(self.n_components, X.shape[0] - 1, X.shape[1]))
        self.scaler_ = StandardScaler().fit(X)
        self.pca_ = PCA(
            n_components=n,
            whiten=self.whiten,
            svd_solver="full",
        ).fit(self.scaler_.transform(X))
        self.n_components_ = n
        return self

    def transform(self, X):
        return self.pca_.transform(self.scaler_.transform(np.asarray(X, float)))

    def inverse_transform(self, Z):
        return self.scaler_.inverse_transform(
            self.pca_.inverse_transform(np.asarray(Z, float))
        )

    @property
    def explained_variance_ratio_(self) -> np.ndarray:
        return self.pca_.explained_variance_ratio_
