"""
Analytics Module

This module contains analytics and metrics calculation functionality.

Components:
    - MetricsCalculator: Statistical calculations (xG, Corsi, Fenwick)
    - PatternDetector: Play style and pattern detection
    - SynergyAnalyzer: Player synergy and line chemistry scoring
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
from src.analytics.synergy import SynergyAnalyzer, SynergyEvent, PlayerSynergyStats

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
    # Synergy
    "SynergyAnalyzer",
    "SynergyEvent",
    "PlayerSynergyStats",
]
