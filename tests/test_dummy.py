"""Dummy test to verify pytest infrastructure is working."""

from src.config import UIConfig


def test_dummy_passes() -> None:
    """Basic sanity check that pytest is configured correctly."""
    assert 1 + 1 == 2


def test_dummy_string_operations() -> None:
    """Test basic string operations to verify test execution."""
    test_string = "Rapid Redact"
    assert test_string.lower() == "rapid redact"
    assert len(test_string) == 12
    assert "Redact" in test_string


def test_config_import() -> None:
    """Test that we can import and use a config class."""
    config = UIConfig()
    assert config.window_min_width == 1200
    assert config.viewer_page_buffer == 3
    assert config.viewer_base_width > 0
