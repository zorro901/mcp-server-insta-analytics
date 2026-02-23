"""Tests for instaloader object → model mapping."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from mcp_insta_analytics.fetcher.instaloader_fetcher import InstaLoaderFetcher
from mcp_insta_analytics.config import Settings


def _make_insta_profile(**overrides):
    defaults = {
        "userid": "123456",
        "username": "testuser",
        "full_name": "Test User",
        "biography": "Hello",
        "followers": 1000,
        "followees": 200,
        "mediacount": 50,
        "is_verified": False,
        "is_private": False,
        "profile_pic_url": "https://example.com/pic.jpg",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_insta_post(**overrides):
    defaults = {
        "mediaid": "9999",
        "shortcode": "XyZ123",
        "caption": "Test caption #test",
        "owner_id": "123456",
        "date_utc": datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc),
        "likes": 200,
        "comments": 30,
        "video_view_count": 0,
        "typename": "GraphImage",
        "is_video": False,
        "video_url": "",
        "url": "https://instagram.com/p/XyZ123/media",
        "caption_hashtags": ["test"],
        "caption_mentions": ["someone"],
        "location": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestToUserProfile:
    def test_maps_all_fields(self):
        fetcher = InstaLoaderFetcher(Settings())
        profile = _make_insta_profile()
        result = fetcher._to_user_profile(profile)
        assert result.id == "123456"
        assert result.username == "testuser"
        assert result.full_name == "Test User"
        assert result.followers_count == 1000
        assert result.following_count == 200
        assert result.media_count == 50

    def test_missing_fields_have_defaults(self):
        fetcher = InstaLoaderFetcher(Settings())
        profile = SimpleNamespace(userid="1", username="u")
        result = fetcher._to_user_profile(profile)
        assert result.full_name == ""
        assert result.followers_count == 0


class TestToPost:
    def test_maps_all_fields(self):
        fetcher = InstaLoaderFetcher(Settings())
        post = _make_insta_post()
        result = fetcher._to_post(post, "testuser")
        assert result.id == "9999"
        assert result.shortcode == "XyZ123"
        assert result.like_count == 200
        assert result.comment_count == 30
        assert result.author_username == "testuser"
        assert result.media_type == "image"
        assert result.hashtags == ["test"]
        assert result.mentions == ["someone"]

    def test_video_post(self):
        fetcher = InstaLoaderFetcher(Settings())
        post = _make_insta_post(is_video=True, typename="GraphVideo", video_view_count=5000)
        result = fetcher._to_post(post, "testuser")
        assert result.media_type == "video"
        assert result.is_video is True
        assert result.view_count == 5000

    def test_sidecar_post(self):
        fetcher = InstaLoaderFetcher(Settings())
        node1 = SimpleNamespace(display_url="https://example.com/1.jpg")
        node2 = SimpleNamespace(display_url="https://example.com/2.jpg")
        post = _make_insta_post(
            typename="GraphSidecar",
            get_sidecar_nodes=lambda: [node1, node2],
        )
        result = fetcher._to_post(post, "testuser")
        assert result.media_type == "sidecar"
        assert len(result.media_urls) == 2

    def test_naive_datetime_gets_utc(self):
        fetcher = InstaLoaderFetcher(Settings())
        post = _make_insta_post(date_utc=datetime(2025, 1, 15, 10, 30))
        result = fetcher._to_post(post, "testuser")
        assert result.created_at is not None
        assert result.created_at.tzinfo == timezone.utc

    def test_location_extraction(self):
        fetcher = InstaLoaderFetcher(Settings())
        location = SimpleNamespace(name="Tokyo Tower")
        post = _make_insta_post(location=location)
        result = fetcher._to_post(post, "testuser")
        assert result.location_name == "Tokyo Tower"
