"""
Season + Game Segmentation Aggregation Pipeline

Produces per-player stats for each (season phase × game phase) combination.
Season phases: early_season, mid_season, late_season, playoffs
Game phases: early_game, mid_game, late_game (from existing segment model)

Reference: docs/season-segmentation-roadmap.md
"""

import csv
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from ..database.db import Database, get_database


class SeasonPhase(str, Enum):
    """Season phase enumeration."""
    EARLY_SEASON = "early_season"
    MID_SEASON = "mid_season"
    LATE_SEASON = "late_season"
    PLAYOFFS = "playoffs"


class GamePhase(str, Enum):
    """Game phase (within-game segment) enumeration."""
    EARLY_GAME = "early_game"
    MID_GAME = "mid_game"
    LATE_GAME = "late_game"


# Game phase time ranges (from config/segments.yaml)
# Maps (period, minute) ranges to game phases
GAME_PHASE_RANGES: dict[GamePhase, list[dict[str, int]]] = {
    GamePhase.EARLY_GAME: [
        {"period": 1, "start_minute": 0, "end_minute": 20},
        {"period": 2, "start_minute": 0, "end_minute": 10},
    ],
    GamePhase.MID_GAME: [
        {"period": 2, "start_minute": 10, "end_minute": 20},
        {"period": 3, "start_minute": 0, "end_minute": 10},
    ],
    GamePhase.LATE_GAME: [
        {"period": 3, "start_minute": 10, "end_minute": 20},
        {"period": 4, "start_minute": 0, "end_minute": 5},  # Overtime
    ],
}


@dataclass
class PlayerPhaseStats:
    """Player statistics for a specific (season phase × game phase) combination."""

    player_id: int
    player_name: str = ""
    season_phase: str = ""
    game_phase: str = ""

    # Counting stats
    games: int = 0
    goals: int = 0
    assists: int = 0
    points: int = 0
    shots: int = 0

    # Special situations
    power_play_goals: int = 0
    game_winning_goals: int = 0

    # Sample size indicator
    sample_size_category: str = "insufficient"  # insufficient, minimum, recommended, high_confidence

    @property
    def goals_per_game(self) -> float:
        """Goals per game rate."""
        return self.goals / self.games if self.games > 0 else 0.0

    @property
    def points_per_game(self) -> float:
        """Points per game rate."""
        return self.points / self.games if self.games > 0 else 0.0

    @property
    def shooting_percentage(self) -> float:
        """Shooting percentage."""
        return (self.goals / self.shots * 100) if self.shots > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with rate stats included."""
        result = asdict(self)
        result["goals_per_game"] = round(self.goals_per_game, 3)
        result["points_per_game"] = round(self.points_per_game, 3)
        result["shooting_percentage"] = round(self.shooting_percentage, 1)
        return result


@dataclass
class SeasonPhaseMapping:
    """Mapping of game_ids to season phases for a season."""

    season: int
    early_season_games: set[int] = field(default_factory=set)
    mid_season_games: set[int] = field(default_factory=set)
    late_season_games: set[int] = field(default_factory=set)
    playoff_games: set[int] = field(default_factory=set)

    def get_phase(self, game_id: int) -> Optional[SeasonPhase]:
        """Get season phase for a game_id."""
        if game_id in self.early_season_games:
            return SeasonPhase.EARLY_SEASON
        elif game_id in self.mid_season_games:
            return SeasonPhase.MID_SEASON
        elif game_id in self.late_season_games:
            return SeasonPhase.LATE_SEASON
        elif game_id in self.playoff_games:
            return SeasonPhase.PLAYOFFS
        return None


@dataclass
class ValidationResult:
    """Result of validation against per-game totals."""

    season: int
    player_id: int
    player_name: str

    # Expected totals from player_game_stats
    expected_goals: int = 0
    expected_assists: int = 0
    expected_points: int = 0
    expected_games: int = 0

    # Aggregated totals from pipeline
    aggregated_goals: int = 0
    aggregated_assists: int = 0
    aggregated_points: int = 0
    aggregated_games: int = 0

    @property
    def is_valid(self) -> bool:
        """Check if totals reconcile."""
        return (
            self.expected_goals == self.aggregated_goals
            and self.expected_assists == self.aggregated_assists
            and self.expected_points == self.aggregated_points
        )

    @property
    def discrepancy(self) -> dict[str, int]:
        """Get discrepancies between expected and aggregated."""
        return {
            "goals_diff": self.aggregated_goals - self.expected_goals,
            "assists_diff": self.aggregated_assists - self.expected_assists,
            "points_diff": self.aggregated_points - self.expected_points,
            "games_diff": self.aggregated_games - self.expected_games,
        }


class SeasonSegmentPipeline:
    """
    Aggregation pipeline for season phase × game phase player stats.

    Workflow:
    1. Build season phase mapping (early/mid/late thirds + playoffs)
    2. For each player, aggregate stats by (season phase × game phase)
    3. Validate against per-game totals
    4. Export results
    """

    # Sample size thresholds (from config/segments.yaml)
    SAMPLE_MINIMUM = 20
    SAMPLE_RECOMMENDED = 100
    SAMPLE_HIGH_CONFIDENCE = 500

    def __init__(self, db: Optional[Database] = None):
        """Initialize pipeline with database connection."""
        self.db = db or get_database()
        self._season_phase_cache: dict[int, SeasonPhaseMapping] = {}

    # -------------------------------------------------------------------------
    # Season Phase Tagging
    # -------------------------------------------------------------------------

    def build_season_phase_mapping(self, season: int) -> SeasonPhaseMapping:
        """
        Build mapping of game_ids to season phases.

        Regular season games are split into thirds by game_date.
        Playoff games (game_type=3) are tagged separately.

        Args:
            season: Season identifier (e.g., 20242025)

        Returns:
            SeasonPhaseMapping with game_ids categorized by phase
        """
        if season in self._season_phase_cache:
            return self._season_phase_cache[season]

        mapping = SeasonPhaseMapping(season=season)

        with self.db.cursor() as cur:
            # Get regular season games ordered by date
            cur.execute(
                """
                SELECT game_id, game_date, game_type
                FROM games
                WHERE season = ?
                ORDER BY game_date, game_id
                """,
                (season,),
            )
            games = cur.fetchall()

        # Separate regular season and playoffs
        regular_games = []
        for game in games:
            game_id = game["game_id"]
            game_type = game["game_type"]

            if game_type == 3:  # Playoffs
                mapping.playoff_games.add(game_id)
            else:  # Regular season (game_type=2) or preseason
                if game_type == 2:  # Only include regular season
                    regular_games.append(game_id)

        # Split regular season into thirds
        total_regular = len(regular_games)
        if total_regular > 0:
            third_size = total_regular // 3
            remainder = total_regular % 3

            # Distribute remainder: first third gets extra if remainder >= 1
            # second third gets extra if remainder >= 2
            first_end = third_size + (1 if remainder >= 1 else 0)
            second_end = first_end + third_size + (1 if remainder >= 2 else 0)

            mapping.early_season_games = set(regular_games[:first_end])
            mapping.mid_season_games = set(regular_games[first_end:second_end])
            mapping.late_season_games = set(regular_games[second_end:])

        logger.info(
            f"Season {season} phase mapping: "
            f"early={len(mapping.early_season_games)}, "
            f"mid={len(mapping.mid_season_games)}, "
            f"late={len(mapping.late_season_games)}, "
            f"playoffs={len(mapping.playoff_games)}"
        )

        self._season_phase_cache[season] = mapping
        return mapping

    def get_game_season_phase(self, game_id: int, season: int) -> Optional[SeasonPhase]:
        """Get season phase for a specific game."""
        mapping = self.build_season_phase_mapping(season)
        return mapping.get_phase(game_id)

    # -------------------------------------------------------------------------
    # Game Phase Tagging
    # -------------------------------------------------------------------------

    def get_game_phase(self, period: int, time_in_period: str) -> Optional[GamePhase]:
        """
        Determine game phase from period and time.

        Args:
            period: Period number (1, 2, 3, 4 for OT)
            time_in_period: Time string in MM:SS format (time elapsed, not remaining)

        Returns:
            GamePhase or None if not in a defined segment
        """
        try:
            parts = time_in_period.split(":")
            minutes = int(parts[0])
        except (ValueError, IndexError, AttributeError):
            return None

        for game_phase, ranges in GAME_PHASE_RANGES.items():
            for time_range in ranges:
                if (
                    time_range["period"] == period
                    and time_range["start_minute"] <= minutes < time_range["end_minute"]
                ):
                    return game_phase

        return None

    def get_game_phase_from_seconds(self, game_seconds: int) -> Optional[GamePhase]:
        """
        Determine game phase from total game seconds.

        Args:
            game_seconds: Total seconds elapsed in game

        Returns:
            GamePhase or None
        """
        # Convert to period and minute
        period = (game_seconds // 1200) + 1
        seconds_in_period = game_seconds % 1200
        minutes = seconds_in_period // 60

        return self.get_game_phase(period, f"{minutes}:00")

    # -------------------------------------------------------------------------
    # Aggregation
    # -------------------------------------------------------------------------

    def aggregate_player_stats(
        self,
        player_id: int,
        season: int,
    ) -> dict[tuple[str, str], PlayerPhaseStats]:
        """
        Aggregate player stats by (season phase × game phase).

        Uses shots table for event-level game phase assignment,
        falls back to player_game_stats for game-level aggregation.

        Args:
            player_id: NHL player ID
            season: Season identifier

        Returns:
            Dictionary mapping (season_phase, game_phase) to PlayerPhaseStats
        """
        phase_mapping = self.build_season_phase_mapping(season)

        # Initialize stats containers for all combinations
        stats: dict[tuple[str, str], PlayerPhaseStats] = {}
        for season_phase in SeasonPhase:
            for game_phase in GamePhase:
                key = (season_phase.value, game_phase.value)
                stats[key] = PlayerPhaseStats(
                    player_id=player_id,
                    season_phase=season_phase.value,
                    game_phase=game_phase.value,
                )

        # Get player name
        player = self.db.get_player(player_id)
        player_name = player["full_name"] if player else f"Player {player_id}"
        for stat in stats.values():
            stat.player_name = player_name

        # Aggregate goals/assists from shots table (event-level)
        self._aggregate_from_shots(player_id, season, phase_mapping, stats)

        # Track games played per phase combination
        self._count_games_per_phase(player_id, season, phase_mapping, stats)

        # Assign sample size categories
        for stat in stats.values():
            stat.sample_size_category = self._get_sample_category(stat.games)

        return stats

    def _aggregate_from_shots(
        self,
        player_id: int,
        season: int,
        phase_mapping: SeasonPhaseMapping,
        stats: dict[tuple[str, str], PlayerPhaseStats],
    ) -> None:
        """Aggregate goals and assists from shots table."""
        with self.db.cursor() as cur:
            # Get goals scored by this player
            cur.execute(
                """
                SELECT game_id, period, time_in_period, is_goal,
                       game_winning_goal, strength
                FROM shots
                WHERE player_id = ? AND season = ?
                """,
                (player_id, season),
            )
            shots = cur.fetchall()

            for shot in shots:
                game_id = shot["game_id"]
                season_phase = phase_mapping.get_phase(game_id)
                if not season_phase:
                    continue

                game_phase = self.get_game_phase(
                    shot["period"],
                    shot["time_in_period"] or "00:00"
                )
                if not game_phase:
                    continue

                key = (season_phase.value, game_phase.value)
                stats[key].shots += 1

                if shot["is_goal"]:
                    stats[key].goals += 1
                    stats[key].points += 1

                    if shot["game_winning_goal"]:
                        stats[key].game_winning_goals += 1

                    if shot["strength"] == "pp":
                        stats[key].power_play_goals += 1

            # Get assists (player appears in assist columns)
            cur.execute(
                """
                SELECT game_id, period, time_in_period
                FROM shots
                WHERE (assist1_player_id = ? OR assist2_player_id = ?)
                AND season = ? AND is_goal = 1
                """,
                (player_id, player_id, season),
            )
            assists = cur.fetchall()

            for assist in assists:
                game_id = assist["game_id"]
                season_phase = phase_mapping.get_phase(game_id)
                if not season_phase:
                    continue

                game_phase = self.get_game_phase(
                    assist["period"],
                    assist["time_in_period"] or "00:00"
                )
                if not game_phase:
                    continue

                key = (season_phase.value, game_phase.value)
                stats[key].assists += 1
                stats[key].points += 1

    def _count_games_per_phase(
        self,
        player_id: int,
        season: int,
        phase_mapping: SeasonPhaseMapping,
        stats: dict[tuple[str, str], PlayerPhaseStats],
    ) -> None:
        """
        Count games played per season phase.

        Note: A player plays all game phases in each game they appear in,
        so games count is per season phase, applied to all game phases.
        """
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT pgs.game_id
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id = ? AND g.season = ?
                """,
                (player_id, season),
            )
            player_games = [row["game_id"] for row in cur.fetchall()]

        # Count games per season phase
        phase_game_counts: dict[str, int] = {
            SeasonPhase.EARLY_SEASON.value: 0,
            SeasonPhase.MID_SEASON.value: 0,
            SeasonPhase.LATE_SEASON.value: 0,
            SeasonPhase.PLAYOFFS.value: 0,
        }

        for game_id in player_games:
            season_phase = phase_mapping.get_phase(game_id)
            if season_phase:
                phase_game_counts[season_phase.value] += 1

        # Apply to all game phase combinations
        for season_phase_val, count in phase_game_counts.items():
            for game_phase in GamePhase:
                key = (season_phase_val, game_phase.value)
                stats[key].games = count

    def _get_sample_category(self, games: int) -> str:
        """Determine sample size category."""
        if games >= self.SAMPLE_HIGH_CONFIDENCE:
            return "high_confidence"
        elif games >= self.SAMPLE_RECOMMENDED:
            return "recommended"
        elif games >= self.SAMPLE_MINIMUM:
            return "minimum"
        return "insufficient"

    def aggregate_all_players(
        self,
        season: int,
        player_ids: Optional[list[int]] = None,
    ) -> dict[int, dict[tuple[str, str], PlayerPhaseStats]]:
        """
        Aggregate stats for all players (or specified subset).

        Args:
            season: Season identifier
            player_ids: Optional list of player IDs to process

        Returns:
            Dictionary mapping player_id to their phase stats
        """
        if player_ids is None:
            player_ids = self.db.get_all_player_ids(active_only=False)

        all_stats: dict[int, dict[tuple[str, str], PlayerPhaseStats]] = {}

        for i, player_id in enumerate(player_ids):
            if (i + 1) % 100 == 0:
                logger.info(f"Processing player {i + 1}/{len(player_ids)}")

            player_stats = self.aggregate_player_stats(player_id, season)

            # Only include if player has any recorded stats
            has_stats = any(
                s.goals > 0 or s.assists > 0 or s.shots > 0
                for s in player_stats.values()
            )
            if has_stats:
                all_stats[player_id] = player_stats

        logger.info(f"Aggregated stats for {len(all_stats)} players with data")
        return all_stats

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    def validate_player(self, player_id: int, season: int) -> ValidationResult:
        """
        Validate aggregated stats against per-game totals.

        Args:
            player_id: NHL player ID
            season: Season identifier

        Returns:
            ValidationResult with comparison data
        """
        player = self.db.get_player(player_id)
        player_name = player["full_name"] if player else f"Player {player_id}"

        result = ValidationResult(
            season=season,
            player_id=player_id,
            player_name=player_name,
        )

        # Get expected totals from player_game_stats
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) as games,
                    SUM(goals) as goals,
                    SUM(assists) as assists,
                    SUM(points) as points
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id = ? AND g.season = ?
                """,
                (player_id, season),
            )
            row = cur.fetchone()

            result.expected_games = row["games"] or 0
            result.expected_goals = row["goals"] or 0
            result.expected_assists = row["assists"] or 0
            result.expected_points = row["points"] or 0

        # Get aggregated totals from pipeline
        phase_stats = self.aggregate_player_stats(player_id, season)

        for stats in phase_stats.values():
            result.aggregated_goals += stats.goals
            result.aggregated_assists += stats.assists
            result.aggregated_points += stats.points

        # Games are counted per season phase, so sum unique season phases
        seen_season_phases: set[str] = set()
        for (season_phase, _), stats in phase_stats.items():
            if season_phase not in seen_season_phases:
                result.aggregated_games += stats.games
                seen_season_phases.add(season_phase)

        return result

    def validate_season(
        self,
        season: int,
        player_ids: Optional[list[int]] = None,
        sample_size: int = 50,
    ) -> list[ValidationResult]:
        """
        Validate aggregation for a sample of players.

        Args:
            season: Season identifier
            player_ids: Optional specific players to validate
            sample_size: Number of players to sample if not specified

        Returns:
            List of ValidationResults
        """
        if player_ids is None:
            # Get players with game stats this season
            with self.db.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT pgs.player_id
                    FROM player_game_stats pgs
                    JOIN games g ON pgs.game_id = g.game_id
                    WHERE g.season = ?
                    ORDER BY RANDOM()
                    LIMIT ?
                    """,
                    (season, sample_size),
                )
                player_ids = [row["player_id"] for row in cur.fetchall()]

        results = []
        valid_count = 0

        for player_id in player_ids:
            result = self.validate_player(player_id, season)
            results.append(result)

            if result.is_valid:
                valid_count += 1
            else:
                logger.warning(
                    f"Validation failed for {result.player_name}: {result.discrepancy}"
                )

        logger.info(
            f"Validation complete: {valid_count}/{len(results)} players passed "
            f"({100 * valid_count / len(results):.1f}%)"
        )

        return results

    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------

    def export_to_json(
        self,
        all_stats: dict[int, dict[tuple[str, str], PlayerPhaseStats]],
        output_path: Path,
    ) -> None:
        """
        Export aggregated stats to JSON.

        Args:
            all_stats: Aggregated stats from aggregate_all_players
            output_path: Path for output JSON file
        """
        export_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "season_phases": [p.value for p in SeasonPhase],
                "game_phases": [p.value for p in GamePhase],
                "sample_thresholds": {
                    "minimum": self.SAMPLE_MINIMUM,
                    "recommended": self.SAMPLE_RECOMMENDED,
                    "high_confidence": self.SAMPLE_HIGH_CONFIDENCE,
                },
            },
            "players": {},
        }

        for player_id, phase_stats in all_stats.items():
            player_data: dict[str, Any] = {
                "player_id": player_id,
                "player_name": "",
                "phases": {},
            }

            for (season_phase, game_phase), stats in phase_stats.items():
                if not player_data["player_name"]:
                    player_data["player_name"] = stats.player_name

                phase_key = f"{season_phase}_{game_phase}"
                player_data["phases"][phase_key] = stats.to_dict()

            export_data["players"][str(player_id)] = player_data

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Exported JSON to {output_path}")

    def export_to_csv(
        self,
        all_stats: dict[int, dict[tuple[str, str], PlayerPhaseStats]],
        output_path: Path,
    ) -> None:
        """
        Export aggregated stats to CSV (flat format).

        Args:
            all_stats: Aggregated stats from aggregate_all_players
            output_path: Path for output CSV file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "player_id", "player_name", "season_phase", "game_phase",
            "games", "goals", "assists", "points", "shots",
            "power_play_goals", "game_winning_goals",
            "goals_per_game", "points_per_game", "shooting_percentage",
            "sample_size_category",
        ]

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for player_id, phase_stats in all_stats.items():
                for stats in phase_stats.values():
                    row = stats.to_dict()
                    writer.writerow(row)

        logger.info(f"Exported CSV to {output_path}")

    def export_validation_report(
        self,
        results: list[ValidationResult],
        output_path: Path,
    ) -> None:
        """
        Export validation results to JSON.

        Args:
            results: List of ValidationResults
            output_path: Path for output JSON file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_players": len(results),
                "passed": sum(1 for r in results if r.is_valid),
                "failed": sum(1 for r in results if not r.is_valid),
                "pass_rate": sum(1 for r in results if r.is_valid) / len(results) if results else 0,
            },
            "results": [
                {
                    "player_id": r.player_id,
                    "player_name": r.player_name,
                    "is_valid": r.is_valid,
                    "expected": {
                        "games": r.expected_games,
                        "goals": r.expected_goals,
                        "assists": r.expected_assists,
                        "points": r.expected_points,
                    },
                    "aggregated": {
                        "games": r.aggregated_games,
                        "goals": r.aggregated_goals,
                        "assists": r.aggregated_assists,
                        "points": r.aggregated_points,
                    },
                    "discrepancy": r.discrepancy if not r.is_valid else None,
                }
                for r in results
            ],
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Exported validation report to {output_path}")


def run_pipeline(
    season: int,
    output_dir: Optional[Path] = None,
    validate: bool = True,
    db: Optional[Database] = None,
) -> dict[int, dict[tuple[str, str], PlayerPhaseStats]]:
    """
    Run the full aggregation pipeline for a season.

    Args:
        season: Season identifier (e.g., 20242025)
        output_dir: Directory for output files (default: data/exports/)
        validate: Whether to run validation
        db: Database instance

    Returns:
        Aggregated stats dictionary
    """
    if output_dir is None:
        output_dir = Path("data/exports")

    pipeline = SeasonSegmentPipeline(db=db)

    logger.info(f"Starting aggregation pipeline for season {season}")

    # Build season phase mapping
    phase_mapping = pipeline.build_season_phase_mapping(season)

    # Aggregate all players
    all_stats = pipeline.aggregate_all_players(season)

    # Validation
    if validate:
        logger.info("Running validation...")
        validation_results = pipeline.validate_season(season)
        pipeline.export_validation_report(
            validation_results,
            output_dir / f"validation_{season}.json",
        )

    # Export
    pipeline.export_to_json(all_stats, output_dir / f"player_phase_stats_{season}.json")
    pipeline.export_to_csv(all_stats, output_dir / f"player_phase_stats_{season}.csv")

    logger.info("Pipeline complete!")
    return all_stats
