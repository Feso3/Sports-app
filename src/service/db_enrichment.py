"""
DB Enrichment Service

Bridges the local SQLite database (5+ years of collected data) to the
simulation pipeline's Team and Player data models.

The DataLoader fetches basic roster/bio data from the NHL API.
This service enriches those objects with aggregated stats from the local DB:
  - Team season stats (goals, shots, PP%, PK%, zone distribution)
  - Forward line and defense pair configurations (by TOI ranking)
  - Starting goalie identification
  - Offensive/defensive zone heat maps
  - Game segment stats (early/mid/late goals)
  - Player season stats and matchup-specific weights
  - Goalie stats (season + vs opponent)
  - Schedule context (fatigue, rest, streaks)
  - Player momentum (hot/cold streaks)
  - Current season phase detection
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from diagnostics import diag
from src.database.db import Database, get_database
from src.models.player import GoalieStats, Player, PlayerStats, ZoneStats
from src.models.team import LineConfiguration, Team, TeamStats
from src.processors.momentum_pipeline import MomentumPipeline
from src.processors.schedule_context_pipeline import (
    FatigueModifier,
    ScheduleContextPipeline,
)
from src.processors.season_segment_pipeline import SeasonPhase, SeasonSegmentPipeline


# Zone mapping: map shot (x, y) coordinates to named zones
def _classify_zone(x: float | None, y: float | None) -> str:
    """Classify a shot into a zone based on coordinates."""
    if x is None or y is None:
        return "neutral_zone"

    abs_x = abs(x)
    abs_y = abs(y)

    # Shots near the net
    if abs_x >= 69:
        if abs_y <= 9:
            return "slot"
        elif abs_y <= 22:
            return "left_circle" if y < 0 else "right_circle"
        else:
            return "behind_net"
    elif abs_x >= 54:
        if abs_y <= 9:
            return "high_slot"
        elif abs_y <= 22:
            return "left_circle" if y < 0 else "right_circle"
        else:
            return "left_point" if y < 0 else "right_point"
    elif abs_x >= 25:
        return "left_point" if y < 0 else "right_point"
    else:
        return "neutral_zone"


@dataclass
class EnrichmentSummary:
    """Summary of data enrichment results."""

    season: int = 0
    season_phase: str = ""
    home_team_stats_loaded: bool = False
    away_team_stats_loaded: bool = False
    home_lines_built: int = 0
    away_lines_built: int = 0
    home_defense_pairs_built: int = 0
    away_defense_pairs_built: int = 0
    home_goalie_set: bool = False
    away_goalie_set: bool = False
    players_enriched: int = 0
    players_with_matchup_data: int = 0
    players_with_momentum: int = 0
    home_fatigue: Optional[FatigueModifier] = None
    away_fatigue: Optional[FatigueModifier] = None


class DBEnrichment:
    """
    Enriches Team and Player objects with data from the local SQLite database.

    This service is the bridge between the collected data (player_game_stats,
    shots, games tables) and the simulation models (Team, Player, TeamStats).
    """

    def __init__(self, db: Optional[Database] = None) -> None:
        self.db = db or get_database()
        self._season_pipeline = SeasonSegmentPipeline(db=self.db)
        self._momentum_pipeline = MomentumPipeline(db=self.db)
        self._schedule_pipeline = ScheduleContextPipeline(db=self.db)

    # -------------------------------------------------------------------------
    # Season Detection
    # -------------------------------------------------------------------------

    def detect_current_season(self) -> int:
        """Detect the latest season with data in the database."""
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT season FROM games ORDER BY season DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                return row["season"]
        # Fallback: construct from current year
        now = datetime.now()
        if now.month >= 9:
            return int(f"{now.year}{now.year + 1}")
        return int(f"{now.year - 1}{now.year}")

    def get_current_season_phase(self, season: int) -> str:
        """Determine current season phase based on latest game date."""
        mapping = self._season_pipeline.build_season_phase_mapping(season)

        # Find the most recent game
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT game_id FROM games
                WHERE season = ? AND game_state IN ('OFF', 'FINAL')
                ORDER BY game_date DESC LIMIT 1
                """,
                (season,),
            )
            row = cur.fetchone()
            if row:
                phase = mapping.get_phase(row["game_id"])
                if phase:
                    return phase.value

        # Fallback: estimate from date
        now = datetime.now()
        month = now.month
        if month in (10, 11):
            return SeasonPhase.EARLY_SEASON.value
        elif month in (12, 1, 2):
            return SeasonPhase.MID_SEASON.value
        elif month in (3, 4):
            return SeasonPhase.LATE_SEASON.value
        else:
            return SeasonPhase.PLAYOFFS.value

    # -------------------------------------------------------------------------
    # Team Enrichment
    # -------------------------------------------------------------------------

    def enrich_team(
        self,
        team: Team,
        season: int,
        opponent_abbrev: str | None = None,
    ) -> None:
        """
        Enrich a Team object with stats from the local database.

        Populates:
        - current_season_stats (goals, shots, PP%, PK%, zone distribution, segments)
        - forward_lines (4 lines from TOI-ranked forwards)
        - defense_pairs (3 pairs from TOI-ranked defensemen)
        - starting_goalie_id
        - offensive_heat_map / defensive_heat_map
        """
        abbrev = team.abbreviation

        # 1. Build team season stats
        team.current_season_stats = self._build_team_stats(abbrev, season)

        # 2. Build line configurations
        team.forward_lines = self._build_forward_lines(abbrev, season, team.roster.forwards)
        team.defense_pairs = self._build_defense_pairs(abbrev, season, team.roster.defensemen)

        # 3. Set starting goalie
        team.starting_goalie_id = self._find_starting_goalie(team.roster.goalies, season)
        if team.roster.goalies:
            backups = [g for g in team.roster.goalies if g != team.starting_goalie_id]
            team.backup_goalie_id = backups[0] if backups else None

        # 4. Build zone heat maps
        off_map, def_map = self._build_zone_heat_maps(abbrev, season)
        team.offensive_heat_map = off_map
        team.defensive_heat_map = def_map

        # 5. Build segment stats (early/mid/late game goals)
        self._populate_segment_stats(team, season)

        logger.info(
            f"Enriched {team.name}: {team.current_season_stats.games_played}GP, "
            f"{len(team.forward_lines)}FL, {len(team.defense_pairs)}DP, "
            f"goalie={team.starting_goalie_id}"
        )

    def _build_team_stats(self, team_abbrev: str, season: int) -> TeamStats:
        """Build TeamStats from player_game_stats aggregation."""
        stats = TeamStats()

        with self.db.cursor() as cur:
            # Team record from games table
            cur.execute(
                """
                SELECT
                    COUNT(*) as games,
                    SUM(CASE
                        WHEN (home_team_abbrev = ? AND home_score > away_score) OR
                             (away_team_abbrev = ? AND away_score > home_score) THEN 1
                        ELSE 0
                    END) as wins,
                    SUM(CASE
                        WHEN (home_team_abbrev = ? AND home_score < away_score AND game_state = 'FINAL') OR
                             (away_team_abbrev = ? AND away_score < home_score AND game_state = 'FINAL') THEN 1
                        ELSE 0
                    END) as losses,
                    SUM(CASE WHEN home_team_abbrev = ? THEN home_score ELSE away_score END) as gf,
                    SUM(CASE WHEN home_team_abbrev = ? THEN away_score ELSE home_score END) as ga
                FROM games
                WHERE (home_team_abbrev = ? OR away_team_abbrev = ?)
                AND season = ?
                AND game_state IN ('OFF', 'FINAL')
                """,
                (
                    team_abbrev, team_abbrev,
                    team_abbrev, team_abbrev,
                    team_abbrev, team_abbrev,
                    team_abbrev, team_abbrev,
                    season,
                ),
            )
            row = cur.fetchone()
            if row and row["games"]:
                stats.games_played = row["games"]
                stats.wins = row["wins"] or 0
                stats.losses = row["losses"] or 0
                stats.overtime_losses = stats.games_played - stats.wins - stats.losses
                stats.points = stats.wins * 2 + stats.overtime_losses
                stats.goals_for = row["gf"] or 0
                stats.goals_against = row["ga"] or 0

            # Aggregate shots from player_game_stats
            cur.execute(
                """
                SELECT
                    SUM(shots) as shots_for,
                    SUM(power_play_goals) as ppg,
                    SUM(power_play_points) as ppp,
                    SUM(shorthanded_goals) as shg
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.team_abbrev = ? AND g.season = ?
                """,
                (team_abbrev, season),
            )
            row = cur.fetchone()
            if row:
                stats.shots_for = row["shots_for"] or 0
                stats.power_play_goals = row["ppg"] or 0

            # Shots against (opponent shots in games where this team played)
            cur.execute(
                """
                SELECT SUM(pgs.shots) as shots_against
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.opponent_abbrev = ? AND g.season = ?
                """,
                (team_abbrev, season),
            )
            row = cur.fetchone()
            if row:
                stats.shots_against = row["shots_against"] or 0

            # Estimate PP/PK from game logs
            # PP opportunities ~ distinct games with PP goals or assists
            if stats.games_played > 0:
                # Rough estimate: ~3.5 PP opportunities per game (league average)
                estimated_pp_opps = int(stats.games_played * 3.5)
                stats.power_play_opportunities = estimated_pp_opps
                if estimated_pp_opps > 0:
                    stats.power_play_percentage = (
                        stats.power_play_goals / estimated_pp_opps * 100
                    )

                # PK: goals against on PP from opponents
                cur.execute(
                    """
                    SELECT SUM(power_play_goals) as opp_ppg
                    FROM player_game_stats pgs
                    JOIN games g ON pgs.game_id = g.game_id
                    WHERE pgs.opponent_abbrev = ? AND g.season = ?
                    """,
                    (team_abbrev, season),
                )
                row = cur.fetchone()
                opp_ppg = (row["opp_ppg"] or 0) if row else 0
                estimated_pk_opps = int(stats.games_played * 3.5)
                stats.penalty_kill_opportunities = estimated_pk_opps
                stats.penalty_kill_goals_against = opp_ppg
                if estimated_pk_opps > 0:
                    stats.penalty_kill_percentage = (
                        (1 - opp_ppg / estimated_pk_opps) * 100
                    )

            # Zone shot distribution from shots table
            cur.execute(
                """
                SELECT x_coord, y_coord, is_goal
                FROM shots
                WHERE team_abbrev = ? AND season = ?
                """,
                (team_abbrev, season),
            )
            shots = cur.fetchall()

            zone_shots: dict[str, int] = {}
            zone_goals: dict[str, int] = {}
            for shot in shots:
                zone = _classify_zone(shot["x_coord"], shot["y_coord"])
                zone_shots[zone] = zone_shots.get(zone, 0) + 1
                if shot["is_goal"]:
                    zone_goals[zone] = zone_goals.get(zone, 0) + 1

            stats.zone_shots_for = zone_shots
            stats.zone_goals_for = zone_goals

            # Zone shots against
            cur.execute(
                """
                SELECT s.x_coord, s.y_coord, s.is_goal
                FROM shots s
                JOIN games g ON s.game_id = g.game_id
                WHERE s.team_abbrev != ? AND s.season = ?
                AND (g.home_team_abbrev = ? OR g.away_team_abbrev = ?)
                """,
                (team_abbrev, season, team_abbrev, team_abbrev),
            )
            opp_shots = cur.fetchall()

            zone_shots_against: dict[str, int] = {}
            zone_goals_against: dict[str, int] = {}
            for shot in opp_shots:
                zone = _classify_zone(shot["x_coord"], shot["y_coord"])
                zone_shots_against[zone] = zone_shots_against.get(zone, 0) + 1
                if shot["is_goal"]:
                    zone_goals_against[zone] = zone_goals_against.get(zone, 0) + 1

            stats.zone_shots_against = zone_shots_against
            stats.zone_goals_against = zone_goals_against

        return stats

    def _build_forward_lines(
        self,
        team_abbrev: str,
        season: int,
        roster_forward_ids: list[int],
    ) -> list[LineConfiguration]:
        """Build 4 forward lines from roster, ranked by average TOI."""
        ranked = self._rank_players_by_toi(roster_forward_ids, team_abbrev, season)

        lines: list[LineConfiguration] = []
        # Group into lines of 3
        for line_num in range(1, 5):
            start = (line_num - 1) * 3
            end = start + 3
            player_ids = ranked[start:end]

            if not player_ids:
                break

            line = LineConfiguration(
                line_number=line_num,
                line_type="forward",
                player_ids=player_ids,
            )

            # Populate line stats from DB
            self._populate_line_stats(line, team_abbrev, season)
            lines.append(line)

        return lines

    def _build_defense_pairs(
        self,
        team_abbrev: str,
        season: int,
        roster_defense_ids: list[int],
    ) -> list[LineConfiguration]:
        """Build 3 defense pairs from roster, ranked by average TOI."""
        ranked = self._rank_players_by_toi(roster_defense_ids, team_abbrev, season)

        pairs: list[LineConfiguration] = []
        for pair_num in range(1, 4):
            start = (pair_num - 1) * 2
            end = start + 2
            player_ids = ranked[start:end]

            if not player_ids:
                break

            pair = LineConfiguration(
                line_number=pair_num,
                line_type="defense",
                player_ids=player_ids,
            )

            self._populate_line_stats(pair, team_abbrev, season)
            pairs.append(pair)

        return pairs

    def _rank_players_by_toi(
        self,
        player_ids: list[int],
        team_abbrev: str,
        season: int,
    ) -> list[int]:
        """Rank players by average time on ice this season."""
        if not player_ids:
            return []

        placeholders = ",".join("?" * len(player_ids))
        with self.db.cursor() as cur:
            cur.execute(
                f"""
                SELECT pgs.player_id, AVG(pgs.toi_seconds) as avg_toi
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id IN ({placeholders})
                AND pgs.team_abbrev = ? AND g.season = ?
                GROUP BY pgs.player_id
                ORDER BY avg_toi DESC
                """,
                (*player_ids, team_abbrev, season),
            )
            ranked = [row["player_id"] for row in cur.fetchall()]

        # Include any roster players not found in game stats (put at end)
        remaining = [pid for pid in player_ids if pid not in ranked]
        return ranked + remaining

    def _populate_line_stats(
        self,
        line: LineConfiguration,
        team_abbrev: str,
        season: int,
    ) -> None:
        """Populate a LineConfiguration with aggregated stats."""
        if not line.player_ids:
            return

        placeholders = ",".join("?" * len(line.player_ids))
        with self.db.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    SUM(goals) as gf,
                    SUM(toi_seconds) as toi,
                    SUM(shots) as shots
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id IN ({placeholders})
                AND pgs.team_abbrev = ? AND g.season = ?
                """,
                (*line.player_ids, team_abbrev, season),
            )
            row = cur.fetchone()
            if row:
                line.goals_for = row["gf"] or 0
                line.time_on_ice_seconds = row["toi"] or 0

                # Estimate corsi % and xG% from goal share
                total_shots = row["shots"] or 1
                if total_shots > 0:
                    shooting_pct = (row["gf"] or 0) / total_shots
                    # Map shooting % to a corsi-like metric (0.4-0.6 range)
                    line.corsi_percentage = max(0.4, min(0.6, 0.5 + shooting_pct))
                    line.expected_goals_percentage = line.corsi_percentage

    def _find_starting_goalie(self, goalie_ids: list[int], season: int) -> int | None:
        """Find the starting goalie (most games started this season)."""
        if not goalie_ids:
            return None

        placeholders = ",".join("?" * len(goalie_ids))
        with self.db.cursor() as cur:
            cur.execute(
                f"""
                SELECT pgs.player_id,
                       SUM(CASE WHEN pgs.games_started = 1 THEN 1 ELSE 0 END) as starts,
                       COUNT(*) as games
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id IN ({placeholders}) AND g.season = ?
                GROUP BY pgs.player_id
                ORDER BY starts DESC, games DESC
                LIMIT 1
                """,
                (*goalie_ids, season),
            )
            row = cur.fetchone()
            if row:
                return row["player_id"]

        # Fallback: first goalie in roster
        return goalie_ids[0] if goalie_ids else None

    def _build_zone_heat_maps(
        self,
        team_abbrev: str,
        season: int,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Build offensive and defensive zone heat maps (zone strength 0-1)."""
        offensive_map: dict[str, float] = {}
        defensive_map: dict[str, float] = {}

        with self.db.cursor() as cur:
            # Offensive: team's shots by zone
            cur.execute(
                """
                SELECT x_coord, y_coord, is_goal
                FROM shots
                WHERE team_abbrev = ? AND season = ?
                """,
                (team_abbrev, season),
            )
            shots = cur.fetchall()

            zone_shots: dict[str, int] = {}
            zone_goals: dict[str, int] = {}
            total_shots = 0

            for shot in shots:
                zone = _classify_zone(shot["x_coord"], shot["y_coord"])
                zone_shots[zone] = zone_shots.get(zone, 0) + 1
                total_shots += 1
                if shot["is_goal"]:
                    zone_goals[zone] = zone_goals.get(zone, 0) + 1

            # Normalize to 0-1 scale (relative to average)
            if total_shots > 0:
                avg_per_zone = total_shots / max(len(zone_shots), 1)
                for zone, count in zone_shots.items():
                    # Combine volume and efficiency
                    volume_factor = count / avg_per_zone
                    goals = zone_goals.get(zone, 0)
                    efficiency = goals / count if count > 0 else 0
                    # Strength = normalized combination
                    offensive_map[zone] = min(1.0, (volume_factor * 0.5 + efficiency * 5) / 2)

            # Defensive: opponents' shots against this team
            cur.execute(
                """
                SELECT s.x_coord, s.y_coord, s.is_goal
                FROM shots s
                JOIN games g ON s.game_id = g.game_id
                WHERE s.team_abbrev != ? AND s.season = ?
                AND (g.home_team_abbrev = ? OR g.away_team_abbrev = ?)
                """,
                (team_abbrev, season, team_abbrev, team_abbrev),
            )
            opp_shots = cur.fetchall()

            opp_zone_shots: dict[str, int] = {}
            opp_zone_goals: dict[str, int] = {}
            opp_total = 0

            for shot in opp_shots:
                zone = _classify_zone(shot["x_coord"], shot["y_coord"])
                opp_zone_shots[zone] = opp_zone_shots.get(zone, 0) + 1
                opp_total += 1
                if shot["is_goal"]:
                    opp_zone_goals[zone] = opp_zone_goals.get(zone, 0) + 1

            # Defensive strength: lower goals against rate = higher strength
            if opp_total > 0:
                avg_opp_per_zone = opp_total / max(len(opp_zone_shots), 1)
                for zone, count in opp_zone_shots.items():
                    goals_against = opp_zone_goals.get(zone, 0)
                    ga_rate = goals_against / count if count > 0 else 0
                    # Invert: lower GA rate = higher defensive strength
                    defensive_map[zone] = min(1.0, max(0.0, 1.0 - ga_rate * 5))

        return offensive_map, defensive_map

    def _populate_segment_stats(self, team: Team, season: int) -> None:
        """Populate early/mid/late game goal stats from shots table."""
        abbrev = team.abbreviation
        stats = team.current_season_stats

        with self.db.cursor() as cur:
            # Goals by period for team
            cur.execute(
                """
                SELECT period, COUNT(*) as goals
                FROM shots
                WHERE team_abbrev = ? AND season = ? AND is_goal = 1
                GROUP BY period
                """,
                (abbrev, season),
            )
            for row in cur.fetchall():
                period = row["period"]
                goals = row["goals"]
                if period == 1:
                    stats.early_game_goals_for += goals
                elif period == 2:
                    # Split P2: first half to early, second half to mid
                    stats.early_game_goals_for += goals // 2
                    stats.mid_game_goals_for += goals - goals // 2
                elif period == 3:
                    # Split P3: first half to mid, second half to late
                    stats.mid_game_goals_for += goals // 2
                    stats.late_game_goals_for += goals - goals // 2
                elif period >= 4:
                    stats.late_game_goals_for += goals

            # Goals against by period
            cur.execute(
                """
                SELECT s.period, COUNT(*) as goals
                FROM shots s
                JOIN games g ON s.game_id = g.game_id
                WHERE s.team_abbrev != ? AND s.season = ? AND s.is_goal = 1
                AND (g.home_team_abbrev = ? OR g.away_team_abbrev = ?)
                GROUP BY s.period
                """,
                (abbrev, season, abbrev, abbrev),
            )
            for row in cur.fetchall():
                period = row["period"]
                goals = row["goals"]
                if period == 1:
                    stats.early_game_goals_against += goals
                elif period == 2:
                    stats.early_game_goals_against += goals // 2
                    stats.mid_game_goals_against += goals - goals // 2
                elif period == 3:
                    stats.mid_game_goals_against += goals // 2
                    stats.late_game_goals_against += goals - goals // 2
                elif period >= 4:
                    stats.late_game_goals_against += goals

    # -------------------------------------------------------------------------
    # Player Enrichment
    # -------------------------------------------------------------------------

    def enrich_players(
        self,
        players: dict[int, Player],
        season: int,
        opponent_abbrev: str | None = None,
    ) -> tuple[int, int]:
        """
        Enrich Player objects with season stats from the local database.

        Returns:
            Tuple of (players_enriched, players_with_matchup_data)
        """
        enriched = 0
        with_matchup = 0

        for player_id, player in players.items():
            if self._enrich_player(player, season, opponent_abbrev):
                enriched += 1
            if opponent_abbrev and self._has_matchup_data(player_id, opponent_abbrev, season):
                with_matchup += 1

        logger.info(
            f"Enriched {enriched}/{len(players)} players, "
            f"{with_matchup} with matchup data vs {opponent_abbrev}"
        )
        return enriched, with_matchup

    def _enrich_player(
        self,
        player: Player,
        season: int,
        opponent_abbrev: str | None = None,
    ) -> bool:
        """Enrich a single player with DB stats. Returns True if data was found."""
        player_id = player.player_id
        found_data = False

        with self.db.cursor() as cur:
            # Season stats from player_game_stats
            cur.execute(
                """
                SELECT
                    COUNT(*) as games,
                    SUM(goals) as goals,
                    SUM(assists) as assists,
                    SUM(points) as points,
                    SUM(shots) as shots,
                    SUM(plus_minus) as pm,
                    SUM(pim) as pim,
                    SUM(toi_seconds) as toi,
                    SUM(power_play_goals) as ppg,
                    SUM(power_play_points) as ppp,
                    SUM(shorthanded_goals) as shg,
                    SUM(shorthanded_points) as shp,
                    SUM(game_winning_goals) as gwg,
                    SUM(overtime_goals) as otg,
                    SUM(hits) as hits,
                    SUM(blocked_shots) as blk
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id = ? AND g.season = ?
                """,
                (player_id, season),
            )
            row = cur.fetchone()

            if row and row["games"] and row["games"] > 0:
                found_data = True
                season_stats = PlayerStats(
                    games_played=row["games"],
                    goals=row["goals"] or 0,
                    assists=row["assists"] or 0,
                    points=row["points"] or 0,
                    plus_minus=row["pm"] or 0,
                    penalty_minutes=row["pim"] or 0,
                    shots=row["shots"] or 0,
                    time_on_ice_seconds=row["toi"] or 0,
                    average_toi_per_game=(row["toi"] or 0) / row["games"],
                    power_play_goals=row["ppg"] or 0,
                    power_play_points=row["ppp"] or 0,
                    shorthanded_goals=row["shg"] or 0,
                    shorthanded_points=row["shp"] or 0,
                )

                if row["shots"] and row["shots"] > 0:
                    season_stats.shooting_percentage = (row["goals"] or 0) / row["shots"]

                # Store as season stats
                season_key = str(season)
                player.season_stats[season_key] = season_stats

                # Also update career stats if they have less data
                if season_stats.games_played > player.career_stats.games_played:
                    player.career_stats = season_stats

            # Goalie stats
            if player.is_goalie:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as games,
                        SUM(CASE WHEN games_started = 1 THEN 1 ELSE 0 END) as starts,
                        SUM(saves) as saves,
                        SUM(shots_against) as sa,
                        SUM(goals_against) as ga,
                        SUM(wins) as wins,
                        SUM(losses) as losses,
                        SUM(ot_losses) as otl,
                        SUM(shutouts) as so,
                        SUM(toi_seconds) as toi
                    FROM player_game_stats pgs
                    JOIN games g ON pgs.game_id = g.game_id
                    WHERE pgs.player_id = ? AND g.season = ?
                    """,
                    (player_id, season),
                )
                grow = cur.fetchone()
                if grow and grow["games"] and grow["games"] > 0:
                    found_data = True
                    goalie_stats = GoalieStats(
                        games_played=grow["games"],
                        games_started=grow["starts"] or 0,
                        saves=grow["saves"] or 0,
                        shots_against=grow["sa"] or 0,
                        goals_against=grow["ga"] or 0,
                        wins=grow["wins"] or 0,
                        losses=grow["losses"] or 0,
                        overtime_losses=grow["otl"] or 0,
                        shutouts=grow["so"] or 0,
                        time_on_ice_seconds=grow["toi"] or 0,
                    )
                    if grow["sa"] and grow["sa"] > 0:
                        goalie_stats.save_percentage = (grow["saves"] or 0) / grow["sa"]
                    if grow["toi"] and grow["toi"] > 0:
                        goalie_stats.goals_against_average = (
                            (grow["ga"] or 0) / grow["toi"] * 3600
                        )
                    player.goalie_stats = goalie_stats

            # Shot zone stats
            cur.execute(
                """
                SELECT x_coord, y_coord, is_goal
                FROM shots
                WHERE player_id = ? AND season = ?
                """,
                (player_id, season),
            )
            shot_rows = cur.fetchall()

            if shot_rows:
                found_data = True
                zone_data: dict[str, dict[str, int]] = {}
                for srow in shot_rows:
                    zone = _classify_zone(srow["x_coord"], srow["y_coord"])
                    if zone not in zone_data:
                        zone_data[zone] = {"shots": 0, "goals": 0}
                    zone_data[zone]["shots"] += 1
                    if srow["is_goal"]:
                        zone_data[zone]["goals"] += 1

                # Update career_stats.zone_stats
                for zone, data in zone_data.items():
                    shooting_pct = data["goals"] / data["shots"] if data["shots"] > 0 else 0
                    player.career_stats.zone_stats[zone] = ZoneStats(
                        zone_name=zone,
                        shots=data["shots"],
                        goals=data["goals"],
                        shooting_percentage=shooting_pct,
                    )

                # Build offensive heat map
                total_shots_player = sum(d["shots"] for d in zone_data.values())
                if total_shots_player > 0:
                    for zone, data in zone_data.items():
                        player.offensive_heat_map[zone] = data["shots"] / total_shots_player

            # Segment stats (period-based)
            cur.execute(
                """
                SELECT period, COUNT(*) as goals
                FROM shots
                WHERE player_id = ? AND season = ? AND is_goal = 1
                GROUP BY period
                """,
                (player_id, season),
            )
            for prow in cur.fetchall():
                period = prow["period"]
                goals = prow["goals"]
                if period == 1:
                    player.career_stats.early_game_goals += goals
                elif period == 2:
                    player.career_stats.early_game_goals += goals // 2
                    player.career_stats.mid_game_goals += goals - goals // 2
                elif period == 3:
                    player.career_stats.mid_game_goals += goals // 2
                    player.career_stats.late_game_goals += goals - goals // 2
                elif period >= 4:
                    player.career_stats.late_game_goals += goals

        return found_data

    def _has_matchup_data(
        self, player_id: int, opponent_abbrev: str, season: int
    ) -> bool:
        """Check if player has matchup data against opponent."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) as games
                FROM player_game_stats pgs
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.player_id = ? AND pgs.opponent_abbrev = ? AND g.season = ?
                """,
                (player_id, opponent_abbrev, season),
            )
            row = cur.fetchone()
            return row is not None and row["games"] >= 1

    # -------------------------------------------------------------------------
    # Schedule Context & Fatigue
    # -------------------------------------------------------------------------

    def get_team_fatigue(
        self,
        team_abbrev: str,
        season: int,
    ) -> FatigueModifier | None:
        """Get fatigue modifier for a team's most recent schedule context."""
        try:
            # Get the most recent schedule context
            with self.db.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM schedule_context
                    WHERE team_abbrev = ?
                    ORDER BY game_date DESC LIMIT 1
                    """,
                    (team_abbrev,),
                )
                row = cur.fetchone()

            if not row:
                # Try computing it fresh from games data
                contexts = self._schedule_pipeline.analyze_team_schedule(team_abbrev, season)
                if contexts:
                    try:
                        self._schedule_pipeline.save_schedule_context(contexts)
                    except Exception:
                        pass  # Table might not exist yet
                    return self._schedule_pipeline.calculate_fatigue_modifier(contexts[-1])
                return None

            from src.processors.schedule_context_pipeline import ScheduleContext

            ctx = ScheduleContext(
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
            return self._schedule_pipeline.calculate_fatigue_modifier(ctx)
        except Exception as e:
            logger.warning(f"Could not compute fatigue for {team_abbrev}: {e}")
            return None

    def apply_team_fatigue_to_players(
        self,
        players: dict[int, Player],
        team_roster_ids: list[int],
        fatigue: FatigueModifier,
    ) -> None:
        """Apply team-level fatigue modifier to all players on a team."""
        modifier = fatigue.combined_modifier
        for pid in team_roster_ids:
            if pid in players:
                players[pid].fatigue_factor = modifier

    # -------------------------------------------------------------------------
    # Player Momentum
    # -------------------------------------------------------------------------

    def compute_player_momentum(
        self,
        players: dict[int, Player],
        season: int,
    ) -> int:
        """
        Compute and apply momentum modifiers to players.

        Returns number of players with momentum data.
        """
        count = 0
        today = datetime.now().strftime("%Y-%m-%d")

        for player_id, player in players.items():
            if player.is_goalie:
                continue

            try:
                analysis = self._momentum_pipeline.analyze_momentum(
                    player_id=player_id,
                    season=season,
                    as_of_date=today,
                    window_games=10,
                )
                if analysis.games_in_window > 0:
                    modifier = self._momentum_pipeline.get_momentum_modifier(analysis)
                    # Apply momentum to clutch_rating as a signal
                    player.clutch_rating = modifier
                    count += 1
            except Exception:
                # Skip players without enough data or missing tables
                pass

        logger.info(f"Momentum computed for {count} players")
        return count

    # -------------------------------------------------------------------------
    # Full Enrichment Pipeline
    # -------------------------------------------------------------------------

    def enrich_all(
        self,
        home_team: Team,
        away_team: Team,
        all_players: dict[int, Player],
    ) -> EnrichmentSummary:
        """
        Run the complete enrichment pipeline.

        This is the main entry point called by the Orchestrator.
        """
        summary = EnrichmentSummary()

        # 1. Detect season and phase
        summary.season = self.detect_current_season()
        summary.season_phase = self.get_current_season_phase(summary.season)
        logger.info(f"Season: {summary.season}, Phase: {summary.season_phase}")

        # 2. Enrich teams
        with diag.timer("ENRICH_TEAMS"):
            self.enrich_team(home_team, summary.season, away_team.abbreviation)
            self.enrich_team(away_team, summary.season, home_team.abbreviation)

            summary.home_team_stats_loaded = home_team.current_season_stats.games_played > 0
            summary.away_team_stats_loaded = away_team.current_season_stats.games_played > 0
            summary.home_lines_built = len(home_team.forward_lines)
            summary.away_lines_built = len(away_team.forward_lines)
            summary.home_defense_pairs_built = len(home_team.defense_pairs)
            summary.away_defense_pairs_built = len(away_team.defense_pairs)
            summary.home_goalie_set = home_team.starting_goalie_id is not None
            summary.away_goalie_set = away_team.starting_goalie_id is not None

        # 3. Enrich players
        with diag.timer("ENRICH_PLAYERS"):
            enriched, with_matchup = self.enrich_players(
                all_players, summary.season, away_team.abbreviation
            )
            summary.players_enriched = enriched
            summary.players_with_matchup_data = with_matchup

        # 4. Schedule context & fatigue
        with diag.timer("ENRICH_FATIGUE"):
            summary.home_fatigue = self.get_team_fatigue(
                home_team.abbreviation, summary.season
            )
            summary.away_fatigue = self.get_team_fatigue(
                away_team.abbreviation, summary.season
            )

            if summary.home_fatigue:
                self.apply_team_fatigue_to_players(
                    all_players, home_team.roster.all_players, summary.home_fatigue
                )
            if summary.away_fatigue:
                self.apply_team_fatigue_to_players(
                    all_players, away_team.roster.all_players, summary.away_fatigue
                )

        # 5. Player momentum
        with diag.timer("ENRICH_MOMENTUM"):
            summary.players_with_momentum = self.compute_player_momentum(
                all_players, summary.season
            )

        return summary
