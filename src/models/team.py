"""
Team Data Model

Pydantic models for representing team composition, line configurations,
and team-level statistics.
"""

from typing import Any

from pydantic import BaseModel, Field


class LineConfiguration(BaseModel):
    """Represents a forward line or defensive pairing."""

    line_number: int  # 1-4 for forward lines, 1-3 for defense pairs
    line_type: str  # "forward" or "defense"
    player_ids: list[int] = Field(default_factory=list)
    chemistry_score: float = 0.0
    goals_for: int = 0
    goals_against: int = 0
    corsi_percentage: float = 0.0
    expected_goals_percentage: float = 0.0
    time_on_ice_seconds: int = 0

    @property
    def goals_for_percentage(self) -> float:
        """Calculate goals for percentage."""
        total = self.goals_for + self.goals_against
        return self.goals_for / total if total > 0 else 0.5


class SpecialTeamsUnit(BaseModel):
    """Represents a power play or penalty kill unit."""

    unit_number: int  # 1 or 2
    unit_type: str  # "power_play" or "penalty_kill"
    player_ids: list[int] = Field(default_factory=list)
    goals: int = 0
    opportunities: int = 0
    time_on_ice_seconds: int = 0

    @property
    def efficiency(self) -> float:
        """Calculate unit efficiency (goals per opportunity)."""
        return self.goals / self.opportunities if self.opportunities > 0 else 0.0


class TeamRoster(BaseModel):
    """Complete team roster."""

    forwards: list[int] = Field(default_factory=list)  # Player IDs
    defensemen: list[int] = Field(default_factory=list)
    goalies: list[int] = Field(default_factory=list)

    @property
    def all_skaters(self) -> list[int]:
        """Get all skater IDs."""
        return self.forwards + self.defensemen

    @property
    def all_players(self) -> list[int]:
        """Get all player IDs."""
        return self.forwards + self.defensemen + self.goalies


class TeamStats(BaseModel):
    """Team-level statistics."""

    games_played: int = 0
    wins: int = 0
    losses: int = 0
    overtime_losses: int = 0
    points: int = 0
    goals_for: int = 0
    goals_against: int = 0
    shots_for: int = 0
    shots_against: int = 0

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
    power_play_opportunities: int = 0
    power_play_percentage: float = 0.0
    penalty_kill_goals_against: int = 0
    penalty_kill_opportunities: int = 0
    penalty_kill_percentage: float = 0.0

    # Zone stats (zone_name -> metric)
    zone_shots_for: dict[str, int] = Field(default_factory=dict)
    zone_shots_against: dict[str, int] = Field(default_factory=dict)
    zone_goals_for: dict[str, int] = Field(default_factory=dict)
    zone_goals_against: dict[str, int] = Field(default_factory=dict)

    # Segment stats
    early_game_goals_for: int = 0
    early_game_goals_against: int = 0
    mid_game_goals_for: int = 0
    mid_game_goals_against: int = 0
    late_game_goals_for: int = 0
    late_game_goals_against: int = 0

    @property
    def goal_differential(self) -> int:
        """Calculate goal differential."""
        return self.goals_for - self.goals_against

    @property
    def win_percentage(self) -> float:
        """Calculate win percentage."""
        return self.wins / self.games_played if self.games_played > 0 else 0.0

    @property
    def shooting_percentage(self) -> float:
        """Calculate team shooting percentage."""
        return self.goals_for / self.shots_for if self.shots_for > 0 else 0.0

    @property
    def save_percentage(self) -> float:
        """Calculate team save percentage."""
        if self.shots_against == 0:
            return 1.0
        return 1 - (self.goals_against / self.shots_against)


class Team(BaseModel):
    """
    Complete team model.

    Represents an NHL team with roster, line configurations,
    and team-level statistics.
    """

    # Identification
    team_id: int
    name: str
    abbreviation: str
    location: str = ""
    division: str = ""
    conference: str = ""

    # Roster
    roster: TeamRoster = Field(default_factory=TeamRoster)

    # Line configurations
    forward_lines: list[LineConfiguration] = Field(default_factory=list)
    defense_pairs: list[LineConfiguration] = Field(default_factory=list)

    # Special teams
    power_play_units: list[SpecialTeamsUnit] = Field(default_factory=list)
    penalty_kill_units: list[SpecialTeamsUnit] = Field(default_factory=list)

    # Starting goalie
    starting_goalie_id: int | None = None
    backup_goalie_id: int | None = None

    # Statistics
    current_season_stats: TeamStats = Field(default_factory=TeamStats)
    historical_stats: dict[str, TeamStats] = Field(default_factory=dict)

    # Heat maps (aggregated from players)
    offensive_heat_map: dict[str, float] = Field(default_factory=dict)
    defensive_heat_map: dict[str, float] = Field(default_factory=dict)

    # Play style indicators
    dump_and_chase_frequency: float = 0.0
    cross_ice_pass_frequency: float = 0.0
    slot_shot_preference: float = 0.0
    perimeter_shot_preference: float = 0.0

    def get_line(self, line_number: int, line_type: str = "forward") -> LineConfiguration | None:
        """
        Get a specific line configuration.

        Args:
            line_number: Line number (1-4 for forwards, 1-3 for defense)
            line_type: "forward" or "defense"

        Returns:
            LineConfiguration or None
        """
        lines = self.forward_lines if line_type == "forward" else self.defense_pairs
        for line in lines:
            if line.line_number == line_number:
                return line
        return None

    def get_zone_strength(self, zone: str, offensive: bool = True) -> float:
        """
        Get team's strength in a specific zone.

        Args:
            zone: Zone name
            offensive: True for offensive strength, False for defensive

        Returns:
            Strength rating (0.0 to 1.0)
        """
        heat_map = self.offensive_heat_map if offensive else self.defensive_heat_map
        return heat_map.get(zone, 0.0)

    def get_segment_goal_differential(self, segment: str) -> int:
        """
        Get goal differential for a specific game segment.

        Args:
            segment: Segment name (early_game, mid_game, late_game)

        Returns:
            Goal differential for the segment
        """
        stats = self.current_season_stats
        if segment == "early_game":
            return stats.early_game_goals_for - stats.early_game_goals_against
        elif segment == "mid_game":
            return stats.mid_game_goals_for - stats.mid_game_goals_against
        elif segment == "late_game":
            return stats.late_game_goals_for - stats.late_game_goals_against
        return 0

    def calculate_matchup_advantage(
        self,
        opponent: "Team",
        zone: str,
    ) -> float:
        """
        Calculate offensive advantage against an opponent in a zone.

        Args:
            opponent: Opponent team
            zone: Zone name

        Returns:
            Advantage rating (positive = advantage, negative = disadvantage)
        """
        offensive_strength = self.get_zone_strength(zone, offensive=True)
        defensive_strength = opponent.get_zone_strength(zone, offensive=False)

        # Higher offensive strength vs lower defensive strength = advantage
        return offensive_strength - defensive_strength
