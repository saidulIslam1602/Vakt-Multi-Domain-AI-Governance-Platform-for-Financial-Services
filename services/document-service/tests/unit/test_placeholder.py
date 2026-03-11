"""Smoke test — verifies the service package is importable."""


def test_document_service_importable() -> None:
    import document_service  # noqa: F401
    assert True
