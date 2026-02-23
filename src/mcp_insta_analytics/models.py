"""Pydantic data models for Instagram Analytics."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """Instagram user profile data."""

    id: str
    username: str
    full_name: str = ""
    biography: str = ""
    followers_count: int = 0
    following_count: int = 0
    media_count: int = 0
    is_verified: bool = False
    is_private: bool = False
    profile_pic_url: str = ""
    created_at: datetime | None = None

    @property
    def follower_following_ratio(self) -> float:
        if self.following_count == 0:
            return float(self.followers_count)
        return self.followers_count / self.following_count

    @property
    def daily_post_frequency(self) -> float | None:
        if self.created_at is None:
            return None
        age = (datetime.now(tz=self.created_at.tzinfo) - self.created_at).days
        if age == 0:
            return None
        return self.media_count / age


class Post(BaseModel):
    """Instagram post data with metrics."""

    id: str
    shortcode: str = ""
    caption: str = ""
    author_id: str = ""
    author_username: str = ""
    created_at: datetime | None = None
    like_count: int = 0
    comment_count: int = 0
    view_count: int = 0  # for videos/reels
    media_type: str = "image"  # "image", "video", "sidecar"
    is_video: bool = False
    video_url: str = ""
    image_url: str = ""
    location_name: str = ""
    hashtags: list[str] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    media_urls: list[str] = Field(default_factory=list)


class Comment(BaseModel):
    """Instagram comment data."""

    id: str
    text: str = ""
    author_username: str = ""
    created_at: datetime | None = None
    like_count: int = 0


class EngagementMetrics(BaseModel):
    """Derived engagement metrics for a post."""

    post_id: str
    engagement_rate: float = 0.0
    like_comment_ratio: float = 0.0
    total_engagements: int = 0


class SentimentResult(BaseModel):
    """Result of sentiment analysis on a text."""

    text: str = ""
    compound_score: float = 0.0
    positive: float = 0.0
    negative: float = 0.0
    neutral: float = 0.0
    label: str = "neutral"


class SentimentSummary(BaseModel):
    """Aggregated sentiment analysis over multiple texts."""

    total_analyzed: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    positive_ratio: float = 0.0
    negative_ratio: float = 0.0
    neutral_ratio: float = 0.0
    average_score: float = 0.0
    most_positive: SentimentResult | None = None
    most_negative: SentimentResult | None = None


class TimeseriesPoint(BaseModel):
    """A single data point in a time series."""

    timestamp: datetime
    value: float
    label: str = ""


class TimeseriesData(BaseModel):
    """Time series data with trend analysis."""

    metric_name: str
    points: list[TimeseriesPoint] = Field(default_factory=lambda: list[TimeseriesPoint]())
    trend_direction: str = "stable"
    trend_slope: float = 0.0
    average: float = 0.0
    peak: TimeseriesPoint | None = None
    bottom: TimeseriesPoint | None = None


class PostingTimeHeatmap(BaseModel):
    """Heatmap of engagement by day-of-week and hour."""

    heatmap: dict[str, dict[int, float]] = Field(default_factory=dict)
    best_windows: list[str] = Field(default_factory=list)
    sample_size: int = 0
    metric_used: str = ""


class UsageStats(BaseModel):
    """API usage statistics."""

    requests_today: int = 0
    daily_budget: int = 500
    remaining_today: int = 500
    requests_this_minute: int = 0
    per_minute_limit: int = 15


# ---------------------------------------------------------------------------
# Tool response models
# ---------------------------------------------------------------------------


class PostWithMetrics(BaseModel):
    """A post combined with its derived engagement metrics."""

    id: str
    shortcode: str = ""
    caption: str = ""
    author_id: str = ""
    author_username: str = ""
    created_at: datetime | None = None
    like_count: int = 0
    comment_count: int = 0
    view_count: int = 0
    media_type: str = "image"
    is_video: bool = False
    image_url: str = ""
    location_name: str = ""
    hashtags: list[str] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    media_urls: list[str] = Field(default_factory=list)
    post_id: str = ""
    engagement_rate: float = 0.0
    like_comment_ratio: float = 0.0
    total_engagements: int = 0


def post_with_metrics(post: Post, metrics: EngagementMetrics) -> PostWithMetrics:
    """Merge a Post and its EngagementMetrics into a single model."""
    return PostWithMetrics(
        **post.model_dump(),
        post_id=metrics.post_id,
        engagement_rate=metrics.engagement_rate,
        like_comment_ratio=metrics.like_comment_ratio,
        total_engagements=metrics.total_engagements,
    )


class MetricStatistics(BaseModel):
    """Min/max/average statistics for a single metric."""

    average: float
    max: float
    min: float


class PostComparisonResult(BaseModel):
    """Response from compare_post_performance."""

    ranked_posts: list[PostWithMetrics]
    statistics: dict[str, MetricStatistics]


class PostComparisonError(BaseModel):
    """Validation error response from compare_post_performance."""

    error: str
    message: str


class SearchResult(BaseModel):
    """Response from search_posts_by_hashtag."""

    hashtag: str
    total_results: int
    posts: list[PostWithMetrics]


class UserProfileAnalytics(BaseModel):
    """Response from get_user_profile_analytics."""

    id: str
    username: str
    full_name: str = ""
    biography: str = ""
    followers_count: int = 0
    following_count: int = 0
    media_count: int = 0
    is_verified: bool = False
    is_private: bool = False
    profile_pic_url: str = ""
    created_at: datetime | None = None
    follower_following_ratio: float
    daily_post_frequency: float | None


def user_profile_analytics(profile: UserProfile) -> UserProfileAnalytics:
    """Build a UserProfileAnalytics from a UserProfile, including computed properties."""
    return UserProfileAnalytics(
        **profile.model_dump(),
        follower_following_ratio=profile.follower_following_ratio,
        daily_post_frequency=profile.daily_post_frequency,
    )


class PostAndMetrics(BaseModel):
    """A post paired with its engagement metrics (nested, not merged)."""

    post: Post
    metrics: EngagementMetrics


class TimelineSummary(BaseModel):
    """Summary statistics for a user's timeline."""

    avg_engagement_rate: float
    total_engagements: int
    post_count: int
    most_engaging_post: PostAndMetrics | None
    least_engaging_post: PostAndMetrics | None


class UserTimelineResult(BaseModel):
    """Response from get_user_timeline_metrics."""

    username: str
    posts: list[PostAndMetrics]
    summary: TimelineSummary


class HashtagPerformanceResult(BaseModel):
    """Response from track_hashtag_trend."""

    hashtag: str
    days_back: int
    total_posts: int
    average_engagement: float
    top_posts: list[PostWithMetrics]
    co_occurring_hashtags: list[tuple[str, int]]
    timeseries: TimeseriesData | None


class SentimentAnalysisResult(BaseModel):
    """Response from analyze_comment_sentiment."""

    post_id: str
    sentiment_summary: SentimentSummary | None
    individual_sentiments: IndividualSentiments


class IndividualSentiments(BaseModel):
    """Top positive and negative sentiments."""

    most_positive: list[SentimentResult]
    most_negative: list[SentimentResult]


class CommentThreadResult(BaseModel):
    """Response from get_post_comments."""

    post_id: str
    comments: list[Comment]
    total_comments: int


class EngagementTimeseriesResult(BaseModel):
    """Response from get_engagement_timeseries."""

    username: str
    granularity: str
    days_back: int
    timeseries: list[TimeseriesData]


class BestPostingTimesResult(BaseModel):
    """Response from analyze_best_posting_times."""

    username: str
    timezone: str
    metric: str
    heatmap: dict[str, dict[int, float]]
    best_windows: list[str]
    sample_size: int
    confidence_note: str
