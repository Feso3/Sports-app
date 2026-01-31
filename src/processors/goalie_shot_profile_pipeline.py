"""
Goalie Shot Profile Pipeline

Builds comprehensive goalie profiles tracking save performance by:
- Zone (where shots come from)
- Shot type (wrist, slap, snap, etc.)
- Season phase (early, mid, late, playoffs)
- Game phase (early, mid, late game)

Produces data for simulation engine and heat map visualization.
Complements player shot location profiles for complete shot modeling.

Reference: Uses zone definitions from config/zones.yaml
           Uses segment definitions from season_segment_pipeline.py
"""

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from ..database.db import Database, get_database
from .zone_analysis import ZoneAnalyzer
from .season_segment_pipeline import (
    SeasonPhase,
    GamePhase,
    SeasonSegmentPipeline,
)


@dataclass
class GoalieZoneStats:
    """Save statistics for a specific zone."""

    zone_name: str = ""
    shots_faced: int = 0
    goals_against: int = 0
    saves: int = 0
    expected_goals_against: float = 0.0

    # Shot type breakdown
    wrist_shots: int = 0
    wrist_goals: int = 0
    slap_shots: int = 0
    slap_goals: int = 0
    snap_shots: int = 0
    snap_goals: int = 0
    backhand_shots: int = 0
    backhand_goals: int = 0
    tip_shots: int = 0
    tip_goals: int = 0
    wrap_around_shots: int = 0
    wrap_around_goals: int = 0
    other_shots: int = 0
    other_goals: int = 0

    @property
    def save_percentage(self) -> float:
        """Calculate save percentage."""
        return (self.saves / self.shots_faced * 100) if self.shots_faced > 0 else 0.0

    @property
    def goals_saved_above_expected(self) -> float:
        """Goals saved above expected (GSAE)."""
        return self.expected_goals_against - self.goals_against

    def get_shot_type_save_pct(self, shot_type: str) -> float:
        """Get save percentage for a specific shot type."""
        mapping = {
            "wrist": (self.wrist_shots, self.wrist_goals),
            "slap": (self.slap_shots, self.slap_goals),
            "snap": (self.snap_shots, self.snap_goals),
            "backhand": (self.backhand_shots, self.backhand_goals),
            "tip": (self.tip_shots, self.tip_goals),
            "wrap_around": (self.wrap_around_shots, self.wrap_around_goals),
            "other": (self.other_shots, self.other_goals),
        }
        shots, goals = mapping.get(shot_type, (0, 0))
        if shots == 0:
            return 0.0
        return ((shots - goals) / shots * 100)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with computed fields."""
        return {
            "zone_name": self.zone_name,
            "shots_faced": self.shots_faced,
            "goals_against": self.goals_against,
            "saves": self.saves,
            "save_percentage": round(self.save_percentage, 2),
            "expected_goals_against": round(self.expected_goals_against, 3),
            "goals_saved_above_expected": round(self.goals_saved_above_expected, 3),
            "shot_types": {
                "wrist": {"shots": self.wrist_shots, "goals": self.wrist_goals,
                          "sv_pct": round(self.get_shot_type_save_pct("wrist"), 2)},
                "slap": {"shots": self.slap_shots, "goals": self.slap_goals,
                         "sv_pct": round(self.get_shot_type_save_pct("slap"), 2)},
                "snap": {"shots": self.snap_shots, "goals": self.snap_goals,
                         "sv_pct": round(self.get_shot_type_save_pct("snap"), 2)},
                "backhand": {"shots": self.backhand_shots, "goals": self.backhand_goals,
                             "sv_pct": round(self.get_shot_type_save_pct("backhand"), 2)},
                "tip": {"shots": self.tip_shots, "goals": self.tip_goals,
                        "sv_pct": round(self.get_shot_type_save_pct("tip"), 2)},
                "wrap_around": {"shots": self.wrap_around_shots, "goals": self.wrap_around_goals,
                                "sv_pct": round(self.get_shot_type_save_pct("wrap_around"), 2)},
                "other": {"shots": self.other_shots, "goals": self.other_goals,
                          "sv_pct": round(self.get_shot_type_save_pct("other"), 2)},
            },
        }


@dataclass
class GoalieSegmentStats:
    """Goalie statistics for a specific segment (season phase × game phase)."""

    season_phase: str = ""
    game_phase: str = ""

    # Total stats for this segment
    shots_faced: int = 0
    goals_against: int = 0
    saves: int = 0
    expected_goals_against: float = 0.0

    # Zone breakdown
    zone_stats: dict[str, GoalieZoneStats] = field(default_factory=dict)

    # Danger level aggregates
    high_danger_shots: int = 0
    high_danger_goals: int = 0
    medium_danger_shots: int = 0
    medium_danger_goals: int = 0
    low_danger_shots: int = 0
    low_danger_goals: int = 0

    @property
    def save_percentage(self) -> float:
        """Overall save percentage for this segment."""
        return (self.saves / self.shots_faced * 100) if self.shots_faced > 0 else 0.0

    @property
    def high_danger_save_pct(self) -> float:
        """Save percentage on high danger shots."""
        if self.high_danger_shots == 0:
            return 0.0
        saves = self.high_danger_shots - self.high_danger_goals
        return (saves / self.high_danger_shots * 100)

    @property
    def medium_danger_save_pct(self) -> float:
        """Save percentage on medium danger shots."""
        if self.medium_danger_shots == 0:
            return 0.0
        saves = self.medium_danger_shots - self.medium_danger_goals
        return (saves / self.medium_danger_shots * 100)

    @property
    def low_danger_save_pct(self) -> float:
        """Save percentage on low danger shots."""
        if self.low_danger_shots == 0:
            return 0.0
        saves = self.low_danger_shots - self.low_danger_goals
        return (saves / self.low_danger_shots * 100)

    @property
    def goals_saved_above_expected(self) -> float:
        """Goals saved above expected for this segment."""
        return self.expected_goals_against - self.goals_against

    def get_zone_save_distribution(self) -> dict[str, float]:
        """Get save percentage by zone."""
        return {
            zone: stats.save_percentage
            for zone, stats in self.zone_stats.items()
            if stats.shots_faced > 0
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "season_phase": self.season_phase,
            "game_phase": self.game_phase,
            "shots_faced": self.shots_faced,
            "goals_against": self.goals_against,
            "saves": self.saves,
            "save_percentage": round(self.save_percentage, 2),
            "expected_goals_against": round(self.expected_goals_against, 3),
            "goals_saved_above_expected": round(self.goals_saved_above_expected, 3),
            "danger_levels": {
                "high": {
                    "shots": self.high_danger_shots,
                    "goals": self.high_danger_goals,
                    "sv_pct": round(self.high_danger_save_pct, 2),
                },
                "medium": {
                    "shots": self.medium_danger_shots,
                    "goals": self.medium_danger_goals,
                    "sv_pct": round(self.medium_danger_save_pct, 2),
                },
                "low": {
                    "shots": self.low_danger_shots,
                    "goals": self.low_danger_goals,
                    "sv_pct": round(self.low_danger_save_pct, 2),
                },
            },
            "zones": {
                zone: stats.to_dict()
                for zone, stats in self.zone_stats.items()
                if stats.shots_faced > 0
            },
        }


@dataclass
class GoalieShotProfile:
    """
    Complete shot profile for a goalie.

    Contains save data broken down by:
    - Zone (slot, left_circle, point, etc.)
    - Shot type (wrist, slap, snap, etc.)
    - Season phase (early, mid, late, playoffs)
    - Game phase (early, mid, late game)
    """

    goalie_id: int
    goalie_name: str = ""
    season: int = 0

    # Overall totals
    games_played: int = 0
    shots_faced: int = 0
    goals_against: int = 0
    saves: int = 0
    expected_goals_against: float = 0.0

    # Segment-specific stats: (season_phase, game_phase) -> GoalieSegmentStats
    segment_stats: dict[tuple[str, str], GoalieSegmentStats] = field(default_factory=dict)

    # Overall zone stats (aggregated across all segments)
    overall_zone_stats: dict[str, GoalieZoneStats] = field(default_factory=dict)

    # Overall shot type stats
    shot_type_stats: dict[str, dict[str, int]] = field(default_factory=dict)

    # Weak zones (lowest save % zones with sufficient sample)
    weak_zones: list[str] = field(default_factory=list)
    strong_zones: list[str] = field(default_factory=list)

    # Computed metrics
    save_percentage: float = 0.0
    goals_saved_above_expected: float = 0.0
    high_danger_save_pct: float = 0.0

    def compute_metrics(self, min_shots_for_zone: int = 10) -> None:
        """Compute derived metrics from raw data."""
        self.saves = self.shots_faced - self.goals_against
        self.save_percentage = (
            (self.saves / self.shots_faced * 100) if self.shots_faced > 0 else 0.0
        )
        self.goals_saved_above_expected = self.expected_goals_against - self.goals_against

        # High danger save percentage
        hd_shots = sum(seg.high_danger_shots for seg in self.segment_stats.values())
        hd_goals = sum(seg.high_danger_goals for seg in self.segment_stats.values())
        if hd_shots > 0:
            self.high_danger_save_pct = ((hd_shots - hd_goals) / hd_shots * 100)

        # Determine weak and strong zones (with minimum sample size)
        zone_sv_pct = []
        for zone, stats in self.overall_zone_stats.items():
            if stats.shots_faced >= min_shots_for_zone:
                zone_sv_pct.append((zone, stats.save_percentage))

        sorted_zones = sorted(zone_sv_pct, key=lambda x: x[1])

        # Weak zones = bottom 3, strong zones = top 3
        self.weak_zones = [z for z, _ in sorted_zones[:3]]
        self.strong_zones = [z for z, _ in sorted_zones[-3:]]

        # Aggregate shot type stats
        self.shot_type_stats = {
            "wrist": {"shots": 0, "goals": 0},
            "slap": {"shots": 0, "goals": 0},
            "snap": {"shots": 0, "goals": 0},
            "backhand": {"shots": 0, "goals": 0},
            "tip": {"shots": 0, "goals": 0},
            "wrap_around": {"shots": 0, "goals": 0},
            "other": {"shots": 0, "goals": 0},
        }

        for zone_stats in self.overall_zone_stats.values():
            self.shot_type_stats["wrist"]["shots"] += zone_stats.wrist_shots
            self.shot_type_stats["wrist"]["goals"] += zone_stats.wrist_goals
            self.shot_type_stats["slap"]["shots"] += zone_stats.slap_shots
            self.shot_type_stats["slap"]["goals"] += zone_stats.slap_goals
            self.shot_type_stats["snap"]["shots"] += zone_stats.snap_shots
            self.shot_type_stats["snap"]["goals"] += zone_stats.snap_goals
            self.shot_type_stats["backhand"]["shots"] += zone_stats.backhand_shots
            self.shot_type_stats["backhand"]["goals"] += zone_stats.backhand_goals
            self.shot_type_stats["tip"]["shots"] += zone_stats.tip_shots
            self.shot_type_stats["tip"]["goals"] += zone_stats.tip_goals
            self.shot_type_stats["wrap_around"]["shots"] += zone_stats.wrap_around_shots
            self.shot_type_stats["wrap_around"]["goals"] += zone_stats.wrap_around_goals
            self.shot_type_stats["other"]["shots"] += zone_stats.other_shots
            self.shot_type_stats["other"]["goals"] += zone_stats.other_goals

    def get_heat_map_data(self) -> dict[str, float]:
        """Get save percentage distribution for heat map generation."""
        return {
            zone: stats.save_percentage
            for zone, stats in self.overall_zone_stats.items()
            if stats.shots_faced > 0
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
        return segment.get_zone_save_distribution()

    def get_simulation_data(self) -> dict[str, Any]:
        """
        Get data formatted for simulation engine.

        Returns zone save percentages and shot type modifiers
        for each segment combination.
        """
        # Calculate shot type save percentages
        shot_type_sv_pct = {}
        for shot_type, stats in self.shot_type_stats.items():
            if stats["shots"] > 0:
                saves = stats["shots"] - stats["goals"]
                shot_type_sv_pct[shot_type] = round(saves / stats["shots"] * 100, 2)
            else:
                shot_type_sv_pct[shot_type] = 0.0

        sim_data = {
            "goalie_id": self.goalie_id,
            "goalie_name": self.goalie_name,
            "overall": {
                "save_percentage": round(self.save_percentage, 2),
                "high_danger_sv_pct": round(self.high_danger_save_pct, 2),
                "goals_saved_above_expected": round(self.goals_saved_above_expected, 3),
                "zone_save_pct": self.get_heat_map_data(),
                "shot_type_sv_pct": shot_type_sv_pct,
                "weak_zones": self.weak_zones,
                "strong_zones": self.strong_zones,
            },
            "segments": {},
        }

        for (season_phase, game_phase), segment in self.segment_stats.items():
            seg_key = f"{season_phase}_{game_phase}"
            sim_data["segments"][seg_key] = {
                "save_percentage": round(segment.save_percentage, 2),
                "high_danger_sv_pct": round(segment.high_danger_save_pct, 2),
                "zone_save_pct": segment.get_zone_save_distribution(),
                "sample_size": segment.shots_faced,
            }

        return sim_data

    def to_dict(self) -> dict[str, Any]:
        """Convert full profile to dictionary."""
        # Shot type save percentages
        shot_type_sv_pct = {}
        for shot_type, stats in self.shot_type_stats.items():
            if stats["shots"] > 0:
                saves = stats["shots"] - stats["goals"]
                shot_type_sv_pct[shot_type] = {
                    "shots": stats["shots"],
                    "goals": stats["goals"],
                    "sv_pct": round(saves / stats["shots"] * 100, 2),
                }

        return {
            "goalie_id": self.goalie_id,
            "goalie_name": self.goalie_name,
            "season": self.season,
            "totals": {
                "games_played": self.games_played,
                "shots_faced": self.shots_faced,
                "goals_against": self.goals_against,
                "saves": self.saves,
                "save_percentage": round(self.save_percentage, 2),
                "expected_goals_against": round(self.expected_goals_against, 3),
                "goals_saved_above_expected": round(self.goals_saved_above_expected, 3),
                "high_danger_sv_pct": round(self.high_danger_save_pct, 2),
            },
            "weak_zones": self.weak_zones,
            "strong_zones": self.strong_zones,
            "shot_type_stats": shot_type_sv_pct,
            "overall_zones": {
                zone: stats.to_dict()
                for zone, stats in self.overall_zone_stats.items()
                if stats.shots_faced > 0
            },
            "segments": {
                f"{sp}_{gp}": seg.to_dict()
                for (sp, gp), seg in self.segment_stats.items()
                if seg.shots_faced > 0
            },
        }


# Danger level zone mappings (same as player pipeline)
HIGH_DANGER_ZONES = {"slot", "inner_slot", "crease"}
MEDIUM_DANGER_ZONES = {"left_circle", "right_circle", "high_slot"}
LOW_DANGER_ZONES = {"left_wing", "right_wing", "left_point", "right_point", "behind_net"}


class GoalieShotProfilePipeline:
    """
    Pipeline for generating goalie shot profiles.

    Combines zone analysis with season/game segmentation to produce
    comprehensive save data for simulation and visualization.
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
        self._profile_cache: dict[tuple[int, int], GoalieShotProfile] = {}

    def _get_shot_type_fields(self, shot_type: str | None) -> tuple[str, str]:
        """Map shot type string to field names (shots_field, goals_field)."""
        if not shot_type:
            return ("other_shots", "other_goals")

        shot_type_lower = shot_type.lower()
        mapping = {
            "wrist": ("wrist_shots", "wrist_goals"),
            "slap": ("slap_shots", "slap_goals"),
            "snap": ("snap_shots", "snap_goals"),
            "backhand": ("backhand_shots", "backhand_goals"),
            "tip-in": ("tip_shots", "tip_goals"),
            "tip": ("tip_shots", "tip_goals"),
            "wrap-around": ("wrap_around_shots", "wrap_around_goals"),
            "wrap": ("wrap_around_shots", "wrap_around_goals"),
            "deflected": ("tip_shots", "tip_goals"),
        }
        return mapping.get(shot_type_lower, ("other_shots", "other_goals"))

    def _get_danger_level(self, zone: str) -> str:
        """Get danger level for a zone."""
        if zone in HIGH_DANGER_ZONES:
            return "high"
        elif zone in MEDIUM_DANGER_ZONES:
            return "medium"
        elif zone in LOW_DANGER_ZONES:
            return "low"
        return "other"

    def build_goalie_profile(
        self,
        goalie_id: int,
        season: int,
    ) -> GoalieShotProfile:
        """
        Build complete shot profile for a goalie.

        Args:
            goalie_id: NHL goalie ID
            season: Season identifier (e.g., 20242025)

        Returns:
            GoalieShotProfile with all save data
        """
        cache_key = (goalie_id, season)
        if cache_key in self._profile_cache:
            return self._profile_cache[cache_key]

        # Get goalie info
        goalie = self.db.get_player(goalie_id)
        goalie_name = goalie["full_name"] if goalie else f"Goalie {goalie_id}"

        # Initialize profile
        profile = GoalieShotProfile(
            goalie_id=goalie_id,
            goalie_name=goalie_name,
            season=season,
        )

        # Build season phase mapping
        phase_mapping = self.segment_pipeline.build_season_phase_mapping(season)

        # Initialize all segment combinations
        for season_phase in SeasonPhase:
            for game_phase in GamePhase:
                key = (season_phase.value, game_phase.value)
                profile.segment_stats[key] = GoalieSegmentStats(
                    season_phase=season_phase.value,
                    game_phase=game_phase.value,
                )

        # Query shots faced by this goalie
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    game_id, period, time_in_period,
                    x_coord, y_coord, distance,
                    shot_type, is_goal, strength,
                    player_id
                FROM shots
                WHERE goalie_id = ? AND season = ?
                """,
                (goalie_id, season),
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

            # Get zone expected shooting percentage (this becomes expected goals against)
            zone_def = self.zone_analyzer.zones.get(zone)
            expected_shooting_pct = zone_def.expected_shooting_pct if zone_def else 0.05

            is_goal = shot["is_goal"]
            shot_type = shot["shot_type"]
            shots_field, goals_field = self._get_shot_type_fields(shot_type)
            danger_level = self._get_danger_level(zone)

            # Update segment stats
            seg_key = (season_phase.value, game_phase.value)
            segment = profile.segment_stats[seg_key]

            # Initialize zone stats if needed
            if zone not in segment.zone_stats:
                segment.zone_stats[zone] = GoalieZoneStats(zone_name=zone)

            zone_stats = segment.zone_stats[zone]

            # Update zone stats
            zone_stats.shots_faced += 1
            zone_stats.expected_goals_against += expected_shooting_pct
            if is_goal:
                zone_stats.goals_against += 1
            else:
                zone_stats.saves += 1

            # Update shot type stats
            current_shots = getattr(zone_stats, shots_field, 0)
            setattr(zone_stats, shots_field, current_shots + 1)
            if is_goal:
                current_goals = getattr(zone_stats, goals_field, 0)
                setattr(zone_stats, goals_field, current_goals + 1)

            # Update segment totals
            segment.shots_faced += 1
            segment.expected_goals_against += expected_shooting_pct
            if is_goal:
                segment.goals_against += 1
            else:
                segment.saves += 1

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
                profile.overall_zone_stats[zone] = GoalieZoneStats(zone_name=zone)

            overall_zone = profile.overall_zone_stats[zone]
            overall_zone.shots_faced += 1
            overall_zone.expected_goals_against += expected_shooting_pct
            if is_goal:
                overall_zone.goals_against += 1
            else:
                overall_zone.saves += 1

            # Update shot type for overall zone
            current_overall_shots = getattr(overall_zone, shots_field, 0)
            setattr(overall_zone, shots_field, current_overall_shots + 1)
            if is_goal:
                current_overall_goals = getattr(overall_zone, goals_field, 0)
                setattr(overall_zone, goals_field, current_overall_goals + 1)

            # Update profile totals
            profile.shots_faced += 1
            profile.expected_goals_against += expected_shooting_pct
            if is_goal:
                profile.goals_against += 1

        # Count games played
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT s.game_id) as games
                FROM shots s
                JOIN games g ON s.game_id = g.game_id
                WHERE s.goalie_id = ? AND g.season = ?
                """,
                (goalie_id, season),
            )
            row = cur.fetchone()
            profile.games_played = row["games"] if row else 0

        # Compute derived metrics
        profile.compute_metrics()

        # Cache the profile
        self._profile_cache[cache_key] = profile

        return profile

    def build_all_goalie_profiles(
        self,
        season: int,
        goalie_ids: Optional[list[int]] = None,
        min_shots: int = 100,
    ) -> dict[int, GoalieShotProfile]:
        """
        Build shot profiles for all goalies (or specified subset).

        Args:
            season: Season identifier
            goalie_ids: Optional list of goalie IDs to process
            min_shots: Minimum shots faced required to include goalie

        Returns:
            Dictionary mapping goalie_id to their profile
        """
        if goalie_ids is None:
            # Get goalies with shots faced this season
            with self.db.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT goalie_id
                    FROM shots
                    WHERE season = ? AND goalie_id IS NOT NULL
                    """,
                    (season,),
                )
                goalie_ids = [row["goalie_id"] for row in cur.fetchall()]

        profiles: dict[int, GoalieShotProfile] = {}

        for i, goalie_id in enumerate(goalie_ids):
            if (i + 1) % 20 == 0:
                logger.info(f"Processing goalie {i + 1}/{len(goalie_ids)}")

            profile = self.build_goalie_profile(goalie_id, season)

            # Only include if meets minimum shot threshold
            if profile.shots_faced >= min_shots:
                profiles[goalie_id] = profile

        logger.info(f"Built profiles for {len(profiles)} goalies with {min_shots}+ shots faced")
        return profiles

    def export_to_json(
        self,
        profiles: dict[int, GoalieShotProfile],
        output_path: Path,
        include_simulation_format: bool = True,
    ) -> None:
        """
        Export profiles to JSON.

        Args:
            profiles: Dictionary of goalie profiles
            output_path: Output file path
            include_simulation_format: Include simulation-ready data
        """
        export_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_goalies": len(profiles),
                "zones": list(self.zone_analyzer.zones.keys()),
                "season_phases": [p.value for p in SeasonPhase],
                "game_phases": [p.value for p in GamePhase],
                "danger_zone_mapping": {
                    "high": list(HIGH_DANGER_ZONES),
                    "medium": list(MEDIUM_DANGER_ZONES),
                    "low": list(LOW_DANGER_ZONES),
                },
            },
            "goalies": {},
        }

        for goalie_id, profile in profiles.items():
            goalie_data = profile.to_dict()

            if include_simulation_format:
                goalie_data["simulation"] = profile.get_simulation_data()

            export_data["goalies"][str(goalie_id)] = goalie_data

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Exported JSON to {output_path}")

    def export_to_csv(
        self,
        profiles: dict[int, GoalieShotProfile],
        output_path: Path,
    ) -> None:
        """
        Export profiles to CSV (flat format with one row per goalie-segment-zone).

        Args:
            profiles: Dictionary of goalie profiles
            output_path: Output file path
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "goalie_id", "goalie_name", "season",
            "season_phase", "game_phase", "zone",
            "shots_faced", "goals_against", "saves", "save_percentage",
            "expected_goals_against", "goals_saved_above_expected",
            "wrist_shots", "wrist_goals",
            "slap_shots", "slap_goals",
            "snap_shots", "snap_goals",
            "backhand_shots", "backhand_goals",
            "tip_shots", "tip_goals",
            "danger_level",
        ]

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for goalie_id, profile in profiles.items():
                for (season_phase, game_phase), segment in profile.segment_stats.items():
                    for zone, zone_stats in segment.zone_stats.items():
                        if zone_stats.shots_faced == 0:
                            continue

                        writer.writerow({
                            "goalie_id": goalie_id,
                            "goalie_name": profile.goalie_name,
                            "season": profile.season,
                            "season_phase": season_phase,
                            "game_phase": game_phase,
                            "zone": zone,
                            "shots_faced": zone_stats.shots_faced,
                            "goals_against": zone_stats.goals_against,
                            "saves": zone_stats.saves,
                            "save_percentage": round(zone_stats.save_percentage, 2),
                            "expected_goals_against": round(zone_stats.expected_goals_against, 3),
                            "goals_saved_above_expected": round(zone_stats.goals_saved_above_expected, 3),
                            "wrist_shots": zone_stats.wrist_shots,
                            "wrist_goals": zone_stats.wrist_goals,
                            "slap_shots": zone_stats.slap_shots,
                            "slap_goals": zone_stats.slap_goals,
                            "snap_shots": zone_stats.snap_shots,
                            "snap_goals": zone_stats.snap_goals,
                            "backhand_shots": zone_stats.backhand_shots,
                            "backhand_goals": zone_stats.backhand_goals,
                            "tip_shots": zone_stats.tip_shots,
                            "tip_goals": zone_stats.tip_goals,
                            "danger_level": self._get_danger_level(zone),
                        })

        logger.info(f"Exported CSV to {output_path}")

    def export_heat_map_data(
        self,
        profiles: dict[int, GoalieShotProfile],
        output_path: Path,
    ) -> None:
        """
        Export heat map data optimized for visualization.

        Args:
            profiles: Dictionary of goalie profiles
            output_path: Output file path
        """
        heat_map_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "description": "Goalie save percentage by zone (higher = better)",
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
            "goalies": {},
        }

        for goalie_id, profile in profiles.items():
            goalie_heat_map = {
                "goalie_id": goalie_id,
                "goalie_name": profile.goalie_name,
                "overall": profile.get_heat_map_data(),
                "segments": {},
            }

            for season_phase in SeasonPhase:
                for game_phase in GamePhase:
                    seg_key = f"{season_phase.value}_{game_phase.value}"
                    goalie_heat_map["segments"][seg_key] = profile.get_segment_heat_map(
                        season_phase.value, game_phase.value
                    )

            heat_map_data["goalies"][str(goalie_id)] = goalie_heat_map

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(heat_map_data, f, indent=2)

        logger.info(f"Exported heat map data to {output_path}")

    def export_simulation_data(
        self,
        profiles: dict[int, GoalieShotProfile],
        output_path: Path,
    ) -> None:
        """
        Export data optimized for simulation engine.

        Args:
            profiles: Dictionary of goalie profiles
            output_path: Output file path
        """
        sim_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "description": "Goalie save percentages by zone/segment for game simulation",
                "zones": list(self.zone_analyzer.zones.keys()),
                "expected_shooting_pct_by_zone": {
                    name: zone_def.expected_shooting_pct
                    for name, zone_def in self.zone_analyzer.zones.items()
                },
            },
            "goalies": {},
        }

        for goalie_id, profile in profiles.items():
            sim_data["goalies"][str(goalie_id)] = profile.get_simulation_data()

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
    min_shots: int = 100,
    goalie_ids: Optional[list[int]] = None,
    db: Optional[Database] = None,
) -> dict[int, GoalieShotProfile]:
    """
    Run the full goalie shot profile pipeline.

    Args:
        season: Season identifier (e.g., 20242025)
        output_dir: Directory for output files (default: data/exports/)
        min_shots: Minimum shots faced required to include goalie
        goalie_ids: Optional specific goalies to process
        db: Database instance

    Returns:
        Dictionary of goalie profiles
    """
    if output_dir is None:
        output_dir = Path("data/exports")

    pipeline = GoalieShotProfilePipeline(db=db)

    logger.info(f"Starting goalie shot profile pipeline for season {season}")

    # Build all profiles
    profiles = pipeline.build_all_goalie_profiles(
        season=season,
        goalie_ids=goalie_ids,
        min_shots=min_shots,
    )

    # Export all formats
    pipeline.export_to_json(
        profiles,
        output_dir / f"goalie_shot_profiles_{season}.json",
    )

    pipeline.export_to_csv(
        profiles,
        output_dir / f"goalie_shot_profiles_{season}.csv",
    )

    pipeline.export_heat_map_data(
        profiles,
        output_dir / f"goalie_shot_heatmaps_{season}.json",
    )

    pipeline.export_simulation_data(
        profiles,
        output_dir / f"goalie_shot_simulation_{season}.json",
    )

    logger.info("Pipeline complete!")
    return profiles
