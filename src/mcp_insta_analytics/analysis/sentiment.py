"""Sentiment analysis with pluggable backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from mcp_insta_analytics.models import SentimentResult, SentimentSummary


class _SentimentScorer(Protocol):
    """Protocol for VADER-like sentiment scorers."""

    def polarity_scores(self, text: str) -> dict[str, float]: ...


class SentimentAnalyzer(ABC):
    """Abstract base class for sentiment analyzers."""

    @abstractmethod
    def analyze(self, text: str) -> SentimentResult: ...

    def analyze_batch(self, texts: list[str]) -> SentimentSummary:
        results = [self.analyze(t) for t in texts]
        if not results:
            return SentimentSummary()

        positive = [r for r in results if r.label == "positive"]
        negative = [r for r in results if r.label == "negative"]
        neutral = [r for r in results if r.label == "neutral"]
        total = len(results)
        avg_score = sum(r.compound_score for r in results) / total

        most_pos = max(results, key=lambda r: r.compound_score)
        most_neg = min(results, key=lambda r: r.compound_score)

        return SentimentSummary(
            total_analyzed=total,
            positive_count=len(positive),
            negative_count=len(negative),
            neutral_count=len(neutral),
            positive_ratio=len(positive) / total,
            negative_ratio=len(negative) / total,
            neutral_ratio=len(neutral) / total,
            average_score=avg_score,
            most_positive=most_pos,
            most_negative=most_neg,
        )


class VaderAnalyzer(SentimentAnalyzer):
    """VADER sentiment analyzer implementation."""

    def __init__(self) -> None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # type: ignore[import-untyped]

        self._analyzer: _SentimentScorer = SentimentIntensityAnalyzer()  # type: ignore[assignment]

    def analyze(self, text: str) -> SentimentResult:
        scores = self._analyzer.polarity_scores(text)
        compound = scores["compound"]
        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"
        return SentimentResult(
            text=text,
            compound_score=compound,
            positive=scores["pos"],
            negative=scores["neg"],
            neutral=scores["neu"],
            label=label,
        )


def create_analyzer(engine: str = "vader") -> SentimentAnalyzer:
    """Factory function to create a sentiment analyzer by engine name."""
    if engine == "vader":
        return VaderAnalyzer()
    raise ValueError(f"Unknown sentiment engine: {engine}")
