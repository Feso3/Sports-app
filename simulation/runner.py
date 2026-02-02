"""
Simulation Runner Module

Main entry point for running hockey game simulations with full context.
Orchestrates all pipelines and produces prediction results.

Reference: docs/simulation-logic-design.md
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from src.database.db import Database, get_database
from simulation.profiles import (
    SimulationProfileBuilder,
    PlayerSimulationProfile,
    GoalieSimulationProfile,
    TeamSimulationContext,
)
from simulation.adjustments import (
    AdjustmentCalculator,
    TeamAdjustments,
    SegmentAdjustment,
    MomentumTracker,
)
from simulation.models import GameSegment, SimulationConfig


@dataclass
class ShotAttempt:
    """A single shot attempt during simulation."""

    shooter_id: int
    zone: str
    shot_type: str
    base_goal_prob: float
    adjusted_goal_prob: float
    is_goal: bool
    segment: GameSegment
    game_time_seconds: int


@dataclass
class SimulatedPeriod:
    """Results from simulating one period."""

    period: int
    home_goals: int = 0
    away_goals: int = 0
    home_shots: int = 0
    away_shots: int = 0
    home_shot_attempts: list[ShotAttempt] = field(default_factory=list)
    away_shot_attempts: list[ShotAttempt] = field(default_factory=list)


@dataclass
class SimulatedGame:
    """Result of a single game simulation."""

    home_score: int = 0
    away_score: int = 0
    home_shots: int = 0
    away_shots: int = 0
    winner: str = ""  # 'home', 'away', 'tie'
    went_to_overtime: bool = False
    periods: list[SimulatedPeriod] = field(default_factory=list)

    # Segment breakdowns
    segment_goals: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class SimulationResult:
    """Aggregated results across all simulation iterations."""

    home_team: str
    away_team: str
    iterations: int
    game_date: str

    # Win probabilities
    home_win_pct: float = 0.0
    away_win_pct: float = 0.0
    tie_pct: float = 0.0  # For regular season (ends in SO)

    # Score distribution
    avg_home_score: float = 0.0
    avg_away_score: float = 0.0
    home_score_distribution: dict[int, int] = field(default_factory=dict)
    away_score_distribution: dict[int, int] = field(default_factory=dict)

    # Most likely outcomes
    most_likely_home_score: int = 0
    most_likely_away_score: int = 0

    # Shot statistics
    avg_home_shots: float = 0.0
    avg_away_shots: float = 0.0

    # Overtime frequency
    overtime_pct: float = 0.0

    # Confidence metrics
    confidence_level: str = "medium"  # low, medium, high
    sample_quality: str = "standard"

    # Key factors
    key_factors: list[str] = field(default_factory=list)


class GameSimulationRunner:
    """
    Main simulation runner that orchestrates all components.

    Usage:
        runner = GameSimulationRunner()
        result = runner.simulate_game(
            home_team="TOR",
            away_team="MTL",
            game_date="2024-12-15",
            season=20242025,
            iterations=10000,
        )
    """

    # Zone-based expected goal probabilities
    ZONE_GOAL_PROBS = {
        "crease": 0.35,
        "inner_slot": 0.25,
        "slot": 0.15,
        "left_circle": 0.08,
        "right_circle": 0.08,
        "high_slot": 0.05,
        "left_wing": 0.03,
        "right_wing": 0.03,
        "left_point": 0.02,
        "right_point": 0.02,
        "behind_net": 0.01,
        "unknown": 0.05,
    }

    # Shot type modifiers
    SHOT_TYPE_MODIFIERS = {
        "wrist": 1.0,
        "slap": 0.95,
        "snap": 1.05,
        "backhand": 0.85,
        "tip-in": 1.20,
        "deflected": 1.15,
        "wrap-around": 0.70,
        "unknown": 1.0,
    }

    # Average shots per team per game
    BASE_SHOTS_PER_GAME = 30

    def __init__(self, db: Optional[Database] = None):
        """Initialize the simulation runner."""
        self.db = db or get_database()
        self.profile_builder = SimulationProfileBuilder(db=self.db)
        self.adjustment_calculator = AdjustmentCalculator()

    def simulate_game(
        self,
        home_team: str,
        away_team: str,
        game_date: str,
        season: int,
        iterations: int = 10000,
        game_id: Optional[int] = None,
        home_goalie_id: Optional[int] = None,
        away_goalie_id: Optional[int] = None,
    ) -> SimulationResult:
        """
        Run full game simulation with all context.

        Args:
            home_team: Home team abbreviation
            away_team: Away team abbreviation
            game_date: Game date
            season: Season identifier
            iterations: Number of simulation iterations
            game_id: Optional game ID for schedule context
            home_goalie_id: Optional starting goalie
            away_goalie_id: Optional starting goalie

        Returns:
            SimulationResult with predictions
        """
        logger.info(
            f"Simulating {away_team} @ {home_team} on {game_date} "
            f"({iterations} iterations)"
        )

        # Build team contexts
        home_context = self.profile_builder.build_team_context(
            team_abbrev=home_team,
            opponent_abbrev=away_team,
            game_date=game_date,
            season=season,
            game_id=game_id,
            starting_goalie_id=home_goalie_id,
        )

        away_context = self.profile_builder.build_team_context(
            team_abbrev=away_team,
            opponent_abbrev=home_team,
            game_date=game_date,
            season=season,
            game_id=game_id,
            starting_goalie_id=away_goalie_id,
        )

        # Run iterations
        results = []
        for i in range(iterations):
            game = self._simulate_single_game(home_context, away_context)
            results.append(game)

            if (i + 1) % 1000 == 0:
                logger.debug(f"Completed {i + 1}/{iterations} iterations")

        # Aggregate results
        return self._aggregate_results(
            results=results,
            home_team=home_team,
            away_team=away_team,
            game_date=game_date,
            home_context=home_context,
            away_context=away_context,
        )

    def _simulate_single_game(
        self,
        home_context: TeamSimulationContext,
        away_context: TeamSimulationContext,
    ) -> SimulatedGame:
        """Simulate a single game iteration."""
        game = SimulatedGame()
        momentum = MomentumTracker()

        # Calculate team offensive strength
        home_strength = self._calculate_team_strength(home_context)
        away_strength = self._calculate_team_strength(away_context)

        # Simulate three periods
        for period in range(1, 4):
            segment = self._get_segment_for_period(period)

            period_result = self._simulate_period(
                home_context=home_context,
                away_context=away_context,
                period=period,
                segment=segment,
                home_strength=home_strength,
                away_strength=away_strength,
                momentum=momentum,
            )

            game.home_score += period_result.home_goals
            game.away_score += period_result.away_goals
            game.home_shots += period_result.home_shots
            game.away_shots += period_result.away_shots
            game.periods.append(period_result)

            momentum.reset_period()

        # Overtime if tied
        if game.home_score == game.away_score:
            game.went_to_overtime = True
            ot_result = self._simulate_overtime(
                home_context, away_context, home_strength, away_strength, momentum
            )
            game.home_score += ot_result.home_goals
            game.away_score += ot_result.away_goals
            game.home_shots += ot_result.home_shots
            game.away_shots += ot_result.away_shots
            game.periods.append(ot_result)

        # Determine winner
        if game.home_score > game.away_score:
            game.winner = "home"
        elif game.away_score > game.home_score:
            game.winner = "away"
        else:
            # Shootout (simplified - coin flip weighted by goalie stats)
            game.winner = "home" if random.random() < 0.52 else "away"

        return game

    def _simulate_period(
        self,
        home_context: TeamSimulationContext,
        away_context: TeamSimulationContext,
        period: int,
        segment: GameSegment,
        home_strength: float,
        away_strength: float,
        momentum: MomentumTracker,
    ) -> SimulatedPeriod:
        """Simulate a single period."""
        result = SimulatedPeriod(period=period)

        # Calculate expected shots for this period
        # Apply fatigue modifier (late periods = slightly fewer shots)
        period_modifier = 1.0 if period == 1 else (0.97 if period == 2 else 0.95)

        home_expected_shots = (
            self.BASE_SHOTS_PER_GAME / 3 * home_strength * period_modifier
        )
        away_expected_shots = (
            self.BASE_SHOTS_PER_GAME / 3 * away_strength * period_modifier
        )

        # Apply schedule fatigue
        if home_context.fatigue_modifier:
            home_expected_shots *= home_context.fatigue_modifier.offensive_modifier
        if away_context.fatigue_modifier:
            away_expected_shots *= away_context.fatigue_modifier.offensive_modifier

        # Generate shots (Poisson-like distribution)
        home_shots = self._generate_shot_count(home_expected_shots)
        away_shots = self._generate_shot_count(away_expected_shots)

        result.home_shots = home_shots
        result.away_shots = away_shots

        # Simulate each shot
        for _ in range(home_shots):
            shot = self._simulate_shot(
                shooting_context=home_context,
                goalie_context=away_context,
                segment=segment,
                momentum=momentum,
                is_home=True,
            )
            result.home_shot_attempts.append(shot)
            if shot.is_goal:
                result.home_goals += 1
                momentum.record_goal(is_home=True)

        for _ in range(away_shots):
            shot = self._simulate_shot(
                shooting_context=away_context,
                goalie_context=home_context,
                segment=segment,
                momentum=momentum,
                is_home=False,
            )
            result.away_shot_attempts.append(shot)
            if shot.is_goal:
                result.away_goals += 1
                momentum.record_goal(is_home=False)

        return result

    def _simulate_overtime(
        self,
        home_context: TeamSimulationContext,
        away_context: TeamSimulationContext,
        home_strength: float,
        away_strength: float,
        momentum: MomentumTracker,
    ) -> SimulatedPeriod:
        """Simulate overtime (3v3, 5 minutes, sudden death)."""
        result = SimulatedPeriod(period=4)

        # 3v3 = more scoring chances, but shorter time
        home_expected_shots = 4 * home_strength
        away_expected_shots = 4 * away_strength

        home_shots = self._generate_shot_count(home_expected_shots)
        away_shots = self._generate_shot_count(away_expected_shots)

        result.home_shots = home_shots
        result.away_shots = away_shots

        # Interleave shots and check for goals (sudden death)
        all_shots = (
            [("home", i) for i in range(home_shots)] +
            [("away", i) for i in range(away_shots)]
        )
        random.shuffle(all_shots)

        for team, _ in all_shots:
            if team == "home":
                shot = self._simulate_shot(
                    shooting_context=home_context,
                    goalie_context=away_context,
                    segment=GameSegment.OVERTIME,
                    momentum=momentum,
                    is_home=True,
                )
                result.home_shot_attempts.append(shot)
                if shot.is_goal:
                    result.home_goals += 1
                    break
            else:
                shot = self._simulate_shot(
                    shooting_context=away_context,
                    goalie_context=home_context,
                    segment=GameSegment.OVERTIME,
                    momentum=momentum,
                    is_home=False,
                )
                result.away_shot_attempts.append(shot)
                if shot.is_goal:
                    result.away_goals += 1
                    break

        return result

    def _simulate_shot(
        self,
        shooting_context: TeamSimulationContext,
        goalie_context: TeamSimulationContext,
        segment: GameSegment,
        momentum: MomentumTracker,
        is_home: bool,
    ) -> ShotAttempt:
        """Simulate a single shot attempt."""
        # Select shooter (weighted by blended scoring rate)
        shooter = self._select_shooter(shooting_context)

        # Select zone (from shooter's profile)
        zone = self._select_zone(shooter)

        # Select shot type
        shot_type = self._select_shot_type(shooter)

        # Calculate base goal probability
        base_prob = self.ZONE_GOAL_PROBS.get(zone, 0.05)

        # Apply shot type modifier
        shot_modifier = self.SHOT_TYPE_MODIFIERS.get(shot_type, 1.0)
        adjusted_prob = base_prob * shot_modifier

        # Apply shooter effectiveness
        if shooter.blended_shooting_pct > 0:
            # Compare to league average ~10%
            shooter_modifier = shooter.blended_shooting_pct / 10.0
            adjusted_prob *= shooter_modifier

        # Apply shooter momentum
        adjusted_prob *= shooter.momentum_modifier

        # Apply goalie adjustment
        if goalie_context.goalie_profile:
            goalie = goalie_context.goalie_profile
            # Better goalies reduce goal probability
            goalie_factor = 1.0 - goalie.blended_save_pct
            if goalie_factor > 0:
                # Normalize: league avg save% is ~0.910
                goalie_modifier = goalie_factor / 0.09
                adjusted_prob *= goalie_modifier

            # Zone-specific goalie weakness
            if zone in goalie.zone_save_pct:
                zone_save = goalie.zone_save_pct[zone]
                league_avg = 0.91
                if zone_save < league_avg:
                    # Weak zone = higher goal prob
                    adjusted_prob *= 1 + (league_avg - zone_save)

        # Apply momentum
        adjusted_prob *= momentum.get_modifier(is_home)

        # Cap probability
        adjusted_prob = min(0.5, max(0.01, adjusted_prob))

        # Determine if goal
        is_goal = random.random() < adjusted_prob

        return ShotAttempt(
            shooter_id=shooter.player_id,
            zone=zone,
            shot_type=shot_type,
            base_goal_prob=base_prob,
            adjusted_goal_prob=adjusted_prob,
            is_goal=is_goal,
            segment=segment,
            game_time_seconds=0,
        )

    def _calculate_team_strength(
        self,
        context: TeamSimulationContext,
    ) -> float:
        """Calculate overall team offensive strength."""
        if not context.skater_profiles:
            return 1.0

        total_scoring = sum(
            p.blended_goals_per_game + p.blended_assists_per_game * 0.5
            for p in context.skater_profiles.values()
        )

        # Normalize to ~1.0 for average team
        # Typical team scores about 3 goals per game
        strength = total_scoring / 3.0

        # Apply fatigue modifier
        if context.fatigue_modifier:
            strength *= context.fatigue_modifier.offensive_modifier

        return max(0.5, min(2.0, strength))

    def _select_shooter(
        self,
        context: TeamSimulationContext,
    ) -> PlayerSimulationProfile:
        """Select a shooter weighted by scoring rate."""
        profiles = list(context.skater_profiles.values())
        if not profiles:
            # Return dummy profile
            return PlayerSimulationProfile(player_id=0)

        # Weight by blended goals per game
        weights = [max(0.01, p.blended_goals_per_game) for p in profiles]
        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]

        return random.choices(profiles, weights=weights, k=1)[0]

    def _select_zone(self, shooter: PlayerSimulationProfile) -> str:
        """Select shooting zone from player's profile."""
        if shooter.shot_profile.zone_distribution:
            zones = list(shooter.shot_profile.zone_distribution.keys())
            weights = list(shooter.shot_profile.zone_distribution.values())
            return random.choices(zones, weights=weights, k=1)[0]

        # Default distribution
        default_zones = ["slot", "high_slot", "left_circle", "right_circle", "left_point"]
        default_weights = [0.3, 0.2, 0.2, 0.2, 0.1]
        return random.choices(default_zones, weights=default_weights, k=1)[0]

    def _select_shot_type(self, shooter: PlayerSimulationProfile) -> str:
        """Select shot type from player's profile."""
        if shooter.shot_profile.shot_type_distribution:
            types = list(shooter.shot_profile.shot_type_distribution.keys())
            weights = list(shooter.shot_profile.shot_type_distribution.values())
            return random.choices(types, weights=weights, k=1)[0]

        # Default distribution
        default_types = ["wrist", "slap", "snap", "backhand"]
        default_weights = [0.5, 0.2, 0.2, 0.1]
        return random.choices(default_types, weights=default_weights, k=1)[0]

    def _generate_shot_count(self, expected: float) -> int:
        """Generate shot count using Poisson-like distribution."""
        # Simple approximation using normal distribution
        variance = expected * 0.5
        count = int(random.gauss(expected, variance ** 0.5))
        return max(0, count)

    def _get_segment_for_period(self, period: int) -> GameSegment:
        """Map period to game segment."""
        if period == 1:
            return GameSegment.EARLY_GAME
        elif period == 2:
            return GameSegment.MID_GAME
        else:
            return GameSegment.LATE_GAME

    def _aggregate_results(
        self,
        results: list[SimulatedGame],
        home_team: str,
        away_team: str,
        game_date: str,
        home_context: TeamSimulationContext,
        away_context: TeamSimulationContext,
    ) -> SimulationResult:
        """Aggregate results from all iterations."""
        n = len(results)

        result = SimulationResult(
            home_team=home_team,
            away_team=away_team,
            iterations=n,
            game_date=game_date,
        )

        # Count outcomes
        home_wins = sum(1 for g in results if g.winner == "home")
        away_wins = sum(1 for g in results if g.winner == "away")
        overtime_games = sum(1 for g in results if g.went_to_overtime)

        result.home_win_pct = home_wins / n
        result.away_win_pct = away_wins / n
        result.overtime_pct = overtime_games / n

        # Score statistics
        home_scores = [g.home_score for g in results]
        away_scores = [g.away_score for g in results]

        result.avg_home_score = sum(home_scores) / n
        result.avg_away_score = sum(away_scores) / n

        # Score distribution
        for score in home_scores:
            result.home_score_distribution[score] = (
                result.home_score_distribution.get(score, 0) + 1
            )
        for score in away_scores:
            result.away_score_distribution[score] = (
                result.away_score_distribution.get(score, 0) + 1
            )

        # Most likely scores
        result.most_likely_home_score = max(
            result.home_score_distribution,
            key=result.home_score_distribution.get,
        )
        result.most_likely_away_score = max(
            result.away_score_distribution,
            key=result.away_score_distribution.get,
        )

        # Shot statistics
        result.avg_home_shots = sum(g.home_shots for g in results) / n
        result.avg_away_shots = sum(g.away_shots for g in results) / n

        # Determine confidence level
        result.confidence_level = self._calculate_confidence(
            home_context, away_context, n
        )

        # Generate key factors
        result.key_factors = self._generate_key_factors(
            home_context, away_context, result
        )

        return result

    def _calculate_confidence(
        self,
        home_context: TeamSimulationContext,
        away_context: TeamSimulationContext,
        iterations: int,
    ) -> str:
        """Determine confidence level of prediction."""
        # Based on data quality and sample sizes
        home_data_quality = len(home_context.skater_profiles)
        away_data_quality = len(away_context.skater_profiles)

        if home_data_quality < 10 or away_data_quality < 10:
            return "low"
        elif iterations >= 10000 and home_data_quality >= 15:
            return "high"
        else:
            return "medium"

    def _generate_key_factors(
        self,
        home_context: TeamSimulationContext,
        away_context: TeamSimulationContext,
        result: SimulationResult,
    ) -> list[str]:
        """Generate list of key factors influencing the prediction."""
        factors = []

        # Home ice advantage
        factors.append(f"{result.home_team} has home ice advantage")

        # Schedule factors
        if home_context.schedule_context:
            if home_context.schedule_context.is_back_to_back:
                factors.append(f"{result.home_team} on back-to-back (fatigue)")
            if home_context.schedule_context.win_streak >= 3:
                factors.append(
                    f"{result.home_team} on {home_context.schedule_context.win_streak}-game win streak"
                )

        if away_context.schedule_context:
            if away_context.schedule_context.is_back_to_back:
                factors.append(f"{result.away_team} on back-to-back (fatigue)")
            if away_context.schedule_context.win_streak >= 3:
                factors.append(
                    f"{result.away_team} on {away_context.schedule_context.win_streak}-game win streak"
                )

        # Hot players
        hot_home = [
            p for p in home_context.skater_profiles.values()
            if p.momentum_state == "hot"
        ]
        hot_away = [
            p for p in away_context.skater_profiles.values()
            if p.momentum_state == "hot"
        ]

        if hot_home:
            factors.append(
                f"{result.home_team} has {len(hot_home)} player(s) on hot streak"
            )
        if hot_away:
            factors.append(
                f"{result.away_team} has {len(hot_away)} player(s) on hot streak"
            )

        return factors[:5]  # Limit to 5 factors


def simulate_game(
    home_team: str,
    away_team: str,
    game_date: str,
    season: int,
    iterations: int = 10000,
    db: Optional[Database] = None,
) -> SimulationResult:
    """
    Convenience function to simulate a game.

    Args:
        home_team: Home team abbreviation
        away_team: Away team abbreviation
        game_date: Game date
        season: Season identifier
        iterations: Number of simulation iterations
        db: Database instance

    Returns:
        SimulationResult with predictions
    """
    runner = GameSimulationRunner(db=db)
    return runner.simulate_game(
        home_team=home_team,
        away_team=away_team,
        game_date=game_date,
        season=season,
        iterations=iterations,
    )
