"""
Schedule Context Analysis Pipeline

Analyzes team schedules to identify fatigue-related factors:
- Back-to-back games
- Rest days between games
- Games in rolling windows (3, 5, 7 days)
- Win/loss streaks

Reference: docs/simulation-logic-design.md
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from ..database.db import Database, get_database


@dataclass
class ScheduleContext:
    """Schedule context for a team's game."""

    team_abbrev: str
    game_id: int
    game_date: str

    # Rest analysis
    days_rest: Optional[int] = None  # Days since last game
    is_back_to_back: bool = False    # Second game in 2 days
    is_first_of_back_to_back: bool = False  # First game of back-to-back

    # Workload windows
    games_in_3_days: int = 1
    games_in_5_days: int = 1
    games_in_7_days: int = 1

    # Location
    is_home: bool = True

    # Previous game reference
    previous_game_id: Optional[int] = None

    # Streak tracking
    win_streak: int = 0
    loss_streak: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "team_abbrev": self.team_abbrev,
            "game_id": self.game_id,
            "game_date": self.game_date,
            "days_rest": self.days_rest,
            "is_back_to_back": 1 if self.is_back_to_back else 0,
            "is_first_of_back_to_back": 1 if self.is_first_of_back_to_back else 0,
            "games_in_3_days": self.games_in_3_days,
            "games_in_5_days": self.games_in_5_days,
            "games_in_7_days": self.games_in_7_days,
            "is_home": 1 if self.is_home else 0,
            "previous_game_id": self.previous_game_id,
            "win_streak": self.win_streak,
            "loss_streak": self.loss_streak,
        }


@dataclass
class FatigueModifier:
    """Fatigue adjustment factors based on schedule context."""

    # Base modifier (1.0 = no change)
    offensive_modifier: float = 1.0
    defensive_modifier: float = 1.0
    goalie_modifier: float = 1.0

    # Components
    rest_factor: float = 1.0      # Based on days rest
    workload_factor: float = 1.0  # Based on games in window
    streak_factor: float = 1.0    # Based on win/loss momentum

    # Context
    fatigue_level: str = "normal"  # fresh, normal, tired, exhausted
    momentum_state: str = "neutral"  # hot, neutral, cold

    @property
    def combined_modifier(self) -> float:
        """Combined modifier across all factors."""
        return (self.rest_factor + self.workload_factor + self.streak_factor) / 3


# Fatigue thresholds and adjustments
FATIGUE_CONFIG = {
    # Days rest -> offensive modifier
    "rest_modifiers": {
        0: 0.92,   # Back-to-back (8% penalty)
        1: 0.97,   # One day rest (3% penalty)
        2: 1.00,   # Two days rest (baseline)
        3: 1.01,   # Three days rest (1% boost)
        4: 1.00,   # Four+ days (potential rust)
    },
    # Games in 7 days -> workload modifier
    "workload_modifiers": {
        1: 1.02,   # Light week (2% boost)
        2: 1.00,   # Normal week
        3: 0.98,   # Busy week (2% penalty)
        4: 0.95,   # Heavy week (5% penalty)
        5: 0.92,   # Extreme week (8% penalty)
    },
    # Win streak -> momentum modifier
    "win_streak_modifiers": {
        0: 1.00,
        1: 1.00,
        2: 1.01,   # 2-game win streak (1% boost)
        3: 1.02,   # 3-game win streak (2% boost)
        4: 1.03,   # 4+ game streak (3% boost)
    },
    # Loss streak -> momentum modifier
    "loss_streak_modifiers": {
        0: 1.00,
        1: 1.00,
        2: 0.99,   # 2-game loss streak (1% penalty)
        3: 0.98,   # 3-game loss streak (2% penalty)
        4: 0.96,   # 4+ game streak (4% penalty)
    },
}


class ScheduleContextPipeline:
    """
    Pipeline for analyzing team schedules and computing fatigue factors.

    Workflow:
    1. Load team game schedule for season
    2. Calculate rest days between games
    3. Identify back-to-back games
    4. Count games in rolling windows
    5. Track win/loss streaks
    6. Store context in database
    """

    def __init__(self, db: Optional[Database] = None):
        """Initialize pipeline with database connection."""
        self.db = db or get_database()

    def get_team_schedule(
        self,
        team_abbrev: str,
        season: int,
    ) -> list[dict[str, Any]]:
        """
        Get all games for a team in a season, ordered by date.

        Args:
            team_abbrev: Team abbreviation (e.g., 'TOR')
            season: Season identifier (e.g., 20242025)

        Returns:
            List of game records with results
        """
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    g.game_id,
                    g.game_date,
                    g.game_type,
                    g.home_team_abbrev,
                    g.away_team_abbrev,
                    g.home_score,
                    g.away_score,
                    g.game_state,
                    CASE WHEN g.home_team_abbrev = ? THEN 1 ELSE 0 END as is_home,
                    CASE
                        WHEN g.home_team_abbrev = ? AND g.home_score > g.away_score THEN 1
                        WHEN g.away_team_abbrev = ? AND g.away_score > g.home_score THEN 1
                        ELSE 0
                    END as is_win
                FROM games g
                WHERE (g.home_team_abbrev = ? OR g.away_team_abbrev = ?)
                AND g.season = ?
                AND g.game_state = 'OFF'
                ORDER BY g.game_date, g.game_id
                """,
                (team_abbrev, team_abbrev, team_abbrev, team_abbrev, team_abbrev, season),
            )
            return [dict(row) for row in cur.fetchall()]

    def analyze_team_schedule(
        self,
        team_abbrev: str,
        season: int,
    ) -> list[ScheduleContext]:
        """
        Analyze schedule context for all games of a team.

        Args:
            team_abbrev: Team abbreviation
            season: Season identifier

        Returns:
            List of ScheduleContext for each game
        """
        games = self.get_team_schedule(team_abbrev, season)

        if not games:
            logger.warning(f"No games found for {team_abbrev} in season {season}")
            return []

        contexts: list[ScheduleContext] = []

        for i, game in enumerate(games):
            game_date = datetime.strptime(game["game_date"], "%Y-%m-%d")

            ctx = ScheduleContext(
                team_abbrev=team_abbrev,
                game_id=game["game_id"],
                game_date=game["game_date"],
                is_home=bool(game["is_home"]),
            )

            # Calculate days rest
            if i > 0:
                prev_game = games[i - 1]
                prev_date = datetime.strptime(prev_game["game_date"], "%Y-%m-%d")
                ctx.days_rest = (game_date - prev_date).days
                ctx.previous_game_id = prev_game["game_id"]

                # Back-to-back detection
                if ctx.days_rest == 1:
                    ctx.is_back_to_back = True
                    # Mark previous game as first of back-to-back
                    if contexts:
                        contexts[-1].is_first_of_back_to_back = True

            # Count games in rolling windows
            ctx.games_in_3_days = self._count_games_in_window(games, i, game_date, 3)
            ctx.games_in_5_days = self._count_games_in_window(games, i, game_date, 5)
            ctx.games_in_7_days = self._count_games_in_window(games, i, game_date, 7)

            # Calculate win/loss streaks
            ctx.win_streak, ctx.loss_streak = self._calculate_streaks(games, i)

            contexts.append(ctx)

        return contexts

    def _count_games_in_window(
        self,
        games: list[dict],
        current_idx: int,
        current_date: datetime,
        window_days: int,
    ) -> int:
        """Count games within a rolling window centered on current game."""
        count = 1  # Current game
        window_start = current_date - timedelta(days=window_days - 1)
        window_end = current_date + timedelta(days=window_days - 1)

        for j, other_game in enumerate(games):
            if j == current_idx:
                continue
            other_date = datetime.strptime(other_game["game_date"], "%Y-%m-%d")
            if window_start <= other_date <= window_end:
                count += 1

        return count

    def _calculate_streaks(
        self,
        games: list[dict],
        current_idx: int,
    ) -> tuple[int, int]:
        """Calculate current win and loss streaks going into this game."""
        win_streak = 0
        loss_streak = 0

        # Look backwards from current game
        for j in range(current_idx - 1, -1, -1):
            game = games[j]
            is_win = bool(game.get("is_win", 0))

            if j == current_idx - 1:
                # First previous game sets which streak we're on
                if is_win:
                    win_streak = 1
                else:
                    loss_streak = 1
            else:
                # Continue streak or break
                if is_win and win_streak > 0:
                    win_streak += 1
                elif not is_win and loss_streak > 0:
                    loss_streak += 1
                else:
                    break

        return win_streak, loss_streak

    def save_schedule_context(self, contexts: list[ScheduleContext]) -> int:
        """
        Save schedule contexts to database.

        Args:
            contexts: List of ScheduleContext to save

        Returns:
            Number of records saved
        """
        if not contexts:
            return 0

        with self.db.cursor() as cur:
            for ctx in contexts:
                data = ctx.to_dict()
                cur.execute(
                    """
                    INSERT INTO schedule_context (
                        team_abbrev, game_id, game_date, days_rest,
                        is_back_to_back, is_first_of_back_to_back,
                        games_in_3_days, games_in_5_days, games_in_7_days,
                        is_home, previous_game_id, win_streak, loss_streak
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(team_abbrev, game_id) DO UPDATE SET
                        days_rest = excluded.days_rest,
                        is_back_to_back = excluded.is_back_to_back,
                        is_first_of_back_to_back = excluded.is_first_of_back_to_back,
                        games_in_3_days = excluded.games_in_3_days,
                        games_in_5_days = excluded.games_in_5_days,
                        games_in_7_days = excluded.games_in_7_days,
                        is_home = excluded.is_home,
                        previous_game_id = excluded.previous_game_id,
                        win_streak = excluded.win_streak,
                        loss_streak = excluded.loss_streak
                    """,
                    (
                        data["team_abbrev"],
                        data["game_id"],
                        data["game_date"],
                        data["days_rest"],
                        data["is_back_to_back"],
                        data["is_first_of_back_to_back"],
                        data["games_in_3_days"],
                        data["games_in_5_days"],
                        data["games_in_7_days"],
                        data["is_home"],
                        data["previous_game_id"],
                        data["win_streak"],
                        data["loss_streak"],
                    ),
                )

        return len(contexts)

    def get_schedule_context(
        self,
        team_abbrev: str,
        game_id: int,
    ) -> Optional[ScheduleContext]:
        """
        Get schedule context for a specific game.

        Args:
            team_abbrev: Team abbreviation
            game_id: Game identifier

        Returns:
            ScheduleContext or None if not found
        """
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM schedule_context
                WHERE team_abbrev = ? AND game_id = ?
                """,
                (team_abbrev, game_id),
            )
            row = cur.fetchone()

            if not row:
                return None

            return ScheduleContext(
                team_abbrev=row["team_abbrev"],
                game_id=row["game_id"],
                game_date=row["game_date"],
                days_rest=row["days_rest"],
                is_back_to_back=bool(row["is_back_to_back"]),
                is_first_of_back_to_back=bool(row["is_first_of_back_to_back"]),
                games_in_3_days=row["games_in_3_days"],
                games_in_5_days=row["games_in_5_days"],
                games_in_7_days=row["games_in_7_days"],
                is_home=bool(row["is_home"]),
                previous_game_id=row["previous_game_id"],
                win_streak=row["win_streak"],
                loss_streak=row["loss_streak"],
            )

    def calculate_fatigue_modifier(
        self,
        context: ScheduleContext,
    ) -> FatigueModifier:
        """
        Calculate fatigue modifiers based on schedule context.

        Args:
            context: Schedule context for the game

        Returns:
            FatigueModifier with adjustment factors
        """
        modifier = FatigueModifier()

        # Rest factor
        if context.days_rest is not None:
            rest_days = min(context.days_rest, 4)
            modifier.rest_factor = FATIGUE_CONFIG["rest_modifiers"].get(
                rest_days, 1.0
            )

        # Workload factor
        games_7 = min(context.games_in_7_days, 5)
        modifier.workload_factor = FATIGUE_CONFIG["workload_modifiers"].get(
            games_7, 1.0
        )

        # Streak factor
        if context.win_streak > 0:
            streak = min(context.win_streak, 4)
            modifier.streak_factor = FATIGUE_CONFIG["win_streak_modifiers"].get(
                streak, 1.0
            )
            modifier.momentum_state = "hot" if streak >= 2 else "neutral"
        elif context.loss_streak > 0:
            streak = min(context.loss_streak, 4)
            modifier.streak_factor = FATIGUE_CONFIG["loss_streak_modifiers"].get(
                streak, 1.0
            )
            modifier.momentum_state = "cold" if streak >= 2 else "neutral"

        # Determine fatigue level
        combined = modifier.rest_factor * modifier.workload_factor
        if combined >= 1.01:
            modifier.fatigue_level = "fresh"
        elif combined >= 0.98:
            modifier.fatigue_level = "normal"
        elif combined >= 0.94:
            modifier.fatigue_level = "tired"
        else:
            modifier.fatigue_level = "exhausted"

        # Apply combined effects
        modifier.offensive_modifier = combined * modifier.streak_factor
        modifier.defensive_modifier = combined  # Streaks don't affect defense as much
        modifier.goalie_modifier = modifier.rest_factor * 0.5 + modifier.workload_factor * 0.5

        return modifier

    def process_all_teams(self, season: int) -> dict[str, int]:
        """
        Process schedule context for all teams in a season.

        Args:
            season: Season identifier

        Returns:
            Dictionary mapping team_abbrev to games processed
        """
        # Get all unique teams from games table
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT home_team_abbrev as team
                FROM games WHERE season = ?
                UNION
                SELECT DISTINCT away_team_abbrev as team
                FROM games WHERE season = ?
                """,
                (season, season),
            )
            teams = [row["team"] for row in cur.fetchall()]

        results: dict[str, int] = {}

        for team in teams:
            if not team:
                continue

            logger.info(f"Processing schedule for {team}")
            contexts = self.analyze_team_schedule(team, season)
            saved = self.save_schedule_context(contexts)
            results[team] = saved

        logger.info(f"Processed {len(results)} teams, {sum(results.values())} total games")
        return results

    def get_team_fatigue_summary(
        self,
        team_abbrev: str,
        season: int,
    ) -> dict[str, Any]:
        """
        Get summary statistics about team's schedule fatigue.

        Args:
            team_abbrev: Team abbreviation
            season: Season identifier

        Returns:
            Summary dictionary with fatigue statistics
        """
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) as total_games,
                    SUM(is_back_to_back) as back_to_back_games,
                    AVG(days_rest) as avg_days_rest,
                    AVG(games_in_7_days) as avg_games_per_week,
                    MAX(win_streak) as max_win_streak,
                    MAX(loss_streak) as max_loss_streak,
                    SUM(CASE WHEN days_rest = 0 THEN 1 ELSE 0 END) as zero_rest_games,
                    SUM(CASE WHEN days_rest >= 3 THEN 1 ELSE 0 END) as well_rested_games
                FROM schedule_context
                WHERE team_abbrev = ?
                AND game_date LIKE ?
                """,
                (team_abbrev, f"{str(season)[:4]}%"),
            )
            row = cur.fetchone()

            if not row:
                return {}

            return {
                "team_abbrev": team_abbrev,
                "season": season,
                "total_games": row["total_games"] or 0,
                "back_to_back_games": row["back_to_back_games"] or 0,
                "avg_days_rest": round(row["avg_days_rest"] or 0, 2),
                "avg_games_per_week": round(row["avg_games_per_week"] or 0, 2),
                "max_win_streak": row["max_win_streak"] or 0,
                "max_loss_streak": row["max_loss_streak"] or 0,
                "zero_rest_games": row["zero_rest_games"] or 0,
                "well_rested_games": row["well_rested_games"] or 0,
            }


def run_pipeline(
    season: int,
    teams: Optional[list[str]] = None,
    db: Optional[Database] = None,
) -> dict[str, int]:
    """
    Run the schedule context pipeline.

    Args:
        season: Season identifier
        teams: Optional list of team abbreviations to process
        db: Database instance

    Returns:
        Dictionary mapping team_abbrev to games processed
    """
    pipeline = ScheduleContextPipeline(db=db)

    if teams:
        results = {}
        for team in teams:
            logger.info(f"Processing schedule for {team}")
            contexts = pipeline.analyze_team_schedule(team, season)
            saved = pipeline.save_schedule_context(contexts)
            results[team] = saved
        return results
    else:
        return pipeline.process_all_teams(season)
