"""Player card builder -- queries the DB and assembles a PlayerCard."""

from typing import Any, Optional

from src.database.db import Database, get_database

from .models import (
    GoaliePeriodSplit,
    GoaliePhaseSplit,
    GoalieStats,
    GoalieStrengthSplit,
    PeriodSplit,
    PhaseSplit,
    PlayerCard,
    ShotEvent,
    SkaterStats,
    StrengthSplit,
)


def _safe_pct(numerator: int, denominator: int) -> float:
    """Compute percentage, returning 0.0 if denominator is 0."""
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _safe_div(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 2) if denominator else 0.0


def _per_60(count: int, toi_seconds: int) -> float:
    """Compute a per-60-minutes rate."""
    if toi_seconds == 0:
        return 0.0
    return round(count / toi_seconds * 3600, 2)


# ---------------------------------------------------------------------------
# League averages
# ---------------------------------------------------------------------------


def get_league_skater_avg(season: int, db: Database) -> SkaterStats:
    """Compute league-average skater stats (per-game rates) for a season."""
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) as total_gp,
                SUM(pgs.goals) as goals,
                SUM(pgs.assists) as assists,
                SUM(pgs.points) as points,
                SUM(pgs.shots) as shots,
                SUM(pgs.toi_seconds) as toi,
                SUM(pgs.hits) as hits,
                SUM(pgs.blocked_shots) as blocked_shots
            FROM player_game_stats pgs
            JOIN players p ON pgs.player_id = p.player_id
            JOIN games g ON pgs.game_id = g.game_id
            WHERE g.season = ? AND p.position != 'G' AND pgs.toi_seconds > 0
            """,
            (season,),
        )
        r = cur.fetchone()

    gp = r["total_gp"] or 1
    toi = r["toi"] or 1
    goals = r["goals"] or 0
    assists = r["assists"] or 0
    points = r["points"] or 0
    shots = r["shots"] or 0

    return SkaterStats(
        games=gp,
        goals=goals,
        assists=assists,
        points=points,
        shots=shots,
        toi_seconds=toi,
        shooting_pct=_safe_pct(goals, shots),
        avg_toi_minutes=round(toi / gp / 60, 1),
        goals_per_60=_per_60(goals, toi),
        points_per_60=_per_60(points, toi),
    )


def get_league_goalie_avg(season: int, db: Database) -> GoalieStats:
    """Compute league-average goalie stats for a season."""
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) as total_gp,
                SUM(pgs.saves) as saves,
                SUM(pgs.shots_against) as shots_against,
                SUM(pgs.goals_against) as goals_against,
                SUM(pgs.shutouts) as shutouts,
                SUM(pgs.toi_seconds) as toi
            FROM player_game_stats pgs
            JOIN players p ON pgs.player_id = p.player_id
            JOIN games g ON pgs.game_id = g.game_id
            WHERE g.season = ? AND p.position = 'G' AND pgs.toi_seconds > 0
            """,
            (season,),
        )
        r = cur.fetchone()

    gp = r["total_gp"] or 1
    saves = r["saves"] or 0
    sa = r["shots_against"] or 0
    ga = r["goals_against"] or 0
    toi = r["toi"] or 1

    return GoalieStats(
        games=gp,
        saves=saves,
        shots_against=sa,
        goals_against=ga,
        save_pct=round(saves / sa, 4) if sa else 0.0,
        gaa=round(ga / (toi / 3600), 2) if toi else 0.0,
        shutouts=r["shutouts"] or 0,
        toi_seconds=toi,
        avg_toi_minutes=round(toi / gp / 60, 1),
    )


# ---------------------------------------------------------------------------
# Player season stats
# ---------------------------------------------------------------------------


def _build_skater_stats(rows: list[dict[str, Any]]) -> SkaterStats:
    """Aggregate player_game_stats rows into a SkaterStats."""
    if not rows:
        return SkaterStats()

    gp = len(rows)
    goals = sum(r["goals"] or 0 for r in rows)
    assists = sum(r["assists"] or 0 for r in rows)
    points = sum(r["points"] or 0 for r in rows)
    shots = sum(r["shots"] or 0 for r in rows)
    toi = sum(r["toi_seconds"] or 0 for r in rows)
    plus_minus = sum(r["plus_minus"] or 0 for r in rows)
    hits = sum(r["hits"] or 0 for r in rows)
    blocked = sum(r["blocked_shots"] or 0 for r in rows)
    pim = sum(r["pim"] or 0 for r in rows)
    ppg = sum(r["power_play_goals"] or 0 for r in rows)
    ppp = sum(r["power_play_points"] or 0 for r in rows)
    shg = sum(r["shorthanded_goals"] or 0 for r in rows)
    shp = sum(r["shorthanded_points"] or 0 for r in rows)
    gwg = sum(r["game_winning_goals"] or 0 for r in rows)
    fow = sum(r["faceoff_wins"] or 0 for r in rows)
    fol = sum(r["faceoff_losses"] or 0 for r in rows)

    return SkaterStats(
        games=gp,
        goals=goals,
        assists=assists,
        points=points,
        plus_minus=plus_minus,
        shots=shots,
        shooting_pct=_safe_pct(goals, shots),
        toi_seconds=toi,
        avg_toi_minutes=round(toi / gp / 60, 1) if gp else 0.0,
        hits=hits,
        blocked_shots=blocked,
        pim=pim,
        power_play_goals=ppg,
        power_play_points=ppp,
        shorthanded_goals=shg,
        shorthanded_points=shp,
        game_winning_goals=gwg,
        faceoff_wins=fow,
        faceoff_losses=fol,
        goals_per_60=_per_60(goals, toi),
        points_per_60=_per_60(points, toi),
    )


def _build_goalie_stats(rows: list[dict[str, Any]]) -> GoalieStats:
    """Aggregate player_game_stats rows into GoalieStats."""
    if not rows:
        return GoalieStats()

    gp = len(rows)
    gs = sum(1 for r in rows if r.get("games_started"))
    wins = sum(r["wins"] or 0 for r in rows)
    losses = sum(r["losses"] or 0 for r in rows)
    otl = sum(r["ot_losses"] or 0 for r in rows)
    saves = sum(r["saves"] or 0 for r in rows)
    sa = sum(r["shots_against"] or 0 for r in rows)
    ga = sum(r["goals_against"] or 0 for r in rows)
    so = sum(r["shutouts"] or 0 for r in rows)
    toi = sum(r["toi_seconds"] or 0 for r in rows)

    return GoalieStats(
        games=gp,
        games_started=gs,
        wins=wins,
        losses=losses,
        otl=otl,
        saves=saves,
        shots_against=sa,
        goals_against=ga,
        save_pct=round(saves / sa, 4) if sa else 0.0,
        gaa=round(ga / (toi / 3600), 2) if toi else 0.0,
        shutouts=so,
        toi_seconds=toi,
        avg_toi_minutes=round(toi / gp / 60, 1) if gp else 0.0,
    )


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------

_PHASE_SQL = """
    CASE
        WHEN g.game_type = 3 THEN 'playoffs'
        WHEN CAST(substr(g.game_date, 6, 2) AS INTEGER) IN (10, 11) THEN 'early'
        WHEN CAST(substr(g.game_date, 6, 2) AS INTEGER) IN (12, 1) THEN 'mid'
        ELSE 'late'
    END
"""


def _get_skater_period_splits(
    player_id: int, season: int, db: Database
) -> list[PeriodSplit]:
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT period,
                   COUNT(*) as shots,
                   SUM(is_goal) as goals
            FROM shots
            WHERE player_id = ? AND season = ?
            GROUP BY period ORDER BY period
            """,
            (player_id, season),
        )
        rows = [dict(r) for r in cur.fetchall()]

    return [
        PeriodSplit(
            period=r["period"],
            shots=r["shots"],
            goals=r["goals"],
            shooting_pct=_safe_pct(r["goals"], r["shots"]),
        )
        for r in rows
    ]


def _get_goalie_period_splits(
    player_id: int, season: int, db: Database
) -> list[GoaliePeriodSplit]:
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT period,
                   COUNT(*) as shots_against,
                   SUM(is_goal) as goals_against
            FROM shots
            WHERE goalie_id = ? AND season = ?
            GROUP BY period ORDER BY period
            """,
            (player_id, season),
        )
        rows = [dict(r) for r in cur.fetchall()]

    return [
        GoaliePeriodSplit(
            period=r["period"],
            shots_against=r["shots_against"],
            goals_against=r["goals_against"],
            saves=r["shots_against"] - r["goals_against"],
            save_pct=_safe_pct(
                r["shots_against"] - r["goals_against"], r["shots_against"]
            ),
        )
        for r in rows
    ]


def _get_skater_phase_splits(
    player_id: int, season: int, db: Database
) -> list[PhaseSplit]:
    with db.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                {_PHASE_SQL} as phase,
                COUNT(*) as games,
                SUM(pgs.goals) as goals,
                SUM(pgs.assists) as assists,
                SUM(pgs.points) as points,
                SUM(pgs.shots) as shots,
                SUM(pgs.toi_seconds) as toi
            FROM player_game_stats pgs
            JOIN games g ON pgs.game_id = g.game_id
            WHERE pgs.player_id = ? AND g.season = ?
            GROUP BY phase
            """,
            (player_id, season),
        )
        rows = [dict(r) for r in cur.fetchall()]

    splits = []
    for r in rows:
        if r["phase"] is None:
            continue
        toi = r["toi"] or 0
        goals = r["goals"] or 0
        shots = r["shots"] or 0
        points = r["points"] or 0
        splits.append(
            PhaseSplit(
                phase=r["phase"],
                games=r["games"],
                goals=goals,
                assists=r["assists"] or 0,
                points=points,
                shots=shots,
                toi_seconds=toi,
                shooting_pct=_safe_pct(goals, shots),
                points_per_60=_per_60(points, toi),
            )
        )
    return splits


def _get_goalie_phase_splits(
    player_id: int, season: int, db: Database
) -> list[GoaliePhaseSplit]:
    with db.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                {_PHASE_SQL} as phase,
                COUNT(*) as games,
                SUM(pgs.wins) as wins,
                SUM(pgs.losses) as losses,
                SUM(pgs.saves) as saves,
                SUM(pgs.shots_against) as shots_against,
                SUM(pgs.goals_against) as goals_against,
                SUM(pgs.toi_seconds) as toi
            FROM player_game_stats pgs
            JOIN games g ON pgs.game_id = g.game_id
            WHERE pgs.player_id = ? AND g.season = ?
            GROUP BY phase
            """,
            (player_id, season),
        )
        rows = [dict(r) for r in cur.fetchall()]

    splits = []
    for r in rows:
        if r["phase"] is None:
            continue
        saves = r["saves"] or 0
        sa = r["shots_against"] or 0
        ga = r["goals_against"] or 0
        toi = r["toi"] or 0
        splits.append(
            GoaliePhaseSplit(
                phase=r["phase"],
                games=r["games"],
                wins=r["wins"] or 0,
                losses=r["losses"] or 0,
                saves=saves,
                shots_against=sa,
                goals_against=ga,
                save_pct=round(saves / sa, 4) if sa else 0.0,
                gaa=round(ga / (toi / 3600), 2) if toi else 0.0,
            )
        )
    return splits


def _get_skater_strength_splits(
    player_id: int, season: int, db: Database
) -> list[StrengthSplit]:
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT strength,
                   COUNT(*) as shots,
                   SUM(is_goal) as goals
            FROM shots
            WHERE player_id = ? AND season = ? AND strength IS NOT NULL
            GROUP BY strength
            """,
            (player_id, season),
        )
        rows = [dict(r) for r in cur.fetchall()]

    return [
        StrengthSplit(
            strength=r["strength"],
            shots=r["shots"],
            goals=r["goals"],
            shooting_pct=_safe_pct(r["goals"], r["shots"]),
        )
        for r in rows
    ]


def _get_goalie_strength_splits(
    player_id: int, season: int, db: Database
) -> list[GoalieStrengthSplit]:
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT strength,
                   COUNT(*) as shots_against,
                   SUM(is_goal) as goals_against
            FROM shots
            WHERE goalie_id = ? AND season = ? AND strength IS NOT NULL
            GROUP BY strength
            """,
            (player_id, season),
        )
        rows = [dict(r) for r in cur.fetchall()]

    return [
        GoalieStrengthSplit(
            strength=r["strength"],
            shots_against=r["shots_against"],
            goals_against=r["goals_against"],
            saves=r["shots_against"] - r["goals_against"],
            save_pct=_safe_pct(
                r["shots_against"] - r["goals_against"], r["shots_against"]
            ),
        )
        for r in rows
    ]


def _get_shot_events(
    player_id: int, season: int, is_goalie: bool, db: Database
) -> list[ShotEvent]:
    """Get raw shot data for the heat map."""
    id_col = "goalie_id" if is_goalie else "player_id"
    with db.cursor() as cur:
        cur.execute(
            f"""
            SELECT x_coord, y_coord, is_goal, shot_type, period, strength
            FROM shots
            WHERE {id_col} = ? AND season = ?
              AND x_coord IS NOT NULL AND y_coord IS NOT NULL
            """,
            (player_id, season),
        )
        rows = [dict(r) for r in cur.fetchall()]

    return [
        ShotEvent(
            x=r["x_coord"],
            y=r["y_coord"],
            is_goal=bool(r["is_goal"]),
            shot_type=r["shot_type"] or "",
            period=r["period"] or 0,
            strength=r["strength"] or "",
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def get_available_seasons(db: Optional[Database] = None) -> list[int]:
    """Return seasons that have data, most recent first."""
    db = db or get_database()
    with db.cursor() as cur:
        cur.execute("SELECT DISTINCT season FROM games ORDER BY season DESC")
        return [row["season"] for row in cur.fetchall()]


def get_player_list(db: Optional[Database] = None) -> list[dict[str, Any]]:
    """Return a lightweight list of all players for search."""
    db = db or get_database()
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT player_id, full_name, position, current_team_abbrev, jersey_number
            FROM players
            WHERE is_active = 1
            ORDER BY full_name
            """
        )
        return [dict(row) for row in cur.fetchall()]


def build_card(
    player_id: int,
    season: Optional[int] = None,
    db: Optional[Database] = None,
) -> PlayerCard:
    """Build a complete player card.

    Args:
        player_id: NHL player ID
        season: Season to build for (defaults to most recent)
        db: Database instance
    """
    db = db or get_database()

    # Resolve season
    if season is None:
        seasons = get_available_seasons(db)
        if not seasons:
            raise ValueError("No seasons in database")
        season = seasons[0]

    # Get player bio
    player = db.get_player(player_id)
    if not player:
        raise ValueError(f"Player {player_id} not found")

    is_goalie = player["position"] == "G"

    # Get all game rows for this player + season
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT pgs.* FROM player_game_stats pgs
            JOIN games g ON pgs.game_id = g.game_id
            WHERE pgs.player_id = ? AND g.season = ?
            ORDER BY g.game_date
            """,
            (player_id, season),
        )
        game_rows = [dict(r) for r in cur.fetchall()]

    # Build season stats + league avg
    if is_goalie:
        goalie_stats = _build_goalie_stats(game_rows)
        league_goalie_avg = get_league_goalie_avg(season, db)

        # Score: save_pct delta (in percentage points)
        delta = (goalie_stats.save_pct - league_goalie_avg.save_pct) * 100
        score = round(delta, 2)
        sign = "+" if score >= 0 else ""
        score_label = f"{sign}{score:.1f} SV%"

        card = PlayerCard(
            player_id=player_id,
            name=player["full_name"],
            first_name=player.get("first_name", ""),
            last_name=player.get("last_name", ""),
            position=player["position"],
            team=player.get("current_team_abbrev", ""),
            number=player.get("jersey_number"),
            shoots=player.get("shoots_catches"),
            height_inches=player.get("height_inches"),
            weight_lbs=player.get("weight_lbs"),
            is_goalie=True,
            season=season,
            goalie_stats=goalie_stats,
            league_goalie_avg=league_goalie_avg,
            player_score=score,
            score_label=score_label,
            period_splits=_get_goalie_period_splits(player_id, season, db),
            season_phase_splits=_get_goalie_phase_splits(player_id, season, db),
            strength_splits=_get_goalie_strength_splits(player_id, season, db),
            shots=_get_shot_events(player_id, season, is_goalie=True, db=db),
        )
    else:
        skater_stats = _build_skater_stats(game_rows)
        league_skater_avg = get_league_skater_avg(season, db)

        # Score: points_per_60 delta
        delta = skater_stats.points_per_60 - league_skater_avg.points_per_60
        score = round(delta, 2)
        sign = "+" if score >= 0 else ""
        score_label = f"{sign}{score:.2f} P/60"

        card = PlayerCard(
            player_id=player_id,
            name=player["full_name"],
            first_name=player.get("first_name", ""),
            last_name=player.get("last_name", ""),
            position=player["position"],
            team=player.get("current_team_abbrev", ""),
            number=player.get("jersey_number"),
            shoots=player.get("shoots_catches"),
            height_inches=player.get("height_inches"),
            weight_lbs=player.get("weight_lbs"),
            is_goalie=False,
            season=season,
            skater_stats=skater_stats,
            league_skater_avg=league_skater_avg,
            player_score=score,
            score_label=score_label,
            period_splits=_get_skater_period_splits(player_id, season, db),
            season_phase_splits=_get_skater_phase_splits(player_id, season, db),
            strength_splits=_get_skater_strength_splits(player_id, season, db),
            shots=_get_shot_events(player_id, season, is_goalie=False, db=db),
        )

    return card
