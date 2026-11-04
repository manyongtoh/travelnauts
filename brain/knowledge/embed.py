"""Embeddings for search by meaning.

LocalEmbedder runs offline: character n-grams reduced to 96 dimensions (LSA). It catches spelling
variants and word forms ("Tailand", "reistijd" and "tijd", "kinderen" and "kids" only partly), not real
synonyms. AzureEmbedder uses an Azure-hosted embedding model (BRAIN_EMBEDDINGS=azure:<deployment>), and in
Postgres the vectors live in pgvector next to the full-text index.
"""
from __future__ import annotations

import os

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize


class LocalEmbedder:
    name = "local-char-lsa"

    def fit(self, docs: list[str]) -> "LocalEmbedder":
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, lowercase=True)
        x = self.vec.fit_transform(docs)
        dims = max(2, min(96, x.shape[0] - 1, x.shape[1] - 1))
        self.svd = TruncatedSVD(n_components=dims, random_state=0)
        self.docs = normalize(self.svd.fit_transform(x))
        return self

    def query(self, text: str) -> np.ndarray:
        return normalize(self.svd.transform(self.vec.transform([text])))[0]

    def scores(self, text: str) -> np.ndarray:
        return self.docs @ self.query(text)


class AzureEmbedder:  # pragma: no cover - needs Azure
    def __init__(self, deployment: str):
        from openai import AzureOpenAI
        self.client = AzureOpenAI(api_version="2024-10-21")
        self.deployment = deployment
        self.name = f"azure:{deployment}"

    def _embed(self, texts: list[str]) -> np.ndarray:
        r = self.client.embeddings.create(model=self.deployment, input=texts)
        return normalize(np.array([d.embedding for d in r.data]))

    def fit(self, docs: list[str]) -> "AzureEmbedder":
        self.docs = self._embed(docs)
        return self

    def scores(self, text: str) -> np.ndarray:
        return self.docs @ self._embed([text])[0]


def embedder():
    cfg = os.getenv("BRAIN_EMBEDDINGS", "local")
    return AzureEmbedder(cfg.split(":", 1)[1]) if cfg.startswith("azure:") else LocalEmbedder()
