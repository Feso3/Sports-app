"""
Zone-Based Expected Goals Calculator

Calculates expected goals based on zone-specific offensive and defensive metrics,
integrating team and line performance data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.player import Player
    from src.models.team import Team, LineConfiguration


@dataclass
class ZoneExpectedGoals:
    """Expected goals breakdown by zone."""

    zone_name: str
    offensive_xg: float = 0.0
    defensive_xg_against: float = 0.0
    net_xg: float = 0.0
    shot_volume: float = 0.0

    def __post_init__(self) -> None:
        """Calculate net xG."""
        self.net_xg = self.offensive_xg - self.defensive_xg_against


@dataclass
class LineExpectedGoals:
    """Expected goals for a specific line configuration."""

    line_number: int
    line_type: str  # "forward" or "defense"
    player_ids: list[int] = field(default_factory=list)

    # Offensive metrics
    offensive_xg_per_60: float = 0.0
    shot_rate_per_60: float = 0.0

    # Defensive metrics
    defensive_xg_against_per_60: float = 0.0
    shots_against_per_60: float = 0.0

    # Zone breakdown
    zone_xg: dict[str, ZoneExpectedGoals] = field(default_factory=dict)

    # Adjustments
    synergy_modifier: float = 1.0
    clutch_modifier: float = 1.0
    fatigue_modifier: float = 1.0

    @property
    def adjusted_offensive_xg(self) -> float:
        """Get offensive xG with all adjustments applied."""
        return (
            self.offensive_xg_per_60
            * self.synergy_modifier
            * self.clutch_modifier
            * self.fatigue_modifier
        )

    @property
    def adjusted_defensive_xg(self) -> float:
        """Get defensive xG against with adjustments (lower is better)."""
        # Fatigue increases goals against
        return self.defensive_xg_against_per_60 / (self.fatigue_modifier or 1.0)


@dataclass
class TeamExpectedGoals:
    """Expected goals summary for a team."""

    team_id: int
    total_xg_for: float = 0.0
    total_xg_against: float = 0.0

    # By situation
    even_strength_xg_for: float = 0.0
    even_strength_xg_against: float = 0.0
    power_play_xg_for: float = 0.0
    penalty_kill_xg_against: float = 0.0

    # By segment
    early_game_xg_for: float = 0.0
    mid_game_xg_for: float = 0.0
    late_game_xg_for: float = 0.0

    # Zone breakdown
    zone_xg: dict[str, ZoneExpectedGoals] = field(default_factory=dict)

    # Line breakdowns
    line_xg: list[LineExpectedGoals] = field(default_factory=list)

    @property
    def net_xg(self) -> float:
        """Net expected goals differential."""
        return self.total_xg_for - self.total_xg_against

    @property
    def xg_percentage(self) -> float:
        """Expected goals percentage."""
        total = self.total_xg_for + self.total_xg_against
        return self.total_xg_for / total if total > 0 else 0.5


class ExpectedGoalsCalculator:
    """
    Calculator for zone-based expected goals.

    Integrates team stats, line configurations, and individual player data
    to compute expected goals for game simulation.
    """

    # Default zone xG rates (per shot)
    DEFAULT_ZONE_XG_RATES = {
        "slot": 0.18,
        "high_slot": 0.10,
        "left_circle": 0.08,
        "right_circle": 0.08,
        "left_point": 0.03,
        "right_point": 0.03,
        "behind_net": 0.02,
        "neutral_zone": 0.01,
    }

    # Zone importance weights
    ZONE_IMPORTANCE = {
        "slot": 1.5,
        "high_slot": 1.3,
        "left_circle": 1.1,
        "right_circle": 1.1,
        "left_point": 0.8,
        "right_point": 0.8,
        "behind_net": 0.5,
        "neutral_zone": 0.3,
    }

    # Base rates per 60 minutes
    BASE_SHOTS_PER_60 = 30.0
    BASE_XG_PER_60 = 2.5

    def __init__(
        self,
        zone_xg_rates: dict[str, float] | None = None,
        zone_importance: dict[str, float] | None = None,
    ) -> None:
        """Initialize the calculator with optional custom rates."""
        self.zone_xg_rates = {**self.DEFAULT_ZONE_XG_RATES, **(zone_xg_rates or {})}
        self.zone_importance = {**self.ZONE_IMPORTANCE, **(zone_importance or {})}

    def calculate_team_xg(
        self,
        team: Team,
        opponent: Team,
        players: dict[int, Player] | None = None,
    ) -> TeamExpectedGoals:
        """
        Calculate expected goals for a team against an opponent.

        Args:
            team: Team to calculate xG for
            opponent: Opposing team
            players: Optional player data dictionary

        Returns:
            TeamExpectedGoals with full breakdown
        """
        result = TeamExpectedGoals(team_id=team.team_id)

        # Calculate zone-by-zone xG
        for zone, base_rate in self.zone_xg_rates.items():
            zone_xg = self._calculate_zone_xg(team, opponent, zone, base_rate)
            result.zone_xg[zone] = zone_xg
            result.total_xg_for += zone_xg.offensive_xg
            result.total_xg_against += zone_xg.defensive_xg_against

        # Calculate line-by-line xG
        for line in team.forward_lines:
            line_xg = self._calculate_line_xg(
                line, team, opponent, players, "forward"
            )
            result.line_xg.append(line_xg)

        for pair in team.defense_pairs:
            pair_xg = self._calculate_line_xg(
                pair, team, opponent, players, "defense"
            )
            result.line_xg.append(pair_xg)

        # Calculate situation-specific xG
        result.even_strength_xg_for = result.total_xg_for * 0.75
        result.power_play_xg_for = self._calculate_power_play_xg(team)
        result.penalty_kill_xg_against = self._calculate_penalty_kill_xg_against(
            team, opponent
        )

        # Calculate segment-specific xG
        result.early_game_xg_for = result.total_xg_for * 0.30
        result.mid_game_xg_for = result.total_xg_for * 0.35
        result.late_game_xg_for = result.total_xg_for * 0.35

        return result

    def calculate_matchup_xg(
        self,
        home_team: Team,
        away_team: Team,
        players: dict[int, Player] | None = None,
    ) -> tuple[TeamExpectedGoals, TeamExpectedGoals]:
        """
        Calculate expected goals for both teams in a matchup.

        Returns:
            Tuple of (home_xg, away_xg)
        """
        home_xg = self.calculate_team_xg(home_team, away_team, players)
        away_xg = self.calculate_team_xg(away_team, home_team, players)

        # Apply home ice advantage
        home_xg.total_xg_for *= 1.03
        away_xg.total_xg_against *= 1.03

        return home_xg, away_xg

    def calculate_line_matchup_xg(
        self,
        home_line: LineConfiguration,
        away_line: LineConfiguration,
        home_team: Team,
        away_team: Team,
        players: dict[int, Player] | None = None,
        segment: str = "mid_game",
    ) -> tuple[float, float]:
        """
        Calculate expected goals for a specific line matchup.

        Args:
            home_line: Home team line
            away_line: Away team line
            home_team: Home team
            away_team: Away team
            players: Optional player data
            segment: Game segment for weighting

        Returns:
            Tuple of (home_xg, away_xg) for the matchup
        """
        # Get line offensive and defensive strengths
        home_offense = self._get_line_offensive_strength(home_line, home_team, players)
        away_defense = self._get_line_defensive_strength(away_line, away_team, players)
        away_offense = self._get_line_offensive_strength(away_line, away_team, players)
        home_defense = self._get_line_defensive_strength(home_line, home_team, players)

        # Calculate xG per 20 minutes (1 period)
        # xG = offensive_strength / (1 + defensive_strength)
        home_xg = (home_offense * self.BASE_XG_PER_60 / 3) / max(0.5, away_defense)
        away_xg = (away_offense * self.BASE_XG_PER_60 / 3) / max(0.5, home_defense)

        # Apply segment modifiers
        segment_modifiers = {
            "early_game": 0.9,
            "mid_game": 1.0,
            "late_game": 1.1,
            "overtime": 1.3,
        }
        modifier = segment_modifiers.get(segment, 1.0)
        home_xg *= modifier
        away_xg *= modifier

        return home_xg, away_xg

    def _calculate_zone_xg(
        self,
        team: Team,
        opponent: Team,
        zone: str,
        base_rate: float,
    ) -> ZoneExpectedGoals:
        """Calculate expected goals for a specific zone."""
        # Get team offensive strength in zone
        offensive_strength = team.get_zone_strength(zone, offensive=True)
        # Get opponent defensive strength in zone
        defensive_strength = opponent.get_zone_strength(zone, offensive=False)

        # Adjust base rate by strengths
        # Higher offensive strength = more xG
        # Higher defensive strength by opponent = less xG
        modifier = (1 + offensive_strength) / (1 + defensive_strength)

        # Calculate shot volume from team stats
        team_stats = team.current_season_stats
        total_shots = team_stats.shots_for or 1
        zone_shots = team_stats.zone_shots_for.get(zone, total_shots // 6)
        shot_share = zone_shots / total_shots if total_shots > 0 else 1 / 6

        # Estimate shots for zone per game
        shots_per_game = (team_stats.shots_for / max(team_stats.games_played, 1)) * shot_share
        shots_per_game = max(shots_per_game, 1)

        # Calculate xG
        offensive_xg = shots_per_game * base_rate * modifier

        # Calculate defensive xG against
        defensive_xg = self._calculate_defensive_zone_xg(team, opponent, zone, base_rate)

        return ZoneExpectedGoals(
            zone_name=zone,
            offensive_xg=offensive_xg,
            defensive_xg_against=defensive_xg,
            shot_volume=shots_per_game,
        )

    def _calculate_defensive_zone_xg(
        self,
        team: Team,
        opponent: Team,
        zone: str,
        base_rate: float,
    ) -> float:
        """Calculate expected goals against in a zone."""
        # Get opponent offensive strength
        opponent_offense = opponent.get_zone_strength(zone, offensive=True)
        # Get team defensive strength
        team_defense = team.get_zone_strength(zone, offensive=False)

        modifier = (1 + opponent_offense) / (1 + team_defense)

        # Get opponent shot volume
        opp_stats = opponent.current_season_stats
        total_shots = opp_stats.shots_for or 1
        zone_shots = opp_stats.zone_shots_for.get(zone, total_shots // 6)
        shot_share = zone_shots / total_shots if total_shots > 0 else 1 / 6

        shots_per_game = (opp_stats.shots_for / max(opp_stats.games_played, 1)) * shot_share
        shots_per_game = max(shots_per_game, 1)

        return shots_per_game * base_rate * modifier

    def _calculate_line_xg(
        self,
        line: LineConfiguration,
        team: Team,
        opponent: Team,
        players: dict[int, Player] | None,
        line_type: str,
    ) -> LineExpectedGoals:
        """Calculate expected goals for a line configuration."""
        result = LineExpectedGoals(
            line_number=line.line_number,
            line_type=line_type,
            player_ids=line.player_ids.copy(),
        )

        # Base xG from line stats
        toi_minutes = line.time_on_ice_seconds / 60 if line.time_on_ice_seconds > 0 else 60
        result.offensive_xg_per_60 = (line.goals_for / toi_minutes) * 60 if toi_minutes > 0 else 2.0

        # Use corsi/xG percentage as basis
        result.offensive_xg_per_60 = max(
            result.offensive_xg_per_60,
            line.expected_goals_percentage * 5.0  # Scale to per-60 rate
        )

        result.defensive_xg_against_per_60 = (
            line.goals_against / toi_minutes
        ) * 60 if toi_minutes > 0 else 2.0

        # Apply chemistry modifier
        result.synergy_modifier = 1 + (line.chemistry_score / 10) if line.chemistry_score else 1.0

        # Calculate zone breakdown if player data available
        if players:
            for zone in self.zone_xg_rates:
                zone_xg = self._calculate_line_zone_xg(line, players, zone)
                result.zone_xg[zone] = zone_xg

        return result

    def _calculate_line_zone_xg(
        self,
        line: LineConfiguration,
        players: dict[int, Player],
        zone: str,
    ) -> ZoneExpectedGoals:
        """Calculate zone-specific xG for a line."""
        offensive_xg = 0.0
        shot_volume = 0.0

        for player_id in line.player_ids:
            player = players.get(player_id)
            if player:
                # Get player zone stats
                zone_stats = player.career_stats.zone_stats.get(zone)
                if zone_stats:
                    offensive_xg += zone_stats.expected_goals
                    shot_volume += zone_stats.shots

        # Normalize to per-game
        games = max(sum(
            players[pid].career_stats.games_played
            for pid in line.player_ids if pid in players
        ) // len(line.player_ids), 1) if line.player_ids else 1

        return ZoneExpectedGoals(
            zone_name=zone,
            offensive_xg=offensive_xg / games,
            shot_volume=shot_volume / games,
        )

    def _calculate_power_play_xg(self, team: Team) -> float:
        """Calculate power play expected goals."""
        stats = team.current_season_stats
        pp_rate = stats.power_play_percentage / 100 if stats.power_play_percentage else 0.20
        # Estimate PP opportunities per game
        pp_opps_per_game = stats.power_play_opportunities / max(stats.games_played, 1)
        return pp_opps_per_game * pp_rate

    def _calculate_penalty_kill_xg_against(self, team: Team, opponent: Team) -> float:
        """Calculate expected goals against on penalty kill."""
        team_stats = team.current_season_stats
        opp_stats = opponent.current_season_stats

        # Team PK success rate
        pk_rate = team_stats.penalty_kill_percentage / 100 if team_stats.penalty_kill_percentage else 0.80
        # Opponent PP conversion rate
        opp_pp_rate = opp_stats.power_play_percentage / 100 if opp_stats.power_play_percentage else 0.20

        # Estimate times shorthanded per game
        pk_opps_per_game = team_stats.penalty_kill_opportunities / max(team_stats.games_played, 1)

        # Combine rates: higher opponent PP means more goals against
        combined_rate = (1 - pk_rate + opp_pp_rate) / 2
        return pk_opps_per_game * combined_rate

    def _get_line_offensive_strength(
        self,
        line: LineConfiguration,
        team: Team,
        players: dict[int, Player] | None,
    ) -> float:
        """Get offensive strength rating for a line (0.5 to 1.5)."""
        # Base from line stats
        base_strength = (line.expected_goals_percentage + line.corsi_percentage) / 2
        if base_strength == 0:
            base_strength = 0.5

        # Adjust by goals scored
        if line.goals_for > 0:
            goal_factor = min(line.goals_for / 20, 0.3)  # Cap at +0.3
            base_strength += goal_factor

        # Adjust by chemistry
        chemistry_factor = line.chemistry_score / 20 if line.chemistry_score else 0
        base_strength += chemistry_factor

        # If player data available, factor in individual xG
        if players:
            player_xg_sum = sum(
                players[pid].career_stats.expected_goals_for
                for pid in line.player_ids if pid in players
            )
            player_factor = min(player_xg_sum / 50, 0.2)  # Cap at +0.2
            base_strength += player_factor

        return max(0.5, min(1.5, base_strength))

    def _get_line_defensive_strength(
        self,
        line: LineConfiguration,
        team: Team,
        players: dict[int, Player] | None,
    ) -> float:
        """Get defensive strength rating for a line (0.5 to 1.5)."""
        # Base from line stats
        base_strength = (line.expected_goals_percentage + line.corsi_percentage) / 2
        if base_strength == 0:
            base_strength = 0.5

        # Good defense means low goals against
        if line.goals_against > 0:
            # Fewer goals against = better defense
            ga_factor = max(-0.3, -line.goals_against / 30)
            base_strength -= ga_factor  # Subtracting negative = adding

        # For defense pairs, weight defensive metrics more
        if line.line_type == "defense":
            base_strength *= 1.1

        return max(0.5, min(1.5, base_strength))
