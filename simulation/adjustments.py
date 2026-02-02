"""
Simulation Adjustments Module

Provides segment-specific weighting, clutch adjustments, and fatigue
modifiers that integrate with Phase 3 analytics and schedule context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from simulation.models import GameSegment

if TYPE_CHECKING:
    from src.analytics.clutch_analysis import (
        ClutchAnalyzer,
        ClutchLevel,
        FatigueLevel,
        StaminaAnalyzer,
        TeamResilienceAnalyzer,
    )
    from src.models.player import Player
    from src.models.team import Team
    from src.processors.schedule_context_pipeline import (
        ScheduleContext,
        FatigueModifier,
    )
    from src.processors.momentum_pipeline import MomentumAnalysis


@dataclass
class SegmentAdjustment:
    """Adjustments for a specific game segment."""

    segment: GameSegment
    base_weight: float = 1.0

    # Performance modifiers
    offensive_modifier: float = 1.0
    defensive_modifier: float = 1.0

    # Situational factors
    clutch_factor: float = 1.0
    fatigue_factor: float = 1.0
    momentum_factor: float = 1.0

    # Schedule-based factors (from schedule_context_pipeline)
    schedule_rest_factor: float = 1.0      # Days rest impact
    schedule_workload_factor: float = 1.0  # Games in window impact
    schedule_streak_factor: float = 1.0    # Win/loss streak impact

    @property
    def total_modifier(self) -> float:
        """Calculate total modifier for segment."""
        # Combine schedule factors
        schedule_modifier = (
            self.schedule_rest_factor
            * self.schedule_workload_factor
            * self.schedule_streak_factor
        )

        return (
            self.base_weight
            * self.offensive_modifier
            * self.clutch_factor
            * self.fatigue_factor
            * self.momentum_factor
            * schedule_modifier
        )

    @property
    def schedule_combined(self) -> float:
        """Get combined schedule-based modifier."""
        return (
            self.schedule_rest_factor
            * self.schedule_workload_factor
            * self.schedule_streak_factor
        )


@dataclass
class TeamAdjustments:
    """Complete adjustments for a team."""

    team_id: int

    # Segment adjustments
    early_game: SegmentAdjustment = field(
        default_factory=lambda: SegmentAdjustment(GameSegment.EARLY_GAME)
    )
    mid_game: SegmentAdjustment = field(
        default_factory=lambda: SegmentAdjustment(GameSegment.MID_GAME)
    )
    late_game: SegmentAdjustment = field(
        default_factory=lambda: SegmentAdjustment(GameSegment.LATE_GAME)
    )
    overtime: SegmentAdjustment = field(
        default_factory=lambda: SegmentAdjustment(GameSegment.OVERTIME)
    )

    # Team-level factors
    overall_clutch_rating: float = 1.0
    overall_fatigue_rating: float = 1.0
    resilience_factor: float = 1.0

    # Special situations
    trailing_late_modifier: float = 1.0
    leading_late_modifier: float = 1.0
    tied_late_modifier: float = 1.0

    def get_segment(self, segment: GameSegment) -> SegmentAdjustment:
        """Get adjustments for a specific segment."""
        mapping = {
            GameSegment.EARLY_GAME: self.early_game,
            GameSegment.MID_GAME: self.mid_game,
            GameSegment.LATE_GAME: self.late_game,
            GameSegment.OVERTIME: self.overtime,
        }
        return mapping.get(segment, self.mid_game)


class AdjustmentCalculator:
    """
    Calculator for simulation adjustments.

    Integrates clutch analysis, stamina tracking, and team resilience
    from Phase 3 to provide comprehensive game situation modifiers.
    """

    # Default segment weights
    DEFAULT_SEGMENT_WEIGHTS = {
        GameSegment.EARLY_GAME: 0.90,
        GameSegment.MID_GAME: 1.00,
        GameSegment.LATE_GAME: 1.10,
        GameSegment.OVERTIME: 1.25,
    }

    # Clutch level modifiers
    CLUTCH_MODIFIERS = {
        "elite": 1.15,
        "strong": 1.08,
        "average": 1.00,
        "below_average": 0.95,
        "poor": 0.90,
    }

    # Fatigue level modifiers
    FATIGUE_MODIFIERS = {
        "minimal": 1.00,
        "low": 0.97,
        "moderate": 0.93,
        "high": 0.88,
        "severe": 0.82,
    }

    def __init__(
        self,
        clutch_analyzer: ClutchAnalyzer | None = None,
        stamina_analyzer: StaminaAnalyzer | None = None,
        resilience_analyzer: TeamResilienceAnalyzer | None = None,
        segment_weights: dict[GameSegment, float] | None = None,
    ) -> None:
        """
        Initialize the adjustment calculator.

        Args:
            clutch_analyzer: Phase 3 clutch analyzer
            stamina_analyzer: Phase 3 stamina analyzer
            resilience_analyzer: Phase 3 team resilience analyzer
            segment_weights: Optional custom segment weights
        """
        self.clutch_analyzer = clutch_analyzer
        self.stamina_analyzer = stamina_analyzer
        self.resilience_analyzer = resilience_analyzer
        self.segment_weights = segment_weights or self.DEFAULT_SEGMENT_WEIGHTS

    def calculate_team_adjustments(
        self,
        team: Team,
        players: dict[int, Player] | None = None,
    ) -> TeamAdjustments:
        """
        Calculate all adjustments for a team.

        Args:
            team: Team to calculate adjustments for
            players: Optional player data dictionary

        Returns:
            TeamAdjustments with all modifiers
        """
        adjustments = TeamAdjustments(team_id=team.team_id)

        # Set base segment weights
        adjustments.early_game.base_weight = self.segment_weights[GameSegment.EARLY_GAME]
        adjustments.mid_game.base_weight = self.segment_weights[GameSegment.MID_GAME]
        adjustments.late_game.base_weight = self.segment_weights[GameSegment.LATE_GAME]
        adjustments.overtime.base_weight = self.segment_weights[GameSegment.OVERTIME]

        # Calculate clutch factors
        if self.clutch_analyzer and players:
            self._apply_clutch_adjustments(adjustments, team, players)

        # Calculate fatigue factors
        if self.stamina_analyzer and players:
            self._apply_fatigue_adjustments(adjustments, team, players)

        # Calculate resilience factors
        if self.resilience_analyzer:
            self._apply_resilience_adjustments(adjustments, team)

        # Calculate overall ratings
        adjustments.overall_clutch_rating = self._calculate_team_clutch_rating(
            team, players
        )
        adjustments.overall_fatigue_rating = self._calculate_team_fatigue_rating(
            team, players
        )

        return adjustments

    def get_situation_modifier(
        self,
        team_adjustments: TeamAdjustments,
        segment: GameSegment,
        score_differential: int,
        time_remaining_minutes: float = 20.0,
    ) -> float:
        """
        Get modifier for a specific game situation.

        Args:
            team_adjustments: Pre-calculated team adjustments
            segment: Current game segment
            score_differential: Team's score minus opponent (positive = leading)
            time_remaining_minutes: Minutes remaining in period

        Returns:
            Situational modifier
        """
        base = team_adjustments.get_segment(segment).total_modifier

        # Apply late-game situation modifiers
        if segment == GameSegment.LATE_GAME:
            if score_differential > 0:
                # Leading
                base *= team_adjustments.leading_late_modifier
            elif score_differential < 0:
                # Trailing
                base *= team_adjustments.trailing_late_modifier
                # Urgency bonus as time runs out
                if time_remaining_minutes < 5:
                    base *= 1.05
            else:
                # Tied
                base *= team_adjustments.tied_late_modifier

        # Apply resilience in close games
        if abs(score_differential) <= 1:
            base *= team_adjustments.resilience_factor

        return base

    def calculate_matchup_edge(
        self,
        home_adjustments: TeamAdjustments,
        away_adjustments: TeamAdjustments,
        segment: GameSegment,
    ) -> float:
        """
        Calculate edge for home team in a segment.

        Returns:
            Positive value = home advantage, negative = away advantage
        """
        home_mod = home_adjustments.get_segment(segment).total_modifier
        away_mod = away_adjustments.get_segment(segment).total_modifier

        # Home ice bonus
        home_mod *= 1.03

        return home_mod - away_mod

    def _apply_clutch_adjustments(
        self,
        adjustments: TeamAdjustments,
        team: Team,
        players: dict[int, Player],
    ) -> None:
        """Apply clutch performance adjustments."""
        # Get clutch metrics for key late-game players
        late_game_players = self._get_late_game_players(team)
        clutch_scores = []

        for player_id in late_game_players:
            metrics = self.clutch_analyzer.get_metrics(player_id)
            if metrics:
                clutch_scores.append(metrics.clutch_score)
                self.clutch_analyzer.calculate_clutch_score(player_id)

        if clutch_scores:
            avg_clutch = sum(clutch_scores) / len(clutch_scores)

            # Map to modifier
            if avg_clutch >= 3.0:
                modifier = self.CLUTCH_MODIFIERS["elite"]
            elif avg_clutch >= 2.0:
                modifier = self.CLUTCH_MODIFIERS["strong"]
            elif avg_clutch >= 1.0:
                modifier = self.CLUTCH_MODIFIERS["average"]
            elif avg_clutch >= 0.5:
                modifier = self.CLUTCH_MODIFIERS["below_average"]
            else:
                modifier = self.CLUTCH_MODIFIERS["poor"]

            # Apply primarily to late game and overtime
            adjustments.late_game.clutch_factor = modifier
            adjustments.overtime.clutch_factor = modifier * 1.05

            # Slight effect on mid game
            adjustments.mid_game.clutch_factor = 1 + (modifier - 1) * 0.3

    def _apply_fatigue_adjustments(
        self,
        adjustments: TeamAdjustments,
        team: Team,
        players: dict[int, Player],
    ) -> None:
        """Apply fatigue/stamina adjustments."""
        fatigue_indicators = []

        for player_id in team.roster.all_skaters:
            metrics = self.stamina_analyzer.get_metrics(player_id)
            if metrics:
                self.stamina_analyzer.calculate_fatigue_indicator(player_id)
                fatigue_indicators.append(metrics.fatigue_indicator)

        if fatigue_indicators:
            avg_fatigue = sum(fatigue_indicators) / len(fatigue_indicators)

            # Map fatigue indicator to modifier
            # fatigue_indicator < 1.0 means performance drops late
            if avg_fatigue >= 0.95:
                modifier = self.FATIGUE_MODIFIERS["minimal"]
            elif avg_fatigue >= 0.85:
                modifier = self.FATIGUE_MODIFIERS["low"]
            elif avg_fatigue >= 0.75:
                modifier = self.FATIGUE_MODIFIERS["moderate"]
            elif avg_fatigue >= 0.65:
                modifier = self.FATIGUE_MODIFIERS["high"]
            else:
                modifier = self.FATIGUE_MODIFIERS["severe"]

            # Early game: no fatigue impact
            adjustments.early_game.fatigue_factor = 1.0

            # Mid game: slight impact
            adjustments.mid_game.fatigue_factor = 1 + (modifier - 1) * 0.3

            # Late game: full impact
            adjustments.late_game.fatigue_factor = modifier

            # Overtime: amplified impact (tired players struggle)
            adjustments.overtime.fatigue_factor = modifier * 0.95

    def _apply_resilience_adjustments(
        self,
        adjustments: TeamAdjustments,
        team: Team,
    ) -> None:
        """Apply team resilience adjustments."""
        metrics = self.resilience_analyzer.get_metrics(team.team_id)

        if not metrics:
            return

        # Lead protection rate affects leading_late_modifier
        # Higher protection rate = better at holding leads
        adjustments.leading_late_modifier = 0.9 + metrics.lead_protection_rate * 0.2

        # Comeback rate affects trailing_late_modifier
        # Higher comeback rate = better at coming back
        adjustments.trailing_late_modifier = 0.95 + metrics.comeback_rate * 0.15

        # Overall resilience
        if metrics.is_resilient:
            adjustments.resilience_factor = 1.08
        elif metrics.is_collapse_prone:
            adjustments.resilience_factor = 0.92
        else:
            adjustments.resilience_factor = 1.0

        # Third period performance
        if metrics.third_period_goal_differential > 0:
            adjustments.late_game.offensive_modifier *= 1.03
        elif metrics.third_period_goal_differential < -5:
            adjustments.late_game.defensive_modifier *= 0.97

    def _calculate_team_clutch_rating(
        self,
        team: Team,
        players: dict[int, Player] | None,
    ) -> float:
        """Calculate overall team clutch rating."""
        if not self.clutch_analyzer or not players:
            return 1.0

        clutch_sum = 0.0
        weight_sum = 0.0

        # Weight by line number (top players matter more)
        for i, line in enumerate(team.forward_lines):
            weight = 1.0 - (i * 0.15)  # 1.0, 0.85, 0.70, 0.55
            for player_id in line.player_ids:
                metrics = self.clutch_analyzer.get_metrics(player_id)
                if metrics:
                    clutch_sum += metrics.clutch_score * weight
                    weight_sum += weight

        for i, pair in enumerate(team.defense_pairs):
            weight = 0.9 - (i * 0.15)
            for player_id in pair.player_ids:
                metrics = self.clutch_analyzer.get_metrics(player_id)
                if metrics:
                    clutch_sum += metrics.clutch_score * weight
                    weight_sum += weight

        if weight_sum == 0:
            return 1.0

        avg_clutch = clutch_sum / weight_sum

        # Normalize to ~1.0 scale
        return 0.9 + avg_clutch * 0.05

    def _calculate_team_fatigue_rating(
        self,
        team: Team,
        players: dict[int, Player] | None,
    ) -> float:
        """Calculate overall team fatigue rating."""
        if not self.stamina_analyzer or not players:
            return 1.0

        fatigue_sum = 0.0
        count = 0

        for player_id in team.roster.all_skaters:
            metrics = self.stamina_analyzer.get_metrics(player_id)
            if metrics:
                fatigue_sum += metrics.fatigue_indicator
                count += 1

        if count == 0:
            return 1.0

        return fatigue_sum / count

    def _get_late_game_players(self, team: Team) -> list[int]:
        """Get players likely to be used in late game situations."""
        late_game_players = []

        # Top 2 forward lines
        for line in team.forward_lines[:2]:
            late_game_players.extend(line.player_ids)

        # Top 2 defense pairs
        for pair in team.defense_pairs[:2]:
            late_game_players.extend(pair.player_ids)

        return late_game_players

    def apply_schedule_context(
        self,
        adjustments: TeamAdjustments,
        schedule_context: ScheduleContext | None,
    ) -> None:
        """
        Apply schedule-based fatigue adjustments.

        Uses data from schedule_context_pipeline to adjust performance
        based on rest days, workload, and streaks.

        Args:
            adjustments: TeamAdjustments to modify
            schedule_context: Schedule context for this game
        """
        if not schedule_context:
            return

        # Import the fatigue config from the pipeline
        from src.processors.schedule_context_pipeline import (
            FATIGUE_CONFIG,
            ScheduleContextPipeline,
        )

        pipeline = ScheduleContextPipeline()
        fatigue_mod = pipeline.calculate_fatigue_modifier(schedule_context)

        # Apply rest factor to all segments (affects whole game)
        for segment_adj in [
            adjustments.early_game,
            adjustments.mid_game,
            adjustments.late_game,
            adjustments.overtime,
        ]:
            segment_adj.schedule_rest_factor = fatigue_mod.rest_factor
            segment_adj.schedule_workload_factor = fatigue_mod.workload_factor
            segment_adj.schedule_streak_factor = fatigue_mod.streak_factor

        # Late game and overtime are more affected by fatigue
        if fatigue_mod.fatigue_level in ("tired", "exhausted"):
            # Additional penalty for tired teams late in game
            penalty = 0.97 if fatigue_mod.fatigue_level == "tired" else 0.94
            adjustments.late_game.fatigue_factor *= penalty
            adjustments.overtime.fatigue_factor *= penalty * 0.98

    def apply_player_momentum(
        self,
        adjustments: TeamAdjustments,
        player_momentum: dict[int, MomentumAnalysis] | None,
        team: Team,
    ) -> None:
        """
        Apply player momentum (hot/cold streaks) to team adjustments.

        Args:
            adjustments: TeamAdjustments to modify
            player_momentum: Dict mapping player_id to MomentumAnalysis
            team: Team being adjusted
        """
        if not player_momentum:
            return

        from src.processors.momentum_pipeline import MomentumState, MomentumPipeline

        pipeline = MomentumPipeline()

        # Calculate weighted team momentum
        momentum_sum = 0.0
        weight_sum = 0.0

        # Get all skater IDs
        all_skaters = []
        if hasattr(team, 'roster') and hasattr(team.roster, 'all_skaters'):
            all_skaters = team.roster.all_skaters
        elif hasattr(team, 'forward_lines'):
            for line in team.forward_lines:
                all_skaters.extend(line.player_ids)
            for pair in team.defense_pairs:
                all_skaters.extend(pair.player_ids)

        for player_id in all_skaters:
            if player_id in player_momentum:
                analysis = player_momentum[player_id]
                modifier = pipeline.get_momentum_modifier(analysis)

                # Weight by player importance (simplified)
                weight = 1.0
                momentum_sum += (modifier - 1.0) * weight
                weight_sum += weight

        if weight_sum > 0:
            avg_momentum_effect = momentum_sum / weight_sum
            team_momentum_modifier = 1.0 + avg_momentum_effect

            # Apply to all segments
            for segment_adj in [
                adjustments.early_game,
                adjustments.mid_game,
                adjustments.late_game,
                adjustments.overtime,
            ]:
                segment_adj.momentum_factor *= team_momentum_modifier

    def calculate_full_adjustments(
        self,
        team: Team,
        players: dict[int, Player] | None = None,
        schedule_context: ScheduleContext | None = None,
        player_momentum: dict[int, MomentumAnalysis] | None = None,
    ) -> TeamAdjustments:
        """
        Calculate complete adjustments including all factors.

        This is the main entry point for getting team adjustments
        that incorporate:
        - Base segment weights
        - Clutch performance
        - Stamina/fatigue (in-game)
        - Schedule context (rest, workload, streaks)
        - Player momentum (hot/cold streaks)
        - Team resilience

        Args:
            team: Team to calculate adjustments for
            players: Optional player data dictionary
            schedule_context: Schedule context for this game
            player_momentum: Dict mapping player_id to MomentumAnalysis

        Returns:
            TeamAdjustments with all modifiers applied
        """
        # Start with base calculations
        adjustments = self.calculate_team_adjustments(team, players)

        # Apply schedule context
        self.apply_schedule_context(adjustments, schedule_context)

        # Apply player momentum
        self.apply_player_momentum(adjustments, player_momentum, team)

        return adjustments


@dataclass
class MomentumTracker:
    """
    Tracks momentum during a simulated game.

    Used to provide dynamic adjustments based on game flow.
    """

    home_momentum: float = 0.5
    away_momentum: float = 0.5

    # Recent events
    recent_home_goals: int = 0
    recent_away_goals: int = 0
    goals_in_last_5_minutes: int = 0

    # Momentum decay
    decay_rate: float = 0.1

    def record_goal(self, is_home: bool) -> None:
        """Record a goal and update momentum."""
        if is_home:
            self.recent_home_goals += 1
            self.home_momentum = min(1.0, self.home_momentum + 0.15)
            self.away_momentum = max(0.0, self.away_momentum - 0.1)
        else:
            self.recent_away_goals += 1
            self.away_momentum = min(1.0, self.away_momentum + 0.15)
            self.home_momentum = max(0.0, self.home_momentum - 0.1)

        self.goals_in_last_5_minutes += 1

    def record_power_play(self, is_home: bool, scored: bool) -> None:
        """Record power play result."""
        if scored:
            self.record_goal(is_home)
        else:
            # Failed PP gives momentum to other team
            if is_home:
                self.away_momentum = min(1.0, self.away_momentum + 0.05)
            else:
                self.home_momentum = min(1.0, self.home_momentum + 0.05)

    def decay(self) -> None:
        """Apply momentum decay toward neutral."""
        self.home_momentum = 0.5 + (self.home_momentum - 0.5) * (1 - self.decay_rate)
        self.away_momentum = 0.5 + (self.away_momentum - 0.5) * (1 - self.decay_rate)
        self.goals_in_last_5_minutes = max(0, self.goals_in_last_5_minutes - 1)

    def get_modifier(self, is_home: bool) -> float:
        """Get momentum modifier for a team."""
        momentum = self.home_momentum if is_home else self.away_momentum

        # Convert momentum (0-1) to modifier (0.9-1.1)
        return 0.9 + momentum * 0.2

    def reset_period(self) -> None:
        """Reset momentum between periods."""
        self.decay()
        self.decay()  # Double decay between periods
        self.recent_home_goals = 0
        self.recent_away_goals = 0
