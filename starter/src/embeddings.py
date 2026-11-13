"""Real embedding model: sentence-transformers/all-MiniLM-L6-v2 (local, CPU).

- 384 dimensions, mean pooling + L2 normalisation (from the model's modules.json),
  max_seq_length 256 word-piece tokens (longer inputs are truncated by the model).
- Documents and queries are encoded identically (the model uses no prefixes).
- ``EMBEDDING_MODEL`` may be the HF hub id (downloads on first use) or a local
  directory holding the same files. No mock / random fallback: any load or
  encode error is raised.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, question: str) -> list[float]:
        ...


class MyEmbedder:
    def __init__(self, model_name: str | None = None, batch_size: int = 32) -> None:
        from sentence_transformers import SentenceTransformer  # raises if not installed
        import sentence_transformers
        import torch

        self.model_name = model_name or os.getenv("EMBEDDING_MODEL") or DEFAULT_MODEL
        torch.manual_seed(0)
        torch.set_num_threads(max(1, (os.cpu_count() or 1)))
        self.model = SentenceTransformer(self.model_name, device="cpu")
        self.dimensions = int(self.model.get_sentence_embedding_dimension())
        self.max_seq_length = int(self.model.max_seq_length)
        self.batch_size = batch_size
        self.versions = {"sentence_transformers": sentence_transformers.__version__, "torch": torch.__version__}
        self.weights_sha256 = self._weights_hash()

    def _weights_hash(self) -> str | None:
        p = Path(self.model_name) / "model.safetensors"
        if not p.exists():
            try:
                from huggingface_hub import try_to_load_from_cache
                cached = try_to_load_from_cache(DEFAULT_MODEL, "model.safetensors")
                p = Path(cached) if isinstance(cached, str) else p
            except Exception:  # noqa: BLE001 - hash is informational only
                return None
        if not p.exists():
            return None
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def token_lengths(self, texts: list[str]) -> list[int]:
        tok = self.model.tokenizer
        return [len(tok(t, add_special_tokens=True, truncation=False)["input_ids"]) for t in texts]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                 convert_to_numpy=True, show_progress_bar=False)
        if vecs.shape != (len(texts), self.dimensions):
            raise RuntimeError(f"unexpected embedding shape {vecs.shape}")
        return vecs.tolist()

    def embed_query(self, question: str) -> list[float]:
        return self.embed_documents([question])[0]

    def describe(self) -> dict:
        return {"provider": "local sentence-transformers (CPU)", "model": DEFAULT_MODEL,
                "loaded_from": self.model_name, "dimensions": self.dimensions,
                "max_seq_length_tokens": self.max_seq_length, "pooling": "mean + L2 normalize",
                "query_document_handling": "identical encoding, no prefix",
                "weights_sha256": self.weights_sha256, **self.versions, "cost_usd": 0}
