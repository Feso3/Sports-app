"""
Pytest Configuration and Fixtures

Shared fixtures and configuration for the NHL Analytics test suite.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def sample_shot_data() -> list[dict[str, Any]]:
    """Sample shot data for testing."""
    return [
        {
            "game_id": "2023020001",
            "event_id": 1,
            "period": 1,
            "time_in_period": "05:30",
            "time_remaining": "14:30",
            "shooter_id": 8478402,
            "shooter_name": "Connor McDavid",
            "team_id": 22,
            "team_abbrev": "EDM",
            "shot_type": "wrist",
            "x_coord": 75.0,
            "y_coord": 5.0,
            "distance": 15.0,
            "is_goal": True,
            "goalie_id": 8477424,
            "strength": "even",
            "empty_net": False,
        },
        {
            "game_id": "2023020001",
            "event_id": 2,
            "period": 1,
            "time_in_period": "08:45",
            "time_remaining": "11:15",
            "shooter_id": 8478402,
            "shooter_name": "Connor McDavid",
            "team_id": 22,
            "team_abbrev": "EDM",
            "shot_type": "snap",
            "x_coord": 60.0,
            "y_coord": -15.0,
            "distance": 25.0,
            "is_goal": False,
            "goalie_id": 8477424,
            "strength": "even",
            "empty_net": False,
        },
        {
            "game_id": "2023020001",
            "event_id": 3,
            "period": 2,
            "time_in_period": "12:00",
            "time_remaining": "08:00",
            "shooter_id": 8479318,
            "shooter_name": "Auston Matthews",
            "team_id": 10,
            "team_abbrev": "TOR",
            "shot_type": "wrist",
            "x_coord": 82.0,
            "y_coord": 0.0,
            "distance": 8.0,
            "is_goal": True,
            "goalie_id": 8477346,
            "strength": "pp",
            "empty_net": False,
        },
    ]


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
        "nationality": "CAN",
        "height_inches": 73,
        "weight_pounds": 193,
        "position": "C",
        "position_code": "C",
        "shoots_catches": "L",
        "current_team_id": 22,
        "current_team_abbrev": "EDM",
        "jersey_number": 97,
        "is_active": True,
        "rookie": False,
        "draft_year": 2015,
        "draft_round": 1,
        "draft_pick": 1,
    }


@pytest.fixture
def sample_game_events() -> list[dict[str, Any]]:
    """Sample game events for testing segment analysis."""
    return [
        {
            "event_id": 1,
            "event_type": "faceoff",
            "period": 1,
            "time_in_period": "00:00",
            "team_id": 22,
            "team_abbrev": "EDM",
            "winner_team_id": 22,
        },
        {
            "event_id": 2,
            "event_type": "shot-on-goal",
            "period": 1,
            "time_in_period": "02:30",
            "team_id": 22,
            "team_abbrev": "EDM",
            "player_id": 8478402,
            "player_name": "Connor McDavid",
        },
        {
            "event_id": 3,
            "event_type": "goal",
            "period": 1,
            "time_in_period": "05:30",
            "team_id": 22,
            "team_abbrev": "EDM",
            "player_id": 8478402,
            "player_name": "Connor McDavid",
            "assists": [
                {"player_id": 8477934, "player_name": "Leon Draisaitl"},
            ],
        },
        {
            "event_id": 4,
            "event_type": "hit",
            "period": 2,
            "time_in_period": "05:00",
            "team_id": 10,
            "team_abbrev": "TOR",
            "player_id": 8479318,
            "player_name": "Auston Matthews",
        },
        {
            "event_id": 5,
            "event_type": "goal",
            "period": 3,
            "time_in_period": "15:00",
            "team_id": 10,
            "team_abbrev": "TOR",
            "player_id": 8479318,
            "player_name": "Auston Matthews",
            "game_winning_goal": True,
        },
    ]


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
    (data_dir / "processed" / "player_profiles").mkdir(parents=True)
    (data_dir / "cache").mkdir(parents=True)
    return data_dir


@pytest.fixture
def sample_zones_config() -> dict[str, Any]:
    """Sample zone configuration for testing."""
    return {
        "zones": {
            "slot": {
                "x_min": 69,
                "x_max": 89,
                "y_min": -22,
                "y_max": 22,
                "danger_level": "high",
                "expected_shooting_pct": 0.15,
            },
            "left_circle": {
                "x_min": 54,
                "x_max": 74,
                "y_min": -32,
                "y_max": -12,
                "danger_level": "medium",
                "expected_shooting_pct": 0.08,
            },
        }
    }


@pytest.fixture
def sample_segments_config() -> dict[str, Any]:
    """Sample segment configuration for testing."""
    return {
        "segments": {
            "early_game": {
                "time_ranges": [
                    {"period": 1, "start_minute": 0, "end_minute": 20},
                    {"period": 2, "start_minute": 0, "end_minute": 10},
                ],
                "total_minutes": 30,
            },
            "mid_game": {
                "time_ranges": [
                    {"period": 2, "start_minute": 10, "end_minute": 20},
                    {"period": 3, "start_minute": 0, "end_minute": 10},
                ],
                "total_minutes": 20,
            },
            "late_game": {
                "time_ranges": [
                    {"period": 3, "start_minute": 10, "end_minute": 20},
                ],
                "total_minutes": 10,
            },
        }
    }
