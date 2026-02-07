"""
Monte Carlo Simulation Engine

Core simulation framework for NHL game outcome prediction using
Monte Carlo methods with 10,000+ iterations per matchup.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger

from simulation.expected_goals import ExpectedGoalsCalculator, TeamExpectedGoals
from simulation.matchups import MatchupAnalyzer
from simulation.models import (
    GameSegment,
    GameSituation,
    LineMatchup,
    MatchupAnalysis,
    ScoreDistribution,
    SegmentResult,
    SeriesResult,
    SimulatedGame,
    SimulationConfig,
    SimulationMode,
    SimulationResult,
)

if TYPE_CHECKING:
    from src.analytics.clutch_analysis import ClutchAnalyzer, StaminaAnalyzer
    from src.analytics.synergy import SynergyAnalyzer
    from src.models.player import Player
    from src.models.team import Team


@dataclass
class SegmentContext:
    """Context for simulating a game segment."""

    segment: GameSegment
    home_xg_base: float
    away_xg_base: float
    segment_weight: float
    clutch_home: float = 1.0
    clutch_away: float = 1.0
    fatigue_home: float = 1.0
    fatigue_away: float = 1.0


class GameSimulationEngine:
    """
    Monte Carlo game simulation engine.

    Simulates NHL games using expected goals models, line matchups,
    and various situational adjustments.
    """

    # Variance parameters
    POISSON_LAMBDA_SCALE = 1.0  # Scale factor for Poisson distribution
    GOALIE_VARIANCE = 0.05  # Goalie performance variance

    # Game structure constants
    PERIODS = 3
    MINUTES_PER_PERIOD = 20
    OVERTIME_MINUTES = 5
    SHOOTOUT_ROUNDS = 3

    # Situation probabilities per period
    PENALTY_PROBABILITY = 0.08  # Per period
    POWER_PLAY_DURATION_MINUTES = 1.5  # Average PP duration

    def __init__(
        self,
        xg_calculator: ExpectedGoalsCalculator | None = None,
        matchup_analyzer: MatchupAnalyzer | None = None,
        synergy_analyzer: SynergyAnalyzer | None = None,
        clutch_analyzer: ClutchAnalyzer | None = None,
        stamina_analyzer: StaminaAnalyzer | None = None,
    ) -> None:
        """
        Initialize the simulation engine.

        Args:
            xg_calculator: Expected goals calculator
            matchup_analyzer: Line matchup analyzer
            synergy_analyzer: Synergy analyzer from Phase 3
            clutch_analyzer: Clutch performance analyzer from Phase 3
            stamina_analyzer: Stamina/fatigue analyzer from Phase 3
        """
        self.xg_calculator = xg_calculator or ExpectedGoalsCalculator()
        self.matchup_analyzer = matchup_analyzer or MatchupAnalyzer(synergy_analyzer)
        self.synergy_analyzer = synergy_analyzer
        self.clutch_analyzer = clutch_analyzer
        self.stamina_analyzer = stamina_analyzer

        self._rng: np.random.Generator | None = None

    def simulate(
        self,
        config: SimulationConfig,
        home_team: Team,
        away_team: Team,
        players: dict[int, Player] | None = None,
    ) -> SimulationResult:
        """
        Run a complete simulation.

        Args:
            config: Simulation configuration
            home_team: Home team
            away_team: Away team
            players: Optional player data dictionary

        Returns:
            SimulationResult with complete analysis
        """
        # Initialize RNG
        self._rng = np.random.default_rng(config.random_seed)

        logger.info(
            f"Starting simulation: {home_team.name} vs {away_team.name} "
            f"({config.iterations} iterations)"
        )

        # Pre-calculate matchup analysis
        matchup_analysis = self.matchup_analyzer.analyze_full_matchup(
            home_team, away_team, players
        )

        # Pre-calculate expected goals
        home_xg, away_xg = self.xg_calculator.calculate_matchup_xg(
            home_team, away_team, players
        )

        # Run simulation based on mode
        if config.mode == SimulationMode.SERIES:
            return self._simulate_series(
                config, home_team, away_team, home_xg, away_xg,
                matchup_analysis, players
            )

        return self._simulate_games(
            config, home_team, away_team, home_xg, away_xg,
            matchup_analysis, players
        )

    def _simulate_games(
        self,
        config: SimulationConfig,
        home_team: Team,
        away_team: Team,
        home_xg: TeamExpectedGoals,
        away_xg: TeamExpectedGoals,
        matchup_analysis: MatchupAnalysis,
        players: dict[int, Player] | None,
    ) -> SimulationResult:
        """Simulate multiple games and aggregate results."""
        result = SimulationResult(
            config=config,
            total_iterations=config.iterations,
            home_wins=0,
            away_wins=0,
            overtime_games=0,
            shootout_games=0,
            matchup_analysis=matchup_analysis,
        )

        sample_games = []

        for i in range(config.iterations):
            game = self._simulate_single_game(
                i + 1, config, home_team, away_team, home_xg, away_xg, players
            )

            # Record outcome
            if game.winner == home_team.team_id:
                result.home_wins += 1
            else:
                result.away_wins += 1

            if game.went_to_overtime:
                result.overtime_games += 1
            if game.went_to_shootout:
                result.shootout_games += 1

            # Add to score distribution
            result.score_distribution.add_result(game.home_score, game.away_score)

            # Track xG
            result.average_home_xg += game.home_xg_total
            result.average_away_xg += game.away_xg_total

            # Save sample games
            if i < 10:
                sample_games.append(game)

        # Calculate averages
        result.average_home_xg /= config.iterations
        result.average_away_xg /= config.iterations

        # Calculate win probabilities
        result.home_win_probability = result.home_wins / config.iterations
        result.away_win_probability = result.away_wins / config.iterations

        # Calculate confidence score
        result.confidence_score = self._calculate_confidence_score(
            home_team, away_team, players
        )

        # Determine variance indicator
        result.variance_indicator = self._classify_variance(result)

        # Calculate segment win rates
        result.segment_win_rates = self._calculate_segment_win_rates(sample_games)

        result.sample_games = sample_games

        logger.info(
            f"Simulation complete: Home {result.home_win_probability:.1%} - "
            f"Away {result.away_win_probability:.1%}"
        )

        return result

    def _simulate_single_game(
        self,
        game_number: int,
        config: SimulationConfig,
        home_team: Team,
        away_team: Team,
        home_xg: TeamExpectedGoals,
        away_xg: TeamExpectedGoals,
        players: dict[int, Player] | None,
    ) -> SimulatedGame:
        """Simulate a single game."""
        game = SimulatedGame(
            game_number=game_number,
            home_score=0,
            away_score=0,
            winner=0,
        )

        # Simulate each segment
        segments = [
            (GameSegment.EARLY_GAME, "early_game", home_xg.early_game_xg_for, away_xg.early_game_xg_for),
            (GameSegment.MID_GAME, "mid_game", home_xg.mid_game_xg_for, away_xg.mid_game_xg_for),
            (GameSegment.LATE_GAME, "late_game", home_xg.late_game_xg_for, away_xg.late_game_xg_for),
        ]

        for segment_enum, segment_name, h_xg, a_xg in segments:
            context = self._build_segment_context(
                segment_enum, h_xg, a_xg, config, home_team, away_team, players
            )
            segment_result = self._simulate_segment(context, config)
            game.segments.append(segment_result)

            game.home_score += segment_result.home_goals
            game.away_score += segment_result.away_goals
            game.home_xg_total += segment_result.home_xg
            game.away_xg_total += segment_result.away_xg

        # Handle ties with overtime
        if game.home_score == game.away_score:
            self._simulate_overtime(game, config, home_xg, away_xg)

        # Determine winner
        if game.home_score > game.away_score:
            game.winner = home_team.team_id
        else:
            game.winner = away_team.team_id

        return game

    def _build_segment_context(
        self,
        segment: GameSegment,
        home_xg: float,
        away_xg: float,
        config: SimulationConfig,
        home_team: Team,
        away_team: Team,
        players: dict[int, Player] | None,
    ) -> SegmentContext:
        """Build context for segment simulation."""
        segment_weight = config.segment_weights.get(segment.value, 1.0)

        # Get clutch adjustments if enabled
        clutch_home = 1.0
        clutch_away = 1.0
        if config.use_clutch_adjustments and self.clutch_analyzer:
            if segment == GameSegment.LATE_GAME:
                # Apply clutch bonuses in late game
                clutch_home = self._get_team_clutch_factor(home_team, players)
                clutch_away = self._get_team_clutch_factor(away_team, players)

        # Get fatigue adjustments if enabled
        # Uses StaminaAnalyzer (per-player) or falls back to player.fatigue_factor
        # (set by schedule context from DB enrichment)
        fatigue_home = 1.0
        fatigue_away = 1.0
        if config.use_fatigue_adjustments:
            if segment in (GameSegment.LATE_GAME, GameSegment.OVERTIME):
                fatigue_home = self._get_team_fatigue_factor(home_team, players)
                fatigue_away = self._get_team_fatigue_factor(away_team, players)

        return SegmentContext(
            segment=segment,
            home_xg_base=home_xg,
            away_xg_base=away_xg,
            segment_weight=segment_weight,
            clutch_home=clutch_home,
            clutch_away=clutch_away,
            fatigue_home=fatigue_home,
            fatigue_away=fatigue_away,
        )

    def _simulate_segment(
        self,
        context: SegmentContext,
        config: SimulationConfig,
    ) -> SegmentResult:
        """Simulate a single game segment."""
        result = SegmentResult(segment=context.segment)

        # Calculate adjusted xG for segment
        home_xg = (
            context.home_xg_base
            * context.segment_weight
            * context.clutch_home
            * context.fatigue_home
        )
        away_xg = (
            context.away_xg_base
            * context.segment_weight
            * context.clutch_away
            * context.fatigue_away
        )

        # Apply variance
        variance = config.variance_factor
        home_xg *= 1 + self._rng.normal(0, variance)
        away_xg *= 1 + self._rng.normal(0, variance)

        # Ensure non-negative
        home_xg = max(0, home_xg)
        away_xg = max(0, away_xg)

        result.home_xg = home_xg
        result.away_xg = away_xg

        # Generate goals from Poisson distribution
        result.home_goals = self._rng.poisson(home_xg)
        result.away_goals = self._rng.poisson(away_xg)

        # Estimate shots (roughly 10x xG)
        result.home_shots = max(result.home_goals, int(home_xg * 10))
        result.away_shots = max(result.away_goals, int(away_xg * 10))

        # Determine dominant team
        if result.home_goals > result.away_goals:
            result.dominant_team = 1  # Home
        elif result.away_goals > result.home_goals:
            result.dominant_team = 2  # Away

        return result

    def _simulate_overtime(
        self,
        game: SimulatedGame,
        config: SimulationConfig,
        home_xg: TeamExpectedGoals,
        away_xg: TeamExpectedGoals,
    ) -> None:
        """Simulate overtime and potentially shootout."""
        game.went_to_overtime = True

        # OT is 3-on-3 with higher scoring
        ot_multiplier = 1.5
        home_ot_xg = (home_xg.total_xg_for / 60) * 5 * ot_multiplier  # 5 min OT
        away_ot_xg = (away_xg.total_xg_for / 60) * 5 * ot_multiplier

        # Apply variance
        home_ot_xg *= 1 + self._rng.normal(0, config.variance_factor)
        away_ot_xg *= 1 + self._rng.normal(0, config.variance_factor)

        # 50% chance someone scores in OT
        ot_goal_prob = 0.5
        if self._rng.random() < ot_goal_prob:
            # Determine who scores based on relative xG
            total_xg = home_ot_xg + away_ot_xg
            home_prob = home_ot_xg / total_xg if total_xg > 0 else 0.5

            if self._rng.random() < home_prob:
                game.home_score += 1
            else:
                game.away_score += 1

            # Add OT segment
            ot_result = SegmentResult(
                segment=GameSegment.OVERTIME,
                home_goals=1 if game.home_score > game.away_score else 0,
                away_goals=0 if game.home_score > game.away_score else 1,
                home_xg=home_ot_xg,
                away_xg=away_ot_xg,
            )
            game.segments.append(ot_result)
        else:
            # Go to shootout
            self._simulate_shootout(game)

    def _simulate_shootout(self, game: SimulatedGame) -> None:
        """Simulate a shootout."""
        game.went_to_shootout = True

        home_goals = 0
        away_goals = 0

        # Simulate 3 rounds
        for _ in range(self.SHOOTOUT_ROUNDS):
            # Home shoots
            if self._rng.random() < 0.33:  # ~33% success rate
                home_goals += 1
            # Away shoots
            if self._rng.random() < 0.33:
                away_goals += 1

        # If still tied, continue until someone wins
        while home_goals == away_goals:
            home_scores = self._rng.random() < 0.33
            away_scores = self._rng.random() < 0.33

            if home_scores and not away_scores:
                home_goals += 1
            elif away_scores and not home_scores:
                away_goals += 1

        # Add 1 goal to winner's total
        if home_goals > away_goals:
            game.home_score += 1
        else:
            game.away_score += 1

    def _simulate_series(
        self,
        config: SimulationConfig,
        home_team: Team,
        away_team: Team,
        home_xg: TeamExpectedGoals,
        away_xg: TeamExpectedGoals,
        matchup_analysis: MatchupAnalysis,
        players: dict[int, Player] | None,
    ) -> SimulationResult:
        """Simulate a playoff series."""
        # For series simulation, we simulate the entire series multiple times
        series_outcomes: dict[tuple[int, int], int] = {}
        total_home_wins = 0
        total_away_wins = 0
        total_ot = 0
        total_so = 0
        score_dist = ScoreDistribution()

        games_to_win = config.series_games_to_win
        start_home, start_away = config.current_series_score

        for _ in range(config.iterations):
            home_series_wins = start_home
            away_series_wins = start_away

            while home_series_wins < games_to_win and away_series_wins < games_to_win:
                # Alternate home ice (simplified: 2-2-1-1-1 format)
                games_played = home_series_wins + away_series_wins - start_home - start_away
                is_home_game = games_played in [0, 1, 4, 6]

                # Adjust xG for home ice
                if is_home_game:
                    h_xg, a_xg = home_xg, away_xg
                else:
                    # Swap home/away for away games
                    h_xg, a_xg = away_xg, home_xg

                game = self._simulate_single_game(
                    games_played + 1, config, home_team, away_team,
                    h_xg, a_xg, players
                )

                if is_home_game:
                    if game.winner == home_team.team_id:
                        home_series_wins += 1
                    else:
                        away_series_wins += 1
                else:
                    if game.winner == away_team.team_id:
                        away_series_wins += 1
                    else:
                        home_series_wins += 1

                score_dist.add_result(game.home_score, game.away_score)
                if game.went_to_overtime:
                    total_ot += 1
                if game.went_to_shootout:
                    total_so += 1

            # Record series outcome
            outcome = (home_series_wins, away_series_wins)
            series_outcomes[outcome] = series_outcomes.get(outcome, 0) + 1

            if home_series_wins == games_to_win:
                total_home_wins += 1
            else:
                total_away_wins += 1

        # Build result
        result = SimulationResult(
            config=config,
            total_iterations=config.iterations,
            home_wins=total_home_wins,
            away_wins=total_away_wins,
            overtime_games=total_ot,
            shootout_games=total_so,
            score_distribution=score_dist,
            matchup_analysis=matchup_analysis,
        )

        result.home_win_probability = total_home_wins / config.iterations
        result.away_win_probability = total_away_wins / config.iterations
        result.confidence_score = self._calculate_confidence_score(
            home_team, away_team, players
        )
        result.variance_indicator = self._classify_variance(result)

        return result

    def _get_team_clutch_factor(
        self,
        team: Team,
        players: dict[int, Player] | None,
    ) -> float:
        """Calculate team's clutch performance factor."""
        if not self.clutch_analyzer or not players:
            return 1.0

        # Average clutch scores of key players
        total_clutch = 0.0
        count = 0

        # Get top 6 forwards and top 4 defensemen
        key_players = team.roster.forwards[:6] + team.roster.defensemen[:4]

        for player_id in key_players:
            metrics = self.clutch_analyzer.get_metrics(player_id)
            if metrics:
                total_clutch += metrics.clutch_score
                count += 1

        if count == 0:
            return 1.0

        avg_clutch = total_clutch / count

        # Convert to factor (1.0 = average, >1 = clutch, <1 = not clutch)
        # Clutch scores typically range 0.5-3.0
        return 1.0 + (avg_clutch - 1.0) * 0.1

    def _get_team_fatigue_factor(
        self,
        team: Team,
        players: dict[int, Player] | None,
    ) -> float:
        """
        Calculate team's fatigue impact factor.

        Uses StaminaAnalyzer (per-player metrics) when available.
        Falls back to player.fatigue_factor (set by schedule context
        from DB enrichment) when StaminaAnalyzer is not provided.
        """
        if not players:
            return 1.0

        key_players = team.roster.forwards[:9] + team.roster.defensemen[:6]

        # Strategy 1: Use StaminaAnalyzer for per-player fatigue metrics
        if self.stamina_analyzer:
            total_fatigue = 0.0
            count = 0
            for player_id in key_players:
                metrics = self.stamina_analyzer.get_metrics(player_id)
                if metrics:
                    total_fatigue += metrics.fatigue_indicator
                    count += 1
            if count > 0:
                return total_fatigue / count

        # Strategy 2: Use player.fatigue_factor from schedule context
        total_fatigue = 0.0
        count = 0
        for player_id in key_players:
            player = players.get(player_id)
            if player and player.fatigue_factor != 1.0:
                total_fatigue += player.fatigue_factor
                count += 1

        if count > 0:
            return total_fatigue / count

        return 1.0

    def _calculate_confidence_score(
        self,
        home_team: Team,
        away_team: Team,
        players: dict[int, Player] | None,
    ) -> float:
        """Calculate confidence score based on data quality."""
        score = 0.5  # Base confidence

        # More games = more confidence
        home_games = home_team.current_season_stats.games_played
        away_games = away_team.current_season_stats.games_played

        if home_games >= 20 and away_games >= 20:
            score += 0.2
        elif home_games >= 10 and away_games >= 10:
            score += 0.1

        # Line data availability
        if home_team.forward_lines and away_team.forward_lines:
            score += 0.1

        # Player data availability
        if players:
            home_players_with_data = sum(
                1 for pid in home_team.roster.all_players if pid in players
            )
            away_players_with_data = sum(
                1 for pid in away_team.roster.all_players if pid in players
            )

            if home_players_with_data >= 15 and away_players_with_data >= 15:
                score += 0.1

        # Synergy/clutch data
        if self.synergy_analyzer:
            score += 0.05
        if self.clutch_analyzer:
            score += 0.05

        return min(score, 1.0)

    def _classify_variance(self, result: SimulationResult) -> str:
        """Classify variance level of the matchup."""
        win_margin = abs(result.home_win_probability - result.away_win_probability)

        if win_margin < 0.08:
            return "high"
        elif win_margin < 0.20:
            return "normal"
        return "low"

    def _calculate_segment_win_rates(
        self,
        games: list[SimulatedGame],
    ) -> dict[str, float]:
        """Calculate segment-specific win rates from sample games."""
        segment_wins: dict[str, dict[str, int]] = {
            "early_game": {"home": 0, "away": 0, "tie": 0},
            "mid_game": {"home": 0, "away": 0, "tie": 0},
            "late_game": {"home": 0, "away": 0, "tie": 0},
        }

        for game in games:
            for segment in game.segments:
                if segment.segment == GameSegment.OVERTIME:
                    continue

                segment_name = segment.segment.value
                if segment_name not in segment_wins:
                    continue

                if segment.home_goals > segment.away_goals:
                    segment_wins[segment_name]["home"] += 1
                elif segment.away_goals > segment.home_goals:
                    segment_wins[segment_name]["away"] += 1
                else:
                    segment_wins[segment_name]["tie"] += 1

        # Convert to win rates
        win_rates = {}
        for segment, wins in segment_wins.items():
            total = wins["home"] + wins["away"] + wins["tie"]
            if total > 0:
                win_rates[f"{segment}_home_win_rate"] = wins["home"] / total
                win_rates[f"{segment}_away_win_rate"] = wins["away"] / total

        return win_rates
