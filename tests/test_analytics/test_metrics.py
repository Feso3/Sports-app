"""
Tests for Metrics Module

Tests for statistical calculations including xG, Corsi, and Fenwick.
"""

import pytest

from src.analytics.metrics import (
    CorsiStats,
    ExpectedGoalsStats,
    MetricsCalculator,
    ZoneMetrics,
)


class TestCorsiStats:
    """Tests for CorsiStats dataclass."""

    def test_corsi_percentage_calculation(self):
        """Test Corsi percentage calculation."""
        stats = CorsiStats(corsi_for=60, corsi_against=40)
        assert stats.corsi_percentage == pytest.approx(0.6)

    def test_corsi_percentage_zero_total(self):
        """Test Corsi percentage with zero total."""
        stats = CorsiStats(corsi_for=0, corsi_against=0)
        assert stats.corsi_percentage == 0.5

    def test_fenwick_calculation(self):
        """Test Fenwick calculation."""
        stats = CorsiStats(
            goals_for=3,
            shots_for=20,
            missed_for=5,
            goals_against=2,
            shots_against=15,
            missed_against=4,
        )
        assert stats.fenwick_for == 28  # 3 + 20 + 5
        assert stats.fenwick_against == 21  # 2 + 15 + 4

    def test_pdo_calculation(self):
        """Test PDO calculation."""
        stats = CorsiStats(
            goals_for=10,
            shots_for=100,
            goals_against=8,
            shots_against=100,
        )
        # Shooting % = 10/100 = 0.1
        # Save % = 1 - 8/100 = 0.92
        # PDO = 0.1 + 0.92 = 1.02
        assert stats.pdo == pytest.approx(1.02)

    def test_per_60_rates(self):
        """Test per-60 minute rate calculations."""
        stats = CorsiStats(
            corsi_for=30,
            corsi_against=25,
            time_on_ice_seconds=1200,  # 20 minutes
        )
        # CF/60 = 30 / (1200/3600) = 30 / 0.333 = 90
        assert stats.corsi_for_per_60 == pytest.approx(90.0)


class TestExpectedGoalsStats:
    """Tests for ExpectedGoalsStats dataclass."""

    def test_xg_percentage(self):
        """Test xG percentage calculation."""
        stats = ExpectedGoalsStats(xg_for=2.5, xg_against=1.5)
        assert stats.xg_percentage == pytest.approx(0.625)

    def test_goals_above_expected(self):
        """Test goals above expected calculation."""
        stats = ExpectedGoalsStats(xg_for=2.0, goals_for=3)
        assert stats.goals_above_expected == pytest.approx(1.0)

    def test_goals_saved_above_expected(self):
        """Test goals saved above expected calculation."""
        stats = ExpectedGoalsStats(xg_against=3.0, goals_against=2)
        assert stats.goals_saved_above_expected == pytest.approx(1.0)


class TestMetricsCalculator:
    """Tests for MetricsCalculator class."""

    @pytest.fixture
    def calculator(self):
        """Create a metrics calculator instance."""
        return MetricsCalculator()

    def test_shot_xg_close_range(self, calculator):
        """Test xG calculation for close-range shot."""
        xg = calculator.calculate_shot_xg(x=85, y=0)
        assert xg > 0.15  # Should be high danger

    def test_shot_xg_long_range(self, calculator):
        """Test xG calculation for long-range shot."""
        xg = calculator.calculate_shot_xg(x=30, y=0)
        assert xg < 0.05  # Should be low danger

    def test_shot_xg_bad_angle(self, calculator):
        """Test xG calculation for bad angle shot."""
        xg = calculator.calculate_shot_xg(x=80, y=40)
        # Bad angle should reduce xG
        xg_straight = calculator.calculate_shot_xg(x=80, y=0)
        assert xg < xg_straight

    def test_shot_type_modifier(self, calculator):
        """Test shot type modifiers."""
        base_xg = calculator.calculate_shot_xg(x=75, y=0)
        deflection_xg = calculator.calculate_shot_xg(x=75, y=0, shot_type="deflection")
        assert deflection_xg > base_xg  # Deflection has higher xG

    def test_rebound_modifier(self, calculator):
        """Test rebound modifier increases xG."""
        base_xg = calculator.calculate_shot_xg(x=80, y=0)
        rebound_xg = calculator.calculate_shot_xg(x=80, y=0, is_rebound=True)
        assert rebound_xg > base_xg

    def test_process_shot_attempt_goal(self, calculator):
        """Test processing a goal."""
        xg = calculator.process_shot_attempt(
            event_type="goal",
            team_id=1,
            opponent_id=2,
            player_id=100,
            x=80,
            y=5,
        )

        player_corsi = calculator.get_player_corsi(100)
        team_corsi = calculator.get_team_corsi(1)

        assert player_corsi is not None
        assert player_corsi.goals_for == 1
        assert player_corsi.corsi_for == 1

        assert team_corsi is not None
        assert team_corsi.goals_for == 1

    def test_process_shot_attempt_blocked(self, calculator):
        """Test processing a blocked shot."""
        calculator.process_shot_attempt(
            event_type="blocked",
            team_id=1,
            opponent_id=2,
            player_id=100,
            x=70,
            y=10,
        )

        player_corsi = calculator.get_player_corsi(100)
        team_corsi = calculator.get_team_corsi(1)
        opp_corsi = calculator.get_team_corsi(2)

        # Blocked shot counts for Corsi but not xG
        assert player_corsi.corsi_for == 1
        assert player_corsi.blocked_against == 1

        # Opponent gets credit for block
        assert opp_corsi.blocked_for == 1

    def test_player_summary(self, calculator):
        """Test player summary calculation."""
        # Process some events
        for _ in range(5):
            calculator.process_shot_attempt(
                event_type="shot",
                team_id=1,
                opponent_id=2,
                player_id=100,
                x=75,
                y=0,
            )

        calculator.process_shot_attempt(
            event_type="goal",
            team_id=1,
            opponent_id=2,
            player_id=100,
            x=80,
            y=5,
        )

        summary = calculator.calculate_player_summary(100)

        assert summary["player_id"] == 100
        assert summary["corsi"]["cf"] == 6
        assert summary["xg"]["xgf"] > 0

    def test_reset(self, calculator):
        """Test reset clears all data."""
        calculator.process_shot_attempt(
            event_type="goal",
            team_id=1,
            opponent_id=2,
            player_id=100,
        )

        calculator.reset()

        assert calculator.get_player_corsi(100) is None
        assert calculator.get_team_corsi(1) is None
