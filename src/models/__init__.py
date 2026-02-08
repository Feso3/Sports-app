"""
Data Models Module

This module contains Pydantic models for representing NHL data entities.

Models:
    - Player: Individual player data and statistics
    - Team: Team composition and configuration
    - Game: Game state and events
    - Segment: Game time segment model
"""

from src.models.player import Player, PlayerStats, PlayerPosition
from src.models.team import Team, LineConfiguration, TeamRoster
from src.models.game import Game, GameState, GameEvent
from src.models.segment import Segment, SegmentStats, SegmentPerformance
from src.models.player_card import (
    PlayerCard,
    PerformanceSnapshot,
    GoaliePerformanceSnapshot,
    PerformanceTrend,
    PeriodProfile,
    SeasonPhase,
    GamePeriod,
)

__all__ = [
    "Player",
    "PlayerStats",
    "PlayerPosition",
    "Team",
    "LineConfiguration",
    "TeamRoster",
    "Game",
    "GameState",
    "GameEvent",
    "Segment",
    "SegmentStats",
    "SegmentPerformance",
    "PlayerCard",
    "PerformanceSnapshot",
    "GoaliePerformanceSnapshot",
    "PerformanceTrend",
    "PeriodProfile",
    "SeasonPhase",
    "GamePeriod",
]
