"""Tests for time series analysis and posting-time heatmap."""

from __future__ import annotations

from datetime import datetime, timezone

from mcp_insta_analytics.analysis.timeseries import (
    build_posting_time_heatmap,
    build_timeseries,
    detect_trend,
)
from mcp_insta_analytics.models import Post, TimeseriesPoint


def _make_post(
    like_count: int = 100,
    comment_count: int = 10,
    created_at: datetime | None = None,
) -> Post:
    return Post(
        id="1",
        shortcode="abc",
        like_count=like_count,
        comment_count=comment_count,
        created_at=created_at,
    )


class TestDetectTrend:
    def test_increasing_trend(self):
        points = [
            TimeseriesPoint(timestamp=datetime(2025, 1, i, tzinfo=timezone.utc), value=float(i * 10))
            for i in range(1, 6)
        ]
        direction, slope = detect_trend(points)
        assert direction == "increasing"
        assert slope > 0

    def test_decreasing_trend(self):
        points = [
            TimeseriesPoint(timestamp=datetime(2025, 1, i, tzinfo=timezone.utc), value=float(100 - i * 20))
            for i in range(1, 6)
        ]
        direction, slope = detect_trend(points)
        assert direction == "decreasing"
        assert slope < 0

    def test_stable_trend(self):
        points = [
            TimeseriesPoint(timestamp=datetime(2025, 1, i, tzinfo=timezone.utc), value=50.0)
            for i in range(1, 6)
        ]
        direction, slope = detect_trend(points)
        assert direction == "stable"

    def test_single_point(self):
        points = [TimeseriesPoint(timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc), value=10.0)]
        direction, slope = detect_trend(points)
        assert direction == "stable"
        assert slope == 0.0


class TestBuildTimeseries:
    def test_groups_by_day(self):
        posts = [
            _make_post(like_count=100, created_at=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)),
            _make_post(like_count=200, created_at=datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc)),
            _make_post(like_count=300, created_at=datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc)),
        ]
        ts = build_timeseries(posts, metric="like_count", granularity="day")
        assert len(ts.points) == 2
        assert ts.points[0].value == 150.0  # avg of 100 and 200
        assert ts.points[1].value == 300.0

    def test_empty_posts(self):
        ts = build_timeseries([], metric="like_count", granularity="day")
        assert len(ts.points) == 0
        assert ts.trend_direction == "stable"

    def test_posts_without_dates_skipped(self):
        posts = [_make_post(created_at=None)]
        ts = build_timeseries(posts, metric="like_count", granularity="day")
        assert len(ts.points) == 0

    def test_peak_and_bottom(self):
        posts = [
            _make_post(like_count=10, created_at=datetime(2025, 1, 1, tzinfo=timezone.utc)),
            _make_post(like_count=500, created_at=datetime(2025, 1, 2, tzinfo=timezone.utc)),
            _make_post(like_count=50, created_at=datetime(2025, 1, 3, tzinfo=timezone.utc)),
        ]
        ts = build_timeseries(posts, metric="like_count", granularity="day")
        assert ts.peak is not None
        assert ts.peak.value == 500.0
        assert ts.bottom is not None
        assert ts.bottom.value == 10.0


class TestBuildPostingTimeHeatmap:
    def test_heatmap_structure(self):
        posts = [
            _make_post(like_count=100, created_at=datetime(2025, 1, 6, 10, 0, tzinfo=timezone.utc)),  # Monday
            _make_post(like_count=200, created_at=datetime(2025, 1, 6, 14, 0, tzinfo=timezone.utc)),  # Monday
        ]
        heatmap = build_posting_time_heatmap(posts, metric="like_count", timezone_str="UTC")
        assert "Monday" in heatmap.heatmap
        assert heatmap.sample_size == 2
        assert len(heatmap.best_windows) > 0

    def test_empty_posts(self):
        heatmap = build_posting_time_heatmap([], metric="like_count")
        assert heatmap.sample_size == 0
        assert heatmap.heatmap == {}
