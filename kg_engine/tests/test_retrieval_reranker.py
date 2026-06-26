from __future__ import annotations

from unittest.mock import MagicMock

from kg_engine.retrieval.reranker import CrossEncoderReranker, IdentityReranker, build_reranker


def test_identity_reranker_returns_top_k():
    reranker = IdentityReranker()
    candidates = [("doc1", 0.1), ("doc2", 0.2), ("doc3", 0.3)]

    top = reranker.rerank("query", candidates, top_k=2)

    assert top == candidates[:2]


def test_cross_encoder_reranker_uses_model(monkeypatch):
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.9, 0.1]

    monkeypatch.setattr("kg_engine.retrieval.reranker.CrossEncoder", lambda name, device=None: fake_model)

    reranker = CrossEncoderReranker(model_name="fake/model")
    candidates = [(MagicMock(page_content="doc1", metadata={}), 0.0), (MagicMock(page_content="doc2", metadata={}), 0.0)]

    ranked = reranker.rerank("query", candidates, top_k=2)

    assert ranked[0][0].page_content == "doc1"
    fake_model.predict.assert_called_once()


def test_cross_encoder_reranker_device_parameter(monkeypatch):
    """Test that device parameter is passed to CrossEncoder."""
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.9, 0.1]
    captured_device = []

    def mock_cross_encoder(name, device=None):  # noqa: ANN001
        captured_device.append(device)
        return fake_model

    monkeypatch.setattr("kg_engine.retrieval.reranker.CrossEncoder", mock_cross_encoder)

    # Test explicit device
    CrossEncoderReranker(model_name="fake/model", device="cuda")
    assert captured_device[-1] == "cuda"

    # Test auto device (will detect based on system)
    CrossEncoderReranker(model_name="fake/model", device="auto")
    assert captured_device[-1] in ("cpu", "cuda")


def test_build_reranker_falls_back_to_identity(monkeypatch):
    def raise_error(name, device=None):  # noqa: ANN001
        raise RuntimeError("Model unavailable")

    monkeypatch.setattr("kg_engine.retrieval.reranker.CrossEncoder", raise_error)

    reranker = build_reranker([{"model_name": "missing/model"}])

    assert isinstance(reranker, IdentityReranker)


def test_build_reranker_passes_device(monkeypatch):
    """Test that build_reranker passes device to CrossEncoderReranker."""
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.9]
    captured_devices = []

    def mock_cross_encoder(name, device=None):  # noqa: ANN001
        captured_devices.append(device)
        return fake_model

    monkeypatch.setattr("kg_engine.retrieval.reranker.CrossEncoder", mock_cross_encoder)

    # Test default device (auto)
    build_reranker([{"model_name": "fake/model"}])
    assert captured_devices[-1] in ("cpu", "cuda")

    # Test explicit device in config
    build_reranker([{"model_name": "fake/model", "device": "cpu"}], device="cuda")
    assert captured_devices[-1] == "cpu"  # Config device takes precedence

    # Test device parameter
    build_reranker([{"model_name": "fake/model"}], device="cpu")
    assert captured_devices[-1] == "cpu"

