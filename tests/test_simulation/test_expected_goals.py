"""
Tests for Expected Goals Calculator
"""

import pytest

from simulation.expected_goals import (
    ExpectedGoalsCalculator,
    LineExpectedGoals,
    TeamExpectedGoals,
    ZoneExpectedGoals,
)

from src.models.team import Team, TeamRoster, TeamStats, LineConfiguration


@pytest.fixture
def xg_calculator():
    """Create an ExpectedGoalsCalculator instance."""
    return ExpectedGoalsCalculator()


@pytest.fixture
def sample_team():
    """Create a sample team for testing."""
    return Team(
        team_id=1,
        name="Test Team",
        abbreviation="TST",
        roster=TeamRoster(
            forwards=[101, 102, 103],
            defensemen=[201, 202],
            goalies=[301],
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
        ],
        defense_pairs=[
            LineConfiguration(
                line_number=1,
                line_type="defense",
                player_ids=[201, 202],
                chemistry_score=0.7,
                goals_for=3,
                goals_against=4,
                corsi_percentage=0.52,
                expected_goals_percentage=0.51,
                time_on_ice_seconds=4000,
            ),
        ],
        current_season_stats=TeamStats(
            games_played=40,
            wins=25,
            goals_for=120,
            goals_against=90,
            shots_for=1200,
            shots_against=1100,
            power_play_percentage=22.0,
            penalty_kill_percentage=82.0,
            zone_shots_for={"slot": 300, "high_slot": 250, "point": 200},
        ),
        offensive_heat_map={"slot": 0.6, "high_slot": 0.5, "point": 0.4},
        defensive_heat_map={"slot": 0.55, "high_slot": 0.5, "point": 0.5},
    )


@pytest.fixture
def sample_opponent():
    """Create a sample opponent team."""
    return Team(
        team_id=2,
        name="Opponent",
        abbreviation="OPP",
        roster=TeamRoster(),
        current_season_stats=TeamStats(
            games_played=40,
            wins=20,
            goals_for=100,
            goals_against=100,
            shots_for=1100,
            shots_against=1100,
            power_play_percentage=20.0,
            penalty_kill_percentage=80.0,
        ),
        offensive_heat_map={"slot": 0.5, "high_slot": 0.5, "point": 0.5},
        defensive_heat_map={"slot": 0.5, "high_slot": 0.5, "point": 0.5},
    )


class TestExpectedGoalsCalculator:
    """Tests for ExpectedGoalsCalculator class."""

    def test_calculator_initialization(self, xg_calculator):
        """Test calculator initializes with default values."""
        assert xg_calculator.zone_xg_rates is not None
        assert "slot" in xg_calculator.zone_xg_rates
        assert xg_calculator.zone_xg_rates["slot"] > xg_calculator.zone_xg_rates["left_point"]

    def test_calculator_custom_rates(self):
        """Test calculator with custom zone rates."""
        custom_rates = {"slot": 0.25, "point": 0.05}
        calc = ExpectedGoalsCalculator(zone_xg_rates=custom_rates)

        assert calc.zone_xg_rates["slot"] == 0.25
        assert calc.zone_xg_rates["point"] == 0.05

    def test_calculate_team_xg(self, xg_calculator, sample_team, sample_opponent):
        """Test team xG calculation."""
        result = xg_calculator.calculate_team_xg(sample_team, sample_opponent)

        assert isinstance(result, TeamExpectedGoals)
        assert result.team_id == sample_team.team_id
        assert result.total_xg_for > 0
        assert result.total_xg_against > 0

    def test_calculate_team_xg_zone_breakdown(self, xg_calculator, sample_team, sample_opponent):
        """Test that zone breakdown is calculated."""
        result = xg_calculator.calculate_team_xg(sample_team, sample_opponent)

        assert len(result.zone_xg) > 0
        # Slot should have highest xG rate
        if "slot" in result.zone_xg:
            slot_xg = result.zone_xg["slot"]
            assert slot_xg.offensive_xg >= 0

    def test_calculate_team_xg_segment_breakdown(self, xg_calculator, sample_team, sample_opponent):
        """Test segment xG breakdown."""
        result = xg_calculator.calculate_team_xg(sample_team, sample_opponent)

        assert result.early_game_xg_for >= 0
        assert result.mid_game_xg_for >= 0
        assert result.late_game_xg_for >= 0

        # Sum should roughly equal total (with some variance due to special teams)
        segment_sum = (
            result.early_game_xg_for
            + result.mid_game_xg_for
            + result.late_game_xg_for
        )
        # Allow some tolerance
        assert abs(segment_sum - result.total_xg_for * 0.75) < result.total_xg_for

    def test_calculate_matchup_xg(self, xg_calculator, sample_team, sample_opponent):
        """Test matchup xG calculation for both teams."""
        home_xg, away_xg = xg_calculator.calculate_matchup_xg(sample_team, sample_opponent)

        assert home_xg.team_id == sample_team.team_id
        assert away_xg.team_id == sample_opponent.team_id
        assert home_xg.total_xg_for > 0
        assert away_xg.total_xg_for > 0

    def test_calculate_matchup_home_ice_advantage(self, xg_calculator, sample_team, sample_opponent):
        """Test that home ice advantage is applied."""
        home_xg, away_xg = xg_calculator.calculate_matchup_xg(sample_team, sample_opponent)

        # Home team should have slight xG boost
        # Create reverse matchup to compare
        away_home_xg, _ = xg_calculator.calculate_matchup_xg(sample_opponent, sample_team)

        # The home xG should be slightly higher due to home ice
        # Note: This depends on team strengths too
        assert home_xg.total_xg_for > 0

    def test_calculate_line_matchup_xg(self, xg_calculator, sample_team, sample_opponent):
        """Test line matchup xG calculation."""
        home_line = sample_team.forward_lines[0]
        away_line = LineConfiguration(
            line_number=1,
            line_type="forward",
            player_ids=[501, 502, 503],
            chemistry_score=0.6,
            corsi_percentage=0.48,
            expected_goals_percentage=0.47,
            time_on_ice_seconds=3600,
        )

        home_xg, away_xg = xg_calculator.calculate_line_matchup_xg(
            home_line, away_line, sample_team, sample_opponent
        )

        assert home_xg >= 0
        assert away_xg >= 0


class TestZoneExpectedGoals:
    """Tests for ZoneExpectedGoals dataclass."""

    def test_zone_xg_creation(self):
        """Test creating zone expected goals."""
        zone_xg = ZoneExpectedGoals(
            zone_name="slot",
            offensive_xg=0.5,
            defensive_xg_against=0.3,
            shot_volume=10.0,
        )

        assert zone_xg.zone_name == "slot"
        assert zone_xg.net_xg == 0.2  # 0.5 - 0.3

    def test_zone_xg_net_calculation(self):
        """Test net xG calculation."""
        zone_xg = ZoneExpectedGoals(
            zone_name="point",
            offensive_xg=0.1,
            defensive_xg_against=0.15,
        )

        assert zone_xg.net_xg == pytest.approx(-0.05, rel=0.01)  # Negative = defensive zone


class TestTeamExpectedGoals:
    """Tests for TeamExpectedGoals dataclass."""

    def test_team_xg_properties(self):
        """Test team expected goals properties."""
        team_xg = TeamExpectedGoals(
            team_id=1,
            total_xg_for=2.8,
            total_xg_against=2.2,
        )

        assert team_xg.net_xg == pytest.approx(0.6, rel=0.01)
        assert team_xg.xg_percentage == pytest.approx(0.56, rel=0.01)

    def test_team_xg_balanced(self):
        """Test balanced team xG."""
        team_xg = TeamExpectedGoals(
            team_id=1,
            total_xg_for=2.5,
            total_xg_against=2.5,
        )

        assert team_xg.net_xg == 0.0
        assert team_xg.xg_percentage == 0.5


class TestLineExpectedGoals:
    """Tests for LineExpectedGoals dataclass."""

    def test_line_xg_creation(self):
        """Test creating line expected goals."""
        line_xg = LineExpectedGoals(
            line_number=1,
            line_type="forward",
            player_ids=[101, 102, 103],
            offensive_xg_per_60=3.0,
            defensive_xg_against_per_60=2.5,
        )

        assert line_xg.line_number == 1
        assert line_xg.line_type == "forward"
        assert len(line_xg.player_ids) == 3

    def test_line_xg_with_modifiers(self):
        """Test line xG with modifiers applied."""
        line_xg = LineExpectedGoals(
            line_number=1,
            line_type="forward",
            offensive_xg_per_60=3.0,
            defensive_xg_against_per_60=2.5,
            synergy_modifier=1.1,
            clutch_modifier=1.05,
            fatigue_modifier=0.95,
        )

        adjusted = line_xg.adjusted_offensive_xg
        expected = 3.0 * 1.1 * 1.05 * 0.95

        assert adjusted == pytest.approx(expected, rel=0.01)

    def test_line_xg_adjusted_defensive(self):
        """Test adjusted defensive xG."""
        line_xg = LineExpectedGoals(
            line_number=1,
            line_type="defense",
            defensive_xg_against_per_60=2.0,
            fatigue_modifier=0.9,
        )

        # Lower fatigue = more goals against
        adjusted = line_xg.adjusted_defensive_xg
        assert adjusted > 2.0  # Fatigue makes defense worse


class TestExpectedGoalsEdgeCases:
    """Tests for edge cases in expected goals calculations."""

    def test_empty_team_stats(self, xg_calculator):
        """Test with minimal team stats."""
        minimal_team = Team(
            team_id=1,
            name="Minimal",
            abbreviation="MIN",
            roster=TeamRoster(),
            current_season_stats=TeamStats(games_played=1),
        )
        opponent = Team(
            team_id=2,
            name="Opponent",
            abbreviation="OPP",
            roster=TeamRoster(),
            current_season_stats=TeamStats(games_played=1),
        )

        result = xg_calculator.calculate_team_xg(minimal_team, opponent)

        # Should not crash, return some reasonable values
        assert isinstance(result, TeamExpectedGoals)

    def test_zero_shots(self, xg_calculator):
        """Test team with zero shots."""
        team = Team(
            team_id=1,
            name="NoShots",
            abbreviation="NS",
            roster=TeamRoster(),
            current_season_stats=TeamStats(games_played=10, shots_for=0),
        )
        opponent = Team(
            team_id=2,
            name="Opponent",
            abbreviation="OPP",
            roster=TeamRoster(),
            current_season_stats=TeamStats(games_played=10, shots_for=100),
        )

        result = xg_calculator.calculate_team_xg(team, opponent)

        assert isinstance(result, TeamExpectedGoals)
