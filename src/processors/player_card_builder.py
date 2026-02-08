"""
Player Card Builder

Constructs PlayerCard objects from existing data sources:
1. SeasonSegmentPipeline output (season phase × game phase stats)
2. Database queries for per-period (1st/2nd/3rd) breakdowns
3. Player model data for identity and overall stats

This is the processor that makes player data DYNAMIC by assembling
the full temporal performance profile for each player.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from loguru import logger

from src.models.player_card import (
    GamePeriod,
    GoaliePerformanceSnapshot,
    PerformanceSnapshot,
    PlayerCard,
    SeasonPhase,
)
from src.processors.season_segment_pipeline import (
    GamePhase,
    PlayerPhaseStats,
    SeasonSegmentPipeline,
)

if TYPE_CHECKING:
    from src.database.db import Database
    from src.models.player import Player


# Maps the game phase early/mid/late to the three periods.
# Each game phase spans parts of multiple periods, so we need
# a separate query path for clean 1st/2nd/3rd period stats.
PERIOD_TIME_RANGES: dict[GamePeriod, dict[str, int]] = {
    GamePeriod.FIRST:  {"period": 1, "start_minute": 0, "end_minute": 20},
    GamePeriod.SECOND: {"period": 2, "start_minute": 0, "end_minute": 20},
    GamePeriod.THIRD:  {"period": 3, "start_minute": 0, "end_minute": 20},
}


class PlayerCardBuilder:
    """
    Builds PlayerCard objects from database and pipeline data.

    Usage:
        builder = PlayerCardBuilder(db=database)
        card = builder.build_card(player, season=20242025)

        # Or build all cards for a roster:
        cards = builder.build_cards(players, season=20242025)
    """

    def __init__(
        self,
        db: Optional[Database] = None,
        pipeline: Optional[SeasonSegmentPipeline] = None,
    ) -> None:
        self._db = db
        self._pipeline = pipeline

    @property
    def db(self) -> Database:
        if self._db is None:
            from src.database.db import get_database
            self._db = get_database()
        return self._db

    @property
    def pipeline(self) -> SeasonSegmentPipeline:
        if self._pipeline is None:
            self._pipeline = SeasonSegmentPipeline(db=self.db)
        return self._pipeline

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_card(
        self,
        player: Player,
        season: int,
    ) -> PlayerCard:
        """
        Build a complete PlayerCard for a single player.

        Args:
            player: Player model with identity/stats
            season: Season identifier (e.g. 20242025)

        Returns:
            Fully populated PlayerCard with trends computed
        """
        card = PlayerCard(
            player_id=player.player_id,
            player_name=player.full_name,
            team_abbrev=player.current_team_abbrev or "",
            position=player.position_code,
            season=str(season),
        )

        # 1. Overall baseline from career/season stats
        card.overall = self._build_overall_snapshot(player)
        card.total_games = player.career_stats.games_played

        # 2. Season phase snapshots (early / mid / late season)
        phase_stats = self.pipeline.aggregate_player_stats(player.player_id, season)
        self._populate_season_phases(card, phase_stats, player)

        # 3. Period snapshots (1st / 2nd / 3rd period)
        self._populate_period_stats(card, player, season)

        # 4. Goalie-specific data if applicable
        if player.is_goalie and player.goalie_stats:
            self._populate_goalie_splits(card, player, season)

        # 5. Compute all derived metrics (trends, profiles, etc.)
        card.compute_trends()

        # 6. Clutch rating from late-season + late-game data
        card.clutch_rating = self._compute_clutch_rating(card, phase_stats)

        logger.debug(
            f"Built player card for {player.full_name} "
            f"(GP={card.total_games}, trend={card.scoring_trend.direction.value})"
        )

        return card

    def build_cards(
        self,
        players: dict[int, Player],
        season: int,
    ) -> dict[int, PlayerCard]:
        """
        Build PlayerCards for a set of players.

        Args:
            players: Dict of player_id -> Player
            season: Season identifier

        Returns:
            Dict of player_id -> PlayerCard
        """
        cards: dict[int, PlayerCard] = {}

        for i, (player_id, player) in enumerate(players.items()):
            if (i + 1) % 50 == 0:
                logger.info(f"Building player cards: {i + 1}/{len(players)}")

            cards[player_id] = self.build_card(player, season)

        logger.info(f"Built {len(cards)} player cards for season {season}")
        return cards

    # ------------------------------------------------------------------
    # Internal: Overall baseline
    # ------------------------------------------------------------------

    def _build_overall_snapshot(self, player: Player) -> PerformanceSnapshot:
        """Build the overall baseline snapshot from player career stats."""
        stats = player.career_stats
        snap = PerformanceSnapshot(
            games_played=stats.games_played,
            time_on_ice_seconds=stats.time_on_ice_seconds,
            goals=stats.goals,
            assists=stats.assists,
            points=stats.points,
            shots=stats.shots,
            plus_minus=stats.plus_minus,
            penalty_minutes=stats.penalty_minutes,
            shooting_percentage=stats.shooting_percentage,
            corsi_for=stats.corsi_for,
            corsi_against=stats.corsi_against,
            corsi_percentage=stats.corsi_percentage,
            expected_goals_for=stats.expected_goals_for,
            expected_goals_against=stats.expected_goals_against,
            power_play_goals=stats.power_play_goals,
            power_play_points=stats.power_play_points,
            shorthanded_goals=stats.shorthanded_goals,
            shorthanded_points=stats.shorthanded_points,
        )
        snap.compute_rates()
        return snap

    # ------------------------------------------------------------------
    # Internal: Season phase population
    # ------------------------------------------------------------------

    def _populate_season_phases(
        self,
        card: PlayerCard,
        phase_stats: dict[tuple[str, str], PlayerPhaseStats],
        player: Player,
    ) -> None:
        """Populate early/mid/late season snapshots from pipeline data."""
        # Aggregate across game phases within each season phase
        season_aggregated: dict[str, PerformanceSnapshot] = {}

        for season_phase_val in ["early_season", "mid_season", "late_season"]:
            snap = PerformanceSnapshot()
            total_games = 0

            for game_phase_val in ["early_game", "mid_game", "late_game"]:
                key = (season_phase_val, game_phase_val)
                ps = phase_stats.get(key)
                if ps is None:
                    continue

                snap.goals += ps.goals
                snap.assists += ps.assists
                snap.points += ps.points
                snap.shots += ps.shots
                snap.power_play_goals += ps.power_play_goals

                # Games are the same across game phases for a season phase
                total_games = max(total_games, ps.games)

            snap.games_played = total_games

            # Estimate TOI proportionally from overall
            if card.overall.games_played > 0 and total_games > 0:
                toi_per_game = (
                    card.overall.time_on_ice_seconds / card.overall.games_played
                )
                snap.time_on_ice_seconds = int(toi_per_game * total_games)

            snap.compute_rates()
            season_aggregated[season_phase_val] = snap

        card.early_season = season_aggregated.get(
            "early_season", PerformanceSnapshot()
        )
        card.mid_season = season_aggregated.get(
            "mid_season", PerformanceSnapshot()
        )
        card.late_season = season_aggregated.get(
            "late_season", PerformanceSnapshot()
        )

    # ------------------------------------------------------------------
    # Internal: Per-period population
    # ------------------------------------------------------------------

    def _populate_period_stats(
        self,
        card: PlayerCard,
        player: Player,
        season: int,
    ) -> None:
        """
        Populate 1st/2nd/3rd period snapshots.

        First tries the database for event-level period data.
        Falls back to PlayerStats period fields if DB isn't available.
        """
        # Try database path first (event-level accuracy)
        db_periods = self._query_period_stats_from_db(player.player_id, season)
        if db_periods:
            card.period_1 = db_periods.get(GamePeriod.FIRST, PerformanceSnapshot())
            card.period_2 = db_periods.get(GamePeriod.SECOND, PerformanceSnapshot())
            card.period_3 = db_periods.get(GamePeriod.THIRD, PerformanceSnapshot())
            return

        # Fallback: use PlayerStats period fields
        stats = player.career_stats
        games = stats.games_played or 1

        card.period_1 = PerformanceSnapshot(
            games_played=games,
            goals=stats.period_1_goals,
            assists=stats.period_1_assists,
            points=stats.period_1_points,
            shots=stats.period_1_shots,
            hits=stats.period_1_hits,
            time_on_ice_seconds=stats.period_1_toi_seconds,
        )
        card.period_1.compute_rates()

        card.period_2 = PerformanceSnapshot(
            games_played=games,
            goals=stats.period_2_goals,
            assists=stats.period_2_assists,
            points=stats.period_2_points,
            shots=stats.period_2_shots,
            hits=stats.period_2_hits,
            time_on_ice_seconds=stats.period_2_toi_seconds,
        )
        card.period_2.compute_rates()

        card.period_3 = PerformanceSnapshot(
            games_played=games,
            goals=stats.period_3_goals,
            assists=stats.period_3_assists,
            points=stats.period_3_points,
            shots=stats.period_3_shots,
            hits=stats.period_3_hits,
            time_on_ice_seconds=stats.period_3_toi_seconds,
        )
        card.period_3.compute_rates()

    def _query_period_stats_from_db(
        self,
        player_id: int,
        season: int,
    ) -> dict[GamePeriod, PerformanceSnapshot] | None:
        """
        Query per-period stats from the shots table.

        Returns None if no data is found (caller should use fallback).
        """
        try:
            with self.db.cursor() as cur:
                # Goals and shots by period
                cur.execute(
                    """
                    SELECT
                        period,
                        COUNT(*) as shots,
                        SUM(CASE WHEN is_goal = 1 THEN 1 ELSE 0 END) as goals
                    FROM shots
                    WHERE player_id = ? AND season = ?
                    AND period IN (1, 2, 3)
                    GROUP BY period
                    """,
                    (player_id, season),
                )
                shot_rows = cur.fetchall()

                if not shot_rows:
                    return None

                # Assists by period
                cur.execute(
                    """
                    SELECT
                        period,
                        COUNT(*) as assists
                    FROM shots
                    WHERE (assist1_player_id = ? OR assist2_player_id = ?)
                    AND season = ? AND is_goal = 1
                    AND period IN (1, 2, 3)
                    GROUP BY period
                    """,
                    (player_id, player_id, season),
                )
                assist_rows = cur.fetchall()

                # Games played
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT pgs.game_id) as games
                    FROM player_game_stats pgs
                    JOIN games g ON pgs.game_id = g.game_id
                    WHERE pgs.player_id = ? AND g.season = ?
                    """,
                    (player_id, season),
                )
                games_row = cur.fetchone()
                games = games_row["games"] if games_row else 0

        except Exception as e:
            logger.debug(f"DB query failed for period stats: {e}")
            return None

        # Build period map
        period_map = {1: GamePeriod.FIRST, 2: GamePeriod.SECOND, 3: GamePeriod.THIRD}
        assists_by_period: dict[int, int] = {}
        for row in assist_rows:
            assists_by_period[row["period"]] = row["assists"]

        result: dict[GamePeriod, PerformanceSnapshot] = {}
        for row in shot_rows:
            p = row["period"]
            gp = period_map.get(p)
            if gp is None:
                continue

            assists = assists_by_period.get(p, 0)
            goals = row["goals"]
            snap = PerformanceSnapshot(
                games_played=games,
                goals=goals,
                assists=assists,
                points=goals + assists,
                shots=row["shots"],
            )
            snap.compute_rates()
            result[gp] = snap

        # Fill missing periods
        for gp in [GamePeriod.FIRST, GamePeriod.SECOND, GamePeriod.THIRD]:
            if gp not in result:
                result[gp] = PerformanceSnapshot(games_played=games)

        return result

    # ------------------------------------------------------------------
    # Internal: Goalie splits
    # ------------------------------------------------------------------

    def _populate_goalie_splits(
        self,
        card: PlayerCard,
        player: Player,
        season: int,
    ) -> None:
        """Populate goalie-specific season phase and period snapshots."""
        if not player.goalie_stats:
            return

        gs = player.goalie_stats

        # For now, create a single overall goalie snapshot as baseline.
        # Per-phase goalie splits require game-level save data from DB.
        baseline = GoaliePerformanceSnapshot(
            games_played=gs.games_played,
            games_started=gs.games_started,
            saves=gs.saves,
            shots_against=gs.shots_against,
            goals_against=gs.goals_against,
            save_percentage=gs.save_percentage,
            goals_against_average=gs.goals_against_average,
            high_danger_saves=gs.high_danger_saves,
            high_danger_shots_against=gs.high_danger_shots_against,
            high_danger_save_percentage=gs.high_danger_save_percentage,
            time_on_ice_seconds=gs.time_on_ice_seconds,
        )

        # Try to get per-phase goalie data from DB
        phase_goalie_data = self._query_goalie_phase_stats(player.player_id, season)
        if phase_goalie_data:
            card.goalie_early_season = phase_goalie_data.get("early_season", baseline)
            card.goalie_mid_season = phase_goalie_data.get("mid_season", baseline)
            card.goalie_late_season = phase_goalie_data.get("late_season", baseline)
        else:
            # Fall back to overall for all phases
            card.goalie_early_season = baseline
            card.goalie_mid_season = baseline
            card.goalie_late_season = baseline

        # Period-level goalie data
        period_goalie_data = self._query_goalie_period_stats(player.player_id, season)
        if period_goalie_data:
            card.goalie_period_1 = period_goalie_data.get(1, baseline)
            card.goalie_period_2 = period_goalie_data.get(2, baseline)
            card.goalie_period_3 = period_goalie_data.get(3, baseline)
        else:
            card.goalie_period_1 = baseline
            card.goalie_period_2 = baseline
            card.goalie_period_3 = baseline

    def _query_goalie_phase_stats(
        self,
        player_id: int,
        season: int,
    ) -> dict[str, GoaliePerformanceSnapshot] | None:
        """Query goalie stats split by season phase from the shots table."""
        try:
            phase_mapping = self.pipeline.build_season_phase_mapping(season)

            with self.db.cursor() as cur:
                # Get all shots faced by this goalie
                cur.execute(
                    """
                    SELECT game_id, is_goal, shot_type
                    FROM shots
                    WHERE goalie_id = ? AND season = ?
                    """,
                    (player_id, season),
                )
                rows = cur.fetchall()

            if not rows:
                return None

            # Bucket by season phase
            phase_data: dict[str, dict[str, int]] = {
                "early_season": {"saves": 0, "shots": 0, "goals": 0},
                "mid_season": {"saves": 0, "shots": 0, "goals": 0},
                "late_season": {"saves": 0, "shots": 0, "goals": 0},
            }

            for row in rows:
                sp = phase_mapping.get_phase(row["game_id"])
                if sp is None or sp.value not in phase_data:
                    continue
                bucket = phase_data[sp.value]
                bucket["shots"] += 1
                if row["is_goal"]:
                    bucket["goals"] += 1
                else:
                    bucket["saves"] += 1

            result = {}
            for phase_name, data in phase_data.items():
                snap = GoaliePerformanceSnapshot(
                    saves=data["saves"],
                    shots_against=data["shots"],
                    goals_against=data["goals"],
                )
                snap.compute_rates()
                result[phase_name] = snap

            return result

        except Exception as e:
            logger.debug(f"Goalie phase query failed: {e}")
            return None

    def _query_goalie_period_stats(
        self,
        player_id: int,
        season: int,
    ) -> dict[int, GoaliePerformanceSnapshot] | None:
        """Query goalie stats split by period."""
        try:
            with self.db.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        period,
                        COUNT(*) as shots,
                        SUM(CASE WHEN is_goal = 1 THEN 1 ELSE 0 END) as goals,
                        SUM(CASE WHEN is_goal = 0 THEN 1 ELSE 0 END) as saves
                    FROM shots
                    WHERE goalie_id = ? AND season = ?
                    AND period IN (1, 2, 3)
                    GROUP BY period
                    """,
                    (player_id, season),
                )
                rows = cur.fetchall()

            if not rows:
                return None

            result = {}
            for row in rows:
                snap = GoaliePerformanceSnapshot(
                    saves=row["saves"],
                    shots_against=row["shots"],
                    goals_against=row["goals"],
                )
                snap.compute_rates()
                result[row["period"]] = snap

            return result

        except Exception as e:
            logger.debug(f"Goalie period query failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Internal: Derived metrics
    # ------------------------------------------------------------------

    def _compute_clutch_rating(
        self,
        card: PlayerCard,
        phase_stats: dict[tuple[str, str], PlayerPhaseStats],
    ) -> float:
        """
        Compute clutch rating from late-season + late-game stats.

        Clutch = how well a player performs when it matters most:
        late in the season during the 3rd period.
        """
        # Get late season × late game stats
        late_late = phase_stats.get(("late_season", "late_game"))
        if not late_late or late_late.games == 0:
            return 0.0

        # Weight game-winning goals heavily
        gwg_weight = 5.0
        ppg_weight = 2.0
        goals_weight = 3.0

        raw = (
            late_late.game_winning_goals * gwg_weight
            + late_late.power_play_goals * ppg_weight
            + late_late.goals * goals_weight
        )

        # Normalize by games
        rating = raw / late_late.games

        # Blend with 3rd period relative performance
        if card.period_profile.period_3_factor > 0:
            rating *= card.period_profile.period_3_factor

        return round(rating, 3)
