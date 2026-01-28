"""Common query functions for NHL player data analysis."""

from typing import Any, Optional

from .db import Database, get_database


def get_player_game_log(
    player_id: int,
    season: Optional[int] = None,
    db: Optional[Database] = None,
) -> list[dict[str, Any]]:
    """Get all games for a player with their stats.

    Args:
        player_id: NHL player ID
        season: Optional season filter (e.g., 20242025)
        db: Database instance (uses default if not provided)

    Returns:
        List of game records with stats, ordered by date descending
    """
    db = db or get_database()
    with db.cursor() as cur:
        if season:
            cur.execute(
                """
                SELECT
                    g.game_date,
                    g.season,
                    pgs.team_abbrev,
                    pgs.opponent_abbrev,
                    pgs.is_home,
                    pgs.goals,
                    pgs.assists,
                    pgs.points,
                    pgs.plus_minus,
                    pgs.shots,
                    pgs.hits,
                    pgs.blocked_shots,
                    pgs.pim,
                    pgs.toi_seconds,
                    pgs.power_play_goals,
                    pgs.power_play_points,
                    g.home_score,
                    g.away_score
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id = ? AND g.season = ?
                ORDER BY g.game_date DESC
                """,
                (player_id, season),
            )
        else:
            cur.execute(
                """
                SELECT
                    g.game_date,
                    g.season,
                    pgs.team_abbrev,
                    pgs.opponent_abbrev,
                    pgs.is_home,
                    pgs.goals,
                    pgs.assists,
                    pgs.points,
                    pgs.plus_minus,
                    pgs.shots,
                    pgs.hits,
                    pgs.blocked_shots,
                    pgs.pim,
                    pgs.toi_seconds,
                    pgs.power_play_goals,
                    pgs.power_play_points,
                    g.home_score,
                    g.away_score
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id = ?
                ORDER BY g.game_date DESC
                """,
                (player_id,),
            )
        return [dict(row) for row in cur.fetchall()]


def get_player_vs_opponent(
    player_id: int,
    opponent_abbrev: str,
    db: Optional[Database] = None,
) -> dict[str, Any]:
    """Get player's aggregate stats against a specific opponent.

    Args:
        player_id: NHL player ID
        opponent_abbrev: Team abbreviation (e.g., 'TOR')
        db: Database instance

    Returns:
        Aggregate stats against opponent
    """
    db = db or get_database()
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) as games_played,
                SUM(goals) as total_goals,
                SUM(assists) as total_assists,
                SUM(points) as total_points,
                SUM(shots) as total_shots,
                AVG(goals) as avg_goals,
                AVG(assists) as avg_assists,
                AVG(points) as avg_points,
                AVG(toi_seconds) as avg_toi_seconds
            FROM player_game_stats
            WHERE player_id = ? AND opponent_abbrev = ?
            """,
            (player_id, opponent_abbrev),
        )
        row = cur.fetchone()
        return dict(row) if row else {}


def get_top_scorers(
    season: Optional[int] = None,
    limit: int = 10,
    db: Optional[Database] = None,
) -> list[dict[str, Any]]:
    """Get top scorers by total goals.

    Args:
        season: Optional season filter
        limit: Number of players to return
        db: Database instance

    Returns:
        List of top scorers with stats
    """
    db = db or get_database()
    with db.cursor() as cur:
        if season:
            cur.execute(
                """
                SELECT
                    p.full_name,
                    p.position,
                    p.current_team_abbrev,
                    COUNT(*) as games_played,
                    SUM(pgs.goals) as total_goals,
                    SUM(pgs.assists) as total_assists,
                    SUM(pgs.points) as total_points,
                    ROUND(AVG(pgs.goals), 2) as goals_per_game,
                    ROUND(AVG(pgs.points), 2) as points_per_game
                FROM player_game_stats pgs
                JOIN players p ON pgs.player_id = p.player_id
                JOIN games g ON pgs.game_id = g.game_id
                WHERE g.season = ?
                GROUP BY pgs.player_id
                ORDER BY total_goals DESC
                LIMIT ?
                """,
                (season, limit),
            )
        else:
            cur.execute(
                """
                SELECT
                    p.full_name,
                    p.position,
                    p.current_team_abbrev,
                    COUNT(*) as games_played,
                    SUM(pgs.goals) as total_goals,
                    SUM(pgs.assists) as total_assists,
                    SUM(pgs.points) as total_points,
                    ROUND(AVG(pgs.goals), 2) as goals_per_game,
                    ROUND(AVG(pgs.points), 2) as points_per_game
                FROM player_game_stats pgs
                JOIN players p ON pgs.player_id = p.player_id
                GROUP BY pgs.player_id
                ORDER BY total_goals DESC
                LIMIT ?
                """,
                (limit,),
            )
        return [dict(row) for row in cur.fetchall()]


def get_team_roster_stats(
    team_abbrev: str,
    season: Optional[int] = None,
    db: Optional[Database] = None,
) -> list[dict[str, Any]]:
    """Get all players on a team with their aggregate stats.

    Args:
        team_abbrev: Team abbreviation (e.g., 'EDM')
        season: Optional season filter
        db: Database instance

    Returns:
        List of players with stats
    """
    db = db or get_database()
    with db.cursor() as cur:
        if season:
            cur.execute(
                """
                SELECT
                    p.player_id,
                    p.full_name,
                    p.position,
                    p.jersey_number,
                    COUNT(*) as games_played,
                    SUM(pgs.goals) as goals,
                    SUM(pgs.assists) as assists,
                    SUM(pgs.points) as points,
                    SUM(pgs.plus_minus) as plus_minus,
                    ROUND(AVG(pgs.toi_seconds / 60.0), 1) as avg_toi_minutes
                FROM players p
                JOIN player_game_stats pgs ON p.player_id = pgs.player_id
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.team_abbrev = ? AND g.season = ?
                GROUP BY p.player_id
                ORDER BY points DESC
                """,
                (team_abbrev, season),
            )
        else:
            cur.execute(
                """
                SELECT
                    p.player_id,
                    p.full_name,
                    p.position,
                    p.jersey_number,
                    COUNT(*) as games_played,
                    SUM(pgs.goals) as goals,
                    SUM(pgs.assists) as assists,
                    SUM(pgs.points) as points,
                    SUM(pgs.plus_minus) as plus_minus,
                    ROUND(AVG(pgs.toi_seconds / 60.0), 1) as avg_toi_minutes
                FROM players p
                JOIN player_game_stats pgs ON p.player_id = pgs.player_id
                WHERE pgs.team_abbrev = ?
                GROUP BY p.player_id
                ORDER BY points DESC
                """,
                (team_abbrev,),
            )
        return [dict(row) for row in cur.fetchall()]


def get_player_by_name(
    name: str,
    db: Optional[Database] = None,
) -> list[dict[str, Any]]:
    """Search for players by name (partial match).

    Args:
        name: Player name to search for
        db: Database instance

    Returns:
        List of matching players
    """
    db = db or get_database()
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT
                player_id,
                full_name,
                position,
                current_team_abbrev,
                jersey_number,
                is_active
            FROM players
            WHERE full_name LIKE ?
            ORDER BY is_active DESC, full_name
            """,
            (f"%{name}%",),
        )
        return [dict(row) for row in cur.fetchall()]


def get_games_for_date(
    game_date: str,
    db: Optional[Database] = None,
) -> list[dict[str, Any]]:
    """Get all games on a specific date.

    Args:
        game_date: Date string in YYYY-MM-DD format
        db: Database instance

    Returns:
        List of games
    """
    db = db or get_database()
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT
                game_id,
                game_date,
                home_team_abbrev,
                away_team_abbrev,
                home_score,
                away_score,
                game_state,
                venue
            FROM games
            WHERE game_date = ?
            ORDER BY game_id
            """,
            (game_date,),
        )
        return [dict(row) for row in cur.fetchall()]


def get_collection_status(
    db: Optional[Database] = None,
) -> dict[str, Any]:
    """Get overall collection progress status.

    Args:
        db: Database instance

    Returns:
        Collection status summary
    """
    db = db or get_database()
    stats = db.get_database_stats()

    with db.cursor() as cur:
        # Roster collection status
        cur.execute(
            """
            SELECT status, COUNT(*) as count
            FROM collection_progress
            WHERE collection_type = 'roster'
            GROUP BY status
            """
        )
        roster_status = {row["status"]: row["count"] for row in cur.fetchall()}

        # Player games collection status
        cur.execute(
            """
            SELECT status, COUNT(*) as count
            FROM collection_progress
            WHERE collection_type = 'player_games'
            GROUP BY status
            """
        )
        player_games_status = {row["status"]: row["count"] for row in cur.fetchall()}

    return {
        **stats,
        "roster_collection": roster_status,
        "player_games_collection": player_games_status,
    }
