"""
Semantic retrieval over the passage corpus.

A self-contained TF-IDF + cosine vector store (no numpy / no model download)
so the prototype runs offline anywhere. The interface mirrors a real vector DB
(`search(query, k)`), so swapping in pgvector / Weaviate + sentence-transformer
embeddings is a drop-in change documented in the README.
"""
from __future__ import annotations

import math
import sqlite3

from ..util import tokenize, cosine


class VectorStore:
    def __init__(self) -> None:
        self.passages: list[dict] = []
        self.vectors: list[dict[str, float]] = []
        self.idf: dict[str, float] = {}

    def build(self, conn: sqlite3.Connection) -> "VectorStore":
        rows = conn.execute(
            "SELECT passage_id,kind,asset_id,ts,title,text,source_ref,doc_id,event_id "
            "FROM passages").fetchall()
        self.passages = [dict(r) for r in rows]

        tokenised = [tokenize(p["text"]) for p in self.passages]
        n = len(tokenised) or 1
        df: dict[str, int] = {}
        for toks in tokenised:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log((1 + n) / (1 + d)) + 1.0 for t, d in df.items()}

        self.vectors = [self._vectorize(toks) for toks in tokenised]
        return self

    def _vectorize(self, toks: list[str]) -> dict[str, float]:
        if not toks:
            return {}
        tf: dict[str, float] = {}
        for t in toks:
            tf[t] = tf.get(t, 0.0) + 1.0
        inv = 1.0 / len(toks)
        return {t: (c * inv) * self.idf.get(t, 1.0) for t, c in tf.items()}

    def search(self, query: str, k: int = 6, asset_id: str | None = None,
               boost_asset: float = 0.15) -> list[dict]:
        """Return top-k passages with a similarity score in [0,1]."""
        qvec = self._vectorize(tokenize(query))
        if not qvec:
            return []
        scored = []
        for p, v in zip(self.passages, self.vectors):
            score = cosine(qvec, v)
            if score <= 0:
                continue
            # graph-aware boost: passages tied to the asset in focus rank higher
            if asset_id and p.get("asset_id") == asset_id:
                score += boost_asset
            scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, p in scored[:k]:
            item = dict(p)
            item["score"] = round(min(score, 1.0), 3)
            out.append(item)
        return out


def build_store(conn: sqlite3.Connection) -> VectorStore:
    return VectorStore().build(conn)
