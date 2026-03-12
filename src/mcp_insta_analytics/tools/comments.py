"""MCP tools for comment retrieval and sentiment analysis."""

from __future__ import annotations

import json
import logging

from fastmcp import Context

from mcp_insta_analytics.analysis.sentiment import create_analyzer
from mcp_insta_analytics.models import (
    Comment,
    CommentThreadResult,
    IndividualSentiments,
    SentimentAnalysisResult,
)
from mcp_insta_analytics.tools import extract_deps

logger = logging.getLogger(__name__)


async def _fetch_comments_with_cache(
    shortcode: str,
    count: int,
    deps: object,
) -> list[Comment]:
    """Fetch comments, reusing cached results if available."""
    cache_key = f"comments:{shortcode}:{count}"
    cached = await deps.cache.get(cache_key)  # type: ignore[union-attr]
    if cached is not None:
        logger.debug("Comment cache hit for %s", shortcode)
        return [Comment(**c) for c in json.loads(cached)]

    await deps.rate_limiter.acquire()  # type: ignore[union-attr]
    comments = await deps.fetcher.get_post_comments(shortcode, count=count)  # type: ignore[union-attr]

    await deps.cache.set(  # type: ignore[union-attr]
        cache_key,
        json.dumps([c.model_dump(mode="json") for c in comments]),
        ttl=deps.config.cache_ttl_posts,  # type: ignore[union-attr]
    )
    return comments


async def get_post_comments(
    shortcode: str,
    ctx: Context,
    max_results: int = 50,
) -> CommentThreadResult:
    """Fetch comments for a specific post."""
    deps = extract_deps(ctx)

    comments = await _fetch_comments_with_cache(shortcode, max_results, deps)

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

    comments = await _fetch_comments_with_cache(shortcode, max_comments, deps)

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
