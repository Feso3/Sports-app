"""
Matchup History Pipeline

Extracts and aggregates player/goalie stats against specific opponents.
Computes similarity scores between matchup and general data.
Calculates weighting for simulation blending.

Reference: docs/simulation-logic-design.md
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from ..database.db import Database, get_database


@dataclass
class PlayerMatchupStats:
    """Player statistics against a specific opponent."""

    player_id: int
    opponent_team_abbrev: str
    season: int

    # Sample size
    games_played: int = 0

    # Raw stats
    goals: int = 0
    assists: int = 0
    points: int = 0
    shots: int = 0
    toi_seconds: int = 0
    power_play_goals: int = 0
    game_winning_goals: int = 0

    # Calculated rates (populated after aggregation)
    goals_per_game: float = 0.0
    assists_per_game: float = 0.0
    points_per_game: float = 0.0
    shots_per_game: float = 0.0
    shooting_pct: float = 0.0
    toi_per_game_seconds: float = 0.0

    def calculate_rates(self) -> None:
        """Calculate per-game rates from raw stats."""
        if self.games_played > 0:
            self.goals_per_game = self.goals / self.games_played
            self.assists_per_game = self.assists / self.games_played
            self.points_per_game = self.points / self.games_played
            self.shots_per_game = self.shots / self.games_played
            self.toi_per_game_seconds = self.toi_seconds / self.games_played

        if self.shots > 0:
            self.shooting_pct = (self.goals / self.shots) * 100


@dataclass
class PlayerSeasonStats:
    """Player season aggregate statistics."""

    player_id: int
    season: int

    # Sample size
    games_played: int = 0

    # Raw stats
    goals: int = 0
    assists: int = 0
    points: int = 0
    shots: int = 0
    toi_seconds: int = 0
    power_play_goals: int = 0
    game_winning_goals: int = 0

    # Calculated rates
    goals_per_game: float = 0.0
    assists_per_game: float = 0.0
    points_per_game: float = 0.0
    shots_per_game: float = 0.0
    shooting_pct: float = 0.0
    toi_per_game_seconds: float = 0.0

    # Standard deviations (for similarity scoring)
    goals_per_game_std: float = 0.0
    points_per_game_std: float = 0.0
    shots_per_game_std: float = 0.0
    shooting_pct_std: float = 0.0

    def calculate_rates(self) -> None:
        """Calculate per-game rates from raw stats."""
        if self.games_played > 0:
            self.goals_per_game = self.goals / self.games_played
            self.assists_per_game = self.assists / self.games_played
            self.points_per_game = self.points / self.games_played
            self.shots_per_game = self.shots / self.games_played
            self.toi_per_game_seconds = self.toi_seconds / self.games_played

        if self.shots > 0:
            self.shooting_pct = (self.goals / self.shots) * 100


@dataclass
class GoalieMatchupStats:
    """Goalie statistics against a specific opponent."""

    goalie_id: int
    opponent_team_abbrev: str
    season: int

    # Sample size
    games_played: int = 0
    games_started: int = 0

    # Raw stats
    shots_against: int = 0
    goals_against: int = 0
    saves: int = 0
    wins: int = 0
    losses: int = 0
    ot_losses: int = 0
    shutouts: int = 0
    toi_seconds: int = 0

    # Calculated rates
    save_pct: float = 0.0
    gaa: float = 0.0

    def calculate_rates(self) -> None:
        """Calculate save percentage and GAA."""
        if self.shots_against > 0:
            self.save_pct = self.saves / self.shots_against

        if self.toi_seconds > 0:
            # GAA = goals against per 60 minutes
            self.gaa = (self.goals_against / self.toi_seconds) * 3600


@dataclass
class GoalieSeasonStats:
    """Goalie season aggregate statistics."""

    goalie_id: int
    season: int

    # Sample size
    games_played: int = 0
    games_started: int = 0

    # Raw stats
    shots_against: int = 0
    goals_against: int = 0
    saves: int = 0
    wins: int = 0
    losses: int = 0
    ot_losses: int = 0
    shutouts: int = 0
    toi_seconds: int = 0

    # Calculated rates
    save_pct: float = 0.0
    gaa: float = 0.0

    # Standard deviations
    save_pct_std: float = 0.0
    gaa_std: float = 0.0

    def calculate_rates(self) -> None:
        """Calculate save percentage and GAA."""
        if self.shots_against > 0:
            self.save_pct = self.saves / self.shots_against

        if self.toi_seconds > 0:
            self.gaa = (self.goals_against / self.toi_seconds) * 3600


@dataclass
class SimilarityResult:
    """Result of comparing matchup stats to general stats."""

    player_id: int
    opponent_team_abbrev: str
    season: int

    # Sample sizes
    general_games: int = 0
    matchup_games: int = 0

    # Deviation scores (z-scores)
    goals_deviation: float = 0.0
    points_deviation: float = 0.0
    shots_deviation: float = 0.0
    shooting_deviation: float = 0.0

    # Overall similarity (0-1, higher = more similar)
    similarity_score: float = 0.0

    # Recommended weights
    general_weight: float = 1.0
    matchup_weight: float = 0.0

    # Confidence level
    confidence: str = "low"  # low, medium, high


@dataclass
class MatchupWeights:
    """Calculated weights for blending general vs matchup data."""

    general_weight: float = 1.0
    matchup_weight: float = 0.0
    confidence: float = 0.0
    reason: str = ""


class MatchupHistoryPipeline:
    """
    Pipeline for extracting and analyzing player matchup history.

    Workflow:
    1. Extract player stats vs specific opponents from player_game_stats
    2. Aggregate season totals for comparison
    3. Calculate standard deviations for similarity scoring
    4. Compute similarity between matchup and general data
    5. Determine weighting for simulation
    """

    # Minimum sample sizes
    MIN_MATCHUP_GAMES = 3   # Minimum games for any matchup weight
    FULL_MATCHUP_GAMES = 10  # Full confidence in matchup data

    def __init__(self, db: Optional[Database] = None):
        """Initialize pipeline with database connection."""
        self.db = db or get_database()

    # -------------------------------------------------------------------------
    # Player Season Stats
    # -------------------------------------------------------------------------

    def aggregate_player_season_stats(
        self,
        player_id: int,
        season: int,
    ) -> PlayerSeasonStats:
        """
        Aggregate player's season totals with variance statistics.

        Args:
            player_id: NHL player ID
            season: Season identifier

        Returns:
            PlayerSeasonStats with rates and standard deviations
        """
        stats = PlayerSeasonStats(player_id=player_id, season=season)

        with self.db.cursor() as cur:
            # Get season totals
            cur.execute(
                """
                SELECT
                    COUNT(*) as games,
                    SUM(goals) as goals,
                    SUM(assists) as assists,
                    SUM(points) as points,
                    SUM(shots) as shots,
                    SUM(toi_seconds) as toi,
                    SUM(power_play_goals) as ppg,
                    SUM(game_winning_goals) as gwg
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id = ? AND g.season = ?
                """,
                (player_id, season),
            )
            row = cur.fetchone()

            if row and row["games"]:
                stats.games_played = row["games"]
                stats.goals = row["goals"] or 0
                stats.assists = row["assists"] or 0
                stats.points = row["points"] or 0
                stats.shots = row["shots"] or 0
                stats.toi_seconds = row["toi"] or 0
                stats.power_play_goals = row["ppg"] or 0
                stats.game_winning_goals = row["gwg"] or 0

            # Calculate game-by-game stats for standard deviation
            cur.execute(
                """
                SELECT goals, points, shots
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id = ? AND g.season = ?
                """,
                (player_id, season),
            )
            game_stats = [dict(row) for row in cur.fetchall()]

        stats.calculate_rates()

        # Calculate standard deviations
        if len(game_stats) >= 2:
            stats.goals_per_game_std = self._calculate_std(
                [g["goals"] for g in game_stats]
            )
            stats.points_per_game_std = self._calculate_std(
                [g["points"] for g in game_stats]
            )
            stats.shots_per_game_std = self._calculate_std(
                [g["shots"] for g in game_stats]
            )

            # Shooting percentage std (only for games with shots)
            shooting_pcts = [
                g["goals"] / g["shots"] * 100
                for g in game_stats
                if g["shots"] and g["shots"] > 0
            ]
            if len(shooting_pcts) >= 2:
                stats.shooting_pct_std = self._calculate_std(shooting_pcts)

        return stats

    def _calculate_std(self, values: list[float]) -> float:
        """Calculate standard deviation of a list of values."""
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)

    def save_player_season_stats(self, stats: PlayerSeasonStats) -> None:
        """Save player season stats to database."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO player_season_stats (
                    player_id, season, games_played,
                    goals, assists, points, shots, toi_seconds,
                    power_play_goals, game_winning_goals,
                    goals_per_game, assists_per_game, points_per_game,
                    shots_per_game, shooting_pct, toi_per_game_seconds,
                    goals_per_game_std, points_per_game_std,
                    shots_per_game_std, shooting_pct_std,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, season) DO UPDATE SET
                    games_played = excluded.games_played,
                    goals = excluded.goals,
                    assists = excluded.assists,
                    points = excluded.points,
                    shots = excluded.shots,
                    toi_seconds = excluded.toi_seconds,
                    power_play_goals = excluded.power_play_goals,
                    game_winning_goals = excluded.game_winning_goals,
                    goals_per_game = excluded.goals_per_game,
                    assists_per_game = excluded.assists_per_game,
                    points_per_game = excluded.points_per_game,
                    shots_per_game = excluded.shots_per_game,
                    shooting_pct = excluded.shooting_pct,
                    toi_per_game_seconds = excluded.toi_per_game_seconds,
                    goals_per_game_std = excluded.goals_per_game_std,
                    points_per_game_std = excluded.points_per_game_std,
                    shots_per_game_std = excluded.shots_per_game_std,
                    shooting_pct_std = excluded.shooting_pct_std,
                    updated_at = excluded.updated_at
                """,
                (
                    stats.player_id,
                    stats.season,
                    stats.games_played,
                    stats.goals,
                    stats.assists,
                    stats.points,
                    stats.shots,
                    stats.toi_seconds,
                    stats.power_play_goals,
                    stats.game_winning_goals,
                    stats.goals_per_game,
                    stats.assists_per_game,
                    stats.points_per_game,
                    stats.shots_per_game,
                    stats.shooting_pct,
                    stats.toi_per_game_seconds,
                    stats.goals_per_game_std,
                    stats.points_per_game_std,
                    stats.shots_per_game_std,
                    stats.shooting_pct_std,
                    datetime.now().isoformat(),
                ),
            )

    # -------------------------------------------------------------------------
    # Player Matchup Stats
    # -------------------------------------------------------------------------

    def aggregate_player_matchup_stats(
        self,
        player_id: int,
        opponent_team_abbrev: str,
        season: int,
    ) -> PlayerMatchupStats:
        """
        Aggregate player's stats against a specific opponent.

        Args:
            player_id: NHL player ID
            opponent_team_abbrev: Opponent team abbreviation
            season: Season identifier

        Returns:
            PlayerMatchupStats with aggregated totals
        """
        stats = PlayerMatchupStats(
            player_id=player_id,
            opponent_team_abbrev=opponent_team_abbrev,
            season=season,
        )

        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) as games,
                    SUM(goals) as goals,
                    SUM(assists) as assists,
                    SUM(points) as points,
                    SUM(shots) as shots,
                    SUM(toi_seconds) as toi,
                    SUM(power_play_goals) as ppg,
                    SUM(game_winning_goals) as gwg
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id = ?
                AND pgs.opponent_abbrev = ?
                AND g.season = ?
                """,
                (player_id, opponent_team_abbrev, season),
            )
            row = cur.fetchone()

            if row and row["games"]:
                stats.games_played = row["games"]
                stats.goals = row["goals"] or 0
                stats.assists = row["assists"] or 0
                stats.points = row["points"] or 0
                stats.shots = row["shots"] or 0
                stats.toi_seconds = row["toi"] or 0
                stats.power_play_goals = row["ppg"] or 0
                stats.game_winning_goals = row["gwg"] or 0

        stats.calculate_rates()
        return stats

    def save_player_matchup_stats(self, stats: PlayerMatchupStats) -> None:
        """Save player matchup stats to database."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO player_matchup_stats (
                    player_id, opponent_team_abbrev, season, games_played,
                    goals, assists, points, shots, toi_seconds,
                    power_play_goals, game_winning_goals,
                    goals_per_game, assists_per_game, points_per_game,
                    shots_per_game, shooting_pct, toi_per_game_seconds,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, opponent_team_abbrev, season) DO UPDATE SET
                    games_played = excluded.games_played,
                    goals = excluded.goals,
                    assists = excluded.assists,
                    points = excluded.points,
                    shots = excluded.shots,
                    toi_seconds = excluded.toi_seconds,
                    power_play_goals = excluded.power_play_goals,
                    game_winning_goals = excluded.game_winning_goals,
                    goals_per_game = excluded.goals_per_game,
                    assists_per_game = excluded.assists_per_game,
                    points_per_game = excluded.points_per_game,
                    shots_per_game = excluded.shots_per_game,
                    shooting_pct = excluded.shooting_pct,
                    toi_per_game_seconds = excluded.toi_per_game_seconds,
                    updated_at = excluded.updated_at
                """,
                (
                    stats.player_id,
                    stats.opponent_team_abbrev,
                    stats.season,
                    stats.games_played,
                    stats.goals,
                    stats.assists,
                    stats.points,
                    stats.shots,
                    stats.toi_seconds,
                    stats.power_play_goals,
                    stats.game_winning_goals,
                    stats.goals_per_game,
                    stats.assists_per_game,
                    stats.points_per_game,
                    stats.shots_per_game,
                    stats.shooting_pct,
                    stats.toi_per_game_seconds,
                    datetime.now().isoformat(),
                ),
            )

    # -------------------------------------------------------------------------
    # Goalie Stats (Season and Matchup)
    # -------------------------------------------------------------------------

    def aggregate_goalie_season_stats(
        self,
        goalie_id: int,
        season: int,
    ) -> GoalieSeasonStats:
        """Aggregate goalie's season totals."""
        stats = GoalieSeasonStats(goalie_id=goalie_id, season=season)

        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) as games,
                    SUM(CASE WHEN games_started = 1 THEN 1 ELSE 0 END) as starts,
                    SUM(shots_against) as sa,
                    SUM(goals_against) as ga,
                    SUM(saves) as saves,
                    SUM(wins) as wins,
                    SUM(losses) as losses,
                    SUM(ot_losses) as otl,
                    SUM(shutouts) as so,
                    SUM(toi_seconds) as toi
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                JOIN players p ON pgs.player_id = p.player_id
                WHERE pgs.player_id = ? AND g.season = ? AND p.position = 'G'
                """,
                (goalie_id, season),
            )
            row = cur.fetchone()

            if row and row["games"]:
                stats.games_played = row["games"]
                stats.games_started = row["starts"] or 0
                stats.shots_against = row["sa"] or 0
                stats.goals_against = row["ga"] or 0
                stats.saves = row["saves"] or 0
                stats.wins = row["wins"] or 0
                stats.losses = row["losses"] or 0
                stats.ot_losses = row["otl"] or 0
                stats.shutouts = row["so"] or 0
                stats.toi_seconds = row["toi"] or 0

        stats.calculate_rates()
        return stats

    def aggregate_goalie_matchup_stats(
        self,
        goalie_id: int,
        opponent_team_abbrev: str,
        season: int,
    ) -> GoalieMatchupStats:
        """Aggregate goalie's stats against a specific opponent."""
        stats = GoalieMatchupStats(
            goalie_id=goalie_id,
            opponent_team_abbrev=opponent_team_abbrev,
            season=season,
        )

        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) as games,
                    SUM(CASE WHEN games_started = 1 THEN 1 ELSE 0 END) as starts,
                    SUM(shots_against) as sa,
                    SUM(goals_against) as ga,
                    SUM(saves) as saves,
                    SUM(wins) as wins,
                    SUM(losses) as losses,
                    SUM(ot_losses) as otl,
                    SUM(shutouts) as so,
                    SUM(toi_seconds) as toi
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                JOIN players p ON pgs.player_id = p.player_id
                WHERE pgs.player_id = ?
                AND pgs.opponent_abbrev = ?
                AND g.season = ?
                AND p.position = 'G'
                """,
                (goalie_id, opponent_team_abbrev, season),
            )
            row = cur.fetchone()

            if row and row["games"]:
                stats.games_played = row["games"]
                stats.games_started = row["starts"] or 0
                stats.shots_against = row["sa"] or 0
                stats.goals_against = row["ga"] or 0
                stats.saves = row["saves"] or 0
                stats.wins = row["wins"] or 0
                stats.losses = row["losses"] or 0
                stats.ot_losses = row["otl"] or 0
                stats.shutouts = row["so"] or 0
                stats.toi_seconds = row["toi"] or 0

        stats.calculate_rates()
        return stats

    def save_goalie_season_stats(self, stats: GoalieSeasonStats) -> None:
        """Save goalie season stats to database."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO goalie_season_stats (
                    goalie_id, season, games_played, games_started,
                    shots_against, goals_against, saves,
                    wins, losses, ot_losses, shutouts, toi_seconds,
                    save_pct, gaa, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(goalie_id, season) DO UPDATE SET
                    games_played = excluded.games_played,
                    games_started = excluded.games_started,
                    shots_against = excluded.shots_against,
                    goals_against = excluded.goals_against,
                    saves = excluded.saves,
                    wins = excluded.wins,
                    losses = excluded.losses,
                    ot_losses = excluded.ot_losses,
                    shutouts = excluded.shutouts,
                    toi_seconds = excluded.toi_seconds,
                    save_pct = excluded.save_pct,
                    gaa = excluded.gaa,
                    updated_at = excluded.updated_at
                """,
                (
                    stats.goalie_id,
                    stats.season,
                    stats.games_played,
                    stats.games_started,
                    stats.shots_against,
                    stats.goals_against,
                    stats.saves,
                    stats.wins,
                    stats.losses,
                    stats.ot_losses,
                    stats.shutouts,
                    stats.toi_seconds,
                    stats.save_pct,
                    stats.gaa,
                    datetime.now().isoformat(),
                ),
            )

    def save_goalie_matchup_stats(self, stats: GoalieMatchupStats) -> None:
        """Save goalie matchup stats to database."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO goalie_matchup_stats (
                    goalie_id, opponent_team_abbrev, season,
                    games_played, games_started,
                    shots_against, goals_against, saves,
                    wins, losses, ot_losses, shutouts, toi_seconds,
                    save_pct, gaa, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(goalie_id, opponent_team_abbrev, season) DO UPDATE SET
                    games_played = excluded.games_played,
                    games_started = excluded.games_started,
                    shots_against = excluded.shots_against,
                    goals_against = excluded.goals_against,
                    saves = excluded.saves,
                    wins = excluded.wins,
                    losses = excluded.losses,
                    ot_losses = excluded.ot_losses,
                    shutouts = excluded.shutouts,
                    toi_seconds = excluded.toi_seconds,
                    save_pct = excluded.save_pct,
                    gaa = excluded.gaa,
                    updated_at = excluded.updated_at
                """,
                (
                    stats.goalie_id,
                    stats.opponent_team_abbrev,
                    stats.season,
                    stats.games_played,
                    stats.games_started,
                    stats.shots_against,
                    stats.goals_against,
                    stats.saves,
                    stats.wins,
                    stats.losses,
                    stats.ot_losses,
                    stats.shutouts,
                    stats.toi_seconds,
                    stats.save_pct,
                    stats.gaa,
                    datetime.now().isoformat(),
                ),
            )

    # -------------------------------------------------------------------------
    # Similarity Scoring
    # -------------------------------------------------------------------------

    def calculate_similarity(
        self,
        general_stats: PlayerSeasonStats,
        matchup_stats: PlayerMatchupStats,
    ) -> SimilarityResult:
        """
        Calculate similarity between matchup and general data.

        Higher similarity (closer to 1.0) means matchup data is similar
        to general data, so we should weight general data more heavily.

        Lower similarity means matchup data differs significantly,
        suggesting opponent-specific effects.

        Args:
            general_stats: Player's season aggregate stats
            matchup_stats: Player's stats vs specific opponent

        Returns:
            SimilarityResult with scores and weights
        """
        result = SimilarityResult(
            player_id=matchup_stats.player_id,
            opponent_team_abbrev=matchup_stats.opponent_team_abbrev,
            season=matchup_stats.season,
            general_games=general_stats.games_played,
            matchup_games=matchup_stats.games_played,
        )

        # Not enough data for matchup analysis
        if matchup_stats.games_played < self.MIN_MATCHUP_GAMES:
            result.similarity_score = 1.0  # Treat as similar (use general data)
            result.general_weight = 1.0
            result.matchup_weight = 0.0
            result.confidence = "low"
            return result

        # Calculate z-scores for each metric
        deviations = []

        # Goals per game deviation
        if general_stats.goals_per_game_std > 0:
            result.goals_deviation = (
                matchup_stats.goals_per_game - general_stats.goals_per_game
            ) / general_stats.goals_per_game_std
            deviations.append(abs(result.goals_deviation))

        # Points per game deviation
        if general_stats.points_per_game_std > 0:
            result.points_deviation = (
                matchup_stats.points_per_game - general_stats.points_per_game
            ) / general_stats.points_per_game_std
            deviations.append(abs(result.points_deviation))

        # Shots per game deviation
        if general_stats.shots_per_game_std > 0:
            result.shots_deviation = (
                matchup_stats.shots_per_game - general_stats.shots_per_game
            ) / general_stats.shots_per_game_std
            deviations.append(abs(result.shots_deviation))

        # Shooting percentage deviation
        if general_stats.shooting_pct_std > 0 and matchup_stats.shots > 0:
            result.shooting_deviation = (
                matchup_stats.shooting_pct - general_stats.shooting_pct
            ) / general_stats.shooting_pct_std
            deviations.append(abs(result.shooting_deviation))

        # Calculate average deviation
        if deviations:
            avg_deviation = sum(deviations) / len(deviations)

            # Convert to similarity score (higher deviation = lower similarity)
            # Using sigmoid-like transformation
            raw_similarity = max(0, 1 - (avg_deviation / 2))

            # Apply sample confidence penalty
            sample_confidence = min(1.0, matchup_stats.games_played / self.FULL_MATCHUP_GAMES)
            result.similarity_score = raw_similarity * sample_confidence
        else:
            result.similarity_score = 1.0

        # Calculate weights
        weights = self.calculate_matchup_weights(
            result.similarity_score,
            matchup_stats.games_played,
        )
        result.general_weight = weights.general_weight
        result.matchup_weight = weights.matchup_weight

        # Determine confidence level
        if matchup_stats.games_played >= self.FULL_MATCHUP_GAMES:
            result.confidence = "high"
        elif matchup_stats.games_played >= self.MIN_MATCHUP_GAMES:
            result.confidence = "medium"
        else:
            result.confidence = "low"

        return result

    def calculate_matchup_weights(
        self,
        similarity_score: float,
        matchup_games: int,
    ) -> MatchupWeights:
        """
        Calculate weights for blending general vs matchup data.

        Args:
            similarity_score: 0-1 score (1 = very similar)
            matchup_games: Number of games vs this opponent

        Returns:
            MatchupWeights with general_weight and matchup_weight
        """
        if matchup_games < self.MIN_MATCHUP_GAMES:
            return MatchupWeights(
                general_weight=1.0,
                matchup_weight=0.0,
                confidence=0.0,
                reason=f"Insufficient sample ({matchup_games} < {self.MIN_MATCHUP_GAMES} games)"
            )

        # Base matchup weight inversely related to similarity
        # Different = high matchup weight, Similar = low matchup weight
        base_matchup_weight = 1.0 - similarity_score

        # Scale by sample confidence
        sample_confidence = min(1.0, matchup_games / self.FULL_MATCHUP_GAMES)
        matchup_weight = base_matchup_weight * sample_confidence

        # Ensure weights sum to 1
        general_weight = 1.0 - matchup_weight

        reason = f"Similarity={similarity_score:.2f}, Sample={matchup_games} games"

        return MatchupWeights(
            general_weight=general_weight,
            matchup_weight=matchup_weight,
            confidence=sample_confidence,
            reason=reason,
        )

    # -------------------------------------------------------------------------
    # Batch Processing
    # -------------------------------------------------------------------------

    def process_player_all_opponents(
        self,
        player_id: int,
        season: int,
    ) -> dict[str, PlayerMatchupStats]:
        """
        Process a player's stats against all opponents.

        Args:
            player_id: NHL player ID
            season: Season identifier

        Returns:
            Dictionary mapping opponent_abbrev to matchup stats
        """
        # Get all opponents faced
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT opponent_abbrev
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id = ? AND g.season = ?
                AND opponent_abbrev IS NOT NULL
                """,
                (player_id, season),
            )
            opponents = [row["opponent_abbrev"] for row in cur.fetchall()]

        results: dict[str, PlayerMatchupStats] = {}

        for opp in opponents:
            if not opp:
                continue
            stats = self.aggregate_player_matchup_stats(player_id, opp, season)
            self.save_player_matchup_stats(stats)
            results[opp] = stats

        return results

    def process_all_players(self, season: int) -> int:
        """
        Process matchup stats for all players in a season.

        Args:
            season: Season identifier

        Returns:
            Number of players processed
        """
        # Get all players with game stats this season
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

        logger.info(f"Processing {len(player_ids)} players for matchup stats")

        for i, player_id in enumerate(player_ids):
            if (i + 1) % 100 == 0:
                logger.info(f"Processing player {i + 1}/{len(player_ids)}")

            # Season stats
            season_stats = self.aggregate_player_season_stats(player_id, season)
            self.save_player_season_stats(season_stats)

            # Matchup stats
            self.process_player_all_opponents(player_id, season)

        return len(player_ids)

    def process_all_goalies(self, season: int) -> int:
        """
        Process matchup stats for all goalies in a season.

        Args:
            season: Season identifier

        Returns:
            Number of goalies processed
        """
        # Get all goalies with game stats this season
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT pgs.player_id
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                JOIN players p ON pgs.player_id = p.player_id
                WHERE g.season = ? AND p.position = 'G'
                """,
                (season,),
            )
            goalie_ids = [row["player_id"] for row in cur.fetchall()]

        logger.info(f"Processing {len(goalie_ids)} goalies for matchup stats")

        for goalie_id in goalie_ids:
            # Season stats
            season_stats = self.aggregate_goalie_season_stats(goalie_id, season)
            self.save_goalie_season_stats(season_stats)

            # Get all opponents faced
            with self.db.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT opponent_abbrev
                    FROM player_game_stats pgs
                    JOIN games g ON pgs.game_id = g.game_id
                    WHERE pgs.player_id = ? AND g.season = ?
                    AND opponent_abbrev IS NOT NULL
                    """,
                    (goalie_id, season),
                )
                opponents = [row["opponent_abbrev"] for row in cur.fetchall()]

            for opp in opponents:
                if not opp:
                    continue
                stats = self.aggregate_goalie_matchup_stats(goalie_id, opp, season)
                self.save_goalie_matchup_stats(stats)

        return len(goalie_ids)


def run_pipeline(
    season: int,
    db: Optional[Database] = None,
) -> dict[str, int]:
    """
    Run the matchup history pipeline.

    Args:
        season: Season identifier
        db: Database instance

    Returns:
        Dictionary with processing counts
    """
    pipeline = MatchupHistoryPipeline(db=db)

    logger.info(f"Starting matchup history pipeline for season {season}")

    players_processed = pipeline.process_all_players(season)
    goalies_processed = pipeline.process_all_goalies(season)

    logger.info(
        f"Matchup pipeline complete: {players_processed} players, "
        f"{goalies_processed} goalies"
    )

    return {
        "players": players_processed,
        "goalies": goalies_processed,
    }
