"""Time series analysis and posting-time heatmap generation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from mcp_insta_analytics.models import (
    Post,
    PostingTimeHeatmap,
    TimeseriesData,
    TimeseriesPoint,
)

_DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def _truncate_to_granularity(dt: datetime, granularity: str) -> datetime:
    if granularity == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    if granularity == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == "week":
        monday = dt - timedelta(days=dt.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"Unknown granularity: {granularity!r}. Use 'hour', 'day', or 'week'.")


def _get_metric_value(post: Post, metric: str) -> float:
    if metric == "engagement_rate":
        total = post.like_count + post.comment_count
        impressions = post.view_count if post.view_count > 0 else max(post.like_count * 10, 1)
        return total / impressions
    return float(getattr(post, metric))


def build_timeseries(
    posts: list[Post],
    metric: str = "like_count",
    granularity: str = "day",
) -> TimeseriesData:
    """Build time series data from posts, aggregating by granularity."""
    buckets: dict[datetime, list[float]] = defaultdict(list)
    for post in posts:
        if post.created_at is None:
            continue
        bucket_key = _truncate_to_granularity(post.created_at, granularity)
        value = _get_metric_value(post, metric)
        buckets[bucket_key].append(value)

    if not buckets:
        return TimeseriesData(metric_name=metric)

    points: list[TimeseriesPoint] = []
    for ts in sorted(buckets):
        values = buckets[ts]
        avg = sum(values) / len(values)
        points.append(
            TimeseriesPoint(
                timestamp=ts,
                value=avg,
                label=ts.strftime("%Y-%m-%d %H:%M"),
            )
        )

    trend_direction, trend_slope = detect_trend(points)
    average = sum(p.value for p in points) / len(points)
    peak = max(points, key=lambda p: p.value)
    bottom = min(points, key=lambda p: p.value)

    return TimeseriesData(
        metric_name=metric,
        points=points,
        trend_direction=trend_direction,
        trend_slope=trend_slope,
        average=average,
        peak=peak,
        bottom=bottom,
    )


def detect_trend(points: list[TimeseriesPoint]) -> tuple[str, float]:
    """Simple linear regression to detect trend direction and slope."""
    if len(points) < 2:
        return "stable", 0.0

    n = len(points)
    x_values = list(range(n))
    y_values = [p.value for p in points]

    x_mean = sum(x_values) / n
    y_mean = sum(y_values) / n

    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
    denominator = sum((x - x_mean) ** 2 for x in x_values)

    if denominator == 0:
        return "stable", 0.0

    slope = numerator / denominator
    relative_slope = slope / (abs(y_mean) + 1e-10)

    if relative_slope > 0.05:
        direction = "increasing"
    elif relative_slope < -0.05:
        direction = "decreasing"
    else:
        direction = "stable"

    return direction, slope


def build_posting_time_heatmap(
    posts: list[Post],
    metric: str = "engagement_rate",
    timezone_str: str = "UTC",
) -> PostingTimeHeatmap:
    """Build a day-of-week x hour heatmap of average metric values."""
    tz = ZoneInfo(timezone_str)
    cells: dict[tuple[str, int], list[float]] = defaultdict(list)

    for post in posts:
        if post.created_at is None:
            continue
        local_dt = post.created_at.astimezone(tz)
        day_name = _DAY_NAMES[local_dt.weekday()]
        hour = local_dt.hour
        value = _get_metric_value(post, metric)
        cells[(day_name, hour)].append(value)

    if not cells:
        return PostingTimeHeatmap(metric_used=metric)

    heatmap: dict[str, dict[int, float]] = {}
    ranked: list[tuple[str, int, float]] = []

    for (day_name, hour), values in cells.items():
        avg = sum(values) / len(values)
        heatmap.setdefault(day_name, {})[hour] = avg
        ranked.append((day_name, hour, avg))

    for day_name in heatmap:
        heatmap[day_name] = dict(sorted(heatmap[day_name].items()))

    ranked.sort(key=lambda item: item[2], reverse=True)
    best_windows = [f"{day} {hour:02d}:00-{hour + 1:02d}:00" for day, hour, _ in ranked[:5]]
    sample_size = sum(len(v) for v in cells.values())

    return PostingTimeHeatmap(
        heatmap=heatmap,
        best_windows=best_windows,
        sample_size=sample_size,
        metric_used=metric,
    )
