"""
Game Data Model

Pydantic models for representing game state, events, and outcomes.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GameType(str, Enum):
    """Game type enumeration."""

    PRESEASON = "PR"
    REGULAR_SEASON = "R"
    PLAYOFFS = "P"
    ALL_STAR = "A"


class GameStatus(str, Enum):
    """Game status enumeration."""

    SCHEDULED = "scheduled"
    PREGAME = "pregame"
    IN_PROGRESS = "in_progress"
    FINAL = "final"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    """Game event type enumeration."""

    GOAL = "goal"
    SHOT = "shot"
    MISSED_SHOT = "missed_shot"
    BLOCKED_SHOT = "blocked_shot"
    HIT = "hit"
    TAKEAWAY = "takeaway"
    GIVEAWAY = "giveaway"
    FACEOFF = "faceoff"
    PENALTY = "penalty"
    STOPPAGE = "stoppage"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"
    GAME_END = "game_end"


class GameEvent(BaseModel):
    """Represents a single game event."""

    event_id: int
    event_type: EventType
    period: int
    time_in_period: str
    time_remaining: str
    game_seconds: int = 0
    segment: str | None = None

    # Location
    x_coord: float | None = None
    y_coord: float | None = None
    zone: str | None = None

    # Teams and players
    team_id: int | None = None
    team_abbrev: str | None = None
    player_id: int | None = None
    player_name: str | None = None

    # Event-specific details
    shot_type: str | None = None
    is_goal: bool = False
    assists: list[dict[str, Any]] = Field(default_factory=list)
    strength: str | None = None  # even, pp, sh
    empty_net: bool = False
    game_winning_goal: bool = False

    # Penalty details
    penalty_type: str | None = None
    penalty_minutes: int | None = None

    # Additional details
    details: dict[str, Any] = Field(default_factory=dict)


class PeriodScore(BaseModel):
    """Score for a single period."""

    period: int
    home_goals: int = 0
    away_goals: int = 0
    home_shots: int = 0
    away_shots: int = 0


class GameState(BaseModel):
    """Current state of a game."""

    period: int = 0
    time_remaining: str = "20:00"
    is_intermission: bool = False

    home_score: int = 0
    away_score: int = 0
    home_shots: int = 0
    away_shots: int = 0

    # Power play state
    home_power_play: bool = False
    away_power_play: bool = False
    home_skaters: int = 5
    away_skaters: int = 5

    # Empty net state
    home_empty_net: bool = False
    away_empty_net: bool = False

    # Period scores
    period_scores: list[PeriodScore] = Field(default_factory=list)

    @property
    def score_differential(self) -> int:
        """Home team score differential (positive = home leading)."""
        return self.home_score - self.away_score

    @property
    def is_tied(self) -> bool:
        """Check if game is tied."""
        return self.home_score == self.away_score

    @property
    def is_close_game(self) -> bool:
        """Check if game is within 1 goal."""
        return abs(self.score_differential) <= 1


class Game(BaseModel):
    """
    Complete game model.

    Represents an NHL game with teams, state, events, and outcomes.
    """

    # Identification
    game_id: str
    season: str
    game_type: GameType = GameType.REGULAR_SEASON
    game_number: int | None = None

    # Schedule
    game_date: str
    start_time: str | None = None
    venue: str | None = None

    # Teams
    home_team_id: int
    home_team_abbrev: str
    away_team_id: int
    away_team_abbrev: str

    # Status
    status: GameStatus = GameStatus.SCHEDULED

    # Current state
    state: GameState = Field(default_factory=GameState)

    # Events
    events: list[GameEvent] = Field(default_factory=list)

    # Final outcome
    home_final_score: int | None = None
    away_final_score: int | None = None
    winning_team_id: int | None = None
    overtime: bool = False
    shootout: bool = False

    # Summary statistics
    home_shots: int = 0
    away_shots: int = 0
    home_hits: int = 0
    away_hits: int = 0
    home_blocked_shots: int = 0
    away_blocked_shots: int = 0
    home_takeaways: int = 0
    away_takeaways: int = 0
    home_giveaways: int = 0
    away_giveaways: int = 0
    home_faceoff_wins: int = 0
    away_faceoff_wins: int = 0
    home_power_play_goals: int = 0
    home_power_play_opportunities: int = 0
    away_power_play_goals: int = 0
    away_power_play_opportunities: int = 0

    # Segment data
    segment_events: dict[str, list[GameEvent]] = Field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """Check if game is complete."""
        return self.status == GameStatus.FINAL

    @property
    def winner(self) -> str | None:
        """Get winning team abbreviation."""
        if not self.is_complete:
            return None
        if self.home_final_score is None or self.away_final_score is None:
            return None
        if self.home_final_score > self.away_final_score:
            return self.home_team_abbrev
        return self.away_team_abbrev

    @property
    def total_goals(self) -> int:
        """Get total goals scored in game."""
        home = self.home_final_score or self.state.home_score
        away = self.away_final_score or self.state.away_score
        return home + away

    def get_events_by_type(self, event_type: EventType) -> list[GameEvent]:
        """Get all events of a specific type."""
        return [e for e in self.events if e.event_type == event_type]

    def get_events_by_period(self, period: int) -> list[GameEvent]:
        """Get all events from a specific period."""
        return [e for e in self.events if e.period == period]

    def get_events_by_segment(self, segment: str) -> list[GameEvent]:
        """Get all events from a specific game segment."""
        return self.segment_events.get(segment, [])

    def get_events_by_team(self, team_id: int) -> list[GameEvent]:
        """Get all events for a specific team."""
        return [e for e in self.events if e.team_id == team_id]

    def get_goals(self) -> list[GameEvent]:
        """Get all goal events."""
        return self.get_events_by_type(EventType.GOAL)

    def get_shots(self, include_goals: bool = True) -> list[GameEvent]:
        """
        Get all shot events.

        Args:
            include_goals: Whether to include goals as shots

        Returns:
            List of shot events
        """
        event_types = {EventType.SHOT}
        if include_goals:
            event_types.add(EventType.GOAL)
        return [e for e in self.events if e.event_type in event_types]

    def calculate_segment_scores(self) -> dict[str, dict[str, int]]:
        """
        Calculate scores by game segment.

        Returns:
            Dictionary with segment scores for each team
        """
        segment_scores: dict[str, dict[str, int]] = {
            "early_game": {"home": 0, "away": 0},
            "mid_game": {"home": 0, "away": 0},
            "late_game": {"home": 0, "away": 0},
        }

        for event in self.events:
            if event.event_type != EventType.GOAL:
                continue
            if event.segment not in segment_scores:
                continue

            if event.team_id == self.home_team_id:
                segment_scores[event.segment]["home"] += 1
            elif event.team_id == self.away_team_id:
                segment_scores[event.segment]["away"] += 1

        return segment_scores

    def get_momentum_shifts(self, window_size: int = 5) -> list[dict[str, Any]]:
        """
        Identify momentum shifts based on event sequences.

        Args:
            window_size: Number of events to consider for momentum

        Returns:
            List of momentum shift events
        """
        shifts = []
        # Simplified momentum tracking based on shots/hits
        positive_events = {EventType.SHOT, EventType.GOAL, EventType.HIT, EventType.TAKEAWAY}

        home_momentum = 0
        away_momentum = 0

        for i, event in enumerate(self.events):
            if event.event_type not in positive_events:
                continue

            if event.team_id == self.home_team_id:
                home_momentum += 1
                away_momentum = max(0, away_momentum - 1)
            elif event.team_id == self.away_team_id:
                away_momentum += 1
                home_momentum = max(0, home_momentum - 1)

            # Check for momentum shift
            if home_momentum >= window_size and away_momentum == 0:
                shifts.append({
                    "event_id": event.event_id,
                    "period": event.period,
                    "time": event.time_in_period,
                    "team": "home",
                    "strength": home_momentum,
                })
                home_momentum = 0
            elif away_momentum >= window_size and home_momentum == 0:
                shifts.append({
                    "event_id": event.event_id,
                    "period": event.period,
                    "time": event.time_in_period,
                    "team": "away",
                    "strength": away_momentum,
                })
                away_momentum = 0

        return shifts
