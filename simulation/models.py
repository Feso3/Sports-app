"""
Simulation Data Models

Pydantic and dataclass models for the game simulation engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SimulationMode(str, Enum):
    """Simulation mode enumeration."""

    SINGLE_GAME = "single_game"
    SERIES = "series"  # Best-of-7 playoff series
    SEASON = "season"


class GameSituation(str, Enum):
    """Game strength situation."""

    EVEN_STRENGTH = "5v5"
    POWER_PLAY_HOME = "5v4_home"
    POWER_PLAY_AWAY = "5v4_away"
    FOUR_ON_FOUR = "4v4"
    THREE_ON_THREE = "3v3"  # OT


class GameSegment(str, Enum):
    """Game time segment."""

    EARLY_GAME = "early_game"
    MID_GAME = "mid_game"
    LATE_GAME = "late_game"
    OVERTIME = "overtime"


class SimulationConfig(BaseModel):
    """Configuration for a simulation run."""

    # Core settings
    iterations: int = Field(default=10000, ge=100, le=100000)
    mode: SimulationMode = SimulationMode.SINGLE_GAME
    random_seed: int | None = None

    # Team identifiers
    home_team_id: int
    away_team_id: int

    # Series settings (for playoff mode)
    series_games_to_win: int = 4
    current_series_score: tuple[int, int] = (0, 0)

    # Weighting factors
    use_synergy_adjustments: bool = True
    use_clutch_adjustments: bool = True
    use_fatigue_adjustments: bool = True
    use_segment_weights: bool = True

    # Segment weights (modifiers for each game segment)
    segment_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "early_game": 0.9,
            "mid_game": 1.0,
            "late_game": 1.1,
            "overtime": 1.2,
        }
    )

    # Zone weights for expected goals
    zone_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "slot": 1.5,
            "high_slot": 1.2,
            "left_circle": 1.0,
            "right_circle": 1.0,
            "point": 0.6,
            "behind_net": 0.3,
        }
    )

    # Variance settings
    variance_factor: float = Field(default=0.15, ge=0.0, le=0.5)
    goalie_variance: float = Field(default=0.05, ge=0.0, le=0.2)

    # Special teams impact
    power_play_goal_rate: float = Field(default=0.20, ge=0.0, le=1.0)
    penalty_frequency: float = Field(default=0.08, ge=0.0, le=0.3)


@dataclass
class LineMatchup:
    """Represents a line vs line matchup."""

    home_line_number: int
    away_line_number: int
    line_type: str  # "forward" or "defense"

    # Calculated values
    home_offensive_strength: float = 0.0
    away_offensive_strength: float = 0.0
    home_defensive_strength: float = 0.0
    away_defensive_strength: float = 0.0

    # Synergy adjustments
    home_chemistry: float = 0.0
    away_chemistry: float = 0.0

    # Expected goals for this matchup per period
    home_xg: float = 0.0
    away_xg: float = 0.0


@dataclass
class SegmentResult:
    """Results for a single game segment."""

    segment: GameSegment
    home_goals: int = 0
    away_goals: int = 0
    home_xg: float = 0.0
    away_xg: float = 0.0
    home_shots: int = 0
    away_shots: int = 0
    dominant_team: int | None = None
    key_matchups: list[LineMatchup] = field(default_factory=list)


@dataclass
class SimulatedGame:
    """Result of a single game simulation."""

    game_number: int
    home_score: int
    away_score: int
    winner: int  # team_id of winner
    went_to_overtime: bool = False
    went_to_shootout: bool = False

    # Detailed breakdowns
    segments: list[SegmentResult] = field(default_factory=list)

    # Expected goals totals
    home_xg_total: float = 0.0
    away_xg_total: float = 0.0

    # Key factors
    home_clutch_impact: float = 0.0
    away_clutch_impact: float = 0.0
    home_fatigue_impact: float = 0.0
    away_fatigue_impact: float = 0.0

    @property
    def goal_differential(self) -> int:
        """Home team goal differential."""
        return self.home_score - self.away_score

    @property
    def total_goals(self) -> int:
        """Total goals in the game."""
        return self.home_score + self.away_score

    @property
    def was_blowout(self) -> bool:
        """Check if game was a blowout (4+ goal differential)."""
        return abs(self.goal_differential) >= 4

    @property
    def was_close(self) -> bool:
        """Check if game was close (1 goal differential or OT)."""
        return abs(self.goal_differential) <= 1 or self.went_to_overtime


@dataclass
class ScoreDistribution:
    """Distribution of scores from simulation."""

    # Score frequencies: (home_score, away_score) -> count
    score_counts: dict[tuple[int, int], int] = field(default_factory=dict)

    # Goal totals
    home_goals_distribution: dict[int, int] = field(default_factory=dict)
    away_goals_distribution: dict[int, int] = field(default_factory=dict)
    total_goals_distribution: dict[int, int] = field(default_factory=dict)

    def add_result(self, home_score: int, away_score: int) -> None:
        """Add a game result to the distribution."""
        key = (home_score, away_score)
        self.score_counts[key] = self.score_counts.get(key, 0) + 1
        self.home_goals_distribution[home_score] = (
            self.home_goals_distribution.get(home_score, 0) + 1
        )
        self.away_goals_distribution[away_score] = (
            self.away_goals_distribution.get(away_score, 0) + 1
        )
        total = home_score + away_score
        self.total_goals_distribution[total] = (
            self.total_goals_distribution.get(total, 0) + 1
        )

    def most_likely_score(self) -> tuple[int, int]:
        """Get the most likely final score."""
        if not self.score_counts:
            return (0, 0)
        return max(self.score_counts, key=self.score_counts.get)

    def average_home_goals(self, total_games: int) -> float:
        """Calculate average home goals."""
        total = sum(goals * count for goals, count in self.home_goals_distribution.items())
        return total / total_games if total_games > 0 else 0.0

    def average_away_goals(self, total_games: int) -> float:
        """Calculate average away goals."""
        total = sum(goals * count for goals, count in self.away_goals_distribution.items())
        return total / total_games if total_games > 0 else 0.0


@dataclass
class MatchupAnalysis:
    """Detailed matchup analysis between two teams."""

    home_team_id: int
    away_team_id: int

    # Zone-by-zone breakdown
    zone_advantages: dict[str, float] = field(default_factory=dict)

    # Line matchup advantages
    forward_line_advantages: list[float] = field(default_factory=list)
    defense_pair_advantages: list[float] = field(default_factory=list)

    # Segment-specific advantages
    early_game_advantage: float = 0.0
    mid_game_advantage: float = 0.0
    late_game_advantage: float = 0.0

    # Special teams comparison
    power_play_advantage: float = 0.0
    penalty_kill_advantage: float = 0.0

    # Goalie comparison
    goalie_advantage: float = 0.0

    # Key mismatches (description -> impact)
    key_mismatches: dict[str, float] = field(default_factory=dict)

    @property
    def overall_advantage(self) -> float:
        """Calculate overall home team advantage."""
        segment_avg = (
            self.early_game_advantage
            + self.mid_game_advantage
            + self.late_game_advantage
        ) / 3
        special_teams = (self.power_play_advantage + self.penalty_kill_advantage) / 2
        return segment_avg * 0.6 + special_teams * 0.2 + self.goalie_advantage * 0.2


@dataclass
class SimulationResult:
    """Complete results from a simulation run."""

    # Configuration used
    config: SimulationConfig

    # Core results
    total_iterations: int
    home_wins: int
    away_wins: int
    overtime_games: int
    shootout_games: int

    # Win probability
    home_win_probability: float = 0.0
    away_win_probability: float = 0.0

    # Confidence metrics
    confidence_score: float = 0.0  # Based on data quality
    variance_indicator: str = "normal"  # "low", "normal", "high"

    # Score distribution
    score_distribution: ScoreDistribution = field(default_factory=ScoreDistribution)

    # Expected goals
    average_home_xg: float = 0.0
    average_away_xg: float = 0.0

    # Segment breakdowns
    segment_win_rates: dict[str, float] = field(default_factory=dict)

    # Matchup analysis
    matchup_analysis: MatchupAnalysis | None = None

    # Individual game results (sample)
    sample_games: list[SimulatedGame] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Calculate derived metrics."""
        if self.total_iterations > 0:
            self.home_win_probability = self.home_wins / self.total_iterations
            self.away_win_probability = self.away_wins / self.total_iterations

    @property
    def overtime_rate(self) -> float:
        """Percentage of games going to overtime."""
        return self.overtime_games / self.total_iterations if self.total_iterations > 0 else 0.0

    @property
    def predicted_winner(self) -> int:
        """Team ID of predicted winner."""
        if self.home_win_probability > self.away_win_probability:
            return self.config.home_team_id
        return self.config.away_team_id

    @property
    def win_margin(self) -> float:
        """Difference in win probabilities."""
        return abs(self.home_win_probability - self.away_win_probability)

    @property
    def is_high_variance(self) -> bool:
        """Check if matchup is high variance (close to 50/50)."""
        return self.win_margin < 0.1

    def get_summary(self) -> dict[str, Any]:
        """Get summary dictionary for reporting."""
        return {
            "home_team_id": self.config.home_team_id,
            "away_team_id": self.config.away_team_id,
            "iterations": self.total_iterations,
            "home_win_probability": round(self.home_win_probability, 4),
            "away_win_probability": round(self.away_win_probability, 4),
            "predicted_winner": self.predicted_winner,
            "confidence_score": round(self.confidence_score, 4),
            "variance_indicator": self.variance_indicator,
            "overtime_rate": round(self.overtime_rate, 4),
            "most_likely_score": self.score_distribution.most_likely_score(),
            "average_home_goals": round(
                self.score_distribution.average_home_goals(self.total_iterations), 2
            ),
            "average_away_goals": round(
                self.score_distribution.average_away_goals(self.total_iterations), 2
            ),
        }


@dataclass
class SeriesResult:
    """Result of a playoff series simulation."""

    config: SimulationConfig
    total_iterations: int

    # Series outcomes: (home_wins, away_wins) -> count
    series_outcomes: dict[tuple[int, int], int] = field(default_factory=dict)

    # Win probability
    home_series_win_probability: float = 0.0
    away_series_win_probability: float = 0.0

    # Average series length
    average_series_length: float = 0.0

    # Game-by-game probabilities
    game_win_probabilities: list[tuple[float, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Calculate derived metrics."""
        if self.total_iterations > 0:
            home_wins = sum(
                count for (h, a), count in self.series_outcomes.items()
                if h == self.config.series_games_to_win
            )
            self.home_series_win_probability = home_wins / self.total_iterations
            self.away_series_win_probability = 1 - self.home_series_win_probability

    def most_likely_outcome(self) -> tuple[int, int]:
        """Get most likely series outcome (games won by each team)."""
        if not self.series_outcomes:
            return (0, 0)
        return max(self.series_outcomes, key=self.series_outcomes.get)
