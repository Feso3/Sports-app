"""
Simulation Profiles Module

Builds comprehensive player and goalie profiles for simulation by combining:
- General season stats
- Matchup-specific stats (with similarity-based weighting)
- Shot location profiles
- Phase-specific performance
- Momentum state (hot/cold streaks)
- Schedule context

Reference: docs/simulation-logic-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from src.database.db import Database, get_database
from src.processors.matchup_history_pipeline import (
    MatchupHistoryPipeline,
    PlayerMatchupStats,
    PlayerSeasonStats,
    GoalieMatchupStats,
    GoalieSeasonStats,
    SimilarityResult,
    MatchupWeights,
)
from src.processors.momentum_pipeline import (
    MomentumPipeline,
    MomentumAnalysis,
    MomentumState,
)
from src.processors.schedule_context_pipeline import (
    ScheduleContextPipeline,
    ScheduleContext,
    FatigueModifier,
)


@dataclass
class ShotProfile:
    """Shot location and type profile for a player."""

    # Zone distribution (% of shots from each zone)
    zone_distribution: dict[str, float] = field(default_factory=dict)

    # Zone-specific outcomes
    zone_shooting_pct: dict[str, float] = field(default_factory=dict)

    # Shot type distribution
    shot_type_distribution: dict[str, float] = field(default_factory=dict)

    # Shot type effectiveness
    shot_type_effectiveness: dict[str, float] = field(default_factory=dict)


@dataclass
class PlayerSimulationProfile:
    """
    Complete player profile for simulation.

    Contains all data needed to simulate a player's performance
    including blended general/matchup stats.
    """

    player_id: int
    player_name: str = ""
    position: str = ""
    team_abbrev: str = ""

    # Season averages
    season_games: int = 0
    season_goals_per_game: float = 0.0
    season_assists_per_game: float = 0.0
    season_points_per_game: float = 0.0
    season_shots_per_game: float = 0.0
    season_shooting_pct: float = 0.0
    season_toi_per_game: float = 0.0

    # Matchup-specific stats (against current opponent)
    matchup_games: int = 0
    matchup_goals_per_game: float = 0.0
    matchup_assists_per_game: float = 0.0
    matchup_points_per_game: float = 0.0
    matchup_shots_per_game: float = 0.0
    matchup_shooting_pct: float = 0.0

    # Blended stats (weighted combination)
    blended_goals_per_game: float = 0.0
    blended_assists_per_game: float = 0.0
    blended_points_per_game: float = 0.0
    blended_shots_per_game: float = 0.0
    blended_shooting_pct: float = 0.0

    # Weights used for blending
    general_weight: float = 1.0
    matchup_weight: float = 0.0
    similarity_score: float = 1.0

    # Shot profile
    shot_profile: ShotProfile = field(default_factory=ShotProfile)

    # Momentum state
    momentum_state: str = "neutral"
    momentum_score: float = 0.0
    momentum_modifier: float = 1.0

    # Combined effectiveness modifier
    effectiveness_modifier: float = 1.0


@dataclass
class GoalieSimulationProfile:
    """
    Complete goalie profile for simulation.

    Contains save percentages by zone and shot type with
    blended general/matchup data.
    """

    goalie_id: int
    goalie_name: str = ""
    team_abbrev: str = ""

    # Season averages
    season_games: int = 0
    season_save_pct: float = 0.0
    season_gaa: float = 0.0

    # Matchup-specific stats
    matchup_games: int = 0
    matchup_save_pct: float = 0.0
    matchup_gaa: float = 0.0

    # Blended stats
    blended_save_pct: float = 0.0
    blended_gaa: float = 0.0

    # Weights
    general_weight: float = 1.0
    matchup_weight: float = 0.0

    # Zone-specific save percentages
    zone_save_pct: dict[str, float] = field(default_factory=dict)

    # Shot type save percentages
    shot_type_save_pct: dict[str, float] = field(default_factory=dict)

    # Momentum
    momentum_state: str = "neutral"
    momentum_modifier: float = 1.0


@dataclass
class TeamSimulationContext:
    """
    Complete context for simulating a team in a specific game.

    Contains all players, schedule context, and adjustments.
    """

    team_abbrev: str
    opponent_abbrev: str
    game_date: str
    season: int

    # Player profiles
    skater_profiles: dict[int, PlayerSimulationProfile] = field(default_factory=dict)
    goalie_profile: Optional[GoalieSimulationProfile] = None

    # Schedule context
    schedule_context: Optional[ScheduleContext] = None
    fatigue_modifier: Optional[FatigueModifier] = None

    # Line configurations (player_id lists)
    forward_lines: list[list[int]] = field(default_factory=list)
    defense_pairs: list[list[int]] = field(default_factory=list)


class SimulationProfileBuilder:
    """
    Builds complete simulation profiles by combining all data sources.

    This is the main orchestrator that:
    1. Loads season stats
    2. Loads matchup stats
    3. Calculates similarity and weights
    4. Blends stats based on weights
    5. Applies momentum modifiers
    6. Returns ready-to-use profiles
    """

    def __init__(self, db: Optional[Database] = None):
        """Initialize the profile builder."""
        self.db = db or get_database()
        self.matchup_pipeline = MatchupHistoryPipeline(db=self.db)
        self.momentum_pipeline = MomentumPipeline(db=self.db)
        self.schedule_pipeline = ScheduleContextPipeline(db=self.db)

    def build_player_profile(
        self,
        player_id: int,
        opponent_team_abbrev: str,
        season: int,
        game_date: Optional[str] = None,
    ) -> PlayerSimulationProfile:
        """
        Build a complete player simulation profile.

        Args:
            player_id: NHL player ID
            opponent_team_abbrev: Opponent team abbreviation
            season: Season identifier
            game_date: Date for momentum calculation

        Returns:
            PlayerSimulationProfile with all stats and modifiers
        """
        profile = PlayerSimulationProfile(player_id=player_id)

        # Get player info
        player = self.db.get_player(player_id)
        if player:
            profile.player_name = player.get("full_name", "")
            profile.position = player.get("position", "")
            profile.team_abbrev = player.get("current_team_abbrev", "")

        # Get season stats
        season_stats = self._get_or_calculate_season_stats(player_id, season)
        if season_stats:
            profile.season_games = season_stats.games_played
            profile.season_goals_per_game = season_stats.goals_per_game
            profile.season_assists_per_game = season_stats.assists_per_game
            profile.season_points_per_game = season_stats.points_per_game
            profile.season_shots_per_game = season_stats.shots_per_game
            profile.season_shooting_pct = season_stats.shooting_pct
            profile.season_toi_per_game = season_stats.toi_per_game_seconds

        # Get matchup stats
        matchup_stats = self._get_or_calculate_matchup_stats(
            player_id, opponent_team_abbrev, season
        )
        if matchup_stats and matchup_stats.games_played > 0:
            profile.matchup_games = matchup_stats.games_played
            profile.matchup_goals_per_game = matchup_stats.goals_per_game
            profile.matchup_assists_per_game = matchup_stats.assists_per_game
            profile.matchup_points_per_game = matchup_stats.points_per_game
            profile.matchup_shots_per_game = matchup_stats.shots_per_game
            profile.matchup_shooting_pct = matchup_stats.shooting_pct

        # Calculate similarity and weights
        if season_stats and matchup_stats:
            similarity = self.matchup_pipeline.calculate_similarity(
                season_stats, matchup_stats
            )
            profile.similarity_score = similarity.similarity_score
            profile.general_weight = similarity.general_weight
            profile.matchup_weight = similarity.matchup_weight

        # Calculate blended stats
        self._blend_player_stats(profile)

        # Get momentum
        if game_date:
            momentum = self._get_or_calculate_momentum(player_id, season, game_date)
            if momentum:
                profile.momentum_state = momentum.momentum_state.value
                profile.momentum_score = momentum.momentum_score
                profile.momentum_modifier = self.momentum_pipeline.get_momentum_modifier(
                    momentum
                )

        # Load shot profile
        profile.shot_profile = self._load_shot_profile(player_id, season)

        # Calculate combined effectiveness
        profile.effectiveness_modifier = profile.momentum_modifier

        return profile

    def build_goalie_profile(
        self,
        goalie_id: int,
        opponent_team_abbrev: str,
        season: int,
    ) -> GoalieSimulationProfile:
        """
        Build a complete goalie simulation profile.

        Args:
            goalie_id: NHL goalie player ID
            opponent_team_abbrev: Opponent team abbreviation
            season: Season identifier

        Returns:
            GoalieSimulationProfile with all stats
        """
        profile = GoalieSimulationProfile(goalie_id=goalie_id)

        # Get goalie info
        goalie = self.db.get_player(goalie_id)
        if goalie:
            profile.goalie_name = goalie.get("full_name", "")
            profile.team_abbrev = goalie.get("current_team_abbrev", "")

        # Get season stats
        season_stats = self._get_goalie_season_stats(goalie_id, season)
        if season_stats:
            profile.season_games = season_stats.games_played
            profile.season_save_pct = season_stats.save_pct
            profile.season_gaa = season_stats.gaa

        # Get matchup stats
        matchup_stats = self._get_goalie_matchup_stats(
            goalie_id, opponent_team_abbrev, season
        )
        if matchup_stats and matchup_stats.games_played > 0:
            profile.matchup_games = matchup_stats.games_played
            profile.matchup_save_pct = matchup_stats.save_pct
            profile.matchup_gaa = matchup_stats.gaa

            # Simple weighting for goalies (based on sample size)
            if matchup_stats.games_played >= 3:
                confidence = min(1.0, matchup_stats.games_played / 10)
                profile.matchup_weight = confidence * 0.3  # Max 30% matchup weight
                profile.general_weight = 1.0 - profile.matchup_weight

        # Calculate blended stats
        profile.blended_save_pct = (
            profile.season_save_pct * profile.general_weight +
            profile.matchup_save_pct * profile.matchup_weight
        )
        profile.blended_gaa = (
            profile.season_gaa * profile.general_weight +
            profile.matchup_gaa * profile.matchup_weight
        )

        # Load zone and shot type profiles
        profile.zone_save_pct = self._load_goalie_zone_profile(goalie_id, season)
        profile.shot_type_save_pct = self._load_goalie_shot_type_profile(goalie_id, season)

        return profile

    def build_team_context(
        self,
        team_abbrev: str,
        opponent_abbrev: str,
        game_date: str,
        season: int,
        game_id: Optional[int] = None,
        starting_goalie_id: Optional[int] = None,
    ) -> TeamSimulationContext:
        """
        Build complete simulation context for a team.

        Args:
            team_abbrev: Team abbreviation
            opponent_abbrev: Opponent team abbreviation
            game_date: Game date
            season: Season identifier
            game_id: Optional game ID for schedule context
            starting_goalie_id: Optional starting goalie ID

        Returns:
            TeamSimulationContext with all profiles and context
        """
        context = TeamSimulationContext(
            team_abbrev=team_abbrev,
            opponent_abbrev=opponent_abbrev,
            game_date=game_date,
            season=season,
        )

        # Get team roster
        skater_ids, goalie_ids = self._get_team_roster(team_abbrev, season)

        # Build skater profiles
        for player_id in skater_ids:
            profile = self.build_player_profile(
                player_id=player_id,
                opponent_team_abbrev=opponent_abbrev,
                season=season,
                game_date=game_date,
            )
            context.skater_profiles[player_id] = profile

        # Build goalie profile
        goalie_id = starting_goalie_id or (goalie_ids[0] if goalie_ids else None)
        if goalie_id:
            context.goalie_profile = self.build_goalie_profile(
                goalie_id=goalie_id,
                opponent_team_abbrev=opponent_abbrev,
                season=season,
            )

        # Get schedule context
        if game_id:
            context.schedule_context = self.schedule_pipeline.get_schedule_context(
                team_abbrev, game_id
            )
            if context.schedule_context:
                context.fatigue_modifier = self.schedule_pipeline.calculate_fatigue_modifier(
                    context.schedule_context
                )

        return context

    def _get_or_calculate_season_stats(
        self,
        player_id: int,
        season: int,
    ) -> Optional[PlayerSeasonStats]:
        """Get season stats from database or calculate fresh."""
        # Try to get from database first
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM player_season_stats
                WHERE player_id = ? AND season = ?
                """,
                (player_id, season),
            )
            row = cur.fetchone()

            if row:
                stats = PlayerSeasonStats(
                    player_id=row["player_id"],
                    season=row["season"],
                    games_played=row["games_played"] or 0,
                    goals=row["goals"] or 0,
                    assists=row["assists"] or 0,
                    points=row["points"] or 0,
                    shots=row["shots"] or 0,
                    toi_seconds=row["toi_seconds"] or 0,
                )
                stats.goals_per_game = row["goals_per_game"] or 0.0
                stats.assists_per_game = row["assists_per_game"] or 0.0
                stats.points_per_game = row["points_per_game"] or 0.0
                stats.shots_per_game = row["shots_per_game"] or 0.0
                stats.shooting_pct = row["shooting_pct"] or 0.0
                stats.toi_per_game_seconds = row["toi_per_game_seconds"] or 0.0
                stats.goals_per_game_std = row["goals_per_game_std"] or 0.0
                stats.points_per_game_std = row["points_per_game_std"] or 0.0
                stats.shots_per_game_std = row["shots_per_game_std"] or 0.0
                stats.shooting_pct_std = row["shooting_pct_std"] or 0.0
                return stats

        # Calculate fresh if not in database
        return self.matchup_pipeline.aggregate_player_season_stats(player_id, season)

    def _get_or_calculate_matchup_stats(
        self,
        player_id: int,
        opponent_team_abbrev: str,
        season: int,
    ) -> Optional[PlayerMatchupStats]:
        """Get matchup stats from database or calculate fresh."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM player_matchup_stats
                WHERE player_id = ? AND opponent_team_abbrev = ? AND season = ?
                """,
                (player_id, opponent_team_abbrev, season),
            )
            row = cur.fetchone()

            if row:
                stats = PlayerMatchupStats(
                    player_id=row["player_id"],
                    opponent_team_abbrev=row["opponent_team_abbrev"],
                    season=row["season"],
                    games_played=row["games_played"] or 0,
                )
                stats.goals_per_game = row["goals_per_game"] or 0.0
                stats.assists_per_game = row["assists_per_game"] or 0.0
                stats.points_per_game = row["points_per_game"] or 0.0
                stats.shots_per_game = row["shots_per_game"] or 0.0
                stats.shooting_pct = row["shooting_pct"] or 0.0
                return stats

        # Calculate fresh
        return self.matchup_pipeline.aggregate_player_matchup_stats(
            player_id, opponent_team_abbrev, season
        )

    def _get_or_calculate_momentum(
        self,
        player_id: int,
        season: int,
        game_date: str,
    ) -> Optional[MomentumAnalysis]:
        """Get momentum analysis from database or calculate fresh."""
        momentum = self.momentum_pipeline.get_player_momentum(
            player_id, game_date, window_games=10
        )
        if momentum:
            return momentum

        # Calculate fresh
        return self.momentum_pipeline.analyze_momentum(
            player_id=player_id,
            season=season,
            as_of_date=game_date,
            window_games=10,
        )

    def _get_goalie_season_stats(
        self,
        goalie_id: int,
        season: int,
    ) -> Optional[GoalieSeasonStats]:
        """Get goalie season stats."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM goalie_season_stats
                WHERE goalie_id = ? AND season = ?
                """,
                (goalie_id, season),
            )
            row = cur.fetchone()

            if row:
                stats = GoalieSeasonStats(
                    goalie_id=row["goalie_id"],
                    season=row["season"],
                    games_played=row["games_played"] or 0,
                )
                stats.save_pct = row["save_pct"] or 0.0
                stats.gaa = row["gaa"] or 0.0
                return stats

        # Calculate fresh
        return self.matchup_pipeline.aggregate_goalie_season_stats(goalie_id, season)

    def _get_goalie_matchup_stats(
        self,
        goalie_id: int,
        opponent_team_abbrev: str,
        season: int,
    ) -> Optional[GoalieMatchupStats]:
        """Get goalie matchup stats."""
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM goalie_matchup_stats
                WHERE goalie_id = ? AND opponent_team_abbrev = ? AND season = ?
                """,
                (goalie_id, opponent_team_abbrev, season),
            )
            row = cur.fetchone()

            if row:
                stats = GoalieMatchupStats(
                    goalie_id=row["goalie_id"],
                    opponent_team_abbrev=row["opponent_team_abbrev"],
                    season=row["season"],
                    games_played=row["games_played"] or 0,
                )
                stats.save_pct = row["save_pct"] or 0.0
                stats.gaa = row["gaa"] or 0.0
                return stats

        return self.matchup_pipeline.aggregate_goalie_matchup_stats(
            goalie_id, opponent_team_abbrev, season
        )

    def _blend_player_stats(self, profile: PlayerSimulationProfile) -> None:
        """Calculate blended stats based on weights."""
        gw = profile.general_weight
        mw = profile.matchup_weight

        profile.blended_goals_per_game = (
            profile.season_goals_per_game * gw +
            profile.matchup_goals_per_game * mw
        )
        profile.blended_assists_per_game = (
            profile.season_assists_per_game * gw +
            profile.matchup_assists_per_game * mw
        )
        profile.blended_points_per_game = (
            profile.season_points_per_game * gw +
            profile.matchup_points_per_game * mw
        )
        profile.blended_shots_per_game = (
            profile.season_shots_per_game * gw +
            profile.matchup_shots_per_game * mw
        )
        profile.blended_shooting_pct = (
            profile.season_shooting_pct * gw +
            profile.matchup_shooting_pct * mw
        )

    def _load_shot_profile(
        self,
        player_id: int,
        season: int,
    ) -> ShotProfile:
        """Load shot location and type profile from shots data."""
        profile = ShotProfile()

        with self.db.cursor() as cur:
            # Get shot type distribution
            cur.execute(
                """
                SELECT
                    shot_type,
                    COUNT(*) as count,
                    SUM(is_goal) as goals
                FROM shots
                WHERE player_id = ? AND season = ?
                GROUP BY shot_type
                """,
                (player_id, season),
            )
            rows = cur.fetchall()

            total_shots = sum(row["count"] for row in rows)
            if total_shots > 0:
                for row in rows:
                    shot_type = row["shot_type"] or "unknown"
                    profile.shot_type_distribution[shot_type] = row["count"] / total_shots
                    if row["count"] > 0:
                        profile.shot_type_effectiveness[shot_type] = (
                            (row["goals"] or 0) / row["count"] * 100
                        )

        return profile

    def _load_goalie_zone_profile(
        self,
        goalie_id: int,
        season: int,
    ) -> dict[str, float]:
        """Load goalie save percentage by zone."""
        # This would integrate with the goalie_shot_profile_pipeline
        # For now return empty dict - can be populated from pipeline data
        return {}

    def _load_goalie_shot_type_profile(
        self,
        goalie_id: int,
        season: int,
    ) -> dict[str, float]:
        """Load goalie save percentage by shot type."""
        profile = {}

        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    shot_type,
                    COUNT(*) as shots,
                    SUM(is_goal) as goals
                FROM shots
                WHERE goalie_id = ? AND season = ?
                GROUP BY shot_type
                """,
                (goalie_id, season),
            )
            rows = cur.fetchall()

            for row in rows:
                shot_type = row["shot_type"] or "unknown"
                shots = row["shots"] or 0
                goals = row["goals"] or 0
                if shots > 0:
                    profile[shot_type] = (shots - goals) / shots

        return profile

    def _get_team_roster(
        self,
        team_abbrev: str,
        season: int,
    ) -> tuple[list[int], list[int]]:
        """Get team roster divided into skaters and goalies."""
        skaters = []
        goalies = []

        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT p.player_id, p.position
                FROM players p
                JOIN player_game_stats pgs ON p.player_id = pgs.player_id
                JOIN games g ON pgs.game_id = g.game_id
                WHERE pgs.team_abbrev = ? AND g.season = ?
                """,
                (team_abbrev, season),
            )
            rows = cur.fetchall()

            for row in rows:
                if row["position"] == "G":
                    goalies.append(row["player_id"])
                else:
                    skaters.append(row["player_id"])

        return skaters, goalies
