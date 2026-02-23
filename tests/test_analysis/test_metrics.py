"""Tests for engagement metrics calculation."""

from __future__ import annotations

from mcp_insta_analytics.analysis.metrics import calculate_engagement_metrics, rank_posts
from mcp_insta_analytics.models import Post


def _make_post(
    like_count: int = 100,
    comment_count: int = 10,
    view_count: int = 0,
    post_id: str = "1",
) -> Post:
    return Post(
        id=post_id,
        shortcode="abc",
        like_count=like_count,
        comment_count=comment_count,
        view_count=view_count,
    )


class TestCalculateEngagementMetrics:
    def test_basic_engagement(self):
        post = _make_post(like_count=100, comment_count=10)
        metrics = calculate_engagement_metrics(post)
        assert metrics.total_engagements == 110
        assert metrics.post_id == post.id

    def test_engagement_rate_without_views(self):
        post = _make_post(like_count=100, comment_count=10, view_count=0)
        metrics = calculate_engagement_metrics(post)
        # impressions = max(100*10, 1) = 1000
        expected_rate = 110 / 1000
        assert abs(metrics.engagement_rate - expected_rate) < 1e-6

    def test_engagement_rate_with_views(self):
        post = _make_post(like_count=100, comment_count=10, view_count=5000)
        metrics = calculate_engagement_metrics(post)
        expected_rate = 110 / 5000
        assert abs(metrics.engagement_rate - expected_rate) < 1e-6

    def test_like_comment_ratio(self):
        post = _make_post(like_count=200, comment_count=50)
        metrics = calculate_engagement_metrics(post)
        assert abs(metrics.like_comment_ratio - 4.0) < 1e-6

    def test_zero_comments_ratio(self):
        post = _make_post(like_count=100, comment_count=0)
        metrics = calculate_engagement_metrics(post)
        assert abs(metrics.like_comment_ratio - 100.0) < 1e-6

    def test_zero_likes(self):
        post = _make_post(like_count=0, comment_count=5, view_count=0)
        metrics = calculate_engagement_metrics(post)
        # impressions = max(0*10, 1) = 1
        assert metrics.total_engagements == 5
        assert metrics.engagement_rate == 5.0


class TestRankPosts:
    def test_rank_by_engagement_rate(self):
        # "high" has view_count so engagement_rate = 110/500 = 0.22
        # "low" has no views so engagement_rate = 11/100 = 0.11
        posts = [
            _make_post(like_count=10, comment_count=1, post_id="low"),
            _make_post(like_count=100, comment_count=10, view_count=500, post_id="high"),
        ]
        ranked = rank_posts(posts, metric="engagement_rate")
        assert ranked[0][0].id == "high"
        assert ranked[1][0].id == "low"

    def test_rank_by_total_engagements(self):
        posts = [
            _make_post(like_count=500, comment_count=50, post_id="big"),
            _make_post(like_count=10, comment_count=5, post_id="small"),
        ]
        ranked = rank_posts(posts, metric="total_engagements")
        assert ranked[0][0].id == "big"
