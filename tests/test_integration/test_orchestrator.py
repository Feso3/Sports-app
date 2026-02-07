"""
Integration tests for Orchestrator service.

Tests the complete prediction workflow with mocked dependencies.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from simulation.models import (
    MatchupAnalysis,
    ScoreDistribution,
    SimulationConfig,
    SimulationResult,
)
from src.models.player import Player, PlayerPosition, PlayerStats
from src.models.team import Team, TeamRoster, TeamStats
from src.service.data_loader import CacheStatus, DataLoader
from src.service.db_enrichment import DBEnrichment, EnrichmentSummary
from src.service.orchestrator import (
    Orchestrator,
    PredictionOptions,
    PredictionResult,
    TeamInfo,
)


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_data_loader():
    """Create a mock data loader."""
    loader = MagicMock(spec=DataLoader)

    # Mock get_available_teams
    loader.get_available_teams.return_value = [
        {
            "team_id": 10,
            "name": "Toronto Maple Leafs",
            "abbreviation": "TOR",
            "division": "Atlantic",
            "conference": "Eastern",
        },
        {
            "team_id": 6,
            "name": "Boston Bruins",
            "abbreviation": "BOS",
            "division": "Atlantic",
            "conference": "Eastern",
        },
    ]

    # Mock load_team
    def mock_load_team(team_id=None, team_abbrev=None):
        if team_id == 10 or team_abbrev == "TOR":
            return Team(
                team_id=10,
                name="Toronto Maple Leafs",
                abbreviation="TOR",
                division="Atlantic",
                conference="Eastern",
                roster=TeamRoster(
                    forwards=[8478402, 8479318, 8480012],
                    defensemen=[8479325, 8480069],
                    goalies=[8479361],
                ),
                current_season_stats=TeamStats(games_played=20),
            )
        elif team_id == 6 or team_abbrev == "BOS":
            return Team(
                team_id=6,
                name="Boston Bruins",
                abbreviation="BOS",
                division="Atlantic",
                conference="Eastern",
                roster=TeamRoster(
                    forwards=[8478498, 8479326, 8480013],
                    defensemen=[8479026, 8480070],
                    goalies=[8479973],
                ),
                current_season_stats=TeamStats(games_played=20),
            )
        raise ValueError(f"Team not found: {team_id or team_abbrev}")

    loader.load_team.side_effect = mock_load_team

    # Mock load_team_players
    def mock_load_players(team):
        players = {}
        for pid in team.roster.all_players:
            players[pid] = Player(
                player_id=pid,
                full_name=f"Player {pid}",
                position=PlayerPosition.CENTER,
                current_team_id=team.team_id,
                career_stats=PlayerStats(games_played=50, goals=20, assists=30),
            )
        return players

    loader.load_team_players.side_effect = mock_load_players

    # Mock cache status
    loader.get_cache_status.return_value = CacheStatus(teams_cached=2, players_cached=12)

    loader.close = MagicMock()

    return loader


@pytest.fixture
def mock_db_enrichment():
    """Create a mock DB enrichment service."""
    enrichment = MagicMock(spec=DBEnrichment)

    # Mock enrich_all to return a summary with plausible data
    enrichment.enrich_all.return_value = EnrichmentSummary(
        season=20252026,
        season_phase="mid_season",
        home_team_stats_loaded=True,
        away_team_stats_loaded=True,
        home_lines_built=4,
        away_lines_built=4,
        home_defense_pairs_built=3,
        away_defense_pairs_built=3,
        home_goalie_set=True,
        away_goalie_set=True,
        players_enriched=12,
        players_with_matchup_data=6,
        players_with_momentum=8,
    )
    return enrichment


@pytest.fixture
def orchestrator(mock_data_loader, mock_db_enrichment):
    """Create an Orchestrator with mocked dependencies."""
    orch = Orchestrator(data_loader=mock_data_loader, db_enrichment=mock_db_enrichment)
    yield orch
    orch.close()


class TestOrchestrator:
    """Tests for Orchestrator class."""

    def test_get_available_teams(self, orchestrator):
        """Test getting available teams."""
        teams = orchestrator.get_available_teams()

        assert len(teams) == 2
        assert all(isinstance(t, TeamInfo) for t in teams)
        assert teams[0].name == "Toronto Maple Leafs"

    def test_predict_game_by_id(self, orchestrator):
        """Test running a prediction by team IDs."""
        result = orchestrator.predict_game(
            home_team_id=10,
            away_team_id=6,
            options=PredictionOptions(iterations=100),  # Low for speed
        )

        assert isinstance(result, PredictionResult)
        assert result.home_team.name == "Toronto Maple Leafs"
        assert result.away_team.name == "Boston Bruins"
        assert result.simulation_result is not None
        assert result.prediction is not None
        assert result.report is not None
        assert len(result.report) > 0

    def test_predict_game_by_abbreviation(self, orchestrator):
        """Test running a prediction by team abbreviations."""
        result = orchestrator.predict_game(
            home_team_abbrev="TOR",
            away_team_abbrev="BOS",
            options=PredictionOptions(quick_mode=True),
        )

        assert isinstance(result, PredictionResult)
        assert result.home_team.abbreviation == "TOR"
        assert result.away_team.abbreviation == "BOS"

    def test_predict_by_abbreviation_convenience(self, orchestrator):
        """Test the convenience method for abbreviation-based prediction."""
        result = orchestrator.predict_by_abbreviation("TOR", "BOS", quick=True)

        assert isinstance(result, PredictionResult)
        assert result.home_team.name == "Toronto Maple Leafs"

    def test_get_quick_prediction(self, orchestrator):
        """Test getting a quick dictionary-based prediction."""
        result = orchestrator.get_quick_prediction("TOR", "BOS")

        assert isinstance(result, dict)
        assert "home_team" in result
        assert "away_team" in result
        assert "home_win_probability" in result
        assert "predicted_winner" in result
        assert "confidence" in result

    def test_prediction_options_quick_mode(self):
        """Test that quick mode sets lower iterations."""
        options = PredictionOptions(quick_mode=True)
        assert options.iterations == 1000

    def test_prediction_options_default(self):
        """Test default prediction options."""
        options = PredictionOptions()
        assert options.iterations == 10000
        assert options.use_synergy is True
        assert options.use_clutch is True
        assert options.use_fatigue is True

    def test_get_cache_status(self, orchestrator):
        """Test getting cache status through orchestrator."""
        status = orchestrator.get_cache_status()

        assert isinstance(status, CacheStatus)
        assert status.teams_cached == 2

    def test_clear_cache(self, orchestrator, mock_data_loader):
        """Test clearing cache through orchestrator."""
        orchestrator.clear_cache()

        mock_data_loader.clear_cache.assert_called_once()

    def test_refresh_data(self, orchestrator, mock_data_loader):
        """Test refreshing team data."""
        orchestrator.refresh_data(team_id=10)

        mock_data_loader.refresh_team_data.assert_called_once_with(
            team_id=10, team_abbrev=None
        )

    def test_context_manager(self, mock_data_loader):
        """Test context manager usage."""
        with Orchestrator(data_loader=mock_data_loader) as orch:
            teams = orch.get_available_teams()
            assert len(teams) == 2

        mock_data_loader.close.assert_called_once()

    def test_simulation_result_structure(self, orchestrator):
        """Test that simulation result has expected structure."""
        result = orchestrator.predict_game(
            home_team_id=10,
            away_team_id=6,
            options=PredictionOptions(iterations=100),
        )

        sim_result = result.simulation_result

        # Check simulation result structure
        assert hasattr(sim_result, "total_iterations")
        assert hasattr(sim_result, "home_wins")
        assert hasattr(sim_result, "away_wins")
        assert hasattr(sim_result, "home_win_probability")
        assert hasattr(sim_result, "score_distribution")

        # Check prediction structure
        pred = result.prediction
        assert hasattr(pred, "home_team_name")
        assert hasattr(pred, "away_team_name")
        assert hasattr(pred, "win_probability")
        assert hasattr(pred, "predicted_winner_name")
        assert hasattr(pred, "most_likely_score")

    def test_players_loaded_count(self, orchestrator):
        """Test that players are loaded and counted correctly."""
        result = orchestrator.predict_game(
            home_team_id=10,
            away_team_id=6,
            options=PredictionOptions(iterations=100),
        )

        # Both teams have 6 players each in the mock
        assert result.players_loaded == 12


class TestTeamInfo:
    """Tests for TeamInfo dataclass."""

    def test_from_dict(self):
        """Test creating TeamInfo from dictionary."""
        data = {
            "team_id": 10,
            "name": "Toronto Maple Leafs",
            "abbreviation": "TOR",
            "division": "Atlantic",
            "conference": "Eastern",
        }

        team = TeamInfo.from_dict(data)

        assert team.team_id == 10
        assert team.name == "Toronto Maple Leafs"
        assert team.abbreviation == "TOR"
        assert team.division == "Atlantic"
        assert team.conference == "Eastern"

    def test_from_dict_minimal(self):
        """Test creating TeamInfo with minimal data."""
        data = {
            "team_id": 1,
            "name": "Test Team",
            "abbreviation": "TST",
        }

        team = TeamInfo.from_dict(data)

        assert team.team_id == 1
        assert team.division == ""
        assert team.conference == ""


class TestPredictionOptions:
    """Tests for PredictionOptions dataclass."""

    def test_default_values(self):
        """Test default option values."""
        options = PredictionOptions()

        assert options.iterations == 10000
        assert options.use_synergy is True
        assert options.use_clutch is True
        assert options.use_fatigue is True
        assert options.quick_mode is False

    def test_quick_mode_overrides_iterations(self):
        """Test that quick mode overrides iterations."""
        options = PredictionOptions(iterations=50000, quick_mode=True)

        # quick_mode should override iterations in __post_init__
        assert options.iterations == 1000

    def test_custom_iterations(self):
        """Test setting custom iteration count."""
        options = PredictionOptions(iterations=25000)

        assert options.iterations == 25000
