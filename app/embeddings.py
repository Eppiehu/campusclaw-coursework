"""Local Chinese semantic embeddings; no external embedding API is required."""
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"


@lru_cache(maxsize=2)
def _model(model_name):
    from fastembed import TextEmbedding

    cache_dir = os.environ.get("EMBEDDING_CACHE_DIR") or str(Path(__file__).resolve().parent.parent / "_model_cache")
    return TextEmbedding(model_name=model_name, cache_dir=cache_dir)


def embed_text(text):
    model = _model(os.environ.get("EMBEDDING_MODEL") or DEFAULT_MODEL)
    return [float(value) for value in next(model.embed([text]))]
