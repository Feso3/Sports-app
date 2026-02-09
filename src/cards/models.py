"""Player card data models."""

from pydantic import BaseModel, Field


class SkaterStats(BaseModel):
    """Skater stat line -- used for season totals, splits, and league averages."""

    games: int = 0
    goals: int = 0
    assists: int = 0
    points: int = 0
    plus_minus: int = 0
    shots: int = 0
    shooting_pct: float = 0.0
    toi_seconds: int = 0
    avg_toi_minutes: float = 0.0
    hits: int = 0
    blocked_shots: int = 0
    pim: int = 0
    power_play_goals: int = 0
    power_play_points: int = 0
    shorthanded_goals: int = 0
    shorthanded_points: int = 0
    game_winning_goals: int = 0
    faceoff_wins: int = 0
    faceoff_losses: int = 0
    goals_per_60: float = 0.0
    points_per_60: float = 0.0


class GoalieStats(BaseModel):
    """Goalie stat line -- used for season totals, splits, and league averages."""

    games: int = 0
    games_started: int = 0
    wins: int = 0
    losses: int = 0
    otl: int = 0
    saves: int = 0
    shots_against: int = 0
    goals_against: int = 0
    save_pct: float = 0.0
    gaa: float = 0.0
    shutouts: int = 0
    toi_seconds: int = 0
    avg_toi_minutes: float = 0.0


class ShotEvent(BaseModel):
    """Single shot event for the heat map."""

    x: float
    y: float
    is_goal: bool
    shot_type: str = ""
    period: int = 0
    strength: str = ""


class PeriodSplit(BaseModel):
    """Shot-level stats for a single period."""

    period: int
    shots: int = 0
    goals: int = 0
    shooting_pct: float = 0.0


class GoaliePeriodSplit(BaseModel):
    """Goalie shot-level stats for a single period."""

    period: int
    shots_against: int = 0
    goals_against: int = 0
    saves: int = 0
    save_pct: float = 0.0


class PhaseSplit(BaseModel):
    """Skater stats for a season phase."""

    phase: str  # early, mid, late, playoffs
    games: int = 0
    goals: int = 0
    assists: int = 0
    points: int = 0
    shots: int = 0
    toi_seconds: int = 0
    shooting_pct: float = 0.0
    points_per_60: float = 0.0


class GoaliePhaseSplit(BaseModel):
    """Goalie stats for a season phase."""

    phase: str
    games: int = 0
    wins: int = 0
    losses: int = 0
    saves: int = 0
    shots_against: int = 0
    goals_against: int = 0
    save_pct: float = 0.0
    gaa: float = 0.0


class StrengthSplit(BaseModel):
    """Shot-level stats by game strength."""

    strength: str  # even, pp, sh
    shots: int = 0
    goals: int = 0
    shooting_pct: float = 0.0


class GoalieStrengthSplit(BaseModel):
    """Goalie stats by game strength."""

    strength: str
    shots_against: int = 0
    goals_against: int = 0
    saves: int = 0
    save_pct: float = 0.0


class PlayerCard(BaseModel):
    """The player card -- the soul of the player."""

    # Identity
    player_id: int
    name: str
    first_name: str = ""
    last_name: str = ""
    position: str
    team: str = ""
    number: int | None = None
    shoots: str | None = None
    height_inches: int | None = None
    weight_lbs: int | None = None
    is_goalie: bool = False

    season: int

    # Season totals
    skater_stats: SkaterStats | None = None
    goalie_stats: GoalieStats | None = None

    # League average for comparison
    league_skater_avg: SkaterStats | None = None
    league_goalie_avg: GoalieStats | None = None

    # Player score: delta from league average
    # Skaters: points_per_60 - league_avg_points_per_60
    # Goalies: (save_pct - league_avg_save_pct) * 100
    player_score: float = 0.0
    score_label: str = ""  # e.g. "+2.1 P/60" or "+1.5 SV%"

    # Splits
    period_splits: list[PeriodSplit | GoaliePeriodSplit] = Field(default_factory=list)
    season_phase_splits: list[PhaseSplit | GoaliePhaseSplit] = Field(default_factory=list)
    strength_splits: list[StrengthSplit | GoalieStrengthSplit] = Field(default_factory=list)

    # Shot data for heat map
    shots: list[ShotEvent] = Field(default_factory=list)
