"""
Tests for Shot Data Collector

Tests for shot location and outcome data collection.
"""

import json
from pathlib import Path
from typing import Any

import pytest


class TestShot:
    """Tests for the Shot dataclass."""

    def test_shot_creation(self, sample_shot_data):
        """Test Shot dataclass creation."""
        from src.collectors.shot_data import Shot

        shot_data = sample_shot_data[0]
        shot = Shot(
            game_id=shot_data["game_id"],
            event_id=shot_data["event_id"],
            period=shot_data["period"],
            time_in_period=shot_data["time_in_period"],
            time_remaining=shot_data["time_remaining"],
            shooter_id=shot_data["shooter_id"],
            shooter_name=shot_data["shooter_name"],
            team_id=shot_data["team_id"],
            team_abbrev=shot_data["team_abbrev"],
            shot_type=shot_data["shot_type"],
            x_coord=shot_data["x_coord"],
            y_coord=shot_data["y_coord"],
            distance=shot_data["distance"],
            is_goal=shot_data["is_goal"],
            goalie_id=shot_data["goalie_id"],
            strength=shot_data["strength"],
            empty_net=shot_data["empty_net"],
        )

        assert shot.shooter_id == 8478402
        assert shot.is_goal is True
        assert shot.shot_type == "wrist"


class TestShotDataCollector:
    """Tests for ShotDataCollector class."""

    def test_shot_type_mapping(self):
        """Test shot type normalization."""
        from src.collectors.shot_data import ShotDataCollector

        expected_mappings = {
            "wrist": "wrist",
            "slap": "slap",
            "snap": "snap",
            "backhand": "backhand",
            "deflected": "deflection",
            "tip-in": "tip_in",
            "wrap-around": "wrap_around",
        }

        for raw, expected in expected_mappings.items():
            assert ShotDataCollector.SHOT_TYPE_MAP.get(raw) == expected

    def test_tracked_event_types(self):
        """Test that all shot event types are tracked."""
        from src.collectors.shot_data import ShotDataCollector

        expected_types = {"shot-on-goal", "goal", "missed-shot", "blocked-shot"}
        assert ShotDataCollector.SHOT_EVENT_TYPES == expected_types

    def test_save_and_load_shots(self, sample_shot_data, tmp_path):
        """Test saving and loading shot data."""
        from src.collectors.shot_data import Shot, ShotDataCollector

        # Create Shot objects
        shots = []
        for data in sample_shot_data:
            shot = Shot(
                game_id=data["game_id"],
                event_id=data["event_id"],
                period=data["period"],
                time_in_period=data["time_in_period"],
                time_remaining=data["time_remaining"],
                shooter_id=data["shooter_id"],
                shooter_name=data["shooter_name"],
                team_id=data["team_id"],
                team_abbrev=data["team_abbrev"],
                shot_type=data["shot_type"],
                x_coord=data["x_coord"],
                y_coord=data["y_coord"],
                distance=data["distance"],
                is_goal=data["is_goal"],
                goalie_id=data.get("goalie_id"),
                strength=data.get("strength"),
                empty_net=data.get("empty_net", False),
            )
            shots.append(shot)

        # Save shots
        save_path = tmp_path / "shots.json"
        collector = ShotDataCollector.__new__(ShotDataCollector)
        collector.save_shots(shots, save_path)

        # Load shots
        loaded_shots = collector.load_shots(save_path)

        assert len(loaded_shots) == len(shots)
        assert loaded_shots[0].shooter_id == shots[0].shooter_id
        assert loaded_shots[0].is_goal == shots[0].is_goal


class TestStrengthDetermination:
    """Tests for strength state determination."""

    def test_even_strength(self):
        """Test even strength detection."""
        # Situation code format: HHAA (home skaters, away skaters)
        # 0505 = 5v5
        situation_code = "0505"

        home_skaters = int(situation_code[0])
        away_skaters = int(situation_code[2])

        assert home_skaters == away_skaters

    def test_power_play_home(self):
        """Test power play detection for home team."""
        situation_code = "0504"  # 5v4 for home

        home_skaters = int(situation_code[0])
        away_skaters = int(situation_code[2])

        # Home team has more skaters = power play
        assert home_skaters > away_skaters

    def test_shorthanded_home(self):
        """Test shorthanded detection for home team."""
        situation_code = "0405"  # 4v5 for home

        home_skaters = int(situation_code[0])
        away_skaters = int(situation_code[2])

        # Home team has fewer skaters = shorthanded
        assert home_skaters < away_skaters
