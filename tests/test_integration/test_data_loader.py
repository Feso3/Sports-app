"""
Integration tests for DataLoader service.

Tests data loading, caching, and offline fallback behavior.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.player import Player, PlayerPosition
from src.models.team import Team, TeamRoster
from src.service.data_loader import CacheStatus, DataLoader


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_api_client():
    """Create a mock NHL API client."""
    client = MagicMock()

    # Mock get_all_teams
    client.get_all_teams.return_value = {
        "teams": [
            {
                "id": 1,
                "name": "New Jersey Devils",
                "abbreviation": "NJD",
                "division": {"name": "Metropolitan"},
                "conference": {"name": "Eastern"},
            },
            {
                "id": 2,
                "name": "New York Islanders",
                "abbreviation": "NYI",
                "division": {"name": "Metropolitan"},
                "conference": {"name": "Eastern"},
            },
            {
                "id": 10,
                "name": "Toronto Maple Leafs",
                "abbreviation": "TOR",
                "division": {"name": "Atlantic"},
                "conference": {"name": "Eastern"},
            },
        ]
    }

    # Mock get_team_roster
    client.get_team_roster.return_value = {
        "forwards": [{"id": 8478402}, {"id": 8479318}, {"id": 8480012}],
        "defensemen": [{"id": 8479325}, {"id": 8480069}],
        "goalies": [{"id": 8479361}],
    }

    # Mock get_player_landing
    client.get_player_landing.return_value = {
        "firstName": {"default": "Auston"},
        "lastName": {"default": "Matthews"},
        "position": "C",
        "currentTeamId": 10,
        "currentTeamAbbrev": "TOR",
        "sweaterNumber": 34,
        "heightInInches": 75,
        "weightInPounds": 208,
        "shootsCatches": "L",
        "birthDate": "1997-09-17",
        "birthCity": {"default": "San Ramon"},
        "birthCountry": "USA",
        "featuredStats": {
            "regularSeason": {
                "career": {
                    "gamesPlayed": 500,
                    "goals": 300,
                    "assists": 250,
                    "points": 550,
                }
            }
        },
    }

    client.close = MagicMock()

    return client


@pytest.fixture
def data_loader(mock_api_client, temp_cache_dir):
    """Create a DataLoader with mocked API client."""
    loader = DataLoader(
        api_client=mock_api_client,
        cache_dir=temp_cache_dir,
    )
    yield loader
    loader.close()


class TestDataLoader:
    """Tests for DataLoader class."""

    def test_get_available_teams(self, data_loader, mock_api_client):
        """Test fetching available teams."""
        teams = data_loader.get_available_teams()

        assert len(teams) == 3
        assert teams[0]["name"] == "New Jersey Devils"
        assert teams[0]["abbreviation"] == "NJD"
        mock_api_client.get_all_teams.assert_called_once()

    def test_get_available_teams_cached(self, data_loader, mock_api_client):
        """Test that teams are cached after first fetch."""
        # First call
        teams1 = data_loader.get_available_teams()
        # Second call should use cache
        teams2 = data_loader.get_available_teams()

        assert teams1 == teams2
        # API should only be called once
        assert mock_api_client.get_all_teams.call_count == 1

    def test_load_team_by_id(self, data_loader, mock_api_client):
        """Test loading a team by ID."""
        team = data_loader.load_team(team_id=10)

        assert isinstance(team, Team)
        assert team.team_id == 10
        assert team.name == "Toronto Maple Leafs"
        assert team.abbreviation == "TOR"

    def test_load_team_by_abbreviation(self, data_loader, mock_api_client):
        """Test loading a team by abbreviation."""
        team = data_loader.load_team(team_abbrev="TOR")

        assert isinstance(team, Team)
        assert team.name == "Toronto Maple Leafs"

    def test_load_team_cached(self, data_loader, mock_api_client):
        """Test that team data is cached."""
        team1 = data_loader.load_team(team_id=10)
        team2 = data_loader.load_team(team_id=10)

        assert team1.team_id == team2.team_id
        # Roster should only be fetched once
        assert mock_api_client.get_team_roster.call_count == 1

    def test_load_roster(self, data_loader, mock_api_client):
        """Test loading team roster."""
        roster = data_loader.load_roster("TOR")

        assert isinstance(roster, TeamRoster)
        assert len(roster.forwards) == 3
        assert len(roster.defensemen) == 2
        assert len(roster.goalies) == 1

    def test_load_player(self, data_loader, mock_api_client):
        """Test loading player data."""
        player = data_loader.load_player(8478402)

        assert isinstance(player, Player)
        assert player.full_name == "Auston Matthews"
        assert player.position == PlayerPosition.CENTER
        assert player.career_stats.goals == 300

    def test_load_player_cached(self, data_loader, mock_api_client):
        """Test that player data is cached."""
        player1 = data_loader.load_player(8478402)
        player2 = data_loader.load_player(8478402)

        assert player1.player_id == player2.player_id
        assert mock_api_client.get_player_landing.call_count == 1

    def test_load_team_players(self, data_loader, mock_api_client):
        """Test loading all players for a team."""
        team = data_loader.load_team(team_id=10)
        players = data_loader.load_team_players(team)

        assert len(players) == 6  # 3 forwards + 2 defense + 1 goalie
        assert all(isinstance(p, Player) for p in players.values())

    def test_get_cache_status(self, data_loader, mock_api_client):
        """Test getting cache status."""
        # Load some data first
        data_loader.get_available_teams()
        data_loader.load_team(team_id=10)

        status = data_loader.get_cache_status()

        assert isinstance(status, CacheStatus)
        assert status.teams_cached >= 1

    def test_clear_cache(self, data_loader, mock_api_client):
        """Test clearing cache."""
        # Load some data
        data_loader.load_team(team_id=10)

        # Clear cache
        data_loader.clear_cache()

        # Should need to fetch again
        data_loader.load_team(team_id=10)
        assert mock_api_client.get_team_roster.call_count == 2

    def test_refresh_team_data(self, data_loader, mock_api_client):
        """Test refreshing team data."""
        # Load initial data
        data_loader.load_team(team_id=10)
        assert mock_api_client.get_team_roster.call_count == 1

        # Refresh
        data_loader.refresh_team_data(team_id=10)
        assert mock_api_client.get_team_roster.call_count == 2

    def test_offline_fallback(self, data_loader, mock_api_client):
        """Test offline mode with cached data."""
        # First, load data successfully
        teams = data_loader.get_available_teams()
        assert len(teams) == 3

        # Simulate offline mode
        mock_api_client.get_all_teams.side_effect = Exception("Network error")

        # Should return cached data
        teams_cached = data_loader.get_available_teams()
        assert len(teams_cached) == 3

    def test_context_manager(self, mock_api_client, temp_cache_dir):
        """Test context manager usage."""
        with DataLoader(api_client=mock_api_client, cache_dir=temp_cache_dir) as loader:
            teams = loader.get_available_teams()
            assert len(teams) == 3

        # Should have closed
        mock_api_client.close.assert_called_once()


class TestCacheStatus:
    """Tests for CacheStatus dataclass."""

    def test_to_dict(self):
        """Test converting cache status to dictionary."""
        status = CacheStatus(
            teams_cached=5,
            players_cached=100,
            cache_size_mb=1.5,
            is_stale=False,
        )

        result = status.to_dict()

        assert result["teams_cached"] == 5
        assert result["players_cached"] == 100
        assert result["cache_size_mb"] == 1.5
        assert result["is_stale"] is False
