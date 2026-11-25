"""Offline embedding safety regression tests; no external model or network needed."""
import os
import tempfile
import unittest
from unittest.mock import patch
from app.local_embeddings import embed_local, model_directory, LocalEmbeddingUnavailable


class FakeModel:
    def __init__(self, vector):
        self.vector = vector
    def encode(self, texts, normalize_embeddings):
        assert normalize_embeddings is True
        return [self.vector]


class LocalEmbeddingTests(unittest.TestCase):
    def test_no_config_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(LocalEmbeddingUnavailable):
                model_directory()

    def test_missing_directory_fails_closed(self):
        with patch.dict(os.environ, {"PRISM_LOCAL_EMBEDDING_MODEL": "/nonexistent/prism-model"}):
            with self.assertRaises(LocalEmbeddingUnavailable):
                model_directory()

    def test_offline_embedding_success(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"PRISM_LOCAL_EMBEDDING_MODEL": directory}):
            with patch("app.local_embeddings._load_model", return_value=FakeModel([0.6, 0.8])):
                self.assertEqual(embed_local("supplier mapping", expected_dimensions=2), [0.6, 0.8])

    def test_dimension_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"PRISM_LOCAL_EMBEDDING_MODEL": directory}):
            with patch("app.local_embeddings._load_model", return_value=FakeModel([1.0, 0.0])):
                with self.assertRaises(LocalEmbeddingUnavailable):
                    embed_local("supplier mapping", expected_dimensions=3)

    def test_nan_and_zero_fail(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"PRISM_LOCAL_EMBEDDING_MODEL": directory}):
            for vector in ([float("nan"), 0], [0.0, 0.0], []):
                with self.subTest(vector=vector), patch("app.local_embeddings._load_model", return_value=FakeModel(vector)):
                    with self.assertRaises(LocalEmbeddingUnavailable):
                        embed_local("supplier mapping")

    def test_invalid_text_fails_without_model(self):
        for value in ("", " ", "x" * 8001):
            with self.assertRaises(ValueError):
                embed_local(value)


if __name__ == "__main__":
    unittest.main()
