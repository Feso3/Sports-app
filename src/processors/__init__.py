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
    - PlayerShotLocationPipeline: Player shot location profiles for simulation/heat maps
    - GoalieShotProfilePipeline: Goalie save profiles for simulation/heat maps
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
from src.processors.player_shot_location_pipeline import (
    PlayerShotLocationPipeline,
    PlayerShotLocationProfile,
    SegmentLocationStats,
    ZoneSegmentStats,
    run_pipeline as run_shot_location_pipeline,
)
from src.processors.goalie_shot_profile_pipeline import (
    GoalieShotProfilePipeline,
    GoalieShotProfile,
    GoalieSegmentStats,
    GoalieZoneStats,
    run_pipeline as run_goalie_profile_pipeline,
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
    "PlayerShotLocationPipeline",
    "PlayerShotLocationProfile",
    "SegmentLocationStats",
    "ZoneSegmentStats",
    "run_shot_location_pipeline",
    "GoalieShotProfilePipeline",
    "GoalieShotProfile",
    "GoalieSegmentStats",
    "GoalieZoneStats",
    "run_goalie_profile_pipeline",
]
