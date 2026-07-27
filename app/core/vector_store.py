"""
FAISS-backed vector store for fast, scalable similarity search over
historical ticket embeddings.

Uses an IndexFlatIP (inner product) index over L2-normalized vectors,
which is mathematically equivalent to cosine similarity search and gives
exact (non-approximate) nearest neighbors — ideal at the scale of a
ticket-history corpus. Swappable for IndexIVFFlat/HNSW if the corpus
grows into the millions.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

import faiss
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class FAISSVectorStore:
    def __init__(self, dim: int = settings.EMBEDDING_DIM):
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        # Parallel metadata store: FAISS index position -> ticket metadata
        self.metadata: List[Dict] = []
        self._id_to_position: Dict[str, int] = {}

    def add(self, vectors: np.ndarray, metadata_list: List[Dict]) -> None:
        """Adds a batch of embeddings + their associated ticket metadata."""
        if vectors.shape[0] != len(metadata_list):
            raise ValueError("vectors and metadata_list must be the same length")

        start_pos = len(self.metadata)
        self.index.add(vectors)
        for i, meta in enumerate(metadata_list):
            self.metadata.append(meta)
            self._id_to_position[meta["id"]] = start_pos + i

    def search(self, query_vector: np.ndarray, k: int = settings.TOP_K_RETRIEVAL) -> List[Tuple[Dict, float]]:
        """Returns up to k (metadata, similarity_score) pairs, best first."""
        if self.index.ntotal == 0:
            return []
        query = query_vector.reshape(1, -1).astype("float32")
        k = min(k, self.index.ntotal)
        scores, indices = self.index.search(query, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            results.append((self.metadata[idx], float(score)))
        return results

    def get_by_id(self, ticket_id: str) -> Dict:
        pos = self._id_to_position.get(ticket_id)
        return self.metadata[pos] if pos is not None else None

    def size(self) -> int:
        return self.index.ntotal

    # -- persistence -------------------------------------------------------
    def save(self, index_path: Path = settings.FAISS_INDEX_PATH, meta_path: Path = settings.FAISS_METADATA_PATH):
        faiss.write_index(self.index, str(index_path))
        with open(meta_path, "w") as f:
            json.dump(self.metadata, f)
        logger.info(f"Saved FAISS index ({self.index.ntotal} vectors) to {index_path}")

    def load(self, index_path: Path = settings.FAISS_INDEX_PATH, meta_path: Path = settings.FAISS_METADATA_PATH) -> bool:
        if not (index_path.exists() and meta_path.exists()):
            return False
        self.index = faiss.read_index(str(index_path))
        with open(meta_path, "r") as f:
            self.metadata = json.load(f)
        self._id_to_position = {m["id"]: i for i, m in enumerate(self.metadata)}
        logger.info(f"Loaded FAISS index with {self.index.ntotal} vectors from {index_path}")
        return True
