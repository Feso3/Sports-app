"""
Clutch and Stamina Analysis Module

Provides comprehensive analysis of clutch performance and fatigue patterns:
- Clutch scoring and performer identification
- Stamina decay modeling
- Late-game resilience vs collapse detection
- Performance under pressure metrics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from loguru import logger


class ClutchLevel(Enum):
    """Classification of clutch performance level."""

    ELITE = "elite"
    STRONG = "strong"
    AVERAGE = "average"
    BELOW_AVERAGE = "below_average"
    POOR = "poor"


class FatigueLevel(Enum):
    """Classification of fatigue impact."""

    MINIMAL = "minimal"  # < 5% decline
    LOW = "low"  # 5-15% decline
    MODERATE = "moderate"  # 15-25% decline
    HIGH = "high"  # 25-35% decline
    SEVERE = "severe"  # > 35% decline


@dataclass
class ClutchMetrics:
    """Comprehensive clutch performance metrics for a player."""

    player_id: int
    games_played: int = 0

    # Core clutch stats
    game_winning_goals: int = 0
    game_tying_goals: int = 0
    overtime_goals: int = 0
    shootout_goals: int = 0
    late_game_goals: int = 0
    late_game_assists: int = 0
    late_game_points: int = 0

    # Performance in close games (within 1 goal)
    close_game_goals: int = 0
    close_game_assists: int = 0
    close_game_points: int = 0
    close_game_plus_minus: int = 0

    # Pressure situations
    must_score_goals: int = 0  # Goals when trailing in final minutes
    lead_protecting_plus_minus: int = 0  # +/- when protecting lead

    # Derived metrics (populated by analyzer)
    clutch_score: float = 0.0
    clutch_level: ClutchLevel = ClutchLevel.AVERAGE

    def __post_init__(self) -> None:
        """Calculate late game points if not set."""
        if self.late_game_points == 0:
            self.late_game_points = self.late_game_goals + self.late_game_assists


@dataclass
class StaminaMetrics:
    """Stamina and fatigue metrics for a player."""

    player_id: int
    games_analyzed: int = 0

    # Performance by segment (per 60 minutes)
    early_game_points_per_60: float = 0.0
    mid_game_points_per_60: float = 0.0
    late_game_points_per_60: float = 0.0

    early_game_xg_per_60: float = 0.0
    mid_game_xg_per_60: float = 0.0
    late_game_xg_per_60: float = 0.0

    # Corsi by segment
    early_game_corsi_pct: float = 50.0
    mid_game_corsi_pct: float = 50.0
    late_game_corsi_pct: float = 50.0

    # Time on ice influence
    avg_toi_minutes: float = 0.0
    high_usage_performance_drop: float = 0.0  # Performance decline on high TOI nights

    # Derived metrics (populated by analyzer)
    fatigue_indicator: float = 1.0  # late / early performance ratio
    stamina_score: float = 0.0
    fatigue_level: FatigueLevel = FatigueLevel.MINIMAL

    # Back-to-back performance
    back_to_back_decline: float = 0.0  # Performance drop in B2B games


@dataclass
class TeamResilienceMetrics:
    """Team-level metrics for resilience vs collapse patterns."""

    team_id: int
    games_analyzed: int = 0

    # Lead protection
    leads_held: int = 0
    leads_blown: int = 0
    lead_protection_rate: float = 0.0

    # Comeback ability
    comebacks_completed: int = 0
    comeback_opportunities: int = 0
    comeback_rate: float = 0.0

    # Third period differential
    third_period_goal_differential: int = 0
    third_period_goals_for: int = 0
    third_period_goals_against: int = 0

    # Classification
    is_resilient: bool = False
    is_collapse_prone: bool = False


@dataclass
class ClutchPerformerRanking:
    """Ranked list of clutch performers."""

    player_id: int
    name: str
    clutch_score: float
    clutch_level: ClutchLevel
    key_stats: dict[str, Any] = field(default_factory=dict)


class ClutchAnalyzer:
    """
    Analyzer for clutch performance metrics.

    Calculates comprehensive clutch scores based on:
    - Game-winning/tying contributions
    - Overtime and shootout performance
    - Close game performance
    - Late game impact
    """

    # Weights for clutch score calculation
    DEFAULT_WEIGHTS = {
        "game_winning_goal": 5.0,
        "game_tying_goal": 4.0,
        "overtime_goal": 4.5,
        "shootout_goal": 2.0,
        "late_game_goal": 2.5,
        "late_game_assist": 1.5,
        "close_game_goal": 2.0,
        "close_game_assist": 1.0,
        "must_score_goal": 4.0,
        "lead_protecting_plus": 0.5,
    }

    # Thresholds for clutch level classification
    CLUTCH_THRESHOLDS = {
        ClutchLevel.ELITE: 3.0,
        ClutchLevel.STRONG: 2.0,
        ClutchLevel.AVERAGE: 1.0,
        ClutchLevel.BELOW_AVERAGE: 0.5,
    }

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        """Initialize the clutch analyzer with optional custom weights."""
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}
        self.player_metrics: dict[int, ClutchMetrics] = {}

    def record_game_winning_goal(self, player_id: int) -> None:
        """Record a game-winning goal for a player."""
        metrics = self._get_or_create_metrics(player_id)
        metrics.game_winning_goals += 1

    def record_game_tying_goal(self, player_id: int) -> None:
        """Record a game-tying goal for a player."""
        metrics = self._get_or_create_metrics(player_id)
        metrics.game_tying_goals += 1

    def record_overtime_goal(self, player_id: int) -> None:
        """Record an overtime goal for a player."""
        metrics = self._get_or_create_metrics(player_id)
        metrics.overtime_goals += 1

    def record_late_game_point(
        self, player_id: int, goals: int = 0, assists: int = 0
    ) -> None:
        """Record late game points for a player."""
        metrics = self._get_or_create_metrics(player_id)
        metrics.late_game_goals += goals
        metrics.late_game_assists += assists
        metrics.late_game_points = metrics.late_game_goals + metrics.late_game_assists

    def record_close_game_performance(
        self, player_id: int, goals: int = 0, assists: int = 0, plus_minus: int = 0
    ) -> None:
        """Record close game performance for a player."""
        metrics = self._get_or_create_metrics(player_id)
        metrics.close_game_goals += goals
        metrics.close_game_assists += assists
        metrics.close_game_points = metrics.close_game_goals + metrics.close_game_assists
        metrics.close_game_plus_minus += plus_minus

    def ingest_player_metrics(self, metrics: ClutchMetrics) -> None:
        """Ingest pre-calculated clutch metrics for a player."""
        self.player_metrics[metrics.player_id] = metrics

    def calculate_clutch_score(self, player_id: int) -> float:
        """
        Calculate comprehensive clutch score for a player.

        Returns:
            Normalized clutch score (per game played)
        """
        metrics = self.player_metrics.get(player_id)
        if not metrics:
            return 0.0

        raw_score = (
            metrics.game_winning_goals * self.weights["game_winning_goal"]
            + metrics.game_tying_goals * self.weights["game_tying_goal"]
            + metrics.overtime_goals * self.weights["overtime_goal"]
            + metrics.shootout_goals * self.weights["shootout_goal"]
            + metrics.late_game_goals * self.weights["late_game_goal"]
            + metrics.late_game_assists * self.weights["late_game_assist"]
            + metrics.close_game_goals * self.weights["close_game_goal"]
            + metrics.close_game_assists * self.weights["close_game_assist"]
            + metrics.must_score_goals * self.weights["must_score_goal"]
            + max(0, metrics.lead_protecting_plus_minus)
            * self.weights["lead_protecting_plus"]
        )

        # Normalize by games played
        games = max(metrics.games_played, 1)
        normalized_score = raw_score / games

        # Update metrics object
        metrics.clutch_score = normalized_score
        metrics.clutch_level = self._classify_clutch_level(normalized_score)

        return normalized_score

    def classify_player(self, player_id: int) -> ClutchLevel:
        """Classify a player's clutch performance level."""
        score = self.calculate_clutch_score(player_id)
        return self._classify_clutch_level(score)

    def get_clutch_rankings(
        self, player_ids: Iterable[int], limit: int = 10
    ) -> list[ClutchPerformerRanking]:
        """
        Get ranked list of clutch performers.

        Args:
            player_ids: Player IDs to rank
            limit: Maximum number of results

        Returns:
            Sorted list of ClutchPerformerRanking objects
        """
        rankings = []
        for player_id in player_ids:
            score = self.calculate_clutch_score(player_id)
            metrics = self.player_metrics.get(player_id)

            if metrics:
                rankings.append(
                    ClutchPerformerRanking(
                        player_id=player_id,
                        name=f"Player_{player_id}",  # Name would come from player model
                        clutch_score=score,
                        clutch_level=self._classify_clutch_level(score),
                        key_stats={
                            "game_winning_goals": metrics.game_winning_goals,
                            "overtime_goals": metrics.overtime_goals,
                            "late_game_points": metrics.late_game_points,
                        },
                    )
                )

        rankings.sort(key=lambda r: r.clutch_score, reverse=True)
        return rankings[:limit]

    def get_metrics(self, player_id: int) -> ClutchMetrics | None:
        """Get clutch metrics for a player."""
        return self.player_metrics.get(player_id)

    def _get_or_create_metrics(self, player_id: int) -> ClutchMetrics:
        """Get or create clutch metrics for a player."""
        if player_id not in self.player_metrics:
            self.player_metrics[player_id] = ClutchMetrics(player_id=player_id)
        return self.player_metrics[player_id]

    def _classify_clutch_level(self, score: float) -> ClutchLevel:
        """Classify clutch level based on score."""
        if score >= self.CLUTCH_THRESHOLDS[ClutchLevel.ELITE]:
            return ClutchLevel.ELITE
        elif score >= self.CLUTCH_THRESHOLDS[ClutchLevel.STRONG]:
            return ClutchLevel.STRONG
        elif score >= self.CLUTCH_THRESHOLDS[ClutchLevel.AVERAGE]:
            return ClutchLevel.AVERAGE
        elif score >= self.CLUTCH_THRESHOLDS[ClutchLevel.BELOW_AVERAGE]:
            return ClutchLevel.BELOW_AVERAGE
        return ClutchLevel.POOR


class StaminaAnalyzer:
    """
    Analyzer for stamina and fatigue patterns.

    Tracks performance degradation across game segments and
    identifies fatigue vulnerabilities.
    """

    # Thresholds for fatigue classification
    FATIGUE_THRESHOLDS = {
        FatigueLevel.MINIMAL: 0.95,  # Less than 5% decline
        FatigueLevel.LOW: 0.85,  # 5-15% decline
        FatigueLevel.MODERATE: 0.75,  # 15-25% decline
        FatigueLevel.HIGH: 0.65,  # 25-35% decline
    }

    def __init__(self) -> None:
        """Initialize the stamina analyzer."""
        self.player_metrics: dict[int, StaminaMetrics] = {}

    def ingest_segment_stats(
        self,
        player_id: int,
        early_stats: dict[str, float],
        mid_stats: dict[str, float],
        late_stats: dict[str, float],
    ) -> None:
        """
        Ingest segment-based statistics for stamina analysis.

        Args:
            player_id: Player ID
            early_stats: Early game stats (must include points_per_60 or goals_per_60)
            mid_stats: Mid game stats
            late_stats: Late game stats
        """
        metrics = self._get_or_create_metrics(player_id)

        metrics.early_game_points_per_60 = early_stats.get(
            "points_per_60", early_stats.get("goals_per_60", 0) * 2
        )
        metrics.mid_game_points_per_60 = mid_stats.get(
            "points_per_60", mid_stats.get("goals_per_60", 0) * 2
        )
        metrics.late_game_points_per_60 = late_stats.get(
            "points_per_60", late_stats.get("goals_per_60", 0) * 2
        )

        metrics.early_game_xg_per_60 = early_stats.get("xg_per_60", 0)
        metrics.mid_game_xg_per_60 = mid_stats.get("xg_per_60", 0)
        metrics.late_game_xg_per_60 = late_stats.get("xg_per_60", 0)

        metrics.early_game_corsi_pct = early_stats.get("corsi_pct", 50.0)
        metrics.mid_game_corsi_pct = mid_stats.get("corsi_pct", 50.0)
        metrics.late_game_corsi_pct = late_stats.get("corsi_pct", 50.0)

        metrics.games_analyzed = early_stats.get("games", 0)

    def ingest_player_metrics(self, metrics: StaminaMetrics) -> None:
        """Ingest pre-calculated stamina metrics for a player."""
        self.player_metrics[metrics.player_id] = metrics

    def calculate_fatigue_indicator(self, player_id: int) -> float:
        """
        Calculate fatigue indicator as ratio of late to early performance.

        Returns:
            Fatigue indicator (< 1.0 indicates performance decline)
        """
        metrics = self.player_metrics.get(player_id)
        if not metrics:
            return 1.0

        early_perf = metrics.early_game_points_per_60
        late_perf = metrics.late_game_points_per_60

        if early_perf <= 0:
            return 1.0

        indicator = late_perf / early_perf
        metrics.fatigue_indicator = indicator

        return indicator

    def calculate_stamina_score(self, player_id: int) -> float:
        """
        Calculate comprehensive stamina score.

        Higher scores indicate better stamina (less performance decline).

        Returns:
            Stamina score from 0-100
        """
        metrics = self.player_metrics.get(player_id)
        if not metrics:
            return 50.0

        # Calculate fatigue indicator if not already done
        fatigue = self.calculate_fatigue_indicator(player_id)

        # Calculate Corsi decline
        corsi_decline = (
            metrics.late_game_corsi_pct - metrics.early_game_corsi_pct
        ) / 50.0  # Normalized

        # Calculate xG decline
        if metrics.early_game_xg_per_60 > 0:
            xg_decline = (
                metrics.late_game_xg_per_60 / metrics.early_game_xg_per_60
            ) - 1.0
        else:
            xg_decline = 0

        # Combine factors (weights sum to 1.0)
        stamina_score = (
            fatigue * 0.5 + (1 + corsi_decline) * 0.25 + (1 + xg_decline) * 0.25
        ) * 50

        # Clamp to 0-100 range
        stamina_score = max(0, min(100, stamina_score))

        metrics.stamina_score = stamina_score
        metrics.fatigue_level = self._classify_fatigue_level(fatigue)

        return stamina_score

    def classify_fatigue(self, player_id: int) -> FatigueLevel:
        """Classify a player's fatigue level."""
        fatigue = self.calculate_fatigue_indicator(player_id)
        return self._classify_fatigue_level(fatigue)

    def identify_fatigue_vulnerable_players(
        self, player_ids: Iterable[int], threshold: FatigueLevel = FatigueLevel.MODERATE
    ) -> list[tuple[int, float]]:
        """
        Identify players vulnerable to fatigue.

        Args:
            player_ids: Player IDs to analyze
            threshold: Minimum fatigue level to include

        Returns:
            List of (player_id, fatigue_indicator) tuples for vulnerable players
        """
        threshold_values = {
            FatigueLevel.MINIMAL: 0.95,
            FatigueLevel.LOW: 0.85,
            FatigueLevel.MODERATE: 0.75,
            FatigueLevel.HIGH: 0.65,
            FatigueLevel.SEVERE: 0.0,
        }

        threshold_value = threshold_values.get(threshold, 0.75)
        vulnerable = []

        for player_id in player_ids:
            fatigue = self.calculate_fatigue_indicator(player_id)
            if fatigue <= threshold_value:
                vulnerable.append((player_id, fatigue))

        vulnerable.sort(key=lambda x: x[1])
        return vulnerable

    def get_late_game_recommendations(self, player_id: int) -> list[str]:
        """
        Get usage recommendations for late game situations.

        Args:
            player_id: Player ID

        Returns:
            List of recommendation strings
        """
        metrics = self.player_metrics.get(player_id)
        if not metrics:
            return ["Insufficient data for recommendations"]

        recommendations = []
        fatigue = self.calculate_fatigue_indicator(player_id)
        level = self._classify_fatigue_level(fatigue)

        if level in (FatigueLevel.HIGH, FatigueLevel.SEVERE):
            recommendations.extend(
                [
                    "Limit ice time in third period",
                    "Avoid deploying in crucial late-game situations",
                    "Consider as early/mid game specialist",
                ]
            )
        elif level == FatigueLevel.MODERATE:
            recommendations.extend(
                [
                    "Monitor ice time in late game",
                    "Use fresh legs for key matchups in third period",
                ]
            )
        elif level in (FatigueLevel.MINIMAL, FatigueLevel.LOW):
            recommendations.extend(
                [
                    "Strong candidate for late game deployment",
                    "Consider for overtime situations",
                ]
            )

        return recommendations

    def get_metrics(self, player_id: int) -> StaminaMetrics | None:
        """Get stamina metrics for a player."""
        return self.player_metrics.get(player_id)

    def _get_or_create_metrics(self, player_id: int) -> StaminaMetrics:
        """Get or create stamina metrics for a player."""
        if player_id not in self.player_metrics:
            self.player_metrics[player_id] = StaminaMetrics(player_id=player_id)
        return self.player_metrics[player_id]

    def _classify_fatigue_level(self, fatigue_indicator: float) -> FatigueLevel:
        """Classify fatigue level based on indicator."""
        if fatigue_indicator >= self.FATIGUE_THRESHOLDS[FatigueLevel.MINIMAL]:
            return FatigueLevel.MINIMAL
        elif fatigue_indicator >= self.FATIGUE_THRESHOLDS[FatigueLevel.LOW]:
            return FatigueLevel.LOW
        elif fatigue_indicator >= self.FATIGUE_THRESHOLDS[FatigueLevel.MODERATE]:
            return FatigueLevel.MODERATE
        elif fatigue_indicator >= self.FATIGUE_THRESHOLDS[FatigueLevel.HIGH]:
            return FatigueLevel.HIGH
        return FatigueLevel.SEVERE


class TeamResilienceAnalyzer:
    """
    Analyzer for team-level resilience and collapse patterns.

    Tracks lead protection, comeback ability, and third period performance.
    """

    RESILIENT_THRESHOLD = 0.65  # Lead protection rate for resilient teams
    COLLAPSE_THRESHOLD = 0.55  # Below this = collapse prone

    def __init__(self) -> None:
        """Initialize the team resilience analyzer."""
        self.team_metrics: dict[int, TeamResilienceMetrics] = {}

    def record_lead_result(self, team_id: int, held: bool) -> None:
        """Record whether a team held or blew a lead."""
        metrics = self._get_or_create_metrics(team_id)
        if held:
            metrics.leads_held += 1
        else:
            metrics.leads_blown += 1
        self._update_rates(team_id)

    def record_comeback_result(self, team_id: int, completed: bool) -> None:
        """Record whether a team completed a comeback."""
        metrics = self._get_or_create_metrics(team_id)
        metrics.comeback_opportunities += 1
        if completed:
            metrics.comebacks_completed += 1
        self._update_rates(team_id)

    def record_third_period_goals(
        self, team_id: int, goals_for: int, goals_against: int
    ) -> None:
        """Record third period goal differential."""
        metrics = self._get_or_create_metrics(team_id)
        metrics.third_period_goals_for += goals_for
        metrics.third_period_goals_against += goals_against
        metrics.third_period_goal_differential = (
            metrics.third_period_goals_for - metrics.third_period_goals_against
        )

    def ingest_team_metrics(self, metrics: TeamResilienceMetrics) -> None:
        """Ingest pre-calculated team resilience metrics."""
        self.team_metrics[metrics.team_id] = metrics
        self._update_rates(metrics.team_id)

    def is_resilient(self, team_id: int) -> bool:
        """Check if a team is classified as resilient."""
        metrics = self.team_metrics.get(team_id)
        if not metrics:
            return False
        return metrics.lead_protection_rate >= self.RESILIENT_THRESHOLD

    def is_collapse_prone(self, team_id: int) -> bool:
        """Check if a team is classified as collapse-prone."""
        metrics = self.team_metrics.get(team_id)
        if not metrics:
            return False
        return metrics.lead_protection_rate < self.COLLAPSE_THRESHOLD

    def get_resilient_teams(self, team_ids: Iterable[int]) -> list[int]:
        """Get list of resilient teams from provided IDs."""
        return [tid for tid in team_ids if self.is_resilient(tid)]

    def get_collapse_prone_teams(self, team_ids: Iterable[int]) -> list[int]:
        """Get list of collapse-prone teams from provided IDs."""
        return [tid for tid in team_ids if self.is_collapse_prone(tid)]

    def get_metrics(self, team_id: int) -> TeamResilienceMetrics | None:
        """Get resilience metrics for a team."""
        return self.team_metrics.get(team_id)

    def _get_or_create_metrics(self, team_id: int) -> TeamResilienceMetrics:
        """Get or create team resilience metrics."""
        if team_id not in self.team_metrics:
            self.team_metrics[team_id] = TeamResilienceMetrics(team_id=team_id)
        return self.team_metrics[team_id]

    def _update_rates(self, team_id: int) -> None:
        """Update calculated rates for a team."""
        metrics = self.team_metrics.get(team_id)
        if not metrics:
            return

        total_leads = metrics.leads_held + metrics.leads_blown
        if total_leads > 0:
            metrics.lead_protection_rate = metrics.leads_held / total_leads

        if metrics.comeback_opportunities > 0:
            metrics.comeback_rate = (
                metrics.comebacks_completed / metrics.comeback_opportunities
            )

        metrics.is_resilient = self.is_resilient(team_id)
        metrics.is_collapse_prone = self.is_collapse_prone(team_id)
