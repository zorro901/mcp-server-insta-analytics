"""Instaloader-based data fetcher implementation."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from functools import partial
from typing import Any

from mcp_insta_analytics.config import Settings
from mcp_insta_analytics.errors import AuthenticationError, FetcherError
from mcp_insta_analytics.models import Comment, Post, UserProfile

from .base import AbstractFetcher

logger = logging.getLogger(__name__)


_LOGIN_RECOVERY = (
    "Check INSTA_ANALYTICS_USERNAME and INSTA_ANALYTICS_PASSWORD in .env. "
    "If using 2FA, you may need to approve the login from the Instagram app."
)

_SESSION_RECOVERY = (
    "Instagram session may have expired or been invalidated. "
    "Restart the server to create a new session."
)


def _is_auth_error(exc: Exception) -> bool:
    """Return True if *exc* looks like an authentication / session error."""
    try:
        from instaloader.exceptions import (  # type: ignore[import-untyped]
            ConnectionException,
            LoginRequiredException,
        )
    except ImportError:
        return False
    if isinstance(exc, LoginRequiredException):
        return True
    if isinstance(exc, ConnectionException):
        msg = str(exc).lower()
        if "401" in msg or "login" in msg or "checkpoint" in msg:
            return True
    return False


class InstaLoaderFetcher(AbstractFetcher):
    """Fetcher that uses instaloader to interact with Instagram."""

    def __init__(self, config: Settings) -> None:
        self._config = config
        self._loader: Any = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize instaloader and optionally log in."""
        try:
            import instaloader  # type: ignore[import-untyped]
        except ImportError as exc:
            raise FetcherError(
                "instaloader is not installed. Install it with: pip install instaloader",
                recovery="Run 'pip install instaloader'.",
            ) from exc

        self._loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
        )

        if self._config.username and self._config.password:
            logger.info("Logging in as %s", self._config.username)
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    partial(
                        self._loader.login,
                        self._config.username,
                        self._config.password,
                    ),
                )
                logger.info("Login successful")
            except Exception as exc:
                raise AuthenticationError(
                    f"Instagram login failed: {exc}",
                    recovery=_LOGIN_RECOVERY,
                ) from exc
        else:
            logger.info("Running in public-only mode (no login credentials)")

        self._initialized = True

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    def _get_loader(self) -> Any:
        assert self._loader is not None, "InstaLoaderFetcher not initialized"
        return self._loader

    async def _run_sync(self, func: partial[Any]) -> Any:
        """Run a blocking instaloader call in an executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func)

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    async def get_user_profile(self, username: str) -> UserProfile:
        await self._ensure_initialized()
        try:
            import instaloader  # type: ignore[import-untyped]

            profile = await self._run_sync(
                partial(instaloader.Profile.from_username, self._get_loader().context, username)
            )
            return self._to_user_profile(profile)
        except (AuthenticationError, FetcherError):
            raise
        except Exception as exc:
            if _is_auth_error(exc):
                raise AuthenticationError(
                    f"Authentication failed while fetching profile for @{username} ({exc})",
                    recovery=_SESSION_RECOVERY,
                ) from exc
            raise FetcherError(f"Failed to fetch profile for @{username}: {exc}") from exc

    async def get_user_posts(self, username: str, count: int = 20) -> list[Post]:
        await self._ensure_initialized()
        try:
            import instaloader  # type: ignore[import-untyped]

            profile = await self._run_sync(
                partial(instaloader.Profile.from_username, self._get_loader().context, username)
            )

            posts: list[Post] = []

            def _collect_posts() -> list[Post]:
                collected: list[Post] = []
                for p in profile.get_posts():
                    collected.append(self._to_post(p, username))
                    if len(collected) >= count:
                        break
                return collected

            posts = await self._run_sync(partial(_collect_posts))
            return posts
        except (AuthenticationError, FetcherError):
            raise
        except Exception as exc:
            if _is_auth_error(exc):
                raise AuthenticationError(
                    f"Authentication failed while fetching posts for @{username} ({exc})",
                    recovery=_SESSION_RECOVERY,
                ) from exc
            raise FetcherError(f"Failed to fetch posts for @{username}: {exc}") from exc

    async def get_post_detail(self, shortcode: str) -> Post:
        await self._ensure_initialized()
        try:
            import instaloader  # type: ignore[import-untyped]

            post = await self._run_sync(
                partial(instaloader.Post.from_shortcode, self._get_loader().context, shortcode)
            )
            owner = getattr(post, "owner_username", "") or ""
            return self._to_post(post, owner)
        except (AuthenticationError, FetcherError):
            raise
        except Exception as exc:
            if _is_auth_error(exc):
                raise AuthenticationError(
                    f"Authentication failed while fetching post {shortcode} ({exc})",
                    recovery=_SESSION_RECOVERY,
                ) from exc
            raise FetcherError(f"Failed to fetch post {shortcode}: {exc}") from exc

    async def get_post_comments(self, shortcode: str, count: int = 50) -> list[Comment]:
        await self._ensure_initialized()
        try:
            import instaloader  # type: ignore[import-untyped]

            post = await self._run_sync(
                partial(instaloader.Post.from_shortcode, self._get_loader().context, shortcode)
            )

            def _collect_comments() -> list[Comment]:
                collected: list[Comment] = []
                for c in post.get_comments():
                    collected.append(
                        Comment(
                            id=str(getattr(c, "id", "")),
                            text=getattr(c, "text", "") or "",
                            author_username=getattr(c, "owner", getattr(c, "username", "")) or "",
                            created_at=getattr(c, "created_at_utc", None),
                            like_count=getattr(c, "likes_count", 0) or 0,
                        )
                    )
                    if len(collected) >= count:
                        break
                return collected

            return await self._run_sync(partial(_collect_comments))
        except (AuthenticationError, FetcherError):
            raise
        except Exception as exc:
            if _is_auth_error(exc):
                raise AuthenticationError(
                    f"Authentication failed while fetching comments for {shortcode} ({exc})",
                    recovery=_SESSION_RECOVERY,
                ) from exc
            raise FetcherError(
                f"Failed to fetch comments for {shortcode}: {exc}"
            ) from exc

    async def get_hashtag_posts(self, hashtag: str, count: int = 50) -> list[Post]:
        await self._ensure_initialized()
        tag = hashtag.lstrip("#")
        try:
            import instaloader  # type: ignore[import-untyped]

            loader = self._get_loader()

            def _collect_hashtag_posts() -> list[Post]:
                collected: list[Post] = []
                for p in loader.get_hashtag_posts(tag):
                    owner = getattr(p, "owner_username", "") or ""
                    collected.append(self._to_post(p, owner))
                    if len(collected) >= count:
                        break
                return collected

            return await self._run_sync(partial(_collect_hashtag_posts))
        except (AuthenticationError, FetcherError):
            raise
        except Exception as exc:
            if _is_auth_error(exc):
                raise AuthenticationError(
                    f"Authentication failed while fetching hashtag #{tag} ({exc})",
                    recovery=_SESSION_RECOVERY,
                ) from exc
            raise FetcherError(f"Failed to fetch hashtag #{tag}: {exc}") from exc

    async def close(self) -> None:
        self._loader = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    def _to_user_profile(self, profile: Any) -> UserProfile:
        """Convert an instaloader Profile to our UserProfile model."""
        return UserProfile(
            id=str(getattr(profile, "userid", "")),
            username=getattr(profile, "username", ""),
            full_name=getattr(profile, "full_name", "") or "",
            biography=getattr(profile, "biography", "") or "",
            followers_count=getattr(profile, "followers", 0) or 0,
            following_count=getattr(profile, "followees", 0) or 0,
            media_count=getattr(profile, "mediacount", 0) or 0,
            is_verified=getattr(profile, "is_verified", False),
            is_private=getattr(profile, "is_private", False),
            profile_pic_url=getattr(profile, "profile_pic_url", "") or "",
        )

    def _to_post(self, post: Any, author_username: str) -> Post:
        """Convert an instaloader Post to our Post model."""
        created_at = getattr(post, "date_utc", None)
        if created_at is not None and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        caption = getattr(post, "caption", "") or ""
        hashtags = list(getattr(post, "caption_hashtags", []) or [])
        mentions = list(getattr(post, "caption_mentions", []) or [])

        is_video = getattr(post, "is_video", False)
        typename = getattr(post, "typename", "GraphImage")
        if typename == "GraphSidecar":
            media_type = "sidecar"
        elif is_video:
            media_type = "video"
        else:
            media_type = "image"

        media_urls: list[str] = []
        if typename == "GraphSidecar":
            try:
                for node in getattr(post, "get_sidecar_nodes", lambda: [])():
                    url = getattr(node, "display_url", "") or ""
                    if url:
                        media_urls.append(url)
            except Exception:
                pass
        if not media_urls:
            display_url = getattr(post, "url", "") or ""
            if display_url:
                media_urls.append(display_url)

        return Post(
            id=str(getattr(post, "mediaid", "")),
            shortcode=getattr(post, "shortcode", "") or "",
            caption=caption,
            author_id=str(getattr(post, "owner_id", "") or ""),
            author_username=author_username,
            created_at=created_at,
            like_count=getattr(post, "likes", 0) or 0,
            comment_count=getattr(post, "comments", 0) or 0,
            view_count=getattr(post, "video_view_count", 0) or 0,
            media_type=media_type,
            is_video=is_video,
            video_url=getattr(post, "video_url", "") or "",
            image_url=getattr(post, "url", "") or "",
            location_name=self._extract_location(post),
            hashtags=hashtags,
            mentions=mentions,
            media_urls=media_urls,
        )

    def _extract_location(self, post: Any) -> str:
        """Extract location name from an instaloader Post."""
        loc = getattr(post, "location", None)
        if loc is None:
            return ""
        return getattr(loc, "name", "") or ""
