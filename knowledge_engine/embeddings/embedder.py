"""Multilingual sentence embeddings on ONNX Runtime, so no PyTorch is needed."""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np


class OnnxEmbedder:
    """multilingual-e5-small. E5 models need the 'query: ' and 'passage: ' prefixes."""

    dimensions = 384

    def __init__(self, model_dir: Path, threads: int = 2, cache_size: int = 512) -> None:
        import onnxruntime
        from tokenizers import Tokenizer

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self._session = onnxruntime.InferenceSession(
            str(model_dir / "onnx" / "model_quantized.onnx"),
            options,
            providers=["CPUExecutionProvider"],
        )
        self._inputs = {item.name for item in self._session.get_inputs()}
        self._tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=256)
        self._tokenizer.enable_padding()
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_size = cache_size

    def _run(self, texts: list[str]) -> np.ndarray:
        encoded = self._tokenizer.encode_batch(texts)
        ids = np.array([item.ids for item in encoded], dtype=np.int64)
        mask = np.array([item.attention_mask for item in encoded], dtype=np.int64)
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._inputs:
            feeds["token_type_ids"] = np.zeros_like(ids)
        hidden = self._session.run(None, feeds)[0]
        weights = mask[..., None].astype(np.float32)
        pooled = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        return pooled / np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9, None)

    def embed_passages(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        batches = [
            self._run([f"passage: {text}" for text in texts[start : start + batch_size]])
            for start in range(0, len(texts), batch_size)
        ]
        return np.vstack(batches).astype(np.float32) if batches else np.zeros((0, self.dimensions), np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        with self._lock:
            cached = self._cache.get(text)
            if cached is not None:
                self._cache.move_to_end(text)
                return cached
        vector = self._run([f"query: {text}"])[0].astype(np.float32)
        with self._lock:
            self._cache[text] = vector
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return vector


class HashEmbedder:
    """Deterministic stand-in for tests: same text, same vector, no model file needed."""

    dimensions = 64

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimensions, np.float32)
        for word in text.lower().split():
            vector[hash_word(word) % self.dimensions] += 1.0
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector

    def embed_passages(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        return np.vstack([self._vector(text) for text in texts]) if texts else np.zeros((0, self.dimensions), np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text)


def hash_word(word: str) -> int:
    value = 2166136261
    for byte in word.encode("utf-8"):
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value
