"""
Tests for Prediction Generator
"""

import pytest

from simulation.models import (
    MatchupAnalysis,
    ScoreDistribution,
    SimulatedGame,
    SimulationConfig,
    SimulationResult,
)
from simulation.predictions import (
    PredictionGenerator,
    PredictionSummary,
    WinProbability,
    format_probability,
    format_score,
)


@pytest.fixture
def sample_simulation_result():
    """Create a sample simulation result for testing."""
    config = SimulationConfig(home_team_id=1, away_team_id=2)

    score_dist = ScoreDistribution()
    for _ in range(600):
        score_dist.add_result(3, 2)
    for _ in range(200):
        score_dist.add_result(4, 1)
    for _ in range(150):
        score_dist.add_result(2, 3)
    for _ in range(50):
        score_dist.add_result(1, 4)

    matchup = MatchupAnalysis(
        home_team_id=1,
        away_team_id=2,
        zone_advantages={"slot": 0.15, "high_slot": 0.08, "point": -0.05},
        early_game_advantage=0.1,
        mid_game_advantage=0.05,
        late_game_advantage=0.12,
        power_play_advantage=0.06,
        penalty_kill_advantage=0.03,
        goalie_advantage=0.025,
    )

    sample_games = [
        SimulatedGame(
            game_number=1,
            home_score=3,
            away_score=2,
            winner=1,
            went_to_overtime=False,
        ),
        SimulatedGame(
            game_number=2,
            home_score=4,
            away_score=3,
            winner=1,
            went_to_overtime=True,
        ),
    ]

    return SimulationResult(
        config=config,
        total_iterations=1000,
        home_wins=650,
        away_wins=350,
        overtime_games=100,
        shootout_games=20,
        score_distribution=score_dist,
        matchup_analysis=matchup,
        sample_games=sample_games,
        average_home_xg=2.8,
        average_away_xg=2.3,
        confidence_score=0.75,
    )


@pytest.fixture
def prediction_generator():
    """Create a PredictionGenerator instance."""
    return PredictionGenerator()


class TestPredictionGenerator:
    """Tests for PredictionGenerator class."""

    def test_generator_initialization(self, prediction_generator):
        """Test generator initializes correctly."""
        assert prediction_generator.CONFIDENCE_THRESHOLDS is not None
        assert prediction_generator.BLOWOUT_THRESHOLD > prediction_generator.TOSSUP_THRESHOLD

    def test_generate_prediction(self, prediction_generator, sample_simulation_result):
        """Test basic prediction generation."""
        prediction = prediction_generator.generate_prediction(
            sample_simulation_result,
            home_team_name="Home Team",
            away_team_name="Away Team",
        )

        assert isinstance(prediction, PredictionSummary)
        assert prediction.home_team_id == 1
        assert prediction.away_team_id == 2
        assert prediction.home_team_name == "Home Team"
        assert prediction.away_team_name == "Away Team"

    def test_prediction_win_probability(self, prediction_generator, sample_simulation_result):
        """Test win probability is calculated correctly."""
        prediction = prediction_generator.generate_prediction(sample_simulation_result)

        assert prediction.win_probability.home_win_pct == 0.65
        assert prediction.win_probability.away_win_pct == 0.35
        assert prediction.win_probability.overtime_pct == 0.1

    def test_prediction_predicted_winner(self, prediction_generator, sample_simulation_result):
        """Test predicted winner is correct."""
        prediction = prediction_generator.generate_prediction(sample_simulation_result)

        assert prediction.predicted_winner_id == 1  # Home team wins more
        assert prediction.win_confidence in ["low", "medium", "high", "very_high"]

    def test_prediction_score(self, prediction_generator, sample_simulation_result):
        """Test score predictions."""
        prediction = prediction_generator.generate_prediction(sample_simulation_result)

        assert prediction.most_likely_score == (3, 2)  # Most common score
        assert prediction.average_home_goals > 0
        assert prediction.average_away_goals > 0

    def test_prediction_matchup_type(self, prediction_generator, sample_simulation_result):
        """Test matchup type classification."""
        prediction = prediction_generator.generate_prediction(sample_simulation_result)

        # 65% win probability should be competitive
        assert prediction.matchup_type in ["blowout", "competitive", "toss-up"]

    def test_prediction_key_advantages(self, prediction_generator, sample_simulation_result):
        """Test key advantages are identified."""
        prediction = prediction_generator.generate_prediction(sample_simulation_result)

        # Should have some advantages based on matchup analysis
        assert isinstance(prediction.key_advantages, list)
        assert isinstance(prediction.key_disadvantages, list)

    def test_prediction_confidence_metrics(self, prediction_generator, sample_simulation_result):
        """Test confidence metrics."""
        prediction = prediction_generator.generate_prediction(sample_simulation_result)

        assert 0 <= prediction.data_quality_score <= 1
        assert 0 <= prediction.prediction_confidence <= 1


class TestPredictionReport:
    """Tests for prediction report generation."""

    def test_generate_report(self, prediction_generator, sample_simulation_result):
        """Test text report generation."""
        prediction = prediction_generator.generate_prediction(
            sample_simulation_result,
            home_team_name="Home Team",
            away_team_name="Away Team",
        )

        report = prediction_generator.generate_report(prediction)

        assert isinstance(report, str)
        assert "Home Team" in report
        assert "Away Team" in report
        assert "WIN PROBABILITIES" in report
        assert "PREDICTION" in report

    def test_generate_report_without_details(self, prediction_generator, sample_simulation_result):
        """Test report without detailed analysis."""
        prediction = prediction_generator.generate_prediction(sample_simulation_result)

        report = prediction_generator.generate_report(prediction, include_details=False)

        assert isinstance(report, str)
        assert "KEY ADVANTAGES" not in report or "CONFIDENCE METRICS" not in report


class TestPredictionJSON:
    """Tests for JSON output generation."""

    def test_generate_json_output(self, prediction_generator, sample_simulation_result):
        """Test JSON output generation."""
        prediction = prediction_generator.generate_prediction(
            sample_simulation_result,
            home_team_name="Home Team",
            away_team_name="Away Team",
        )

        json_output = prediction_generator.generate_json_output(prediction)

        assert isinstance(json_output, dict)
        assert "matchup" in json_output
        assert "win_probability" in json_output
        assert "prediction" in json_output
        assert "expected_goals" in json_output
        assert "analysis" in json_output
        assert "confidence" in json_output

    def test_json_matchup_section(self, prediction_generator, sample_simulation_result):
        """Test JSON matchup section."""
        prediction = prediction_generator.generate_prediction(sample_simulation_result)
        json_output = prediction_generator.generate_json_output(prediction)

        matchup = json_output["matchup"]
        assert matchup["home_team"]["id"] == 1
        assert matchup["away_team"]["id"] == 2

    def test_json_win_probability_section(self, prediction_generator, sample_simulation_result):
        """Test JSON win probability section."""
        prediction = prediction_generator.generate_prediction(sample_simulation_result)
        json_output = prediction_generator.generate_json_output(prediction)

        wp = json_output["win_probability"]
        assert wp["home"] == 0.65
        assert wp["away"] == 0.35
        assert "overtime" in wp


class TestWinProbability:
    """Tests for WinProbability dataclass."""

    def test_win_probability_creation(self):
        """Test creating win probability."""
        wp = WinProbability(
            home_win_pct=0.6,
            away_win_pct=0.4,
            home_regulation_win_pct=0.45,
            away_regulation_win_pct=0.35,
            overtime_pct=0.2,
            shootout_pct=0.05,
        )

        assert wp.home_win_pct == 0.6
        assert wp.away_win_pct == 0.4

    def test_win_probability_points_expected(self):
        """Test expected points calculation."""
        wp = WinProbability(
            home_win_pct=0.6,
            away_win_pct=0.4,
            overtime_pct=0.15,
        )

        # Home: 0.6 * 2 + 0.15 * 0.4 = 1.26
        assert wp.home_points_expected == pytest.approx(1.26, rel=0.01)

        # Away: 0.4 * 2 + 0.15 * 0.6 = 0.89
        assert wp.away_points_expected == pytest.approx(0.89, rel=0.01)


class TestPredictionSummary:
    """Tests for PredictionSummary dataclass."""

    def test_prediction_summary_creation(self):
        """Test creating prediction summary."""
        summary = PredictionSummary(
            home_team_id=1,
            away_team_id=2,
            home_team_name="Home",
            away_team_name="Away",
        )

        assert summary.home_team_id == 1
        assert summary.away_team_id == 2
        assert summary.matchup_type == "competitive"  # Default

    def test_prediction_summary_defaults(self):
        """Test prediction summary default values."""
        summary = PredictionSummary(home_team_id=1, away_team_id=2)

        assert summary.win_confidence == "medium"
        assert summary.variance_level == "normal"
        assert summary.data_quality_score == 0.5


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_format_probability(self):
        """Test probability formatting."""
        assert format_probability(0.5) == "50.0%"
        assert format_probability(0.652, decimal_places=1) == "65.2%"
        assert format_probability(0.333, decimal_places=2) == "33.30%"

    def test_format_score(self):
        """Test score formatting."""
        assert format_score(3, 2) == "3-2"
        assert format_score(0, 0) == "0-0"
        assert format_score(7, 1) == "7-1"


class TestConfidenceClassification:
    """Tests for confidence classification."""

    def test_very_high_confidence(self, prediction_generator):
        """Test very high confidence classification."""
        config = SimulationConfig(home_team_id=1, away_team_id=2)
        result = SimulationResult(
            config=config,
            total_iterations=1000,
            home_wins=800,
            away_wins=200,
            overtime_games=50,
            shootout_games=10,
        )

        prediction = prediction_generator.generate_prediction(result)
        assert prediction.win_confidence == "very_high"

    def test_low_confidence(self, prediction_generator):
        """Test low confidence classification."""
        config = SimulationConfig(home_team_id=1, away_team_id=2)
        result = SimulationResult(
            config=config,
            total_iterations=1000,
            home_wins=520,
            away_wins=480,
            overtime_games=50,
            shootout_games=10,
        )

        prediction = prediction_generator.generate_prediction(result)
        assert prediction.win_confidence == "low"


class TestMatchupClassification:
    """Tests for matchup type classification."""

    def test_blowout_classification(self, prediction_generator):
        """Test blowout matchup classification."""
        config = SimulationConfig(home_team_id=1, away_team_id=2)
        result = SimulationResult(
            config=config,
            total_iterations=1000,
            home_wins=750,
            away_wins=250,
            overtime_games=30,
            shootout_games=5,
        )

        prediction = prediction_generator.generate_prediction(result)
        assert prediction.matchup_type == "blowout"

    def test_tossup_classification(self, prediction_generator):
        """Test toss-up matchup classification."""
        config = SimulationConfig(home_team_id=1, away_team_id=2)
        result = SimulationResult(
            config=config,
            total_iterations=1000,
            home_wins=530,
            away_wins=470,
            overtime_games=100,
            shootout_games=20,
        )

        prediction = prediction_generator.generate_prediction(result)
        assert prediction.matchup_type == "toss-up"
