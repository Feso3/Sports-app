"""
Analytics Module

This module contains analytics and metrics calculation functionality.

Components:
    - MetricsCalculator: Statistical calculations (xG, Corsi, Fenwick)
    - PatternDetector: Play style and pattern detection
"""

from src.analytics.metrics import (
    MetricsCalculator,
    CorsiStats,
    ExpectedGoalsStats,
    ZoneMetrics,
)
from src.analytics.patterns import (
    PatternDetector,
    PlayStyle,
    PatternStrength,
    PatternMatch,
    SpatialPattern,
    TemporalPattern,
    MismatchOpportunity,
)

__all__ = [
    # Metrics
    "MetricsCalculator",
    "CorsiStats",
    "ExpectedGoalsStats",
    "ZoneMetrics",
    # Patterns
    "PatternDetector",
    "PlayStyle",
    "PatternStrength",
    "PatternMatch",
    "SpatialPattern",
    "TemporalPattern",
    "MismatchOpportunity",
]
