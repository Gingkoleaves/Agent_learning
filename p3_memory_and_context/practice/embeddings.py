"""Embedding backends. Hashing is an offline protocol baseline, not semantic embedding."""
import hashlib
import math
import os
import re
from pathlib import Path


def terms(text):
    text = text.casefold()
    words = re.findall(r"[a-z0-9_]+", text)
    for span in re.findall(r"[\u4e00-\u9fff]+", text):
        words.extend(span[i:i + 2] for i in range(max(1, len(span) - 1)))
    return words


def normalize(vector):
    values = [float(v) for v in vector]
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values] if norm else values


class HashEmbedding:
    name = "offline-hash-256-not-semantic"
    def encode(self, texts):
        result = []
        for text in texts:
            vector = [0.0] * 256
            for term in terms(text):
                digest = hashlib.sha256(term.encode()).digest()
                vector[int.from_bytes(digest[:4], "big") % 256] += 1
            result.append(normalize(vector))
        return result

    def encode_query(self, text):
        return self.encode([text])[0]


class LocalEmbedding:
    def __init__(self):
        from fastembed import TextEmbedding
        model_name = os.environ.get("EMBEDDING_LOCAL_MODEL", "BAAI/bge-small-zh-v1.5")
        cache = Path(__file__).parent / "artifacts" / "models"
        self.model = TextEmbedding(model_name=model_name, cache_dir=str(cache), threads=2,
                                   local_files_only=os.environ.get("P3_DOWNLOAD_MODEL") != "1")
        self.name = "fastembed:" + model_name

    def encode(self, texts):
        return [normalize(v) for v in self.model.passage_embed(texts)]

    def encode_query(self, text):
        return normalize(next(iter(self.model.query_embed(text))))


def get_embedder():
    provider = os.environ.get("P3_EMBEDDING_PROVIDER", "hash")
    if provider == "hash":
        return HashEmbedding()
    if provider == "local":
        return LocalEmbedding()
    raise ValueError("unknown_embedding_provider")
