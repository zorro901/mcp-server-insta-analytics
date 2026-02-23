"""MCP tools for comment retrieval and sentiment analysis."""

from __future__ import annotations

import logging

from fastmcp import Context

from mcp_insta_analytics.analysis.sentiment import create_analyzer
from mcp_insta_analytics.models import (
    CommentThreadResult,
    IndividualSentiments,
    SentimentAnalysisResult,
)
from mcp_insta_analytics.tools import extract_deps

logger = logging.getLogger(__name__)


async def get_post_comments(
    shortcode: str,
    ctx: Context,
    max_results: int = 50,
) -> CommentThreadResult:
    """Fetch comments for a specific post."""
    deps = extract_deps(ctx)

    await deps.rate_limiter.acquire()
    comments = await deps.fetcher.get_post_comments(shortcode, count=max_results)

    return CommentThreadResult(
        post_id=shortcode,
        comments=comments,
        total_comments=len(comments),
    )


async def analyze_comment_sentiment(
    shortcode: str,
    ctx: Context,
    max_comments: int = 100,
    engine: str = "vader",
) -> SentimentAnalysisResult:
    """Analyze the sentiment of comments on a given post."""
    deps = extract_deps(ctx)

    await deps.rate_limiter.acquire()
    comments = await deps.fetcher.get_post_comments(shortcode, count=max_comments)

    texts = [c.text for c in comments if c.text.strip()]

    if not texts:
        return SentimentAnalysisResult(
            post_id=shortcode,
            sentiment_summary=None,
            individual_sentiments=IndividualSentiments(
                most_positive=[],
                most_negative=[],
            ),
        )

    analyzer = create_analyzer(engine)
    summary = analyzer.analyze_batch(texts)
    individual_results = [analyzer.analyze(text) for text in texts]

    sorted_by_score = sorted(
        individual_results,
        key=lambda r: r.compound_score,
        reverse=True,
    )

    return SentimentAnalysisResult(
        post_id=shortcode,
        sentiment_summary=summary,
        individual_sentiments=IndividualSentiments(
            most_positive=sorted_by_score[:5],
            most_negative=sorted_by_score[-5:],
        ),
    )
