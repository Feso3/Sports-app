"""
Win Probability and Prediction Output Module

Generates win probability predictions, confidence scores,
and formatted output for simulation results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simulation.models import MatchupAnalysis, SimulationResult


@dataclass
class WinProbability:
    """Win probability breakdown."""

    home_win_pct: float = 0.5
    away_win_pct: float = 0.5
    home_regulation_win_pct: float = 0.0
    away_regulation_win_pct: float = 0.0
    overtime_pct: float = 0.0
    shootout_pct: float = 0.0

    @property
    def home_points_expected(self) -> float:
        """Expected points for home team (2 for win, 1 for OT loss)."""
        return self.home_win_pct * 2 + (self.overtime_pct * self.away_win_pct)

    @property
    def away_points_expected(self) -> float:
        """Expected points for away team."""
        return self.away_win_pct * 2 + (self.overtime_pct * self.home_win_pct)


@dataclass
class PredictionSummary:
    """Complete prediction summary for a matchup."""

    # Teams
    home_team_id: int
    away_team_id: int
    home_team_name: str = ""
    away_team_name: str = ""

    # Win probabilities
    win_probability: WinProbability = field(default_factory=WinProbability)

    # Predicted outcome
    predicted_winner_id: int = 0
    predicted_winner_name: str = ""
    win_confidence: str = "medium"  # "low", "medium", "high", "very_high"

    # Score predictions
    most_likely_score: tuple[int, int] = (0, 0)
    average_home_goals: float = 0.0
    average_away_goals: float = 0.0
    average_total_goals: float = 0.0

    # Key factors
    key_advantages: list[str] = field(default_factory=list)
    key_disadvantages: list[str] = field(default_factory=list)

    # Matchup classification
    matchup_type: str = "competitive"  # "blowout", "competitive", "toss-up"
    variance_level: str = "normal"  # "low", "normal", "high"

    # Confidence metrics
    data_quality_score: float = 0.5
    prediction_confidence: float = 0.5


class PredictionGenerator:
    """
    Generator for win probability predictions.

    Processes simulation results into formatted predictions and analysis.
    """

    # Confidence thresholds
    CONFIDENCE_THRESHOLDS = {
        "very_high": 0.75,  # 75%+ win probability
        "high": 0.65,
        "medium": 0.55,
        "low": 0.50,
    }

    # Matchup type thresholds
    BLOWOUT_THRESHOLD = 0.70  # 70%+ = expected blowout
    TOSSUP_THRESHOLD = 0.55  # Under 55% = toss-up

    def generate_prediction(
        self,
        result: SimulationResult,
        home_team_name: str = "",
        away_team_name: str = "",
    ) -> PredictionSummary:
        """
        Generate complete prediction from simulation results.

        Args:
            result: SimulationResult from engine
            home_team_name: Home team display name
            away_team_name: Away team display name

        Returns:
            PredictionSummary with all predictions
        """
        summary = PredictionSummary(
            home_team_id=result.config.home_team_id,
            away_team_id=result.config.away_team_id,
            home_team_name=home_team_name or f"Team {result.config.home_team_id}",
            away_team_name=away_team_name or f"Team {result.config.away_team_id}",
        )

        # Calculate win probabilities
        summary.win_probability = self._calculate_win_probability(result)

        # Determine predicted winner
        if result.home_win_probability > result.away_win_probability:
            summary.predicted_winner_id = result.config.home_team_id
            summary.predicted_winner_name = summary.home_team_name
            win_pct = result.home_win_probability
        else:
            summary.predicted_winner_id = result.config.away_team_id
            summary.predicted_winner_name = summary.away_team_name
            win_pct = result.away_win_probability

        # Determine confidence level
        summary.win_confidence = self._classify_confidence(win_pct)

        # Score predictions
        summary.most_likely_score = result.score_distribution.most_likely_score()
        summary.average_home_goals = result.score_distribution.average_home_goals(
            result.total_iterations
        )
        summary.average_away_goals = result.score_distribution.average_away_goals(
            result.total_iterations
        )
        summary.average_total_goals = summary.average_home_goals + summary.average_away_goals

        # Analyze key factors from matchup analysis
        if result.matchup_analysis:
            advantages, disadvantages = self._analyze_matchup_factors(
                result.matchup_analysis,
                result.home_win_probability > 0.5,
            )
            summary.key_advantages = advantages
            summary.key_disadvantages = disadvantages

        # Classify matchup
        summary.matchup_type = self._classify_matchup(result)
        summary.variance_level = result.variance_indicator

        # Confidence metrics
        summary.data_quality_score = result.confidence_score
        summary.prediction_confidence = self._calculate_prediction_confidence(result)

        return summary

    def generate_report(
        self,
        prediction: PredictionSummary,
        include_details: bool = True,
    ) -> str:
        """
        Generate formatted text report from prediction.

        Args:
            prediction: PredictionSummary to format
            include_details: Whether to include detailed analysis

        Returns:
            Formatted report string
        """
        lines = []

        # Header
        lines.append("=" * 60)
        lines.append("GAME PREDICTION REPORT")
        lines.append("=" * 60)
        lines.append("")

        # Matchup
        lines.append(f"{prediction.home_team_name} vs {prediction.away_team_name}")
        lines.append("-" * 40)
        lines.append("")

        # Win probabilities
        lines.append("WIN PROBABILITIES:")
        lines.append(
            f"  {prediction.home_team_name}: "
            f"{prediction.win_probability.home_win_pct:.1%}"
        )
        lines.append(
            f"  {prediction.away_team_name}: "
            f"{prediction.win_probability.away_win_pct:.1%}"
        )
        lines.append(f"  Overtime likelihood: {prediction.win_probability.overtime_pct:.1%}")
        lines.append("")

        # Prediction
        lines.append("PREDICTION:")
        lines.append(
            f"  Winner: {prediction.predicted_winner_name} "
            f"(Confidence: {prediction.win_confidence.upper()})"
        )
        lines.append(f"  Most Likely Score: {prediction.most_likely_score[0]}-{prediction.most_likely_score[1]}")
        lines.append(
            f"  Expected Goals: {prediction.average_home_goals:.1f} - "
            f"{prediction.average_away_goals:.1f}"
        )
        lines.append(f"  Matchup Type: {prediction.matchup_type.replace('_', ' ').title()}")
        lines.append("")

        if include_details:
            # Key factors
            if prediction.key_advantages:
                lines.append("KEY ADVANTAGES:")
                for adv in prediction.key_advantages[:5]:
                    lines.append(f"  + {adv}")
                lines.append("")

            if prediction.key_disadvantages:
                lines.append("KEY CONCERNS:")
                for dis in prediction.key_disadvantages[:5]:
                    lines.append(f"  - {dis}")
                lines.append("")

            # Confidence metrics
            lines.append("CONFIDENCE METRICS:")
            lines.append(f"  Data Quality: {prediction.data_quality_score:.0%}")
            lines.append(f"  Prediction Confidence: {prediction.prediction_confidence:.0%}")
            lines.append(f"  Variance Level: {prediction.variance_level.title()}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def generate_json_output(self, prediction: PredictionSummary) -> dict[str, Any]:
        """
        Generate JSON-serializable output.

        Args:
            prediction: PredictionSummary to convert

        Returns:
            Dictionary suitable for JSON serialization
        """
        return {
            "matchup": {
                "home_team": {
                    "id": prediction.home_team_id,
                    "name": prediction.home_team_name,
                },
                "away_team": {
                    "id": prediction.away_team_id,
                    "name": prediction.away_team_name,
                },
            },
            "win_probability": {
                "home": round(prediction.win_probability.home_win_pct, 4),
                "away": round(prediction.win_probability.away_win_pct, 4),
                "home_regulation": round(prediction.win_probability.home_regulation_win_pct, 4),
                "away_regulation": round(prediction.win_probability.away_regulation_win_pct, 4),
                "overtime": round(prediction.win_probability.overtime_pct, 4),
                "shootout": round(prediction.win_probability.shootout_pct, 4),
            },
            "prediction": {
                "winner_id": prediction.predicted_winner_id,
                "winner_name": prediction.predicted_winner_name,
                "confidence": prediction.win_confidence,
                "most_likely_score": list(prediction.most_likely_score),
            },
            "expected_goals": {
                "home": round(prediction.average_home_goals, 2),
                "away": round(prediction.average_away_goals, 2),
                "total": round(prediction.average_total_goals, 2),
            },
            "analysis": {
                "matchup_type": prediction.matchup_type,
                "variance_level": prediction.variance_level,
                "key_advantages": prediction.key_advantages,
                "key_disadvantages": prediction.key_disadvantages,
            },
            "confidence": {
                "data_quality": round(prediction.data_quality_score, 4),
                "prediction_confidence": round(prediction.prediction_confidence, 4),
            },
        }

    def _calculate_win_probability(self, result: SimulationResult) -> WinProbability:
        """Calculate detailed win probability breakdown."""
        total = result.total_iterations

        # Regulation wins (non-OT games where team won)
        regulation_games = total - result.overtime_games
        home_reg_wins = 0
        away_reg_wins = 0

        for game in result.sample_games:
            if not game.went_to_overtime:
                if game.winner == result.config.home_team_id:
                    home_reg_wins += 1
                else:
                    away_reg_wins += 1

        # Scale up from sample
        sample_size = len(result.sample_games) or 1
        scale = total / sample_size

        return WinProbability(
            home_win_pct=result.home_win_probability,
            away_win_pct=result.away_win_probability,
            home_regulation_win_pct=(home_reg_wins * scale) / total,
            away_regulation_win_pct=(away_reg_wins * scale) / total,
            overtime_pct=result.overtime_rate,
            shootout_pct=result.shootout_games / total if total > 0 else 0,
        )

    def _classify_confidence(self, win_pct: float) -> str:
        """Classify confidence level based on win percentage."""
        if win_pct >= self.CONFIDENCE_THRESHOLDS["very_high"]:
            return "very_high"
        elif win_pct >= self.CONFIDENCE_THRESHOLDS["high"]:
            return "high"
        elif win_pct >= self.CONFIDENCE_THRESHOLDS["medium"]:
            return "medium"
        return "low"

    def _classify_matchup(self, result: SimulationResult) -> str:
        """Classify the matchup type."""
        max_prob = max(result.home_win_probability, result.away_win_probability)

        if max_prob >= self.BLOWOUT_THRESHOLD:
            return "blowout"
        elif max_prob < self.TOSSUP_THRESHOLD:
            return "toss-up"
        return "competitive"

    def _calculate_prediction_confidence(self, result: SimulationResult) -> float:
        """Calculate overall prediction confidence."""
        # Base on data quality
        base = result.confidence_score

        # Adjust for clarity of result
        win_margin = abs(result.home_win_probability - result.away_win_probability)
        clarity_bonus = min(win_margin * 0.5, 0.2)

        # Penalty for high variance
        if result.variance_indicator == "high":
            clarity_bonus -= 0.1

        return min(base + clarity_bonus, 1.0)

    def _analyze_matchup_factors(
        self,
        analysis: MatchupAnalysis,
        home_favored: bool,
    ) -> tuple[list[str], list[str]]:
        """Analyze matchup and return advantages/disadvantages for predicted winner."""
        advantages = []
        disadvantages = []

        # Analyze zone advantages
        for zone, advantage in analysis.zone_advantages.items():
            if home_favored:
                if advantage > 0.1:
                    advantages.append(f"Strong {zone.replace('_', ' ')} control")
                elif advantage < -0.1:
                    disadvantages.append(f"Vulnerable in {zone.replace('_', ' ')}")
            else:
                if advantage < -0.1:
                    advantages.append(f"Strong {zone.replace('_', ' ')} control")
                elif advantage > 0.1:
                    disadvantages.append(f"Vulnerable in {zone.replace('_', ' ')}")

        # Analyze segment advantages
        segments = [
            ("early_game", analysis.early_game_advantage),
            ("mid_game", analysis.mid_game_advantage),
            ("late_game", analysis.late_game_advantage),
        ]

        for segment_name, advantage in segments:
            threshold = 0.08
            if home_favored:
                if advantage > threshold:
                    advantages.append(f"{segment_name.replace('_', ' ').title()} dominance")
                elif advantage < -threshold:
                    disadvantages.append(f"Weak in {segment_name.replace('_', ' ')}")
            else:
                if advantage < -threshold:
                    advantages.append(f"{segment_name.replace('_', ' ').title()} dominance")
                elif advantage > threshold:
                    disadvantages.append(f"Weak in {segment_name.replace('_', ' ')}")

        # Special teams
        if home_favored:
            if analysis.power_play_advantage > 0.03:
                advantages.append("Power play advantage")
            elif analysis.power_play_advantage < -0.03:
                disadvantages.append("Power play disadvantage")
            if analysis.penalty_kill_advantage > 0.03:
                advantages.append("Penalty kill advantage")
        else:
            if analysis.power_play_advantage < -0.03:
                advantages.append("Power play advantage")
            elif analysis.power_play_advantage > 0.03:
                disadvantages.append("Power play disadvantage")
            if analysis.penalty_kill_advantage < -0.03:
                advantages.append("Penalty kill advantage")

        # Goaltending
        if home_favored:
            if analysis.goalie_advantage > 0.02:
                advantages.append("Goaltending edge")
            elif analysis.goalie_advantage < -0.02:
                disadvantages.append("Goaltending concern")
        else:
            if analysis.goalie_advantage < -0.02:
                advantages.append("Goaltending edge")
            elif analysis.goalie_advantage > 0.02:
                disadvantages.append("Goaltending concern")

        # Key mismatches
        for mismatch, impact in analysis.key_mismatches.items():
            if impact > 0.1:
                if (home_favored and "home" in mismatch) or (not home_favored and "away" in mismatch):
                    clean_name = mismatch.replace("home_", "").replace("away_", "").replace("_", " ").title()
                    advantages.append(clean_name)

        return advantages[:7], disadvantages[:5]


def format_probability(prob: float, decimal_places: int = 1) -> str:
    """Format probability as percentage string."""
    return f"{prob * 100:.{decimal_places}f}%"


def format_score(home: int, away: int) -> str:
    """Format score as string."""
    return f"{home}-{away}"


def get_confidence_emoji(confidence: str) -> str:
    """Get emoji for confidence level."""
    emojis = {
        "very_high": "🔥",
        "high": "✅",
        "medium": "➡️",
        "low": "⚠️",
    }
    return emojis.get(confidence, "")
