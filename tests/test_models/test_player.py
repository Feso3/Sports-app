"""
Tests for Player Model

Tests for player data model and statistics.
"""

import pytest


class TestPlayerPosition:
    """Tests for PlayerPosition enum."""

    def test_position_values(self):
        """Test position enum values."""
        from src.models.player import PlayerPosition

        assert PlayerPosition.CENTER.value == "C"
        assert PlayerPosition.LEFT_WING.value == "LW"
        assert PlayerPosition.RIGHT_WING.value == "RW"
        assert PlayerPosition.DEFENSEMAN.value == "D"
        assert PlayerPosition.GOALIE.value == "G"


class TestPlayer:
    """Tests for Player model."""

    def test_player_creation(self, sample_player_profile):
        """Test creating a player from profile data."""
        from src.models.player import Player, PlayerPosition

        player = Player(
            player_id=sample_player_profile["player_id"],
            full_name=sample_player_profile["full_name"],
            first_name=sample_player_profile["first_name"],
            last_name=sample_player_profile["last_name"],
            position=PlayerPosition.CENTER,
            position_code="C",
            current_team_id=sample_player_profile["current_team_id"],
            current_team_abbrev=sample_player_profile["current_team_abbrev"],
        )

        assert player.player_id == 8478402
        assert player.full_name == "Connor McDavid"
        assert player.is_forward is True
        assert player.is_goalie is False
        assert player.is_defenseman is False

    def test_player_is_forward(self):
        """Test forward position detection."""
        from src.models.player import Player, PlayerPosition

        center = Player(
            player_id=1,
            full_name="Test Center",
            position=PlayerPosition.CENTER,
        )
        assert center.is_forward is True

        lw = Player(
            player_id=2,
            full_name="Test LW",
            position=PlayerPosition.LEFT_WING,
        )
        assert lw.is_forward is True

        rw = Player(
            player_id=3,
            full_name="Test RW",
            position=PlayerPosition.RIGHT_WING,
        )
        assert rw.is_forward is True

    def test_player_is_defenseman(self):
        """Test defenseman position detection."""
        from src.models.player import Player, PlayerPosition

        defenseman = Player(
            player_id=1,
            full_name="Test D",
            position=PlayerPosition.DEFENSEMAN,
        )
        assert defenseman.is_defenseman is True
        assert defenseman.is_forward is False

    def test_player_is_goalie(self):
        """Test goalie position detection."""
        from src.models.player import Player, PlayerPosition

        goalie = Player(
            player_id=1,
            full_name="Test G",
            position=PlayerPosition.GOALIE,
        )
        assert goalie.is_goalie is True
        assert goalie.is_forward is False
        assert goalie.is_defenseman is False


class TestPlayerStats:
    """Tests for PlayerStats model."""

    def test_player_stats_defaults(self):
        """Test default values for player stats."""
        from src.models.player import PlayerStats

        stats = PlayerStats()

        assert stats.games_played == 0
        assert stats.goals == 0
        assert stats.assists == 0
        assert stats.points == 0
        assert stats.shooting_percentage == 0.0

    def test_player_stats_zone_stats(self):
        """Test zone stats in player stats."""
        from src.models.player import PlayerStats, ZoneStats

        stats = PlayerStats()
        stats.zone_stats["slot"] = ZoneStats(
            zone_name="slot",
            shots=20,
            goals=4,
            shooting_percentage=0.20,
        )

        assert "slot" in stats.zone_stats
        assert stats.zone_stats["slot"].shots == 20


class TestZoneStats:
    """Tests for ZoneStats model."""

    def test_zone_stats_creation(self):
        """Test creating zone stats."""
        from src.models.player import ZoneStats

        zone_stats = ZoneStats(
            zone_name="slot",
            shots=50,
            goals=10,
            shooting_percentage=0.20,
            expected_goals=8.5,
        )

        assert zone_stats.zone_name == "slot"
        assert zone_stats.shots == 50
        assert zone_stats.goals == 10
        assert zone_stats.shooting_percentage == pytest.approx(0.20)
