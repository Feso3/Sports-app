"""
Tests for Zone Analysis Processor

Tests for zone-based aggregation and heat map generation.
"""

import pytest


class TestZoneDefinition:
    """Tests for ZoneDefinition class."""

    def test_zone_contains_point(self):
        """Test point containment check."""
        from src.processors.zone_analysis import ZoneDefinition

        zone = ZoneDefinition(
            name="slot",
            x_min=69,
            x_max=89,
            y_min=-22,
            y_max=22,
            danger_level="high",
            expected_shooting_pct=0.15,
        )

        # Point inside zone
        assert zone.contains_point(75, 0) is True
        assert zone.contains_point(80, 10) is True

        # Point outside zone
        assert zone.contains_point(50, 0) is False
        assert zone.contains_point(75, 30) is False


class TestZoneAnalyzer:
    """Tests for ZoneAnalyzer class."""

    def test_identify_zone_slot(self):
        """Test zone identification for slot area."""
        from src.processors.zone_analysis import ZoneAnalyzer

        analyzer = ZoneAnalyzer.__new__(ZoneAnalyzer)
        analyzer.config = {
            "zones": {
                "slot": {
                    "x_min": 69,
                    "x_max": 89,
                    "y_min": -22,
                    "y_max": 22,
                    "danger_level": "high",
                    "expected_shooting_pct": 0.15,
                },
            }
        }
        analyzer.zones = analyzer._build_zone_definitions()

        # Coordinates in the slot
        zone = analyzer.identify_zone(75.0, 5.0)
        assert zone == "slot"

    def test_identify_zone_none(self):
        """Test zone identification with None coordinates."""
        from src.processors.zone_analysis import ZoneAnalyzer

        analyzer = ZoneAnalyzer.__new__(ZoneAnalyzer)
        analyzer.config = {"zones": {}}
        analyzer.zones = {}

        assert analyzer.identify_zone(None, None) is None
        assert analyzer.identify_zone(50.0, None) is None

    def test_process_shot(self, sample_shot_data):
        """Test processing a single shot."""
        from src.processors.zone_analysis import ZoneAnalyzer

        analyzer = ZoneAnalyzer.__new__(ZoneAnalyzer)
        analyzer.config = {
            "zones": {
                "slot": {
                    "x_min": 69,
                    "x_max": 89,
                    "y_min": -22,
                    "y_max": 22,
                    "danger_level": "high",
                    "expected_shooting_pct": 0.15,
                },
            }
        }
        analyzer.zones = analyzer._build_zone_definitions()
        analyzer.player_profiles = {}
        analyzer.team_profiles = {}

        shot = sample_shot_data[0]
        analyzer.process_shot(
            x=shot["x_coord"],
            y=shot["y_coord"],
            is_goal=shot["is_goal"],
            shot_type=shot["shot_type"],
            player_id=shot["shooter_id"],
            player_name=shot["shooter_name"],
            team_id=shot["team_id"],
            team_abbrev=shot["team_abbrev"],
            opponent_team_id=10,
        )

        # Verify player profile updated
        assert shot["shooter_id"] in analyzer.player_profiles
        profile = analyzer.player_profiles[shot["shooter_id"]]
        assert profile.total_shots == 1
        assert profile.total_goals == 1

    def test_player_heat_map_generation(self):
        """Test heat map generation for a player."""
        from src.processors.zone_analysis import PlayerZoneProfile, ZoneStats

        profile = PlayerZoneProfile(
            player_id=8478402,
            player_name="Connor McDavid",
        )
        profile.zone_stats["slot"] = ZoneStats(shots=10, goals=3)
        profile.zone_stats["left_circle"] = ZoneStats(shots=5, goals=1)
        profile.total_shots = 15

        heat_map = profile.get_heat_map()

        assert heat_map["slot"] == pytest.approx(10 / 15)
        assert heat_map["left_circle"] == pytest.approx(5 / 15)

    def test_zone_mismatch_calculation(self):
        """Test zone mismatch calculation between teams."""
        from src.processors.zone_analysis import (
            TeamZoneProfile,
            ZoneAnalyzer,
            ZoneStats,
        )

        analyzer = ZoneAnalyzer.__new__(ZoneAnalyzer)
        analyzer.config = {
            "zones": {
                "slot": {
                    "x_min": 69,
                    "x_max": 89,
                    "y_min": -22,
                    "y_max": 22,
                    "danger_level": "high",
                    "expected_shooting_pct": 0.15,
                },
            }
        }
        analyzer.zones = analyzer._build_zone_definitions()
        analyzer.team_profiles = {}

        # Create team profiles
        offensive_team = TeamZoneProfile(team_id=22, team_abbrev="EDM")
        offensive_team.offensive_zone_stats["slot"] = ZoneStats(shots=100, goals=15)
        offensive_team.total_shots_for = 100

        defensive_team = TeamZoneProfile(team_id=10, team_abbrev="TOR")
        defensive_team.defensive_zone_stats["slot"] = ZoneStats(shots=80, goals=12)
        defensive_team.total_shots_against = 80

        analyzer.team_profiles[22] = offensive_team
        analyzer.team_profiles[10] = defensive_team

        mismatches = analyzer.calculate_zone_mismatch(22, 10)

        # Mismatch should be calculated
        assert "slot" in mismatches
        assert mismatches["slot"] > 0


class TestZoneStats:
    """Tests for ZoneStats class."""

    def test_shooting_percentage_calculation(self):
        """Test shooting percentage update."""
        from src.processors.zone_analysis import ZoneStats

        stats = ZoneStats(shots=20, goals=3)
        stats.update_shooting_percentage()

        assert stats.shooting_percentage == pytest.approx(0.15)

    def test_shooting_percentage_zero_shots(self):
        """Test shooting percentage with zero shots."""
        from src.processors.zone_analysis import ZoneStats

        stats = ZoneStats(shots=0, goals=0)
        stats.update_shooting_percentage()

        assert stats.shooting_percentage == 0.0
