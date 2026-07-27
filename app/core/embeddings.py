"""
Semantic embedding layer built on Sentence Transformers.

Encodes ticket text (title + description) into dense vectors used for
semantic similarity search. Kept as a thin, swappable wrapper so the
underlying model can be changed via config without touching callers.
"""
import logging
from typing import List, Union

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingModel:
    def __init__(self, model_name: str = settings.EMBEDDING_MODEL_NAME):
        logger.info(f"Loading sentence-transformer model '{model_name}'...")
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

    def encode(self, texts: Union[str, List[str]], normalize: bool = True) -> np.ndarray:
        """
        Encodes one or many texts into L2-normalized embeddings (so that
        inner-product search in FAISS is equivalent to cosine similarity).
        """
        single_input = isinstance(texts, str)
        texts_list = [texts] if single_input else texts

        embeddings = self.model.encode(
            texts_list,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )
        return embeddings.astype("float32")

    def encode_single(self, text: str, normalize: bool = True) -> np.ndarray:
        return self.encode(text, normalize=normalize)[0]
