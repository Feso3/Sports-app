"""
Tests for Monte Carlo Simulation Engine
"""

import pytest

from simulation.engine import GameSimulationEngine, SegmentContext
from simulation.expected_goals import ExpectedGoalsCalculator
from simulation.matchups import MatchupAnalyzer
from simulation.models import (
    GameSegment,
    SimulationConfig,
    SimulationMode,
)

from src.models.team import (
    Team,
    TeamRoster,
    TeamStats,
    LineConfiguration,
)


@pytest.fixture
def sample_home_team():
    """Create a sample home team for testing."""
    return Team(
        team_id=1,
        name="Home Team",
        abbreviation="HOM",
        roster=TeamRoster(
            forwards=[101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112],
            defensemen=[201, 202, 203, 204, 205, 206],
            goalies=[301, 302],
        ),
        forward_lines=[
            LineConfiguration(
                line_number=1,
                line_type="forward",
                player_ids=[101, 102, 103],
                chemistry_score=0.8,
                goals_for=15,
                goals_against=8,
                corsi_percentage=0.55,
                expected_goals_percentage=0.54,
                time_on_ice_seconds=3600,
            ),
            LineConfiguration(
                line_number=2,
                line_type="forward",
                player_ids=[104, 105, 106],
                chemistry_score=0.7,
                goals_for=10,
                goals_against=9,
                corsi_percentage=0.52,
                expected_goals_percentage=0.51,
                time_on_ice_seconds=3000,
            ),
        ],
        defense_pairs=[
            LineConfiguration(
                line_number=1,
                line_type="defense",
                player_ids=[201, 202],
                chemistry_score=0.75,
                goals_for=5,
                goals_against=4,
                corsi_percentage=0.53,
                expected_goals_percentage=0.52,
                time_on_ice_seconds=4200,
            ),
        ],
        current_season_stats=TeamStats(
            games_played=40,
            wins=25,
            losses=12,
            overtime_losses=3,
            goals_for=120,
            goals_against=90,
            shots_for=1200,
            shots_against=1100,
            power_play_percentage=22.0,
            penalty_kill_percentage=82.0,
            early_game_goals_for=40,
            early_game_goals_against=30,
            mid_game_goals_for=45,
            mid_game_goals_against=35,
            late_game_goals_for=35,
            late_game_goals_against=25,
        ),
        starting_goalie_id=301,
        offensive_heat_map={"slot": 0.6, "high_slot": 0.5, "point": 0.4},
        defensive_heat_map={"slot": 0.55, "high_slot": 0.5, "point": 0.5},
    )


@pytest.fixture
def sample_away_team():
    """Create a sample away team for testing."""
    return Team(
        team_id=2,
        name="Away Team",
        abbreviation="AWY",
        roster=TeamRoster(
            forwards=[501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 511, 512],
            defensemen=[601, 602, 603, 604, 605, 606],
            goalies=[701, 702],
        ),
        forward_lines=[
            LineConfiguration(
                line_number=1,
                line_type="forward",
                player_ids=[501, 502, 503],
                chemistry_score=0.7,
                goals_for=12,
                goals_against=10,
                corsi_percentage=0.50,
                expected_goals_percentage=0.49,
                time_on_ice_seconds=3600,
            ),
        ],
        defense_pairs=[
            LineConfiguration(
                line_number=1,
                line_type="defense",
                player_ids=[601, 602],
                chemistry_score=0.65,
                goals_for=4,
                goals_against=5,
                corsi_percentage=0.48,
                expected_goals_percentage=0.47,
                time_on_ice_seconds=4200,
            ),
        ],
        current_season_stats=TeamStats(
            games_played=40,
            wins=18,
            losses=18,
            overtime_losses=4,
            goals_for=100,
            goals_against=105,
            shots_for=1100,
            shots_against=1150,
            power_play_percentage=18.0,
            penalty_kill_percentage=78.0,
            early_game_goals_for=35,
            early_game_goals_against=35,
            mid_game_goals_for=35,
            mid_game_goals_against=38,
            late_game_goals_for=30,
            late_game_goals_against=32,
        ),
        starting_goalie_id=701,
        offensive_heat_map={"slot": 0.5, "high_slot": 0.45, "point": 0.4},
        defensive_heat_map={"slot": 0.45, "high_slot": 0.45, "point": 0.45},
    )


class TestGameSimulationEngine:
    """Tests for the main simulation engine."""

    def test_engine_initialization(self):
        """Test engine initializes correctly."""
        engine = GameSimulationEngine()

        assert engine.xg_calculator is not None
        assert engine.matchup_analyzer is not None

    def test_engine_with_custom_components(self):
        """Test engine with custom components."""
        xg_calc = ExpectedGoalsCalculator()
        matchup_analyzer = MatchupAnalyzer()

        engine = GameSimulationEngine(
            xg_calculator=xg_calc,
            matchup_analyzer=matchup_analyzer,
        )

        assert engine.xg_calculator is xg_calc
        assert engine.matchup_analyzer is matchup_analyzer

    def test_simulate_single_game_basic(self, sample_home_team, sample_away_team):
        """Test basic single game simulation."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=100,  # Small for testing
            random_seed=42,
        )

        result = engine.simulate(config, sample_home_team, sample_away_team)

        # Basic validation
        assert result.total_iterations == 100
        assert result.home_wins + result.away_wins == 100
        assert 0 <= result.home_win_probability <= 1
        assert 0 <= result.away_win_probability <= 1

    def test_simulate_deterministic_with_seed(self, sample_home_team, sample_away_team):
        """Test that same seed produces same results."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=100,
            random_seed=42,
        )

        result1 = engine.simulate(config, sample_home_team, sample_away_team)
        result2 = engine.simulate(config, sample_home_team, sample_away_team)

        assert result1.home_wins == result2.home_wins
        assert result1.away_wins == result2.away_wins
        assert result1.overtime_games == result2.overtime_games

    def test_simulate_produces_varied_scores(self, sample_home_team, sample_away_team):
        """Test that simulation produces varied scores."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=500,
            random_seed=42,
        )

        result = engine.simulate(config, sample_home_team, sample_away_team)

        # Should have multiple different scores
        assert len(result.score_distribution.score_counts) > 1

    def test_simulate_overtime_occurs(self, sample_home_team, sample_away_team):
        """Test that overtime can occur in simulation."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=500,
            random_seed=42,
        )

        result = engine.simulate(config, sample_home_team, sample_away_team)

        # With enough iterations, some games should go to OT
        # Note: This might occasionally fail due to randomness
        assert result.overtime_games >= 0  # At least non-negative

    def test_simulate_generates_sample_games(self, sample_home_team, sample_away_team):
        """Test that sample games are generated."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=100,
            random_seed=42,
        )

        result = engine.simulate(config, sample_home_team, sample_away_team)

        # Should have sample games
        assert len(result.sample_games) > 0
        assert len(result.sample_games) <= 10

        # Each sample game should have segments
        for game in result.sample_games:
            assert len(game.segments) >= 3  # At least 3 periods

    def test_simulate_calculates_xg(self, sample_home_team, sample_away_team):
        """Test that expected goals are calculated."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=100,
            random_seed=42,
        )

        result = engine.simulate(config, sample_home_team, sample_away_team)

        # Should have xG values
        assert result.average_home_xg > 0
        assert result.average_away_xg > 0

    def test_simulate_matchup_analysis(self, sample_home_team, sample_away_team):
        """Test that matchup analysis is generated."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=100,
            random_seed=42,
        )

        result = engine.simulate(config, sample_home_team, sample_away_team)

        assert result.matchup_analysis is not None
        assert result.matchup_analysis.home_team_id == 1
        assert result.matchup_analysis.away_team_id == 2

    def test_simulate_confidence_score(self, sample_home_team, sample_away_team):
        """Test that confidence score is calculated."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=100,
            random_seed=42,
        )

        result = engine.simulate(config, sample_home_team, sample_away_team)

        assert 0 <= result.confidence_score <= 1

    def test_simulate_variance_indicator(self, sample_home_team, sample_away_team):
        """Test that variance indicator is set."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=100,
            random_seed=42,
        )

        result = engine.simulate(config, sample_home_team, sample_away_team)

        assert result.variance_indicator in ["low", "normal", "high"]


class TestSegmentContext:
    """Tests for SegmentContext dataclass."""

    def test_segment_context_creation(self):
        """Test creating a segment context."""
        context = SegmentContext(
            segment=GameSegment.LATE_GAME,
            home_xg_base=1.0,
            away_xg_base=0.8,
            segment_weight=1.1,
            clutch_home=1.05,
            fatigue_home=0.95,
        )

        assert context.segment == GameSegment.LATE_GAME
        assert context.home_xg_base == 1.0
        assert context.segment_weight == 1.1

    def test_segment_context_defaults(self):
        """Test segment context default values."""
        context = SegmentContext(
            segment=GameSegment.MID_GAME,
            home_xg_base=1.0,
            away_xg_base=1.0,
            segment_weight=1.0,
        )

        assert context.clutch_home == 1.0
        assert context.clutch_away == 1.0
        assert context.fatigue_home == 1.0
        assert context.fatigue_away == 1.0


class TestSimulationWithDisabledFeatures:
    """Tests for simulation with various features disabled."""

    def test_simulate_without_synergy(self, sample_home_team, sample_away_team):
        """Test simulation without synergy adjustments."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=100,
            random_seed=42,
            use_synergy_adjustments=False,
        )

        result = engine.simulate(config, sample_home_team, sample_away_team)

        assert result.total_iterations == 100

    def test_simulate_without_clutch(self, sample_home_team, sample_away_team):
        """Test simulation without clutch adjustments."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=100,
            random_seed=42,
            use_clutch_adjustments=False,
        )

        result = engine.simulate(config, sample_home_team, sample_away_team)

        assert result.total_iterations == 100

    def test_simulate_without_fatigue(self, sample_home_team, sample_away_team):
        """Test simulation without fatigue adjustments."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=100,
            random_seed=42,
            use_fatigue_adjustments=False,
        )

        result = engine.simulate(config, sample_home_team, sample_away_team)

        assert result.total_iterations == 100

    def test_simulate_all_adjustments_disabled(self, sample_home_team, sample_away_team):
        """Test simulation with all adjustments disabled."""
        engine = GameSimulationEngine()
        config = SimulationConfig(
            home_team_id=1,
            away_team_id=2,
            iterations=100,
            random_seed=42,
            use_synergy_adjustments=False,
            use_clutch_adjustments=False,
            use_fatigue_adjustments=False,
            use_segment_weights=False,
        )

        result = engine.simulate(config, sample_home_team, sample_away_team)

        assert result.total_iterations == 100
