"""
Tests for Simulation Data Models
"""

import pytest

from simulation.models import (
    GameSegment,
    GameSituation,
    LineMatchup,
    MatchupAnalysis,
    ScoreDistribution,
    SegmentResult,
    SimulatedGame,
    SimulationConfig,
    SimulationMode,
    SimulationResult,
)


class TestSimulationConfig:
    """Tests for SimulationConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SimulationConfig(home_team_id=1, away_team_id=2)

        assert config.iterations == 10000
        assert config.mode == SimulationMode.SINGLE_GAME
        assert config.home_team_id == 1
        assert config.away_team_id == 2
        assert config.use_synergy_adjustments is True
        assert config.use_clutch_adjustments is True
        assert config.use_fatigue_adjustments is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = SimulationConfig(
            home_team_id=10,
            away_team_id=22,
            iterations=5000,
            mode=SimulationMode.SERIES,
            random_seed=42,
            use_synergy_adjustments=False,
        )

        assert config.iterations == 5000
        assert config.mode == SimulationMode.SERIES
        assert config.random_seed == 42
        assert config.use_synergy_adjustments is False

    def test_config_segment_weights(self):
        """Test segment weight defaults."""
        config = SimulationConfig(home_team_id=1, away_team_id=2)

        assert "early_game" in config.segment_weights
        assert "late_game" in config.segment_weights
        assert config.segment_weights["late_game"] > config.segment_weights["early_game"]

    def test_config_validation(self):
        """Test config validation constraints."""
        # Valid minimum iterations
        config = SimulationConfig(home_team_id=1, away_team_id=2, iterations=100)
        assert config.iterations == 100

        # Variance factor constraints
        config = SimulationConfig(
            home_team_id=1, away_team_id=2, variance_factor=0.3
        )
        assert config.variance_factor == 0.3


class TestLineMatchup:
    """Tests for LineMatchup model."""

    def test_line_matchup_creation(self):
        """Test creating a line matchup."""
        matchup = LineMatchup(
            home_line_number=1,
            away_line_number=2,
            line_type="forward",
            home_offensive_strength=0.8,
            away_offensive_strength=0.7,
            home_xg=0.5,
            away_xg=0.4,
        )

        assert matchup.home_line_number == 1
        assert matchup.away_line_number == 2
        assert matchup.line_type == "forward"
        assert matchup.home_xg > matchup.away_xg


class TestScoreDistribution:
    """Tests for ScoreDistribution model."""

    def test_empty_distribution(self):
        """Test empty score distribution."""
        dist = ScoreDistribution()
        assert dist.most_likely_score() == (0, 0)

    def test_add_results(self):
        """Test adding results to distribution."""
        dist = ScoreDistribution()

        # Add multiple 3-2 home wins
        for _ in range(5):
            dist.add_result(3, 2)

        # Add some 2-1 games
        for _ in range(3):
            dist.add_result(2, 1)

        assert dist.score_counts[(3, 2)] == 5
        assert dist.score_counts[(2, 1)] == 3
        assert dist.most_likely_score() == (3, 2)

    def test_average_goals(self):
        """Test average goal calculations."""
        dist = ScoreDistribution()

        dist.add_result(3, 2)
        dist.add_result(4, 1)
        dist.add_result(2, 3)

        assert dist.average_home_goals(3) == 3.0  # (3+4+2)/3
        assert dist.average_away_goals(3) == 2.0  # (2+1+3)/3


class TestSimulatedGame:
    """Tests for SimulatedGame model."""

    def test_game_properties(self):
        """Test game properties."""
        game = SimulatedGame(
            game_number=1,
            home_score=4,
            away_score=2,
            winner=1,
        )

        assert game.goal_differential == 2
        assert game.total_goals == 6
        assert game.was_blowout is False
        assert game.was_close is False

    def test_close_game(self):
        """Test close game detection."""
        game = SimulatedGame(
            game_number=1,
            home_score=3,
            away_score=2,
            winner=1,
        )

        assert game.was_close is True
        assert game.was_blowout is False

    def test_blowout_game(self):
        """Test blowout detection."""
        game = SimulatedGame(
            game_number=1,
            home_score=7,
            away_score=1,
            winner=1,
        )

        assert game.was_blowout is True
        assert game.goal_differential == 6

    def test_overtime_game(self):
        """Test overtime game."""
        game = SimulatedGame(
            game_number=1,
            home_score=3,
            away_score=2,
            winner=1,
            went_to_overtime=True,
        )

        assert game.was_close is True
        assert game.went_to_overtime is True


class TestSimulationResult:
    """Tests for SimulationResult model."""

    def test_win_probability_calculation(self):
        """Test automatic win probability calculation."""
        config = SimulationConfig(home_team_id=1, away_team_id=2)
        result = SimulationResult(
            config=config,
            total_iterations=1000,
            home_wins=600,
            away_wins=400,
            overtime_games=100,
            shootout_games=20,
        )

        assert result.home_win_probability == 0.6
        assert result.away_win_probability == 0.4
        assert result.overtime_rate == 0.1
        assert result.predicted_winner == 1  # Home team

    def test_variance_classification(self):
        """Test variance classification."""
        config = SimulationConfig(home_team_id=1, away_team_id=2)

        # Close matchup - high variance
        result = SimulationResult(
            config=config,
            total_iterations=1000,
            home_wins=520,
            away_wins=480,
            overtime_games=0,
            shootout_games=0,
        )
        assert result.is_high_variance is True

        # One-sided matchup
        result2 = SimulationResult(
            config=config,
            total_iterations=1000,
            home_wins=750,
            away_wins=250,
            overtime_games=0,
            shootout_games=0,
        )
        assert result2.is_high_variance is False
        assert result2.win_margin == 0.5

    def test_get_summary(self):
        """Test summary generation."""
        config = SimulationConfig(home_team_id=1, away_team_id=2)
        result = SimulationResult(
            config=config,
            total_iterations=1000,
            home_wins=600,
            away_wins=400,
            overtime_games=100,
            shootout_games=20,
            confidence_score=0.8,
        )

        summary = result.get_summary()

        assert summary["home_team_id"] == 1
        assert summary["away_team_id"] == 2
        assert summary["iterations"] == 1000
        assert summary["home_win_probability"] == 0.6
        assert summary["predicted_winner"] == 1
        assert summary["confidence_score"] == 0.8


class TestSegmentResult:
    """Tests for SegmentResult model."""

    def test_segment_result(self):
        """Test segment result creation."""
        result = SegmentResult(
            segment=GameSegment.LATE_GAME,
            home_goals=2,
            away_goals=1,
            home_xg=1.5,
            away_xg=1.2,
            home_shots=10,
            away_shots=8,
        )

        assert result.segment == GameSegment.LATE_GAME
        assert result.home_goals > result.away_goals
        assert result.dominant_team is None  # Not set automatically


class TestMatchupAnalysis:
    """Tests for MatchupAnalysis model."""

    def test_matchup_analysis(self):
        """Test matchup analysis properties."""
        analysis = MatchupAnalysis(
            home_team_id=1,
            away_team_id=2,
            early_game_advantage=0.1,
            mid_game_advantage=0.05,
            late_game_advantage=0.15,
            power_play_advantage=0.08,
            penalty_kill_advantage=0.04,
            goalie_advantage=0.02,
        )

        overall = analysis.overall_advantage
        assert overall > 0  # Home team has advantage


class TestGameEnums:
    """Tests for game-related enums."""

    def test_game_segment_values(self):
        """Test GameSegment enum values."""
        assert GameSegment.EARLY_GAME.value == "early_game"
        assert GameSegment.LATE_GAME.value == "late_game"
        assert GameSegment.OVERTIME.value == "overtime"

    def test_game_situation_values(self):
        """Test GameSituation enum values."""
        assert GameSituation.EVEN_STRENGTH.value == "5v5"
        assert GameSituation.POWER_PLAY_HOME.value == "5v4_home"

    def test_simulation_mode_values(self):
        """Test SimulationMode enum values."""
        assert SimulationMode.SINGLE_GAME.value == "single_game"
        assert SimulationMode.SERIES.value == "series"
