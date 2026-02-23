"""Tests for sentiment analysis."""

from __future__ import annotations

import pytest

from mcp_insta_analytics.analysis.sentiment import VaderAnalyzer, create_analyzer


class TestVaderAnalyzer:
    def test_positive_text(self):
        analyzer = VaderAnalyzer()
        result = analyzer.analyze("This is absolutely wonderful and amazing!")
        assert result.label == "positive"
        assert result.compound_score > 0.05

    def test_negative_text(self):
        analyzer = VaderAnalyzer()
        result = analyzer.analyze("This is terrible and awful")
        assert result.label == "negative"
        assert result.compound_score < -0.05

    def test_neutral_text(self):
        analyzer = VaderAnalyzer()
        result = analyzer.analyze("The weather is cloudy today")
        assert result.label == "neutral"


class TestAnalyzeBatch:
    def test_batch_summary(self):
        analyzer = VaderAnalyzer()
        texts = [
            "I love this so much!",
            "This is terrible",
            "Just a normal day",
        ]
        summary = analyzer.analyze_batch(texts)
        assert summary.total_analyzed == 3
        assert summary.positive_count >= 1
        assert summary.negative_count >= 1
        assert summary.most_positive is not None
        assert summary.most_negative is not None
        assert summary.most_positive.compound_score >= summary.most_negative.compound_score

    def test_empty_batch(self):
        analyzer = VaderAnalyzer()
        summary = analyzer.analyze_batch([])
        assert summary.total_analyzed == 0


class TestCreateAnalyzer:
    def test_vader_engine(self):
        analyzer = create_analyzer("vader")
        assert isinstance(analyzer, VaderAnalyzer)

    def test_unknown_engine_raises(self):
        with pytest.raises(ValueError, match="Unknown sentiment engine"):
            create_analyzer("nonexistent")
