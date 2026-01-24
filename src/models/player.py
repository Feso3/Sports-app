"""
Player Data Model

Pydantic models for representing player data, statistics, and performance metrics.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PlayerPosition(str, Enum):
    """Player position enumeration."""

    CENTER = "C"
    LEFT_WING = "LW"
    RIGHT_WING = "RW"
    DEFENSEMAN = "D"
    GOALIE = "G"
    UNKNOWN = "U"


class ZoneStats(BaseModel):
    """Statistics for a specific ice zone."""

    zone_name: str
    shots: int = 0
    goals: int = 0
    shooting_percentage: float = 0.0
    expected_goals: float = 0.0
    time_in_zone_seconds: int = 0


class PlayerStats(BaseModel):
    """Aggregated player statistics."""

    games_played: int = 0
    goals: int = 0
    assists: int = 0
    points: int = 0
    plus_minus: int = 0
    penalty_minutes: int = 0
    shots: int = 0
    shooting_percentage: float = 0.0
    time_on_ice_seconds: int = 0
    average_toi_per_game: float = 0.0

    # Advanced stats
    corsi_for: int = 0
    corsi_against: int = 0
    corsi_percentage: float = 0.0
    fenwick_for: int = 0
    fenwick_against: int = 0
    fenwick_percentage: float = 0.0
    expected_goals_for: float = 0.0
    expected_goals_against: float = 0.0

    # Special teams
    power_play_goals: int = 0
    power_play_assists: int = 0
    power_play_points: int = 0
    power_play_time_seconds: int = 0
    shorthanded_goals: int = 0
    shorthanded_assists: int = 0
    shorthanded_points: int = 0
    shorthanded_time_seconds: int = 0

    # Zone-based stats
    zone_stats: dict[str, ZoneStats] = Field(default_factory=dict)

    # Segment-based stats
    early_game_goals: int = 0
    mid_game_goals: int = 0
    late_game_goals: int = 0
    early_game_points: int = 0
    mid_game_points: int = 0
    late_game_points: int = 0


class GoalieStats(BaseModel):
    """Goalie-specific statistics."""

    games_played: int = 0
    games_started: int = 0
    wins: int = 0
    losses: int = 0
    overtime_losses: int = 0
    saves: int = 0
    shots_against: int = 0
    goals_against: int = 0
    save_percentage: float = 0.0
    goals_against_average: float = 0.0
    shutouts: int = 0
    time_on_ice_seconds: int = 0

    # Zone-based save stats
    zone_save_stats: dict[str, ZoneStats] = Field(default_factory=dict)

    # High danger saves
    high_danger_saves: int = 0
    high_danger_shots_against: int = 0
    high_danger_save_percentage: float = 0.0


class Player(BaseModel):
    """
    Complete player model with biographical and statistical data.

    Represents an NHL player with all relevant information for
    analytics and simulation purposes.
    """

    # Identification
    player_id: int
    full_name: str
    first_name: str = ""
    last_name: str = ""

    # Biographical
    birth_date: str | None = None
    birth_city: str | None = None
    birth_country: str | None = None
    nationality: str | None = None
    height_inches: int | None = None
    weight_pounds: int | None = None

    # Position and handedness
    position: PlayerPosition = PlayerPosition.UNKNOWN
    position_code: str = "U"
    shoots_catches: str | None = None  # "L" or "R"

    # Current team
    current_team_id: int | None = None
    current_team_abbrev: str | None = None
    jersey_number: int | None = None

    # Status
    is_active: bool = True
    is_rookie: bool = False

    # Draft info
    draft_year: int | None = None
    draft_round: int | None = None
    draft_pick: int | None = None

    # Statistics
    career_stats: PlayerStats = Field(default_factory=PlayerStats)
    season_stats: dict[str, PlayerStats] = Field(default_factory=dict)
    goalie_stats: GoalieStats | None = None

    # Heat map data (zone -> shot count)
    offensive_heat_map: dict[str, float] = Field(default_factory=dict)
    defensive_heat_map: dict[str, float] = Field(default_factory=dict)

    # Synergy data (player_id -> synergy score)
    synergies: dict[int, float] = Field(default_factory=dict)

    # Performance metrics
    clutch_rating: float = 0.0
    fatigue_factor: float = 1.0

    class Config:
        """Pydantic configuration."""

        use_enum_values = True

    @property
    def is_goalie(self) -> bool:
        """Check if player is a goalie."""
        return self.position == PlayerPosition.GOALIE

    @property
    def is_forward(self) -> bool:
        """Check if player is a forward."""
        return self.position in {
            PlayerPosition.CENTER,
            PlayerPosition.LEFT_WING,
            PlayerPosition.RIGHT_WING,
        }

    @property
    def is_defenseman(self) -> bool:
        """Check if player is a defenseman."""
        return self.position == PlayerPosition.DEFENSEMAN

    def get_season_stats(self, season: str) -> PlayerStats | None:
        """Get statistics for a specific season."""
        return self.season_stats.get(season)

    def get_zone_shooting_percentage(self, zone: str) -> float:
        """Get shooting percentage for a specific zone."""
        zone_stats = self.career_stats.zone_stats.get(zone)
        if zone_stats and zone_stats.shots > 0:
            return zone_stats.goals / zone_stats.shots
        return 0.0

    def get_segment_performance(self, segment: str) -> dict[str, int]:
        """Get performance metrics for a game segment."""
        stats = self.career_stats
        if segment == "early_game":
            return {"goals": stats.early_game_goals, "points": stats.early_game_points}
        elif segment == "mid_game":
            return {"goals": stats.mid_game_goals, "points": stats.mid_game_points}
        elif segment == "late_game":
            return {"goals": stats.late_game_goals, "points": stats.late_game_points}
        return {"goals": 0, "points": 0}

    def calculate_expected_goals(self, zone: str, shot_type: str = "wrist") -> float:
        """
        Calculate expected goals for a shot from a given zone.

        Args:
            zone: Ice zone name
            shot_type: Type of shot

        Returns:
            Expected goals value
        """
        zone_stats = self.career_stats.zone_stats.get(zone)
        if not zone_stats:
            return 0.0

        base_xg = zone_stats.expected_goals
        shooting_pct = self.get_zone_shooting_percentage(zone)

        # Adjust for player's shooting ability
        league_avg_shooting_pct = 0.10  # Placeholder
        player_modifier = shooting_pct / league_avg_shooting_pct if league_avg_shooting_pct > 0 else 1.0

        return base_xg * player_modifier
