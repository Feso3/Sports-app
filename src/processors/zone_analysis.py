"""
Zone Analysis Processor

Processes shot data into zone-based aggregations for heat maps and analysis.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from loguru import logger


@dataclass
class ZoneDefinition:
    """Definition of an ice zone."""

    name: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    danger_level: str
    expected_shooting_pct: float

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is within this zone."""
        return (
            self.x_min <= x <= self.x_max
            and self.y_min <= y <= self.y_max
        )


@dataclass
class ZoneStats:
    """Statistics for a single zone."""

    shots: int = 0
    goals: int = 0
    expected_goals: float = 0.0
    shooting_percentage: float = 0.0

    # Shot types
    wrist_shots: int = 0
    slap_shots: int = 0
    snap_shots: int = 0
    backhand_shots: int = 0
    other_shots: int = 0

    def update_shooting_percentage(self) -> None:
        """Recalculate shooting percentage."""
        self.shooting_percentage = self.goals / self.shots if self.shots > 0 else 0.0


@dataclass
class PlayerZoneProfile:
    """Zone-based profile for a player."""

    player_id: int
    player_name: str
    zone_stats: dict[str, ZoneStats] = field(default_factory=dict)
    total_shots: int = 0
    total_goals: int = 0
    total_xg: float = 0.0

    def get_heat_map(self) -> dict[str, float]:
        """Generate normalized heat map of shot distribution."""
        if self.total_shots == 0:
            return {}

        return {
            zone: stats.shots / self.total_shots
            for zone, stats in self.zone_stats.items()
        }

    def get_shooting_pct_map(self) -> dict[str, float]:
        """Generate map of shooting percentage by zone."""
        return {
            zone: stats.shooting_percentage
            for zone, stats in self.zone_stats.items()
            if stats.shots > 0
        }


@dataclass
class TeamZoneProfile:
    """Zone-based profile for a team."""

    team_id: int
    team_abbrev: str
    offensive_zone_stats: dict[str, ZoneStats] = field(default_factory=dict)
    defensive_zone_stats: dict[str, ZoneStats] = field(default_factory=dict)
    total_shots_for: int = 0
    total_shots_against: int = 0
    total_goals_for: int = 0
    total_goals_against: int = 0

    def get_offensive_heat_map(self) -> dict[str, float]:
        """Generate normalized offensive heat map."""
        if self.total_shots_for == 0:
            return {}

        return {
            zone: stats.shots / self.total_shots_for
            for zone, stats in self.offensive_zone_stats.items()
        }

    def get_defensive_heat_map(self) -> dict[str, float]:
        """Generate normalized defensive heat map."""
        if self.total_shots_against == 0:
            return {}

        return {
            zone: stats.shots / self.total_shots_against
            for zone, stats in self.defensive_zone_stats.items()
        }


class ZoneAnalyzer:
    """
    Analyzer for zone-based shot data.

    Processes shot coordinates into zone aggregations and generates
    heat maps for players and teams.
    """

    def __init__(self, zones_config_path: str | Path | None = None):
        """
        Initialize the zone analyzer.

        Args:
            zones_config_path: Path to zones configuration file.
        """
        self.config = self._load_config(zones_config_path)
        self.zones = self._build_zone_definitions()

        # Storage for profiles
        self.player_profiles: dict[int, PlayerZoneProfile] = {}
        self.team_profiles: dict[int, TeamZoneProfile] = {}

    def _load_config(self, config_path: str | Path | None) -> dict[str, Any]:
        """Load zone configuration from YAML file."""
        if config_path is None:
            config_path = Path("config/zones.yaml")
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            logger.warning(f"Zones config not found at {config_path}, using defaults")
            return self._default_zones_config()

        with open(config_path) as f:
            return yaml.safe_load(f)

    def _default_zones_config(self) -> dict[str, Any]:
        """Return default zone configuration."""
        return {
            "zones": {
                "slot": {
                    "x_min": 69, "x_max": 89, "y_min": -22, "y_max": 22,
                    "danger_level": "high", "expected_shooting_pct": 0.15
                },
                "inner_slot": {
                    "x_min": 79, "x_max": 89, "y_min": -9, "y_max": 9,
                    "danger_level": "extreme", "expected_shooting_pct": 0.25
                },
                "left_circle": {
                    "x_min": 54, "x_max": 74, "y_min": -32, "y_max": -12,
                    "danger_level": "medium", "expected_shooting_pct": 0.08
                },
                "right_circle": {
                    "x_min": 54, "x_max": 74, "y_min": 12, "y_max": 32,
                    "danger_level": "medium", "expected_shooting_pct": 0.08
                },
                "high_slot": {
                    "x_min": 25, "x_max": 69, "y_min": -15, "y_max": 15,
                    "danger_level": "medium-low", "expected_shooting_pct": 0.05
                },
                "left_point": {
                    "x_min": 25, "x_max": 54, "y_min": -42.5, "y_max": -15,
                    "danger_level": "low", "expected_shooting_pct": 0.03
                },
                "right_point": {
                    "x_min": 25, "x_max": 54, "y_min": 15, "y_max": 42.5,
                    "danger_level": "low", "expected_shooting_pct": 0.03
                },
            }
        }

    def _build_zone_definitions(self) -> dict[str, ZoneDefinition]:
        """Build zone definitions from configuration."""
        zones = {}
        for zone_name, zone_config in self.config.get("zones", {}).items():
            zones[zone_name] = ZoneDefinition(
                name=zone_name,
                x_min=zone_config.get("x_min", 0),
                x_max=zone_config.get("x_max", 100),
                y_min=zone_config.get("y_min", -42.5),
                y_max=zone_config.get("y_max", 42.5),
                danger_level=zone_config.get("danger_level", "low"),
                expected_shooting_pct=zone_config.get("expected_shooting_pct", 0.05),
            )
        return zones

    def identify_zone(self, x: float | None, y: float | None) -> str | None:
        """
        Identify which zone a coordinate falls into.

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            Zone name or None if outside all zones
        """
        if x is None or y is None:
            return None

        # Normalize coordinates to offensive zone (positive x)
        x = abs(x)

        # Check zones in order of specificity (inner_slot before slot)
        zone_priority = [
            "inner_slot", "crease", "slot", "left_circle", "right_circle",
            "left_wing", "right_wing", "high_slot", "left_point", "right_point",
            "behind_net"
        ]

        for zone_name in zone_priority:
            if zone_name in self.zones:
                if self.zones[zone_name].contains_point(x, y):
                    return zone_name

        return "other"

    def process_shot(
        self,
        x: float | None,
        y: float | None,
        is_goal: bool,
        shot_type: str | None,
        player_id: int,
        player_name: str,
        team_id: int,
        team_abbrev: str,
        opponent_team_id: int,
    ) -> None:
        """
        Process a single shot and update profiles.

        Args:
            x: X coordinate of shot
            y: Y coordinate of shot
            is_goal: Whether the shot was a goal
            shot_type: Type of shot
            player_id: Shooter's player ID
            player_name: Shooter's name
            team_id: Shooting team ID
            team_abbrev: Shooting team abbreviation
            opponent_team_id: Opponent team ID
        """
        zone = self.identify_zone(x, y)
        if not zone:
            return

        zone_def = self.zones.get(zone)
        expected_shooting_pct = zone_def.expected_shooting_pct if zone_def else 0.05

        # Update player profile
        self._update_player_profile(
            player_id, player_name, zone, is_goal, shot_type, expected_shooting_pct
        )

        # Update team offensive profile
        self._update_team_offensive_profile(
            team_id, team_abbrev, zone, is_goal, expected_shooting_pct
        )

        # Update opponent defensive profile
        self._update_team_defensive_profile(
            opponent_team_id, zone, is_goal, expected_shooting_pct
        )

    def _update_player_profile(
        self,
        player_id: int,
        player_name: str,
        zone: str,
        is_goal: bool,
        shot_type: str | None,
        expected_shooting_pct: float,
    ) -> None:
        """Update player zone profile with shot data."""
        if player_id not in self.player_profiles:
            self.player_profiles[player_id] = PlayerZoneProfile(
                player_id=player_id,
                player_name=player_name,
            )

        profile = self.player_profiles[player_id]

        # Initialize zone stats if needed
        if zone not in profile.zone_stats:
            profile.zone_stats[zone] = ZoneStats()

        stats = profile.zone_stats[zone]
        stats.shots += 1
        stats.expected_goals += expected_shooting_pct

        if is_goal:
            stats.goals += 1
            profile.total_goals += 1

        # Track shot type
        if shot_type:
            if shot_type == "wrist":
                stats.wrist_shots += 1
            elif shot_type == "slap":
                stats.slap_shots += 1
            elif shot_type == "snap":
                stats.snap_shots += 1
            elif shot_type == "backhand":
                stats.backhand_shots += 1
            else:
                stats.other_shots += 1

        stats.update_shooting_percentage()
        profile.total_shots += 1
        profile.total_xg += expected_shooting_pct

    def _update_team_offensive_profile(
        self,
        team_id: int,
        team_abbrev: str,
        zone: str,
        is_goal: bool,
        expected_shooting_pct: float,
    ) -> None:
        """Update team offensive zone profile."""
        if team_id not in self.team_profiles:
            self.team_profiles[team_id] = TeamZoneProfile(
                team_id=team_id,
                team_abbrev=team_abbrev,
            )

        profile = self.team_profiles[team_id]

        if zone not in profile.offensive_zone_stats:
            profile.offensive_zone_stats[zone] = ZoneStats()

        stats = profile.offensive_zone_stats[zone]
        stats.shots += 1
        stats.expected_goals += expected_shooting_pct

        if is_goal:
            stats.goals += 1
            profile.total_goals_for += 1

        stats.update_shooting_percentage()
        profile.total_shots_for += 1

    def _update_team_defensive_profile(
        self,
        team_id: int,
        zone: str,
        is_goal: bool,
        expected_shooting_pct: float,
    ) -> None:
        """Update team defensive zone profile (shots against)."""
        if team_id not in self.team_profiles:
            self.team_profiles[team_id] = TeamZoneProfile(
                team_id=team_id,
                team_abbrev="UNK",  # Will be updated when team shoots
            )

        profile = self.team_profiles[team_id]

        if zone not in profile.defensive_zone_stats:
            profile.defensive_zone_stats[zone] = ZoneStats()

        stats = profile.defensive_zone_stats[zone]
        stats.shots += 1
        stats.expected_goals += expected_shooting_pct

        if is_goal:
            stats.goals += 1
            profile.total_goals_against += 1

        stats.update_shooting_percentage()
        profile.total_shots_against += 1

    def process_shots_batch(
        self,
        shots: list[dict[str, Any]],
        game_context: dict[str, Any] | None = None,
    ) -> None:
        """
        Process a batch of shots.

        Args:
            shots: List of shot dictionaries
            game_context: Optional game context with team mappings
        """
        for shot in shots:
            # Determine opponent team
            team_id = shot.get("team_id")
            if game_context and team_id:
                home_id = game_context.get("home_team_id")
                away_id = game_context.get("away_team_id")
                opponent_id = away_id if team_id == home_id else home_id
            else:
                opponent_id = 0

            self.process_shot(
                x=shot.get("x_coord"),
                y=shot.get("y_coord"),
                is_goal=shot.get("is_goal", False),
                shot_type=shot.get("shot_type"),
                player_id=shot.get("shooter_id", 0),
                player_name=shot.get("shooter_name", ""),
                team_id=team_id or 0,
                team_abbrev=shot.get("team_abbrev", ""),
                opponent_team_id=opponent_id or 0,
            )

    def get_player_profile(self, player_id: int) -> PlayerZoneProfile | None:
        """Get zone profile for a player."""
        return self.player_profiles.get(player_id)

    def get_team_profile(self, team_id: int) -> TeamZoneProfile | None:
        """Get zone profile for a team."""
        return self.team_profiles.get(team_id)

    def generate_heat_map_grid(
        self,
        player_id: int | None = None,
        team_id: int | None = None,
        grid_size: int = 40,
    ) -> np.ndarray:
        """
        Generate a 2D heat map grid for visualization.

        Args:
            player_id: Player ID (mutually exclusive with team_id)
            team_id: Team ID (mutually exclusive with player_id)
            grid_size: Size of the output grid

        Returns:
            2D numpy array representing the heat map
        """
        heat_map = np.zeros((grid_size, grid_size))

        if player_id:
            profile = self.player_profiles.get(player_id)
            if not profile:
                return heat_map
            zone_map = profile.get_heat_map()
        elif team_id:
            profile = self.team_profiles.get(team_id)
            if not profile:
                return heat_map
            zone_map = profile.get_offensive_heat_map()
        else:
            return heat_map

        # Map zone stats to grid
        for zone_name, intensity in zone_map.items():
            if zone_name not in self.zones:
                continue

            zone_def = self.zones[zone_name]

            # Convert zone coordinates to grid indices
            x_start = int((zone_def.x_min + 100) / 200 * grid_size)
            x_end = int((zone_def.x_max + 100) / 200 * grid_size)
            y_start = int((zone_def.y_min + 42.5) / 85 * grid_size)
            y_end = int((zone_def.y_max + 42.5) / 85 * grid_size)

            # Clamp to grid bounds
            x_start = max(0, min(x_start, grid_size - 1))
            x_end = max(0, min(x_end, grid_size))
            y_start = max(0, min(y_start, grid_size - 1))
            y_end = max(0, min(y_end, grid_size))

            heat_map[y_start:y_end, x_start:x_end] = intensity

        return heat_map

    def calculate_zone_mismatch(
        self,
        offensive_team_id: int,
        defensive_team_id: int,
    ) -> dict[str, float]:
        """
        Calculate zone-by-zone mismatch between teams.

        Args:
            offensive_team_id: ID of the attacking team
            defensive_team_id: ID of the defending team

        Returns:
            Dictionary mapping zone names to mismatch scores
            (positive = advantage for offensive team)
        """
        off_profile = self.team_profiles.get(offensive_team_id)
        def_profile = self.team_profiles.get(defensive_team_id)

        if not off_profile or not def_profile:
            return {}

        mismatches = {}
        off_heat_map = off_profile.get_offensive_heat_map()
        def_heat_map = def_profile.get_defensive_heat_map()

        for zone_name in self.zones:
            off_strength = off_heat_map.get(zone_name, 0.0)

            # For defense, higher value = more shots allowed = weaker defense
            def_weakness = def_heat_map.get(zone_name, 0.0)

            # Mismatch: offensive strength meets defensive weakness
            # Normalize by zone danger level
            zone_def = self.zones[zone_name]
            danger_mult = {
                "extreme": 2.0,
                "high": 1.5,
                "medium": 1.0,
                "medium-low": 0.8,
                "low": 0.5,
                "none": 0.0,
            }.get(zone_def.danger_level, 1.0)

            mismatches[zone_name] = (off_strength * def_weakness) * danger_mult

        return mismatches

    def get_league_zone_averages(self) -> dict[str, ZoneStats]:
        """
        Calculate league-average zone statistics.

        Returns:
            Dictionary mapping zone names to aggregated stats
        """
        league_stats: dict[str, ZoneStats] = {}

        for profile in self.player_profiles.values():
            for zone_name, stats in profile.zone_stats.items():
                if zone_name not in league_stats:
                    league_stats[zone_name] = ZoneStats()

                league_stats[zone_name].shots += stats.shots
                league_stats[zone_name].goals += stats.goals
                league_stats[zone_name].expected_goals += stats.expected_goals

        # Update shooting percentages
        for stats in league_stats.values():
            stats.update_shooting_percentage()

        return league_stats

    def reset(self) -> None:
        """Reset all profiles."""
        self.player_profiles.clear()
        self.team_profiles.clear()
