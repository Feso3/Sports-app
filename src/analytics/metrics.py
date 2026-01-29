"""
Statistical Metrics Module

Calculates advanced hockey statistics including:
- Expected Goals (xG)
- Corsi and Fenwick
- PDO and luck metrics
- Zone-specific metrics
- Per-60 minute rates
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from loguru import logger


@dataclass
class ShotAttempt:
    """Represents a shot attempt for Corsi/Fenwick calculations."""

    event_type: str  # "shot", "goal", "blocked", "missed"
    team_id: int
    player_id: int | None = None
    x_coord: float | None = None
    y_coord: float | None = None
    period: int = 0
    game_seconds: int = 0
    strength: str = "5v5"  # "5v5", "5v4", "4v5", etc.


@dataclass
class CorsiStats:
    """Corsi statistics for a player or team."""

    corsi_for: int = 0  # Shot attempts for (goals + shots + blocked + missed)
    corsi_against: int = 0  # Shot attempts against
    goals_for: int = 0
    goals_against: int = 0
    shots_for: int = 0  # Shots on goal
    shots_against: int = 0
    blocked_for: int = 0  # Blocked shots (we blocked opponent)
    blocked_against: int = 0  # Our shots blocked
    missed_for: int = 0
    missed_against: int = 0
    time_on_ice_seconds: int = 0

    @property
    def corsi_percentage(self) -> float:
        """Calculate Corsi percentage (CF%)."""
        total = self.corsi_for + self.corsi_against
        return self.corsi_for / total if total > 0 else 0.5

    @property
    def corsi_relative(self) -> float:
        """Calculate relative Corsi (CF% - Team CF% when player is off ice)."""
        # This would need team context - returns 0 as placeholder
        return 0.0

    @property
    def fenwick_for(self) -> int:
        """Fenwick for (unblocked shot attempts)."""
        return self.goals_for + self.shots_for + self.missed_for

    @property
    def fenwick_against(self) -> int:
        """Fenwick against."""
        return self.goals_against + self.shots_against + self.missed_against

    @property
    def fenwick_percentage(self) -> float:
        """Calculate Fenwick percentage (FF%)."""
        total = self.fenwick_for + self.fenwick_against
        return self.fenwick_for / total if total > 0 else 0.5

    @property
    def shooting_percentage(self) -> float:
        """Calculate shooting percentage."""
        return self.goals_for / self.shots_for if self.shots_for > 0 else 0.0

    @property
    def save_percentage(self) -> float:
        """Calculate team save percentage when player is on ice."""
        return 1 - (self.goals_against / self.shots_against) if self.shots_against > 0 else 1.0

    @property
    def pdo(self) -> float:
        """Calculate PDO (shooting % + save %)."""
        return self.shooting_percentage + self.save_percentage

    @property
    def corsi_for_per_60(self) -> float:
        """Corsi for per 60 minutes."""
        if self.time_on_ice_seconds == 0:
            return 0.0
        return self.corsi_for / (self.time_on_ice_seconds / 3600)

    @property
    def corsi_against_per_60(self) -> float:
        """Corsi against per 60 minutes."""
        if self.time_on_ice_seconds == 0:
            return 0.0
        return self.corsi_against / (self.time_on_ice_seconds / 3600)


@dataclass
class ExpectedGoalsStats:
    """Expected goals statistics."""

    xg_for: float = 0.0
    xg_against: float = 0.0
    goals_for: int = 0
    goals_against: int = 0
    shots_for: int = 0
    shots_against: int = 0

    @property
    def xg_percentage(self) -> float:
        """Expected goals percentage."""
        total = self.xg_for + self.xg_against
        return self.xg_for / total if total > 0 else 0.5

    @property
    def goals_above_expected(self) -> float:
        """Goals scored above expected."""
        return self.goals_for - self.xg_for

    @property
    def goals_saved_above_expected(self) -> float:
        """Goals saved above expected (for goalies/defense)."""
        return self.xg_against - self.goals_against

    @property
    def xg_differential(self) -> float:
        """Expected goals differential."""
        return self.xg_for - self.xg_against


@dataclass
class ZoneMetrics:
    """Zone-specific metrics for a player or team."""

    zone_name: str
    shots: int = 0
    goals: int = 0
    expected_goals: float = 0.0
    shooting_percentage: float = 0.0
    shot_share: float = 0.0  # Percentage of total shots from this zone

    @property
    def goals_above_expected(self) -> float:
        """Goals above expected for this zone."""
        return self.goals - self.expected_goals


class MetricsCalculator:
    """
    Calculator for advanced hockey statistics.

    Processes raw event data into meaningful analytics metrics.
    """

    # Expected goals model parameters by distance and angle
    XG_DISTANCE_DECAY = 0.05
    XG_ANGLE_PENALTY = 0.3
    XG_BASE_RATE = 0.08

    # Shot type xG modifiers
    # Note: Keys must match normalized names from shot_data.py SHOT_TYPE_MAP
    SHOT_TYPE_MODIFIERS = {
        "wrist": 1.0,
        "slap": 0.85,
        "snap": 1.1,
        "backhand": 0.9,
        "deflection": 1.4,
        "tip_in": 1.5,
        "wrap_around": 0.7,
        "bat": 0.6,
        "poke": 0.5,
        "cradle": 0.8,
    }

    # Rebound and rush modifiers
    REBOUND_MODIFIER = 1.3
    RUSH_MODIFIER = 1.2

    def __init__(self) -> None:
        """Initialize the metrics calculator."""
        # Storage for accumulated stats
        self.player_corsi: dict[int, CorsiStats] = {}
        self.team_corsi: dict[int, CorsiStats] = {}
        self.player_xg: dict[int, ExpectedGoalsStats] = {}
        self.team_xg: dict[int, ExpectedGoalsStats] = {}
        self.player_zone_metrics: dict[int, dict[str, ZoneMetrics]] = {}

    def calculate_shot_xg(
        self,
        x: float | None,
        y: float | None,
        shot_type: str | None = None,
        is_rebound: bool = False,
        is_rush: bool = False,
        is_power_play: bool = False,
        shooter_position: str | None = None,
    ) -> float:
        """
        Calculate expected goals value for a shot.

        Args:
            x: X coordinate (goal at x=89)
            y: Y coordinate (center = 0)
            shot_type: Type of shot
            is_rebound: Whether shot is a rebound
            is_rush: Whether shot is on a rush
            is_power_play: Whether shot is on power play
            shooter_position: Position of shooter (C, LW, RW, D)

        Returns:
            Expected goals value (0-1)
        """
        if x is None or y is None:
            return self.XG_BASE_RATE

        # Normalize to offensive zone
        x = abs(x)
        goal_x = 89
        goal_y = 0

        # Calculate distance to goal
        distance = np.sqrt((goal_x - x) ** 2 + y ** 2)

        # Calculate angle to goal (0 = straight on, pi/2 = from side)
        angle = np.arctan2(abs(y), max(goal_x - x, 0.1))

        # Base xG from distance
        if distance < 10:
            base_xg = 0.25
        elif distance < 20:
            base_xg = 0.12
        elif distance < 35:
            base_xg = 0.06
        elif distance < 50:
            base_xg = 0.03
        else:
            base_xg = 0.01

        # Angle penalty
        angle_factor = max(0.3, 1 - (angle / (np.pi / 2)) * self.XG_ANGLE_PENALTY)
        xg = base_xg * angle_factor

        # Shot type modifier
        if shot_type:
            modifier = self.SHOT_TYPE_MODIFIERS.get(shot_type.lower(), 1.0)
            xg *= modifier

        # Situation modifiers
        if is_rebound:
            xg *= self.REBOUND_MODIFIER
        if is_rush:
            xg *= self.RUSH_MODIFIER
        if is_power_play:
            xg *= 1.15

        # Cap at reasonable maximum
        return min(xg, 0.95)

    def process_shot_attempt(
        self,
        event_type: str,
        team_id: int,
        opponent_id: int,
        player_id: int | None = None,
        x: float | None = None,
        y: float | None = None,
        shot_type: str | None = None,
        strength: str = "5v5",
        is_rebound: bool = False,
        is_rush: bool = False,
        zone: str | None = None,
    ) -> float:
        """
        Process a shot attempt and update all relevant metrics.

        Args:
            event_type: "goal", "shot", "blocked", "missed"
            team_id: Shooting team ID
            opponent_id: Defending team ID
            player_id: Shooter player ID
            x, y: Shot coordinates
            shot_type: Type of shot
            strength: Game strength state
            is_rebound: Rebound shot
            is_rush: Rush shot
            zone: Ice zone name

        Returns:
            Expected goals value for the shot
        """
        # Calculate xG
        xg = self.calculate_shot_xg(
            x, y, shot_type, is_rebound, is_rush,
            is_power_play=(strength in ["5v4", "5v3", "4v3"])
        )

        is_goal = event_type == "goal"
        is_blocked = event_type == "blocked"
        is_missed = event_type == "missed"
        is_shot_on_goal = event_type in ["goal", "shot"]

        # Update team Corsi stats
        self._update_team_corsi(
            team_id, opponent_id, is_goal, is_shot_on_goal, is_blocked, is_missed
        )

        # Update player Corsi stats
        if player_id is not None:
            self._update_player_corsi(
                player_id, True, is_goal, is_shot_on_goal, is_blocked, is_missed
            )

        # Update xG stats (only for unblocked shots)
        if not is_blocked:
            self._update_team_xg(team_id, opponent_id, xg, is_goal)
            if player_id is not None:
                self._update_player_xg(player_id, xg, is_goal, is_shot_on_goal)

        # Update zone metrics
        if player_id is not None and zone:
            self._update_zone_metrics(player_id, zone, is_shot_on_goal, is_goal, xg)

        return xg

    def _ensure_team_corsi(self, team_id: int) -> CorsiStats:
        """Ensure team Corsi stats exist."""
        if team_id not in self.team_corsi:
            self.team_corsi[team_id] = CorsiStats()
        return self.team_corsi[team_id]

    def _ensure_player_corsi(self, player_id: int) -> CorsiStats:
        """Ensure player Corsi stats exist."""
        if player_id not in self.player_corsi:
            self.player_corsi[player_id] = CorsiStats()
        return self.player_corsi[player_id]

    def _ensure_team_xg(self, team_id: int) -> ExpectedGoalsStats:
        """Ensure team xG stats exist."""
        if team_id not in self.team_xg:
            self.team_xg[team_id] = ExpectedGoalsStats()
        return self.team_xg[team_id]

    def _ensure_player_xg(self, player_id: int) -> ExpectedGoalsStats:
        """Ensure player xG stats exist."""
        if player_id not in self.player_xg:
            self.player_xg[player_id] = ExpectedGoalsStats()
        return self.player_xg[player_id]

    def _update_team_corsi(
        self,
        team_id: int,
        opponent_id: int,
        is_goal: bool,
        is_shot: bool,
        is_blocked: bool,
        is_missed: bool,
    ) -> None:
        """Update team Corsi statistics."""
        team_stats = self._ensure_team_corsi(team_id)
        opp_stats = self._ensure_team_corsi(opponent_id)

        # For shooting team
        team_stats.corsi_for += 1
        if is_goal:
            team_stats.goals_for += 1
        if is_shot:
            team_stats.shots_for += 1
        if is_blocked:
            team_stats.blocked_against += 1
        if is_missed:
            team_stats.missed_for += 1

        # For defending team
        opp_stats.corsi_against += 1
        if is_goal:
            opp_stats.goals_against += 1
        if is_shot:
            opp_stats.shots_against += 1
        if is_blocked:
            opp_stats.blocked_for += 1
        if is_missed:
            opp_stats.missed_against += 1

    def _update_player_corsi(
        self,
        player_id: int,
        is_for: bool,
        is_goal: bool,
        is_shot: bool,
        is_blocked: bool,
        is_missed: bool,
    ) -> None:
        """Update player Corsi statistics."""
        stats = self._ensure_player_corsi(player_id)

        if is_for:
            stats.corsi_for += 1
            if is_goal:
                stats.goals_for += 1
            if is_shot:
                stats.shots_for += 1
            if is_blocked:
                stats.blocked_against += 1
            if is_missed:
                stats.missed_for += 1

    def _update_team_xg(
        self,
        team_id: int,
        opponent_id: int,
        xg: float,
        is_goal: bool,
    ) -> None:
        """Update team expected goals statistics."""
        team_stats = self._ensure_team_xg(team_id)
        opp_stats = self._ensure_team_xg(opponent_id)

        team_stats.xg_for += xg
        team_stats.shots_for += 1
        if is_goal:
            team_stats.goals_for += 1

        opp_stats.xg_against += xg
        opp_stats.shots_against += 1
        if is_goal:
            opp_stats.goals_against += 1

    def _update_player_xg(
        self,
        player_id: int,
        xg: float,
        is_goal: bool,
        is_shot: bool,
    ) -> None:
        """Update player expected goals statistics."""
        stats = self._ensure_player_xg(player_id)

        stats.xg_for += xg
        if is_shot:
            stats.shots_for += 1
        if is_goal:
            stats.goals_for += 1

    def _update_zone_metrics(
        self,
        player_id: int,
        zone: str,
        is_shot: bool,
        is_goal: bool,
        xg: float,
    ) -> None:
        """Update zone-specific metrics for a player."""
        if player_id not in self.player_zone_metrics:
            self.player_zone_metrics[player_id] = {}

        if zone not in self.player_zone_metrics[player_id]:
            self.player_zone_metrics[player_id][zone] = ZoneMetrics(zone_name=zone)

        metrics = self.player_zone_metrics[player_id][zone]
        if is_shot:
            metrics.shots += 1
        if is_goal:
            metrics.goals += 1
        metrics.expected_goals += xg

        # Update shooting percentage
        if metrics.shots > 0:
            metrics.shooting_percentage = metrics.goals / metrics.shots

    def get_player_corsi(self, player_id: int) -> CorsiStats | None:
        """Get Corsi stats for a player."""
        return self.player_corsi.get(player_id)

    def get_team_corsi(self, team_id: int) -> CorsiStats | None:
        """Get Corsi stats for a team."""
        return self.team_corsi.get(team_id)

    def get_player_xg(self, player_id: int) -> ExpectedGoalsStats | None:
        """Get xG stats for a player."""
        return self.player_xg.get(player_id)

    def get_team_xg(self, team_id: int) -> ExpectedGoalsStats | None:
        """Get xG stats for a team."""
        return self.team_xg.get(team_id)

    def get_player_zone_metrics(self, player_id: int) -> dict[str, ZoneMetrics]:
        """Get zone metrics for a player."""
        return self.player_zone_metrics.get(player_id, {})

    def calculate_player_summary(self, player_id: int) -> dict[str, Any]:
        """
        Calculate comprehensive summary stats for a player.

        Args:
            player_id: Player ID

        Returns:
            Dictionary with all calculated metrics
        """
        corsi = self.player_corsi.get(player_id)
        xg_stats = self.player_xg.get(player_id)
        zone_metrics = self.player_zone_metrics.get(player_id, {})

        summary = {
            "player_id": player_id,
            "corsi": None,
            "xg": None,
            "zones": {},
        }

        if corsi:
            summary["corsi"] = {
                "cf": corsi.corsi_for,
                "ca": corsi.corsi_against,
                "cf_pct": corsi.corsi_percentage,
                "ff": corsi.fenwick_for,
                "fa": corsi.fenwick_against,
                "ff_pct": corsi.fenwick_percentage,
                "shooting_pct": corsi.shooting_percentage,
                "pdo": corsi.pdo,
            }

        if xg_stats:
            summary["xg"] = {
                "xgf": xg_stats.xg_for,
                "xga": xg_stats.xg_against,
                "xg_pct": xg_stats.xg_percentage,
                "goals_above_expected": xg_stats.goals_above_expected,
                "xg_differential": xg_stats.xg_differential,
            }

        for zone_name, metrics in zone_metrics.items():
            summary["zones"][zone_name] = {
                "shots": metrics.shots,
                "goals": metrics.goals,
                "xg": metrics.expected_goals,
                "shooting_pct": metrics.shooting_percentage,
                "goals_above_expected": metrics.goals_above_expected,
            }

        return summary

    def calculate_team_summary(self, team_id: int) -> dict[str, Any]:
        """
        Calculate comprehensive summary stats for a team.

        Args:
            team_id: Team ID

        Returns:
            Dictionary with all calculated metrics
        """
        corsi = self.team_corsi.get(team_id)
        xg_stats = self.team_xg.get(team_id)

        summary = {
            "team_id": team_id,
            "corsi": None,
            "xg": None,
        }

        if corsi:
            summary["corsi"] = {
                "cf": corsi.corsi_for,
                "ca": corsi.corsi_against,
                "cf_pct": corsi.corsi_percentage,
                "ff": corsi.fenwick_for,
                "fa": corsi.fenwick_against,
                "ff_pct": corsi.fenwick_percentage,
                "gf": corsi.goals_for,
                "ga": corsi.goals_against,
                "shooting_pct": corsi.shooting_percentage,
                "save_pct": corsi.save_percentage,
                "pdo": corsi.pdo,
            }

        if xg_stats:
            summary["xg"] = {
                "xgf": xg_stats.xg_for,
                "xga": xg_stats.xg_against,
                "xg_pct": xg_stats.xg_percentage,
                "gf": xg_stats.goals_for,
                "ga": xg_stats.goals_against,
                "goals_above_expected": xg_stats.goals_above_expected,
                "goals_saved_above_expected": xg_stats.goals_saved_above_expected,
                "xg_differential": xg_stats.xg_differential,
            }

        return summary

    def reset(self) -> None:
        """Reset all accumulated statistics."""
        self.player_corsi.clear()
        self.team_corsi.clear()
        self.player_xg.clear()
        self.team_xg.clear()
        self.player_zone_metrics.clear()
