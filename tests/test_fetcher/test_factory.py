"""Tests for the fetcher factory."""

from __future__ import annotations

import pytest

from mcp_insta_analytics.config import Settings
from mcp_insta_analytics.errors import ConfigError
from mcp_insta_analytics.fetcher.factory import create_fetcher
from mcp_insta_analytics.fetcher.instaloader_fetcher import InstaLoaderFetcher


class TestCreateFetcher:
    def test_instaloader_backend(self):
        config = Settings(fetcher_backend="instaloader")
        fetcher = create_fetcher(config)
        assert isinstance(fetcher, InstaLoaderFetcher)

    def test_unknown_backend_raises(self):
        config = Settings(fetcher_backend="nonexistent")
        with pytest.raises(ConfigError, match="Unknown fetcher backend"):
            create_fetcher(config)
