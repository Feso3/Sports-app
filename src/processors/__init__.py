"""
Data Processors Module

This module contains processors for transforming and analyzing NHL data.

Processors:
    - ZoneAnalyzer: Zone-based aggregation and analysis
    - SegmentProcessor: Game segment processing and analysis
    - HeatMapProcessor: Heat map generation and analysis
    - MatchupProcessor: Historical matchup tracking and analysis
    - ChemistryTracker: Synergy and line chemistry analysis
    - SeasonSegmentPipeline: Season phase × game phase aggregation
"""

from src.processors.zone_analysis import ZoneAnalyzer
from src.processors.segment_analysis import SegmentProcessor
from src.processors.heat_map import HeatMapProcessor, HeatMapData, HeatMapCell
from src.processors.matchup import MatchupProcessor, PlayerMatchup, TeamMatchup, MatchupStats
from src.processors.synergy import ChemistryTracker, SynergySummary
from src.processors.season_segment_pipeline import (
    SeasonSegmentPipeline,
    SeasonPhase,
    GamePhase,
    PlayerPhaseStats,
    ValidationResult,
    run_pipeline,
)

__all__ = [
    "ZoneAnalyzer",
    "SegmentProcessor",
    "HeatMapProcessor",
    "HeatMapData",
    "HeatMapCell",
    "MatchupProcessor",
    "PlayerMatchup",
    "TeamMatchup",
    "MatchupStats",
    "ChemistryTracker",
    "SynergySummary",
    "SeasonSegmentPipeline",
    "SeasonPhase",
    "GamePhase",
    "PlayerPhaseStats",
    "ValidationResult",
    "run_pipeline",
]
