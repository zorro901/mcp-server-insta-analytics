"""Derived engagement metrics calculator."""

from __future__ import annotations

from mcp_insta_analytics.models import EngagementMetrics, Post


def calculate_engagement_metrics(post: Post) -> EngagementMetrics:
    """Calculate derived engagement metrics for a single post."""
    total = post.like_count + post.comment_count
    # Use view_count for videos/reels, otherwise use like_count as proxy for reach
    impressions = post.view_count if post.view_count > 0 else max(post.like_count * 10, 1)

    return EngagementMetrics(
        post_id=post.id,
        engagement_rate=total / impressions,
        like_comment_ratio=post.like_count / max(post.comment_count, 1),
        total_engagements=total,
    )


def rank_posts(
    posts: list[Post],
    metric: str = "engagement_rate",
) -> list[tuple[Post, EngagementMetrics]]:
    """Rank posts by a given metric. Returns sorted list of (post, metrics) tuples."""
    pairs: list[tuple[Post, EngagementMetrics]] = [
        (post, calculate_engagement_metrics(post)) for post in posts
    ]
    pairs.sort(key=lambda pair: getattr(pair[1], metric), reverse=True)
    return pairs
