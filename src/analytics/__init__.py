"""
Analytics Module

This module contains analytics and metrics calculation functionality.

Components:
    - MetricsCalculator: Statistical calculations (xG, Corsi, Fenwick)
    - PatternDetector: Play style and pattern detection
    - SynergyAnalyzer: Player synergy and line chemistry scoring
    - ClutchAnalyzer: Clutch performance scoring and identification
    - StaminaAnalyzer: Fatigue and stamina pattern analysis
    - TeamResilienceAnalyzer: Team resilience vs collapse detection
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
from src.analytics.clutch_analysis import (
    ClutchAnalyzer,
    ClutchLevel,
    ClutchMetrics,
    ClutchPerformerRanking,
    StaminaAnalyzer,
    StaminaMetrics,
    FatigueLevel,
    TeamResilienceAnalyzer,
    TeamResilienceMetrics,
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
    # Synergy
    "SynergyAnalyzer",
    "SynergyEvent",
    "PlayerSynergyStats",
    # Clutch Analysis
    "ClutchAnalyzer",
    "ClutchLevel",
    "ClutchMetrics",
    "ClutchPerformerRanking",
    # Stamina Analysis
    "StaminaAnalyzer",
    "StaminaMetrics",
    "FatigueLevel",
    # Team Resilience
    "TeamResilienceAnalyzer",
    "TeamResilienceMetrics",
]
