"""
Player Shot Location Pipeline

Combines zone-based shot analysis with season/game segmentation.
Produces player shot location profiles for simulation and heat map generation.

Output structure:
- Player × Zone × Season Phase × Game Phase matrix
- Suitable for simulation engine and visualization

Reference: Uses zone definitions from config/zones.yaml
           Uses segment definitions from season_segment_pipeline.py
"""

import csv
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from ..database.db import Database, get_database
from .zone_analysis import ZoneAnalyzer, ZoneStats
from .season_segment_pipeline import (
    SeasonPhase,
    GamePhase,
    SeasonSegmentPipeline,
    GAME_PHASE_RANGES,
)


@dataclass
class ZoneSegmentStats:
    """Shot statistics for a specific zone within a segment."""

    zone_name: str = ""
    shots: int = 0
    goals: int = 0
    expected_goals: float = 0.0

    # Shot types
    wrist_shots: int = 0
    slap_shots: int = 0
    snap_shots: int = 0
    backhand_shots: int = 0
    tip_shots: int = 0
    wrap_around_shots: int = 0
    other_shots: int = 0

    @property
    def shooting_percentage(self) -> float:
        """Calculate shooting percentage."""
        return (self.goals / self.shots * 100) if self.shots > 0 else 0.0

    @property
    def shot_distribution(self) -> dict[str, float]:
        """Get shot type distribution as percentages."""
        if self.shots == 0:
            return {}
        return {
            "wrist": self.wrist_shots / self.shots,
            "slap": self.slap_shots / self.shots,
            "snap": self.snap_shots / self.shots,
            "backhand": self.backhand_shots / self.shots,
            "tip": self.tip_shots / self.shots,
            "wrap_around": self.wrap_around_shots / self.shots,
            "other": self.other_shots / self.shots,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with computed fields."""
        return {
            "zone_name": self.zone_name,
            "shots": self.shots,
            "goals": self.goals,
            "expected_goals": round(self.expected_goals, 3),
            "shooting_percentage": round(self.shooting_percentage, 2),
            "shot_types": {
                "wrist": self.wrist_shots,
                "slap": self.slap_shots,
                "snap": self.snap_shots,
                "backhand": self.backhand_shots,
                "tip": self.tip_shots,
                "wrap_around": self.wrap_around_shots,
                "other": self.other_shots,
            },
        }


@dataclass
class SegmentLocationStats:
    """Shot location statistics for a specific segment (season phase × game phase)."""

    season_phase: str = ""
    game_phase: str = ""

    # Total stats for this segment
    total_shots: int = 0
    total_goals: int = 0
    total_expected_goals: float = 0.0

    # Zone breakdown
    zone_stats: dict[str, ZoneSegmentStats] = field(default_factory=dict)

    # Aggregated danger level stats
    high_danger_shots: int = 0
    high_danger_goals: int = 0
    medium_danger_shots: int = 0
    medium_danger_goals: int = 0
    low_danger_shots: int = 0
    low_danger_goals: int = 0

    @property
    def shooting_percentage(self) -> float:
        """Overall shooting percentage for this segment."""
        return (self.total_goals / self.total_shots * 100) if self.total_shots > 0 else 0.0

    @property
    def high_danger_shot_rate(self) -> float:
        """Proportion of shots from high danger areas."""
        return self.high_danger_shots / self.total_shots if self.total_shots > 0 else 0.0

    def get_zone_distribution(self) -> dict[str, float]:
        """Get normalized shot distribution across zones."""
        if self.total_shots == 0:
            return {}
        return {
            zone: stats.shots / self.total_shots
            for zone, stats in self.zone_stats.items()
            if stats.shots > 0
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "season_phase": self.season_phase,
            "game_phase": self.game_phase,
            "total_shots": self.total_shots,
            "total_goals": self.total_goals,
            "total_expected_goals": round(self.total_expected_goals, 3),
            "shooting_percentage": round(self.shooting_percentage, 2),
            "high_danger": {
                "shots": self.high_danger_shots,
                "goals": self.high_danger_goals,
                "shot_rate": round(self.high_danger_shot_rate, 3),
            },
            "medium_danger": {
                "shots": self.medium_danger_shots,
                "goals": self.medium_danger_goals,
            },
            "low_danger": {
                "shots": self.low_danger_shots,
                "goals": self.low_danger_goals,
            },
            "zones": {
                zone: stats.to_dict()
                for zone, stats in self.zone_stats.items()
                if stats.shots > 0
            },
            "zone_distribution": self.get_zone_distribution(),
        }


@dataclass
class PlayerShotLocationProfile:
    """
    Complete shot location profile for a player.

    Contains shot data broken down by:
    - Zone (slot, left_circle, point, etc.)
    - Season phase (early, mid, late, playoffs)
    - Game phase (early, mid, late game)
    """

    player_id: int
    player_name: str = ""
    season: int = 0

    # Overall totals
    total_shots: int = 0
    total_goals: int = 0
    total_expected_goals: float = 0.0
    games_played: int = 0

    # Segment-specific stats: (season_phase, game_phase) -> SegmentLocationStats
    segment_stats: dict[tuple[str, str], SegmentLocationStats] = field(default_factory=dict)

    # Overall zone stats (aggregated across all segments)
    overall_zone_stats: dict[str, ZoneSegmentStats] = field(default_factory=dict)

    # Preferred zones (top zones by shot volume)
    preferred_zones: list[str] = field(default_factory=list)

    # Computed metrics
    shooting_percentage: float = 0.0
    goals_above_expected: float = 0.0
    high_danger_shot_rate: float = 0.0

    def compute_metrics(self) -> None:
        """Compute derived metrics from raw data."""
        self.shooting_percentage = (
            (self.total_goals / self.total_shots * 100) if self.total_shots > 0 else 0.0
        )
        self.goals_above_expected = self.total_goals - self.total_expected_goals

        # High danger shot rate
        high_danger_shots = sum(
            seg.high_danger_shots for seg in self.segment_stats.values()
        )
        self.high_danger_shot_rate = (
            high_danger_shots / self.total_shots if self.total_shots > 0 else 0.0
        )

        # Determine preferred zones (top 3 by volume)
        zone_shots = {}
        for zone, stats in self.overall_zone_stats.items():
            zone_shots[zone] = stats.shots

        sorted_zones = sorted(zone_shots.items(), key=lambda x: x[1], reverse=True)
        self.preferred_zones = [zone for zone, _ in sorted_zones[:3]]

    def get_heat_map_data(self) -> dict[str, float]:
        """Get normalized shot distribution for heat map generation."""
        if self.total_shots == 0:
            return {}
        return {
            zone: stats.shots / self.total_shots
            for zone, stats in self.overall_zone_stats.items()
            if stats.shots > 0
        }

    def get_segment_heat_map(
        self,
        season_phase: str,
        game_phase: str
    ) -> dict[str, float]:
        """Get heat map data for a specific segment."""
        key = (season_phase, game_phase)
        if key not in self.segment_stats:
            return {}

        segment = self.segment_stats[key]
        return segment.get_zone_distribution()

    def get_simulation_data(self) -> dict[str, Any]:
        """
        Get data formatted for simulation engine.

        Returns zone probabilities and shooting percentages
        for each segment combination.
        """
        sim_data = {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "overall": {
                "zone_probabilities": self.get_heat_map_data(),
                "shooting_percentage": self.shooting_percentage,
                "preferred_zones": self.preferred_zones,
            },
            "segments": {},
        }

        for (season_phase, game_phase), segment in self.segment_stats.items():
            seg_key = f"{season_phase}_{game_phase}"
            sim_data["segments"][seg_key] = {
                "zone_probabilities": segment.get_zone_distribution(),
                "shooting_percentage": segment.shooting_percentage,
                "high_danger_shot_rate": segment.high_danger_shot_rate,
                "sample_size": segment.total_shots,
            }

        return sim_data

    def to_dict(self) -> dict[str, Any]:
        """Convert full profile to dictionary."""
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "season": self.season,
            "totals": {
                "shots": self.total_shots,
                "goals": self.total_goals,
                "expected_goals": round(self.total_expected_goals, 3),
                "games_played": self.games_played,
                "shooting_percentage": round(self.shooting_percentage, 2),
                "goals_above_expected": round(self.goals_above_expected, 3),
                "high_danger_shot_rate": round(self.high_danger_shot_rate, 3),
            },
            "preferred_zones": self.preferred_zones,
            "overall_zones": {
                zone: stats.to_dict()
                for zone, stats in self.overall_zone_stats.items()
                if stats.shots > 0
            },
            "segments": {
                f"{sp}_{gp}": seg.to_dict()
                for (sp, gp), seg in self.segment_stats.items()
                if seg.total_shots > 0
            },
        }


# Danger level zone mappings
HIGH_DANGER_ZONES = {"slot", "inner_slot", "crease"}
MEDIUM_DANGER_ZONES = {"left_circle", "right_circle", "high_slot"}
LOW_DANGER_ZONES = {"left_wing", "right_wing", "left_point", "right_point", "behind_net"}


class PlayerShotLocationPipeline:
    """
    Pipeline for generating player shot location profiles.

    Combines zone analysis with season/game segmentation to produce
    comprehensive shot location data for simulation and visualization.
    """

    def __init__(self, db: Optional[Database] = None, zones_config: Optional[Path] = None):
        """
        Initialize the pipeline.

        Args:
            db: Database connection
            zones_config: Path to zones configuration file
        """
        self.db = db or get_database()
        self.zone_analyzer = ZoneAnalyzer(zones_config)
        self.segment_pipeline = SeasonSegmentPipeline(self.db)

        # Cache for processed profiles
        self._profile_cache: dict[tuple[int, int], PlayerShotLocationProfile] = {}

    def _get_shot_type_field(self, shot_type: str | None) -> str:
        """Map shot type string to field name."""
        if not shot_type:
            return "other_shots"

        shot_type_lower = shot_type.lower()
        mapping = {
            "wrist": "wrist_shots",
            "slap": "slap_shots",
            "snap": "snap_shots",
            "backhand": "backhand_shots",
            "tip-in": "tip_shots",
            "tip": "tip_shots",
            "wrap-around": "wrap_around_shots",
            "wrap": "wrap_around_shots",
            "deflected": "tip_shots",
        }
        return mapping.get(shot_type_lower, "other_shots")

    def _get_danger_level(self, zone: str) -> str:
        """Get danger level for a zone."""
        if zone in HIGH_DANGER_ZONES:
            return "high"
        elif zone in MEDIUM_DANGER_ZONES:
            return "medium"
        elif zone in LOW_DANGER_ZONES:
            return "low"
        return "other"

    def build_player_profile(
        self,
        player_id: int,
        season: int,
    ) -> PlayerShotLocationProfile:
        """
        Build complete shot location profile for a player.

        Args:
            player_id: NHL player ID
            season: Season identifier (e.g., 20242025)

        Returns:
            PlayerShotLocationProfile with all shot location data
        """
        cache_key = (player_id, season)
        if cache_key in self._profile_cache:
            return self._profile_cache[cache_key]

        # Get player info
        player = self.db.get_player(player_id)
        player_name = player["full_name"] if player else f"Player {player_id}"

        # Initialize profile
        profile = PlayerShotLocationProfile(
            player_id=player_id,
            player_name=player_name,
            season=season,
        )

        # Build season phase mapping
        phase_mapping = self.segment_pipeline.build_season_phase_mapping(season)

        # Initialize all segment combinations
        for season_phase in SeasonPhase:
            for game_phase in GamePhase:
                key = (season_phase.value, game_phase.value)
                profile.segment_stats[key] = SegmentLocationStats(
                    season_phase=season_phase.value,
                    game_phase=game_phase.value,
                )

        # Query shots for this player
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    game_id, period, time_in_period,
                    x_coord, y_coord, distance,
                    shot_type, is_goal, strength
                FROM shots
                WHERE player_id = ? AND season = ?
                """,
                (player_id, season),
            )
            shots = cur.fetchall()

        # Process each shot
        for shot in shots:
            game_id = shot["game_id"]

            # Determine season phase
            season_phase = phase_mapping.get_phase(game_id)
            if not season_phase:
                continue

            # Determine game phase
            game_phase = self.segment_pipeline.get_game_phase(
                shot["period"],
                shot["time_in_period"] or "00:00"
            )
            if not game_phase:
                continue

            # Identify zone
            zone = self.zone_analyzer.identify_zone(
                shot["x_coord"],
                shot["y_coord"]
            )
            if not zone:
                zone = "other"

            # Get zone expected shooting percentage
            zone_def = self.zone_analyzer.zones.get(zone)
            expected_shooting_pct = zone_def.expected_shooting_pct if zone_def else 0.05

            is_goal = shot["is_goal"]
            shot_type = shot["shot_type"]
            shot_type_field = self._get_shot_type_field(shot_type)
            danger_level = self._get_danger_level(zone)

            # Update segment stats
            seg_key = (season_phase.value, game_phase.value)
            segment = profile.segment_stats[seg_key]

            # Initialize zone stats if needed
            if zone not in segment.zone_stats:
                segment.zone_stats[zone] = ZoneSegmentStats(zone_name=zone)

            zone_stats = segment.zone_stats[zone]

            # Update zone stats
            zone_stats.shots += 1
            zone_stats.expected_goals += expected_shooting_pct
            if is_goal:
                zone_stats.goals += 1

            # Update shot type
            current_val = getattr(zone_stats, shot_type_field, 0)
            setattr(zone_stats, shot_type_field, current_val + 1)

            # Update segment totals
            segment.total_shots += 1
            segment.total_expected_goals += expected_shooting_pct
            if is_goal:
                segment.total_goals += 1

            # Update danger level stats
            if danger_level == "high":
                segment.high_danger_shots += 1
                if is_goal:
                    segment.high_danger_goals += 1
            elif danger_level == "medium":
                segment.medium_danger_shots += 1
                if is_goal:
                    segment.medium_danger_goals += 1
            elif danger_level == "low":
                segment.low_danger_shots += 1
                if is_goal:
                    segment.low_danger_goals += 1

            # Update overall zone stats
            if zone not in profile.overall_zone_stats:
                profile.overall_zone_stats[zone] = ZoneSegmentStats(zone_name=zone)

            overall_zone = profile.overall_zone_stats[zone]
            overall_zone.shots += 1
            overall_zone.expected_goals += expected_shooting_pct
            if is_goal:
                overall_zone.goals += 1

            current_overall = getattr(overall_zone, shot_type_field, 0)
            setattr(overall_zone, shot_type_field, current_overall + 1)

            # Update profile totals
            profile.total_shots += 1
            profile.total_expected_goals += expected_shooting_pct
            if is_goal:
                profile.total_goals += 1

        # Count games played
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT pgs.game_id) as games
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id = ? AND g.season = ?
                """,
                (player_id, season),
            )
            row = cur.fetchone()
            profile.games_played = row["games"] if row else 0

        # Compute derived metrics
        profile.compute_metrics()

        # Cache the profile
        self._profile_cache[cache_key] = profile

        return profile

    def build_all_player_profiles(
        self,
        season: int,
        player_ids: Optional[list[int]] = None,
        min_shots: int = 10,
    ) -> dict[int, PlayerShotLocationProfile]:
        """
        Build shot location profiles for all players (or specified subset).

        Args:
            season: Season identifier
            player_ids: Optional list of player IDs to process
            min_shots: Minimum shots required to include player

        Returns:
            Dictionary mapping player_id to their profile
        """
        if player_ids is None:
            # Get players with shots this season
            with self.db.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT player_id
                    FROM shots
                    WHERE season = ?
                    """,
                    (season,),
                )
                player_ids = [row["player_id"] for row in cur.fetchall()]

        profiles: dict[int, PlayerShotLocationProfile] = {}

        for i, player_id in enumerate(player_ids):
            if (i + 1) % 100 == 0:
                logger.info(f"Processing player {i + 1}/{len(player_ids)}")

            profile = self.build_player_profile(player_id, season)

            # Only include if meets minimum shot threshold
            if profile.total_shots >= min_shots:
                profiles[player_id] = profile

        logger.info(f"Built profiles for {len(profiles)} players with {min_shots}+ shots")
        return profiles

    def export_to_json(
        self,
        profiles: dict[int, PlayerShotLocationProfile],
        output_path: Path,
        include_simulation_format: bool = True,
    ) -> None:
        """
        Export profiles to JSON.

        Args:
            profiles: Dictionary of player profiles
            output_path: Output file path
            include_simulation_format: Include simulation-ready data
        """
        export_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_players": len(profiles),
                "zones": list(self.zone_analyzer.zones.keys()),
                "season_phases": [p.value for p in SeasonPhase],
                "game_phases": [p.value for p in GamePhase],
                "danger_zone_mapping": {
                    "high": list(HIGH_DANGER_ZONES),
                    "medium": list(MEDIUM_DANGER_ZONES),
                    "low": list(LOW_DANGER_ZONES),
                },
            },
            "players": {},
        }

        for player_id, profile in profiles.items():
            player_data = profile.to_dict()

            if include_simulation_format:
                player_data["simulation"] = profile.get_simulation_data()

            export_data["players"][str(player_id)] = player_data

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Exported JSON to {output_path}")

    def export_to_csv(
        self,
        profiles: dict[int, PlayerShotLocationProfile],
        output_path: Path,
    ) -> None:
        """
        Export profiles to CSV (flat format with one row per player-segment-zone).

        Args:
            profiles: Dictionary of player profiles
            output_path: Output file path
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "player_id", "player_name", "season",
            "season_phase", "game_phase", "zone",
            "shots", "goals", "expected_goals", "shooting_percentage",
            "wrist_shots", "slap_shots", "snap_shots", "backhand_shots",
            "tip_shots", "wrap_around_shots", "other_shots",
            "danger_level",
        ]

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for player_id, profile in profiles.items():
                for (season_phase, game_phase), segment in profile.segment_stats.items():
                    for zone, zone_stats in segment.zone_stats.items():
                        if zone_stats.shots == 0:
                            continue

                        writer.writerow({
                            "player_id": player_id,
                            "player_name": profile.player_name,
                            "season": profile.season,
                            "season_phase": season_phase,
                            "game_phase": game_phase,
                            "zone": zone,
                            "shots": zone_stats.shots,
                            "goals": zone_stats.goals,
                            "expected_goals": round(zone_stats.expected_goals, 3),
                            "shooting_percentage": round(zone_stats.shooting_percentage, 2),
                            "wrist_shots": zone_stats.wrist_shots,
                            "slap_shots": zone_stats.slap_shots,
                            "snap_shots": zone_stats.snap_shots,
                            "backhand_shots": zone_stats.backhand_shots,
                            "tip_shots": zone_stats.tip_shots,
                            "wrap_around_shots": zone_stats.wrap_around_shots,
                            "other_shots": zone_stats.other_shots,
                            "danger_level": self._get_danger_level(zone),
                        })

        logger.info(f"Exported CSV to {output_path}")

    def export_heat_map_data(
        self,
        profiles: dict[int, PlayerShotLocationProfile],
        output_path: Path,
    ) -> None:
        """
        Export heat map data optimized for visualization.

        Args:
            profiles: Dictionary of player profiles
            output_path: Output file path
        """
        heat_map_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "zones": {
                    name: {
                        "x_min": zone_def.x_min,
                        "x_max": zone_def.x_max,
                        "y_min": zone_def.y_min,
                        "y_max": zone_def.y_max,
                        "danger_level": zone_def.danger_level,
                    }
                    for name, zone_def in self.zone_analyzer.zones.items()
                },
            },
            "players": {},
        }

        for player_id, profile in profiles.items():
            player_heat_map = {
                "player_id": player_id,
                "player_name": profile.player_name,
                "overall": profile.get_heat_map_data(),
                "segments": {},
            }

            for season_phase in SeasonPhase:
                for game_phase in GamePhase:
                    seg_key = f"{season_phase.value}_{game_phase.value}"
                    player_heat_map["segments"][seg_key] = profile.get_segment_heat_map(
                        season_phase.value, game_phase.value
                    )

            heat_map_data["players"][str(player_id)] = player_heat_map

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(heat_map_data, f, indent=2)

        logger.info(f"Exported heat map data to {output_path}")

    def export_simulation_data(
        self,
        profiles: dict[int, PlayerShotLocationProfile],
        output_path: Path,
    ) -> None:
        """
        Export data optimized for simulation engine.

        Args:
            profiles: Dictionary of player profiles
            output_path: Output file path
        """
        sim_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "description": "Player shot location probabilities for game simulation",
                "zones": list(self.zone_analyzer.zones.keys()),
                "expected_shooting_pct_by_zone": {
                    name: zone_def.expected_shooting_pct
                    for name, zone_def in self.zone_analyzer.zones.items()
                },
            },
            "players": {},
        }

        for player_id, profile in profiles.items():
            sim_data["players"][str(player_id)] = profile.get_simulation_data()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(sim_data, f, indent=2)

        logger.info(f"Exported simulation data to {output_path}")

    def clear_cache(self) -> None:
        """Clear the profile cache."""
        self._profile_cache.clear()


def run_pipeline(
    season: int,
    output_dir: Optional[Path] = None,
    min_shots: int = 10,
    player_ids: Optional[list[int]] = None,
    db: Optional[Database] = None,
) -> dict[int, PlayerShotLocationProfile]:
    """
    Run the full player shot location pipeline.

    Args:
        season: Season identifier (e.g., 20242025)
        output_dir: Directory for output files (default: data/exports/)
        min_shots: Minimum shots required to include player
        player_ids: Optional specific players to process
        db: Database instance

    Returns:
        Dictionary of player profiles
    """
    if output_dir is None:
        output_dir = Path("data/exports")

    pipeline = PlayerShotLocationPipeline(db=db)

    logger.info(f"Starting player shot location pipeline for season {season}")

    # Build all profiles
    profiles = pipeline.build_all_player_profiles(
        season=season,
        player_ids=player_ids,
        min_shots=min_shots,
    )

    # Export all formats
    pipeline.export_to_json(
        profiles,
        output_dir / f"player_shot_locations_{season}.json",
    )

    pipeline.export_to_csv(
        profiles,
        output_dir / f"player_shot_locations_{season}.csv",
    )

    pipeline.export_heat_map_data(
        profiles,
        output_dir / f"player_shot_heatmaps_{season}.json",
    )

    pipeline.export_simulation_data(
        profiles,
        output_dir / f"player_shot_simulation_{season}.json",
    )

    logger.info("Pipeline complete!")
    return profiles
