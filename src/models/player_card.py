"""
Player Card Model

The player card is the complete performance profile for a player.
It captures HOW a player performs across two temporal dimensions:

1. Season Phases: Early / Mid / Late season
   - Shows whether a player starts hot and fades, is a slow starter,
     or peaks for the playoff push.

2. Game Periods: 1st / 2nd / 3rd period
   - Shows whether a player dominates early, disappears in the middle,
     or is a clutch closer.

The combination of these dimensions makes player data DYNAMIC —
a player is not one flat number, they are a performance surface
that shifts based on WHEN in the season and WHEN in the game.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SeasonPhase(str, Enum):
    """Phase within an NHL season (82 games)."""
    EARLY = "early_season"   # Games 1-27
    MID = "mid_season"       # Games 28-55
    LATE = "late_season"     # Games 56-82


class GamePeriod(str, Enum):
    """Period within an NHL game."""
    FIRST = "period_1"
    SECOND = "period_2"
    THIRD = "period_3"
    OVERTIME = "overtime"


# ---------------------------------------------------------------------------
# Per-split performance snapshot
# ---------------------------------------------------------------------------

class PerformanceSnapshot(BaseModel):
    """
    A self-contained slice of player performance.

    Used for both season-phase splits AND period splits so every
    dimension is measured with the same set of metrics.
    """

    # Sample size
    games_played: int = 0
    time_on_ice_seconds: int = 0

    # Counting stats
    goals: int = 0
    assists: int = 0
    points: int = 0
    shots: int = 0
    hits: int = 0
    blocked_shots: int = 0
    takeaways: int = 0
    giveaways: int = 0
    plus_minus: int = 0
    penalty_minutes: int = 0

    # Rate stats (per 60 minutes of ice time)
    goals_per_60: float = 0.0
    assists_per_60: float = 0.0
    points_per_60: float = 0.0
    shots_per_60: float = 0.0

    # Efficiency
    shooting_percentage: float = 0.0

    # Possession / advanced
    corsi_for: int = 0
    corsi_against: int = 0
    corsi_percentage: float = 0.0
    expected_goals_for: float = 0.0
    expected_goals_against: float = 0.0

    # Special teams
    power_play_goals: int = 0
    power_play_points: int = 0
    shorthanded_goals: int = 0
    shorthanded_points: int = 0

    # Derived quality signal
    # How does this split compare to the player's overall average?
    # > 1.0 = above average, < 1.0 = below average
    relative_performance: float = 1.0

    # ---- Convenience properties ----

    @property
    def toi_minutes(self) -> float:
        return self.time_on_ice_seconds / 60.0 if self.time_on_ice_seconds else 0.0

    @property
    def points_per_game(self) -> float:
        return self.points / self.games_played if self.games_played else 0.0

    @property
    def goals_per_game(self) -> float:
        return self.goals / self.games_played if self.games_played else 0.0

    def compute_rates(self) -> None:
        """Recalculate per-60 rates from counting stats and TOI."""
        minutes = self.toi_minutes
        if minutes <= 0:
            return
        factor = 60.0 / minutes
        self.goals_per_60 = self.goals * factor
        self.assists_per_60 = self.assists * factor
        self.points_per_60 = self.points * factor
        self.shots_per_60 = self.shots * factor

        if self.shots > 0:
            self.shooting_percentage = self.goals / self.shots

        total_corsi = self.corsi_for + self.corsi_against
        if total_corsi > 0:
            self.corsi_percentage = self.corsi_for / total_corsi


class GoaliePerformanceSnapshot(BaseModel):
    """Performance snapshot tailored for goalies."""

    games_played: int = 0
    games_started: int = 0
    time_on_ice_seconds: int = 0

    # Core goalie stats
    saves: int = 0
    shots_against: int = 0
    goals_against: int = 0
    save_percentage: float = 0.0
    goals_against_average: float = 0.0

    # High-danger
    high_danger_saves: int = 0
    high_danger_shots_against: int = 0
    high_danger_save_percentage: float = 0.0

    # Quality
    quality_starts: int = 0
    really_bad_starts: int = 0

    # Relative to own overall
    relative_performance: float = 1.0

    @property
    def toi_minutes(self) -> float:
        return self.time_on_ice_seconds / 60.0 if self.time_on_ice_seconds else 0.0

    def compute_rates(self) -> None:
        """Recalculate derived stats."""
        if self.shots_against > 0:
            self.save_percentage = self.saves / self.shots_against
            self.goals_against_average = (
                self.goals_against / (self.toi_minutes / 60.0)
                if self.toi_minutes > 0 else 0.0
            )
        if self.high_danger_shots_against > 0:
            self.high_danger_save_percentage = (
                self.high_danger_saves / self.high_danger_shots_against
            )


# ---------------------------------------------------------------------------
# Trend indicators
# ---------------------------------------------------------------------------

class TrendDirection(str, Enum):
    """Which direction performance is trending."""
    RISING = "rising"
    STABLE = "stable"
    FALLING = "falling"


class PerformanceTrend(BaseModel):
    """
    Captures the trajectory of a metric across season phases.

    Example: A player whose goals_per_60 goes 0.8 → 1.1 → 1.5
    across early → mid → late season has a RISING trend.
    """
    metric_name: str
    early_value: float = 0.0
    mid_value: float = 0.0
    late_value: float = 0.0
    direction: TrendDirection = TrendDirection.STABLE
    magnitude: float = 0.0  # % change from early to late

    def compute(self) -> None:
        """Derive direction and magnitude from the three phase values."""
        if self.early_value > 0:
            self.magnitude = (self.late_value - self.early_value) / self.early_value
        elif self.late_value > 0:
            self.magnitude = 1.0  # went from 0 to something
        else:
            self.magnitude = 0.0

        if self.magnitude > 0.10:
            self.direction = TrendDirection.RISING
        elif self.magnitude < -0.10:
            self.direction = TrendDirection.FALLING
        else:
            self.direction = TrendDirection.STABLE


class PeriodProfile(BaseModel):
    """
    Captures how a player's output shifts across periods within a game.

    Example: A player with period_1=1.2, period_2=0.9, period_3=1.4
    relative performance is a slow-second-period type who turns it
    on in the 3rd.
    """
    strongest_period: GamePeriod = GamePeriod.FIRST
    weakest_period: GamePeriod = GamePeriod.SECOND

    # Relative multipliers vs overall average (1.0 = average)
    period_1_factor: float = 1.0
    period_2_factor: float = 1.0
    period_3_factor: float = 1.0

    def compute(
        self,
        p1: PerformanceSnapshot,
        p2: PerformanceSnapshot,
        p3: PerformanceSnapshot,
    ) -> None:
        """Derive period factors from three period snapshots."""
        avg_ppg = (p1.points_per_game + p2.points_per_game + p3.points_per_game) / 3
        if avg_ppg <= 0:
            return

        self.period_1_factor = p1.points_per_game / avg_ppg if avg_ppg else 1.0
        self.period_2_factor = p2.points_per_game / avg_ppg if avg_ppg else 1.0
        self.period_3_factor = p3.points_per_game / avg_ppg if avg_ppg else 1.0

        factors = {
            GamePeriod.FIRST: self.period_1_factor,
            GamePeriod.SECOND: self.period_2_factor,
            GamePeriod.THIRD: self.period_3_factor,
        }
        self.strongest_period = max(factors, key=factors.get)  # type: ignore[arg-type]
        self.weakest_period = min(factors, key=factors.get)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The Player Card
# ---------------------------------------------------------------------------

class PlayerCard(BaseModel):
    """
    The complete dynamic performance profile for a single player.

    This is the DATA that makes the simulation dynamic. Instead of
    treating every player as a flat stat line, the player card lets the
    sim engine ask:

        "What does this player look like in the 3rd period
         during the late season?"

    And get a specific, data-backed answer.

    ┌──────────────────────────────────────────────────────┐
    │                    PLAYER CARD                        │
    │  Name: Connor McDavid          Team: EDM             │
    │  Position: C    Age: 28        Shoots: L             │
    │                                                       │
    │  ── Season Phase Performance ──                       │
    │  Early   Mid     Late                                 │
    │  P/GP:  1.21    1.35    1.58    ▲ RISING             │
    │  G/60:  1.02    1.14    1.41    ▲ RISING             │
    │  CF%:   54.2    55.1    56.8    ▲ RISING             │
    │                                                       │
    │  ── Period Performance ──                             │
    │  1st     2nd     3rd                                  │
    │  P/GP:  0.45    0.38    0.52                          │
    │  G/60:  0.41    0.35    0.64                          │
    │  Best period: 3rd (clutch closer)                     │
    │                                                       │
    │  ── Trends ──                                         │
    │  Season: RISING (+30.6% early→late)                   │
    │  Clutch: 0.82                                         │
    │  Fatigue resistance: 0.97                             │
    └──────────────────────────────────────────────────────┘
    """

    # ---- Identity ----
    player_id: int
    player_name: str
    team_abbrev: str = ""
    position: str = "U"
    season: str = ""  # e.g. "2024-25"

    # ---- Season Phase Performance ----
    # How does this player perform across the season timeline?
    early_season: PerformanceSnapshot = Field(default_factory=PerformanceSnapshot)
    mid_season: PerformanceSnapshot = Field(default_factory=PerformanceSnapshot)
    late_season: PerformanceSnapshot = Field(default_factory=PerformanceSnapshot)

    # ---- Game Period Performance ----
    # How does this player perform within a single game?
    period_1: PerformanceSnapshot = Field(default_factory=PerformanceSnapshot)
    period_2: PerformanceSnapshot = Field(default_factory=PerformanceSnapshot)
    period_3: PerformanceSnapshot = Field(default_factory=PerformanceSnapshot)

    # ---- Overall (baseline for relative comparisons) ----
    overall: PerformanceSnapshot = Field(default_factory=PerformanceSnapshot)

    # ---- Trends (derived from season phases) ----
    scoring_trend: PerformanceTrend = Field(
        default_factory=lambda: PerformanceTrend(metric_name="points_per_60")
    )
    shooting_trend: PerformanceTrend = Field(
        default_factory=lambda: PerformanceTrend(metric_name="shooting_percentage")
    )
    possession_trend: PerformanceTrend = Field(
        default_factory=lambda: PerformanceTrend(metric_name="corsi_percentage")
    )

    # ---- Period Profile (derived from period snapshots) ----
    period_profile: PeriodProfile = Field(default_factory=PeriodProfile)

    # ---- Key derived metrics ----
    clutch_rating: float = 0.0       # Late-game / late-season performance
    fatigue_resistance: float = 1.0  # How well they maintain output over time
    consistency: float = 0.0         # Variance across splits (lower = more consistent)

    # ---- Data quality ----
    total_games: int = 0
    has_sufficient_data: bool = False  # True if min thresholds met across phases

    # ---- Goalie-specific (only populated for goalies) ----
    goalie_early_season: GoaliePerformanceSnapshot | None = None
    goalie_mid_season: GoaliePerformanceSnapshot | None = None
    goalie_late_season: GoaliePerformanceSnapshot | None = None
    goalie_period_1: GoaliePerformanceSnapshot | None = None
    goalie_period_2: GoaliePerformanceSnapshot | None = None
    goalie_period_3: GoaliePerformanceSnapshot | None = None

    # ---- Methods ----

    def get_season_phase(self, phase: SeasonPhase) -> PerformanceSnapshot:
        """Get performance snapshot for a season phase."""
        mapping = {
            SeasonPhase.EARLY: self.early_season,
            SeasonPhase.MID: self.mid_season,
            SeasonPhase.LATE: self.late_season,
        }
        return mapping[phase]

    def get_period(self, period: GamePeriod) -> PerformanceSnapshot:
        """Get performance snapshot for a game period."""
        mapping = {
            GamePeriod.FIRST: self.period_1,
            GamePeriod.SECOND: self.period_2,
            GamePeriod.THIRD: self.period_3,
        }
        return mapping.get(period, self.overall)

    def get_goalie_season_phase(
        self, phase: SeasonPhase
    ) -> GoaliePerformanceSnapshot | None:
        """Get goalie performance for a season phase."""
        mapping = {
            SeasonPhase.EARLY: self.goalie_early_season,
            SeasonPhase.MID: self.goalie_mid_season,
            SeasonPhase.LATE: self.goalie_late_season,
        }
        return mapping.get(phase)

    def get_goalie_period(
        self, period: GamePeriod
    ) -> GoaliePerformanceSnapshot | None:
        """Get goalie performance for a game period."""
        mapping = {
            GamePeriod.FIRST: self.goalie_period_1,
            GamePeriod.SECOND: self.goalie_period_2,
            GamePeriod.THIRD: self.goalie_period_3,
        }
        return mapping.get(period)

    def compute_trends(self) -> None:
        """Derive all trend data from the phase and period snapshots."""
        # Season scoring trend
        self.scoring_trend.early_value = self.early_season.points_per_60
        self.scoring_trend.mid_value = self.mid_season.points_per_60
        self.scoring_trend.late_value = self.late_season.points_per_60
        self.scoring_trend.compute()

        # Season shooting trend
        self.shooting_trend.early_value = self.early_season.shooting_percentage
        self.shooting_trend.mid_value = self.mid_season.shooting_percentage
        self.shooting_trend.late_value = self.late_season.shooting_percentage
        self.shooting_trend.compute()

        # Season possession trend
        self.possession_trend.early_value = self.early_season.corsi_percentage
        self.possession_trend.mid_value = self.mid_season.corsi_percentage
        self.possession_trend.late_value = self.late_season.corsi_percentage
        self.possession_trend.compute()

        # Period profile
        self.period_profile.compute(self.period_1, self.period_2, self.period_3)

        # Relative performance for each split vs overall
        if self.overall.points_per_60 > 0:
            base = self.overall.points_per_60
            self.early_season.relative_performance = self.early_season.points_per_60 / base if self.early_season.points_per_60 else 0.0
            self.mid_season.relative_performance = self.mid_season.points_per_60 / base if self.mid_season.points_per_60 else 0.0
            self.late_season.relative_performance = self.late_season.points_per_60 / base if self.late_season.points_per_60 else 0.0

            self.period_1.relative_performance = self.period_1.points_per_60 / base if self.period_1.points_per_60 else 0.0
            self.period_2.relative_performance = self.period_2.points_per_60 / base if self.period_2.points_per_60 else 0.0
            self.period_3.relative_performance = self.period_3.points_per_60 / base if self.period_3.points_per_60 else 0.0

        # Fatigue resistance: late season output / early season output
        if self.early_season.points_per_60 > 0:
            self.fatigue_resistance = (
                self.late_season.points_per_60 / self.early_season.points_per_60
            )
        else:
            self.fatigue_resistance = 1.0

        # Consistency: inverse of coefficient of variation across phases
        phase_values = [
            self.early_season.points_per_60,
            self.mid_season.points_per_60,
            self.late_season.points_per_60,
        ]
        mean_val = sum(phase_values) / 3 if any(phase_values) else 0.0
        if mean_val > 0:
            variance = sum((v - mean_val) ** 2 for v in phase_values) / 3
            cv = (variance ** 0.5) / mean_val
            self.consistency = max(0.0, 1.0 - cv)  # 1.0 = perfectly consistent
        else:
            self.consistency = 0.0

        # Data quality check
        min_games = 5
        self.has_sufficient_data = all(
            phase.games_played >= min_games
            for phase in [self.early_season, self.mid_season, self.late_season]
        )

    def get_dynamic_factor(
        self,
        season_phase: SeasonPhase,
        game_period: GamePeriod,
    ) -> float:
        """
        Get the combined dynamic performance factor for a specific
        season phase + game period combination.

        This is the key method the simulation engine will use.
        It answers: "How much better/worse is this player performing
        RIGHT NOW compared to their baseline?"

        Returns a multiplier around 1.0:
          > 1.0 = performing above baseline
          < 1.0 = performing below baseline
        """
        phase_snap = self.get_season_phase(season_phase)
        period_snap = self.get_period(game_period)

        # Combine the two relative performance signals
        # Both are ratios vs overall (1.0 = average)
        phase_factor = phase_snap.relative_performance
        period_factor = period_snap.relative_performance

        if phase_factor <= 0 or period_factor <= 0:
            return 1.0

        # Geometric mean preserves the multiplicative relationship
        # If a player is 1.2x in late season and 1.3x in 3rd period,
        # the combined factor is ~1.25x, not 1.56x (avoids stacking)
        return (phase_factor * period_factor) ** 0.5
