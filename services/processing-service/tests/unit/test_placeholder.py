"""Smoke test — verifies the service package is importable."""


def test_processing_service_importable() -> None:
    import processing_service  # noqa: F401
    assert True
