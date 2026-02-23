"""Abstract base class for data fetchers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from mcp_insta_analytics.models import Comment, Post, UserProfile


class AbstractFetcher(ABC):
    """Abstract interface for fetching data from Instagram."""

    @abstractmethod
    async def get_user_profile(self, username: str) -> UserProfile:
        """Fetch a user's profile by username."""

    @abstractmethod
    async def get_user_posts(self, username: str, count: int = 20) -> list[Post]:
        """Fetch recent posts from a user's profile."""

    @abstractmethod
    async def get_post_detail(self, shortcode: str) -> Post:
        """Fetch a single post by its shortcode."""

    @abstractmethod
    async def get_post_comments(self, shortcode: str, count: int = 50) -> list[Comment]:
        """Fetch comments on a specific post."""

    @abstractmethod
    async def get_hashtag_posts(self, hashtag: str, count: int = 50) -> list[Post]:
        """Fetch posts for a given hashtag."""

    async def close(self) -> None:
        """Clean up resources. Override in subclasses if needed."""
