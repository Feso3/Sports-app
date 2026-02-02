"""
Player Momentum Detection Pipeline

Detects hot streaks and slumps by comparing recent performance
to season averages. Calculates momentum scores and confidence levels.

Reference: docs/simulation-logic-design.md
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from ..database.db import Database, get_database


class MomentumState(str, Enum):
    """Player momentum state."""

    HOT = "hot"
    NEUTRAL = "neutral"
    COLD = "cold"


@dataclass
class PlayerGameData:
    """Single game data point for momentum analysis."""

    game_id: int
    game_date: str
    goals: int = 0
    assists: int = 0
    points: int = 0
    shots: int = 0


@dataclass
class MomentumAnalysis:
    """Result of momentum analysis for a player."""

    player_id: int
    calculated_date: str
    season: int
    window_games: int

    # Sample size
    games_in_window: int = 0

    # Recent performance (within window)
    recent_goals: int = 0
    recent_assists: int = 0
    recent_points: int = 0
    recent_shots: int = 0
    recent_ppg: float = 0.0
    recent_gpg: float = 0.0
    recent_shooting_pct: float = 0.0

    # Season baseline
    season_ppg: float = 0.0
    season_gpg: float = 0.0
    season_shooting_pct: float = 0.0

    # Deviation analysis
    ppg_deviation: float = 0.0  # (recent - season) / season
    gpg_deviation: float = 0.0
    shooting_pct_deviation: float = 0.0

    # Momentum state
    momentum_state: MomentumState = MomentumState.NEUTRAL
    momentum_score: float = 0.0  # -1.0 to 1.0
    confidence: float = 0.0      # 0.0 to 1.0


# Momentum detection thresholds
MOMENTUM_CONFIG = {
    # Windows to analyze
    "windows": [5, 10, 20],

    # Deviation thresholds for hot streak
    "hot_streak": {
        "ppg_threshold": 0.20,      # 20% above season average
        "shooting_threshold": 0.15,  # 15% above season average
    },

    # Deviation thresholds for slump
    "slump": {
        "ppg_threshold": -0.20,      # 20% below season average
        "shooting_threshold": -0.15,  # 15% below season average
    },

    # Simulation modifiers
    "modifiers": {
        "hot_high_confidence": 1.10,   # +10%
        "hot_low_confidence": 1.05,    # +5%
        "neutral": 1.00,
        "cold_low_confidence": 0.95,   # -5%
        "cold_high_confidence": 0.90,  # -10%
    },

    # Minimum games for analysis
    "min_recent_games": 3,
    "min_season_games": 10,
}


class MomentumPipeline:
    """
    Pipeline for detecting player hot streaks and slumps.

    Workflow:
    1. Get player's game-by-game stats for season
    2. Calculate season averages
    3. Calculate recent averages (multiple windows)
    4. Compare to detect momentum state
    5. Calculate confidence and modifier
    """

    def __init__(self, db: Optional[Database] = None):
        """Initialize pipeline with database connection."""
        self.db = db or get_database()

    def get_player_game_log(
        self,
        player_id: int,
        season: int,
    ) -> list[PlayerGameData]:
        """
        Get player's game-by-game stats for a season.

        Args:
            player_id: NHL player ID
            season: Season identifier

        Returns:
            List of PlayerGameData ordered by game date (oldest first)
        """
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pgs.game_id,
                    g.game_date,
                    pgs.goals,
                    pgs.assists,
                    pgs.points,
                    pgs.shots
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id = ? AND g.season = ?
                ORDER BY g.game_date, g.game_id
                """,
                (player_id, season),
            )
            rows = cur.fetchall()

            return [
                PlayerGameData(
                    game_id=row["game_id"],
                    game_date=row["game_date"],
                    goals=row["goals"] or 0,
                    assists=row["assists"] or 0,
                    points=row["points"] or 0,
                    shots=row["shots"] or 0,
                )
                for row in rows
            ]

    def analyze_momentum(
        self,
        player_id: int,
        season: int,
        as_of_date: Optional[str] = None,
        window_games: int = 10,
    ) -> MomentumAnalysis:
        """
        Analyze player's momentum state.

        Args:
            player_id: NHL player ID
            season: Season identifier
            as_of_date: Date to analyze momentum as of (default: today)
            window_games: Number of recent games to analyze

        Returns:
            MomentumAnalysis with state and confidence
        """
        calculated_date = as_of_date or datetime.now().strftime("%Y-%m-%d")

        analysis = MomentumAnalysis(
            player_id=player_id,
            calculated_date=calculated_date,
            season=season,
            window_games=window_games,
        )

        # Get game log
        game_log = self.get_player_game_log(player_id, season)

        if not game_log:
            return analysis

        # Filter to games before as_of_date
        if as_of_date:
            game_log = [g for g in game_log if g.game_date <= as_of_date]

        if len(game_log) < MOMENTUM_CONFIG["min_season_games"]:
            return analysis

        # Calculate season averages (excluding most recent games for baseline)
        season_games = game_log[:-window_games] if len(game_log) > window_games else game_log
        analysis.season_ppg = self._calculate_ppg(season_games)
        analysis.season_gpg = self._calculate_gpg(season_games)
        analysis.season_shooting_pct = self._calculate_shooting_pct(season_games)

        # Calculate recent averages
        recent_games = game_log[-window_games:]
        analysis.games_in_window = len(recent_games)

        if analysis.games_in_window < MOMENTUM_CONFIG["min_recent_games"]:
            return analysis

        analysis.recent_goals = sum(g.goals for g in recent_games)
        analysis.recent_assists = sum(g.assists for g in recent_games)
        analysis.recent_points = sum(g.points for g in recent_games)
        analysis.recent_shots = sum(g.shots for g in recent_games)

        analysis.recent_ppg = self._calculate_ppg(recent_games)
        analysis.recent_gpg = self._calculate_gpg(recent_games)
        analysis.recent_shooting_pct = self._calculate_shooting_pct(recent_games)

        # Calculate deviations
        if analysis.season_ppg > 0:
            analysis.ppg_deviation = (
                (analysis.recent_ppg - analysis.season_ppg) / analysis.season_ppg
            )
        if analysis.season_gpg > 0:
            analysis.gpg_deviation = (
                (analysis.recent_gpg - analysis.season_gpg) / analysis.season_gpg
            )
        if analysis.season_shooting_pct > 0:
            analysis.shooting_pct_deviation = (
                (analysis.recent_shooting_pct - analysis.season_shooting_pct)
                / analysis.season_shooting_pct
            )

        # Determine momentum state
        analysis.momentum_state, analysis.momentum_score = self._determine_momentum_state(
            analysis.ppg_deviation,
            analysis.shooting_pct_deviation,
        )

        # Calculate confidence based on sample size and deviation magnitude
        analysis.confidence = self._calculate_confidence(
            analysis.games_in_window,
            window_games,
            abs(analysis.ppg_deviation),
            abs(analysis.shooting_pct_deviation),
        )

        return analysis

    def _calculate_ppg(self, games: list[PlayerGameData]) -> float:
        """Calculate points per game."""
        if not games:
            return 0.0
        total_points = sum(g.points for g in games)
        return total_points / len(games)

    def _calculate_gpg(self, games: list[PlayerGameData]) -> float:
        """Calculate goals per game."""
        if not games:
            return 0.0
        total_goals = sum(g.goals for g in games)
        return total_goals / len(games)

    def _calculate_shooting_pct(self, games: list[PlayerGameData]) -> float:
        """Calculate shooting percentage."""
        total_goals = sum(g.goals for g in games)
        total_shots = sum(g.shots for g in games)
        if total_shots == 0:
            return 0.0
        return (total_goals / total_shots) * 100

    def _determine_momentum_state(
        self,
        ppg_deviation: float,
        shooting_deviation: float,
    ) -> tuple[MomentumState, float]:
        """
        Determine momentum state from deviations.

        Returns:
            Tuple of (MomentumState, momentum_score)
        """
        hot_config = MOMENTUM_CONFIG["hot_streak"]
        cold_config = MOMENTUM_CONFIG["slump"]

        # Hot streak: both metrics above threshold
        if (ppg_deviation > hot_config["ppg_threshold"] and
                shooting_deviation > hot_config["shooting_threshold"]):
            # Score based on how far above threshold
            score = min(1.0, (ppg_deviation + shooting_deviation) / 0.5)
            return MomentumState.HOT, score

        # Slump: both metrics below threshold
        if (ppg_deviation < cold_config["ppg_threshold"] and
                shooting_deviation < cold_config["shooting_threshold"]):
            # Score based on how far below threshold
            score = max(-1.0, (ppg_deviation + shooting_deviation) / 0.5)
            return MomentumState.COLD, score

        # Neutral
        return MomentumState.NEUTRAL, 0.0

    def _calculate_confidence(
        self,
        games_in_window: int,
        window_size: int,
        ppg_magnitude: float,
        shooting_magnitude: float,
    ) -> float:
        """
        Calculate confidence in momentum assessment.

        Higher confidence when:
        - More games in window
        - Larger deviations (stronger signal)
        """
        # Sample size factor (0.5 to 1.0)
        sample_factor = 0.5 + 0.5 * min(1.0, games_in_window / window_size)

        # Deviation magnitude factor (0.0 to 1.0)
        avg_magnitude = (ppg_magnitude + shooting_magnitude) / 2
        magnitude_factor = min(1.0, avg_magnitude / 0.3)  # Normalize to 30% deviation

        return sample_factor * magnitude_factor

    def get_momentum_modifier(self, analysis: MomentumAnalysis) -> float:
        """
        Get simulation modifier based on momentum analysis.

        Args:
            analysis: MomentumAnalysis result

        Returns:
            Modifier value (e.g., 1.10 for +10%)
        """
        modifiers = MOMENTUM_CONFIG["modifiers"]

        if analysis.momentum_state == MomentumState.HOT:
            if analysis.confidence >= 0.5:
                return modifiers["hot_high_confidence"]
            return modifiers["hot_low_confidence"]

        if analysis.momentum_state == MomentumState.COLD:
            if analysis.confidence >= 0.5:
                return modifiers["cold_high_confidence"]
            return modifiers["cold_low_confidence"]

        return modifiers["neutral"]

    def save_momentum_analysis(self, analysis: MomentumAnalysis) -> None:
        """Save momentum analysis to database."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO player_momentum (
                    player_id, calculated_date, season, window_games,
                    games_in_window, recent_goals, recent_assists,
                    recent_points, recent_shots,
                    recent_ppg, recent_gpg, recent_shooting_pct,
                    season_ppg, season_gpg, season_shooting_pct,
                    ppg_deviation, gpg_deviation, shooting_pct_deviation,
                    momentum_state, momentum_score, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, calculated_date, window_games) DO UPDATE SET
                    games_in_window = excluded.games_in_window,
                    recent_goals = excluded.recent_goals,
                    recent_assists = excluded.recent_assists,
                    recent_points = excluded.recent_points,
                    recent_shots = excluded.recent_shots,
                    recent_ppg = excluded.recent_ppg,
                    recent_gpg = excluded.recent_gpg,
                    recent_shooting_pct = excluded.recent_shooting_pct,
                    season_ppg = excluded.season_ppg,
                    season_gpg = excluded.season_gpg,
                    season_shooting_pct = excluded.season_shooting_pct,
                    ppg_deviation = excluded.ppg_deviation,
                    gpg_deviation = excluded.gpg_deviation,
                    shooting_pct_deviation = excluded.shooting_pct_deviation,
                    momentum_state = excluded.momentum_state,
                    momentum_score = excluded.momentum_score,
                    confidence = excluded.confidence
                """,
                (
                    analysis.player_id,
                    analysis.calculated_date,
                    analysis.season,
                    analysis.window_games,
                    analysis.games_in_window,
                    analysis.recent_goals,
                    analysis.recent_assists,
                    analysis.recent_points,
                    analysis.recent_shots,
                    analysis.recent_ppg,
                    analysis.recent_gpg,
                    analysis.recent_shooting_pct,
                    analysis.season_ppg,
                    analysis.season_gpg,
                    analysis.season_shooting_pct,
                    analysis.ppg_deviation,
                    analysis.gpg_deviation,
                    analysis.shooting_pct_deviation,
                    analysis.momentum_state.value,
                    analysis.momentum_score,
                    analysis.confidence,
                ),
            )

    def get_player_momentum(
        self,
        player_id: int,
        date: str,
        window_games: int = 10,
    ) -> Optional[MomentumAnalysis]:
        """
        Get stored momentum analysis for a player.

        Args:
            player_id: NHL player ID
            date: Date of analysis
            window_games: Window size

        Returns:
            MomentumAnalysis or None if not found
        """
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM player_momentum
                WHERE player_id = ?
                AND calculated_date = ?
                AND window_games = ?
                """,
                (player_id, date, window_games),
            )
            row = cur.fetchone()

            if not row:
                return None

            return MomentumAnalysis(
                player_id=row["player_id"],
                calculated_date=row["calculated_date"],
                season=row["season"],
                window_games=row["window_games"],
                games_in_window=row["games_in_window"] or 0,
                recent_goals=row["recent_goals"] or 0,
                recent_assists=row["recent_assists"] or 0,
                recent_points=row["recent_points"] or 0,
                recent_shots=row["recent_shots"] or 0,
                recent_ppg=row["recent_ppg"] or 0.0,
                recent_gpg=row["recent_gpg"] or 0.0,
                recent_shooting_pct=row["recent_shooting_pct"] or 0.0,
                season_ppg=row["season_ppg"] or 0.0,
                season_gpg=row["season_gpg"] or 0.0,
                season_shooting_pct=row["season_shooting_pct"] or 0.0,
                ppg_deviation=row["ppg_deviation"] or 0.0,
                gpg_deviation=row["gpg_deviation"] or 0.0,
                shooting_pct_deviation=row["shooting_pct_deviation"] or 0.0,
                momentum_state=MomentumState(row["momentum_state"] or "neutral"),
                momentum_score=row["momentum_score"] or 0.0,
                confidence=row["confidence"] or 0.0,
            )

    def analyze_all_players(
        self,
        season: int,
        as_of_date: Optional[str] = None,
    ) -> dict[int, dict[int, MomentumAnalysis]]:
        """
        Analyze momentum for all players in a season.

        Args:
            season: Season identifier
            as_of_date: Date to analyze as of

        Returns:
            Dictionary mapping player_id to {window_size: MomentumAnalysis}
        """
        # Get all skaters with game stats this season
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT pgs.player_id
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                JOIN players p ON pgs.player_id = p.player_id
                WHERE g.season = ? AND p.position != 'G'
                """,
                (season,),
            )
            player_ids = [row["player_id"] for row in cur.fetchall()]

        logger.info(f"Analyzing momentum for {len(player_ids)} players")

        results: dict[int, dict[int, MomentumAnalysis]] = {}

        for i, player_id in enumerate(player_ids):
            if (i + 1) % 100 == 0:
                logger.info(f"Processing player {i + 1}/{len(player_ids)}")

            player_results: dict[int, MomentumAnalysis] = {}

            for window in MOMENTUM_CONFIG["windows"]:
                analysis = self.analyze_momentum(
                    player_id=player_id,
                    season=season,
                    as_of_date=as_of_date,
                    window_games=window,
                )
                self.save_momentum_analysis(analysis)
                player_results[window] = analysis

            results[player_id] = player_results

        # Log summary
        hot_count = sum(
            1 for player_results in results.values()
            for analysis in player_results.values()
            if analysis.momentum_state == MomentumState.HOT
        )
        cold_count = sum(
            1 for player_results in results.values()
            for analysis in player_results.values()
            if analysis.momentum_state == MomentumState.COLD
        )

        logger.info(
            f"Momentum analysis complete: {hot_count} hot streak instances, "
            f"{cold_count} slump instances"
        )

        return results

    def get_hot_players(
        self,
        season: int,
        date: str,
        window_games: int = 10,
        min_confidence: float = 0.3,
    ) -> list[dict[str, Any]]:
        """
        Get all players currently on a hot streak.

        Args:
            season: Season identifier
            date: Date to check
            window_games: Window size
            min_confidence: Minimum confidence threshold

        Returns:
            List of player info with momentum details
        """
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pm.*,
                    p.full_name,
                    p.position,
                    p.current_team_abbrev
                FROM player_momentum pm
                JOIN players p ON pm.player_id = p.player_id
                WHERE pm.calculated_date = ?
                AND pm.window_games = ?
                AND pm.season = ?
                AND pm.momentum_state = 'hot'
                AND pm.confidence >= ?
                ORDER BY pm.momentum_score DESC
                """,
                (date, window_games, season, min_confidence),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_cold_players(
        self,
        season: int,
        date: str,
        window_games: int = 10,
        min_confidence: float = 0.3,
    ) -> list[dict[str, Any]]:
        """
        Get all players currently in a slump.

        Args:
            season: Season identifier
            date: Date to check
            window_games: Window size
            min_confidence: Minimum confidence threshold

        Returns:
            List of player info with momentum details
        """
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pm.*,
                    p.full_name,
                    p.position,
                    p.current_team_abbrev
                FROM player_momentum pm
                JOIN players p ON pm.player_id = p.player_id
                WHERE pm.calculated_date = ?
                AND pm.window_games = ?
                AND pm.season = ?
                AND pm.momentum_state = 'cold'
                AND pm.confidence >= ?
                ORDER BY pm.momentum_score ASC
                """,
                (date, window_games, season, min_confidence),
            )
            return [dict(row) for row in cur.fetchall()]


def run_pipeline(
    season: int,
    as_of_date: Optional[str] = None,
    db: Optional[Database] = None,
) -> dict[str, Any]:
    """
    Run the momentum detection pipeline.

    Args:
        season: Season identifier
        as_of_date: Date to analyze as of
        db: Database instance

    Returns:
        Dictionary with processing summary
    """
    pipeline = MomentumPipeline(db=db)

    date = as_of_date or datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Starting momentum pipeline for season {season}, as of {date}")

    results = pipeline.analyze_all_players(season, as_of_date=date)

    # Count states across all windows
    hot_count = 0
    cold_count = 0
    neutral_count = 0

    for player_results in results.values():
        for analysis in player_results.values():
            if analysis.momentum_state == MomentumState.HOT:
                hot_count += 1
            elif analysis.momentum_state == MomentumState.COLD:
                cold_count += 1
            else:
                neutral_count += 1

    return {
        "players_analyzed": len(results),
        "date": date,
        "hot_instances": hot_count,
        "cold_instances": cold_count,
        "neutral_instances": neutral_count,
    }
