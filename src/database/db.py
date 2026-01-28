"""Database connection and helper functions for NHL player data collection."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "nhl_players.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    """SQLite database wrapper for NHL player data."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file. Defaults to data/nhl_players.db
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[sqlite3.Connection] = None

    @property
    def connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(str(self.db_path))
            self._connection.row_factory = sqlite3.Row
            # Enable foreign keys
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

    def close(self) -> None:
        """Close database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @contextmanager
    def cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for database cursor with auto-commit."""
        cur = self.connection.cursor()
        try:
            yield cur
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        finally:
            cur.close()

    def initialize(self) -> None:
        """Initialize database schema from schema.sql."""
        schema_sql = SCHEMA_PATH.read_text()
        with self.cursor() as cur:
            cur.executescript(schema_sql)

    def is_initialized(self) -> bool:
        """Check if database has been initialized with schema."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='players'"
            )
            return cur.fetchone() is not None

    # -------------------------------------------------------------------------
    # Player operations
    # -------------------------------------------------------------------------

    def insert_player(self, player: dict[str, Any]) -> None:
        """Insert or update a player record.

        Args:
            player: Dictionary with player data
        """
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO players (
                    player_id, full_name, first_name, last_name, position,
                    shoots_catches, height_inches, weight_lbs, birth_date,
                    birth_city, birth_country, current_team_id, current_team_abbrev,
                    jersey_number, is_active, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    position = excluded.position,
                    shoots_catches = excluded.shoots_catches,
                    height_inches = excluded.height_inches,
                    weight_lbs = excluded.weight_lbs,
                    current_team_id = excluded.current_team_id,
                    current_team_abbrev = excluded.current_team_abbrev,
                    jersey_number = excluded.jersey_number,
                    is_active = excluded.is_active,
                    updated_at = excluded.updated_at
                """,
                (
                    player.get("player_id"),
                    player.get("full_name"),
                    player.get("first_name"),
                    player.get("last_name"),
                    player.get("position"),
                    player.get("shoots_catches"),
                    player.get("height_inches"),
                    player.get("weight_lbs"),
                    player.get("birth_date"),
                    player.get("birth_city"),
                    player.get("birth_country"),
                    player.get("current_team_id"),
                    player.get("current_team_abbrev"),
                    player.get("jersey_number"),
                    1 if player.get("is_active", True) else 0,
                    datetime.now().isoformat(),
                ),
            )

    def get_player(self, player_id: int) -> Optional[dict[str, Any]]:
        """Get a player by ID.

        Args:
            player_id: NHL player ID

        Returns:
            Player data as dictionary or None if not found
        """
        with self.cursor() as cur:
            cur.execute("SELECT * FROM players WHERE player_id = ?", (player_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_player_ids(self, active_only: bool = True) -> list[int]:
        """Get all player IDs in database.

        Args:
            active_only: Only return active players

        Returns:
            List of player IDs
        """
        with self.cursor() as cur:
            if active_only:
                cur.execute("SELECT player_id FROM players WHERE is_active = 1")
            else:
                cur.execute("SELECT player_id FROM players")
            return [row["player_id"] for row in cur.fetchall()]

    def get_player_count(self, active_only: bool = True) -> int:
        """Get count of players in database."""
        with self.cursor() as cur:
            if active_only:
                cur.execute("SELECT COUNT(*) as count FROM players WHERE is_active = 1")
            else:
                cur.execute("SELECT COUNT(*) as count FROM players")
            return cur.fetchone()["count"]

    # -------------------------------------------------------------------------
    # Game operations
    # -------------------------------------------------------------------------

    def insert_game(self, game: dict[str, Any]) -> None:
        """Insert or update a game record.

        Args:
            game: Dictionary with game data
        """
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO games (
                    game_id, season, game_type, game_date, home_team_id,
                    home_team_abbrev, away_team_id, away_team_abbrev,
                    home_score, away_score, game_state, venue
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(game_id) DO UPDATE SET
                    home_score = excluded.home_score,
                    away_score = excluded.away_score,
                    game_state = excluded.game_state
                """,
                (
                    game.get("game_id"),
                    game.get("season"),
                    game.get("game_type"),
                    game.get("game_date"),
                    game.get("home_team_id"),
                    game.get("home_team_abbrev"),
                    game.get("away_team_id"),
                    game.get("away_team_abbrev"),
                    game.get("home_score"),
                    game.get("away_score"),
                    game.get("game_state"),
                    game.get("venue"),
                ),
            )

    def get_game(self, game_id: int) -> Optional[dict[str, Any]]:
        """Get a game by ID."""
        with self.cursor() as cur:
            cur.execute("SELECT * FROM games WHERE game_id = ?", (game_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_game_count(self, season: Optional[int] = None) -> int:
        """Get count of games in database."""
        with self.cursor() as cur:
            if season:
                cur.execute(
                    "SELECT COUNT(*) as count FROM games WHERE season = ?", (season,)
                )
            else:
                cur.execute("SELECT COUNT(*) as count FROM games")
            return cur.fetchone()["count"]

    # -------------------------------------------------------------------------
    # Player game stats operations
    # -------------------------------------------------------------------------

    def insert_player_game_stats(self, stats: dict[str, Any]) -> None:
        """Insert or update player game stats.

        Args:
            stats: Dictionary with player game statistics
        """
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO player_game_stats (
                    player_id, game_id, team_abbrev, opponent_abbrev, is_home,
                    goals, assists, points, plus_minus, pim, shots, hits,
                    blocked_shots, power_play_goals, power_play_points,
                    shorthanded_goals, shorthanded_points, game_winning_goals,
                    overtime_goals, toi_seconds, faceoff_wins, faceoff_losses,
                    games_started, wins, losses, ot_losses, saves, shots_against,
                    goals_against, save_percentage, gaa, shutouts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, game_id) DO UPDATE SET
                    goals = excluded.goals,
                    assists = excluded.assists,
                    points = excluded.points,
                    plus_minus = excluded.plus_minus,
                    pim = excluded.pim,
                    shots = excluded.shots,
                    hits = excluded.hits,
                    blocked_shots = excluded.blocked_shots,
                    power_play_goals = excluded.power_play_goals,
                    power_play_points = excluded.power_play_points,
                    shorthanded_goals = excluded.shorthanded_goals,
                    shorthanded_points = excluded.shorthanded_points,
                    game_winning_goals = excluded.game_winning_goals,
                    overtime_goals = excluded.overtime_goals,
                    toi_seconds = excluded.toi_seconds,
                    faceoff_wins = excluded.faceoff_wins,
                    faceoff_losses = excluded.faceoff_losses,
                    games_started = excluded.games_started,
                    wins = excluded.wins,
                    losses = excluded.losses,
                    ot_losses = excluded.ot_losses,
                    saves = excluded.saves,
                    shots_against = excluded.shots_against,
                    goals_against = excluded.goals_against,
                    save_percentage = excluded.save_percentage,
                    gaa = excluded.gaa,
                    shutouts = excluded.shutouts
                """,
                (
                    stats.get("player_id"),
                    stats.get("game_id"),
                    stats.get("team_abbrev"),
                    stats.get("opponent_abbrev"),
                    1 if stats.get("is_home") else 0,
                    stats.get("goals", 0),
                    stats.get("assists", 0),
                    stats.get("points", 0),
                    stats.get("plus_minus", 0),
                    stats.get("pim", 0),
                    stats.get("shots", 0),
                    stats.get("hits", 0),
                    stats.get("blocked_shots", 0),
                    stats.get("power_play_goals", 0),
                    stats.get("power_play_points", 0),
                    stats.get("shorthanded_goals", 0),
                    stats.get("shorthanded_points", 0),
                    stats.get("game_winning_goals", 0),
                    stats.get("overtime_goals", 0),
                    stats.get("toi_seconds", 0),
                    stats.get("faceoff_wins", 0),
                    stats.get("faceoff_losses", 0),
                    stats.get("games_started"),
                    stats.get("wins"),
                    stats.get("losses"),
                    stats.get("ot_losses"),
                    stats.get("saves"),
                    stats.get("shots_against"),
                    stats.get("goals_against"),
                    stats.get("save_percentage"),
                    stats.get("gaa"),
                    stats.get("shutouts"),
                ),
            )

    def get_player_game_stats_count(
        self, player_id: Optional[int] = None, season: Optional[int] = None
    ) -> int:
        """Get count of player game stats records."""
        with self.cursor() as cur:
            if player_id and season:
                cur.execute(
                    """
                    SELECT COUNT(*) as count FROM player_game_stats pgs
                    JOIN games g ON pgs.game_id = g.game_id
                    WHERE pgs.player_id = ? AND g.season = ?
                    """,
                    (player_id, season),
                )
            elif player_id:
                cur.execute(
                    "SELECT COUNT(*) as count FROM player_game_stats WHERE player_id = ?",
                    (player_id,),
                )
            elif season:
                cur.execute(
                    """
                    SELECT COUNT(*) as count FROM player_game_stats pgs
                    JOIN games g ON pgs.game_id = g.game_id
                    WHERE g.season = ?
                    """,
                    (season,),
                )
            else:
                cur.execute("SELECT COUNT(*) as count FROM player_game_stats")
            return cur.fetchone()["count"]

    # -------------------------------------------------------------------------
    # Collection progress tracking
    # -------------------------------------------------------------------------

    def set_collection_progress(
        self,
        collection_type: str,
        entity_id: str,
        status: str,
        season: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update collection progress for an entity.

        Args:
            collection_type: Type of collection ('roster', 'player_games', etc.)
            entity_id: ID of entity being collected (player_id, team_abbrev)
            status: Status ('pending', 'in_progress', 'complete', 'error')
            season: Season for game log collection
            error: Error message if status is 'error'
        """
        now = datetime.now().isoformat()
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO collection_progress (
                    collection_type, entity_id, season, status, last_error,
                    started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(collection_type, entity_id, season) DO UPDATE SET
                    status = excluded.status,
                    last_error = excluded.last_error,
                    started_at = CASE
                        WHEN excluded.status = 'in_progress' THEN excluded.started_at
                        ELSE collection_progress.started_at
                    END,
                    completed_at = CASE
                        WHEN excluded.status IN ('complete', 'error') THEN excluded.completed_at
                        ELSE NULL
                    END
                """,
                (
                    collection_type,
                    entity_id,
                    season,
                    status,
                    error,
                    now if status == "in_progress" else None,
                    now if status in ("complete", "error") else None,
                ),
            )

    def get_collection_progress(
        self, collection_type: str, status: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Get collection progress records.

        Args:
            collection_type: Type of collection
            status: Filter by status

        Returns:
            List of progress records
        """
        with self.cursor() as cur:
            if status:
                cur.execute(
                    "SELECT * FROM collection_progress WHERE collection_type = ? AND status = ?",
                    (collection_type, status),
                )
            else:
                cur.execute(
                    "SELECT * FROM collection_progress WHERE collection_type = ?",
                    (collection_type,),
                )
            return [dict(row) for row in cur.fetchall()]

    def get_incomplete_players(self, season: int) -> list[int]:
        """Get player IDs that haven't been fully collected for a season.

        Args:
            season: Season to check

        Returns:
            List of player IDs needing collection
        """
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT p.player_id FROM players p
                WHERE p.is_active = 1
                AND NOT EXISTS (
                    SELECT 1 FROM collection_progress cp
                    WHERE cp.collection_type = 'player_games'
                    AND cp.entity_id = CAST(p.player_id AS TEXT)
                    AND cp.season = ?
                    AND cp.status = 'complete'
                )
                """,
                (season,),
            )
            return [row["player_id"] for row in cur.fetchall()]

    # -------------------------------------------------------------------------
    # Statistics and summaries
    # -------------------------------------------------------------------------

    def get_database_stats(self) -> dict[str, Any]:
        """Get summary statistics about database contents."""
        with self.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM players WHERE is_active = 1")
            active_players = cur.fetchone()["count"]

            cur.execute("SELECT COUNT(*) as count FROM players")
            total_players = cur.fetchone()["count"]

            cur.execute("SELECT COUNT(*) as count FROM games")
            total_games = cur.fetchone()["count"]

            cur.execute("SELECT COUNT(*) as count FROM player_game_stats")
            total_stats = cur.fetchone()["count"]

            cur.execute("SELECT DISTINCT season FROM games ORDER BY season DESC")
            seasons = [row["season"] for row in cur.fetchall()]

            return {
                "active_players": active_players,
                "total_players": total_players,
                "total_games": total_games,
                "total_player_game_stats": total_stats,
                "seasons": seasons,
            }


# Module-level database instance
_db_instance: Optional[Database] = None


def get_database(db_path: Optional[Path] = None) -> Database:
    """Get or create the database singleton.

    Args:
        db_path: Optional custom path for database

    Returns:
        Database instance
    """
    global _db_instance
    if _db_instance is None or (db_path and _db_instance.db_path != db_path):
        _db_instance = Database(db_path)
        if not _db_instance.is_initialized():
            _db_instance.initialize()
    return _db_instance
