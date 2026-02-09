"""
Pytest Configuration and Fixtures

Shared fixtures for the NHL Player Cards test suite.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def sample_player_profile() -> dict[str, Any]:
    """Sample player profile data for testing."""
    return {
        "player_id": 8478402,
        "full_name": "Connor McDavid",
        "first_name": "Connor",
        "last_name": "McDavid",
        "birth_date": "1997-01-13",
        "birth_city": "Richmond Hill",
        "birth_country": "CAN",
        "height_inches": 73,
        "weight_pounds": 193,
        "position": "C",
        "shoots_catches": "L",
        "current_team_id": 22,
        "current_team_abbrev": "EDM",
        "jersey_number": 97,
        "is_active": True,
    }


@pytest.fixture
def mock_api_client() -> MagicMock:
    """Create a mock NHL API client."""
    client = MagicMock()

    # Mock schedule response
    client.get_schedule.return_value = {
        "games": [
            {"gamePk": 2023020001, "gameType": 2},
            {"gamePk": 2023020002, "gameType": 2},
        ]
    }

    # Mock play-by-play response
    client.get_game_play_by_play.return_value = {
        "plays": [
            {
                "eventId": 1,
                "typeDescKey": "shot-on-goal",
                "periodDescriptor": {"number": 1},
                "timeInPeriod": "05:30",
                "timeRemaining": "14:30",
                "details": {
                    "shootingPlayerId": 8478402,
                    "eventOwnerTeamId": 22,
                    "eventOwnerTeamAbbrev": "EDM",
                    "xCoord": 75.0,
                    "yCoord": 5.0,
                    "shotType": "wrist",
                },
            }
        ]
    }

    # Mock player landing response
    client.get_player_landing.return_value = {
        "playerId": 8478402,
        "firstName": {"default": "Connor"},
        "lastName": {"default": "McDavid"},
        "position": "Center",
        "positionCode": "C",
        "currentTeamId": 22,
        "currentTeamAbbrev": "EDM",
    }

    return client


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create temporary data directory structure."""
    data_dir = tmp_path / "data"
    (data_dir / "raw" / "shots").mkdir(parents=True)
    (data_dir / "raw" / "players").mkdir(parents=True)
    (data_dir / "raw" / "games").mkdir(parents=True)
    (data_dir / "processed" / "player_profiles").mkdir(parents=True)
    (data_dir / "cache").mkdir(parents=True)
    return data_dir
