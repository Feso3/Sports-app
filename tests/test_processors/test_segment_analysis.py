"""
Tests for Segment Analysis Processor

Tests for game segment processing and time-based analytics.
"""

import pytest


class TestSegmentDefinition:
    """Tests for SegmentDefinition class."""

    def test_contains_time_early_game(self):
        """Test time containment for early game segment."""
        from src.processors.segment_analysis import SegmentDefinition

        segment = SegmentDefinition(
            name="early_game",
            time_ranges=[
                {"period": 1, "start_minute": 0, "end_minute": 20},
                {"period": 2, "start_minute": 0, "end_minute": 10},
            ],
            total_minutes=30,
            characteristics=["Fresh legs"],
        )

        # Period 1 times
        assert segment.contains_time(1, 5) is True
        assert segment.contains_time(1, 15) is True

        # Period 2 first 10 minutes
        assert segment.contains_time(2, 5) is True

        # Period 2 after 10 minutes (not early game)
        assert segment.contains_time(2, 15) is False

        # Period 3 (not early game)
        assert segment.contains_time(3, 5) is False

    def test_contains_game_seconds(self):
        """Test containment by game seconds."""
        from src.processors.segment_analysis import SegmentDefinition

        segment = SegmentDefinition(
            name="early_game",
            time_ranges=[
                {"period": 1, "start_minute": 0, "end_minute": 20},
            ],
            total_minutes=20,
            characteristics=[],
        )

        # First period is 0-1200 seconds
        assert segment.contains_game_seconds(600) is True  # 10 minutes in
        assert segment.contains_game_seconds(1199) is True  # Just before end
        assert segment.contains_game_seconds(1200) is False  # Start of P2


class TestSegmentProcessor:
    """Tests for SegmentProcessor class."""

    def test_identify_segment_early_game(self):
        """Test segment identification for early game."""
        from src.processors.segment_analysis import SegmentProcessor

        processor = SegmentProcessor.__new__(SegmentProcessor)
        processor.config = {
            "segments": {
                "early_game": {
                    "time_ranges": [
                        {"period": 1, "start_minute": 0, "end_minute": 20},
                        {"period": 2, "start_minute": 0, "end_minute": 10},
                    ],
                    "total_minutes": 30,
                    "characteristics": [],
                },
                "mid_game": {
                    "time_ranges": [
                        {"period": 2, "start_minute": 10, "end_minute": 20},
                    ],
                    "total_minutes": 10,
                    "characteristics": [],
                },
            }
        }
        processor.segments = processor._build_segment_definitions()

        # Test early game
        assert processor.identify_segment(1, "05:30") == "early_game"
        assert processor.identify_segment(2, "05:00") == "early_game"

        # Test mid game
        assert processor.identify_segment(2, "15:00") == "mid_game"

    def test_process_goal_event(self, sample_game_events):
        """Test processing a goal event."""
        from src.processors.segment_analysis import SegmentProcessor

        processor = SegmentProcessor.__new__(SegmentProcessor)
        processor.config = {
            "segments": {
                "early_game": {
                    "time_ranges": [
                        {"period": 1, "start_minute": 0, "end_minute": 20},
                    ],
                    "total_minutes": 20,
                    "characteristics": [],
                },
            }
        }
        processor.segments = processor._build_segment_definitions()
        processor.player_stats = {"early_game": {}}
        processor.team_stats = {"early_game": {}}
        processor.games_processed = set()

        # Process goal event
        goal_event = sample_game_events[2]  # The goal event
        game_context = {
            "game_id": "2023020001",
            "home_team_id": 22,
            "away_team_id": 10,
            "home_score": 0,
            "away_score": 0,
        }

        processor.process_event(goal_event, game_context)

        # Check player stats updated
        player_id = goal_event["player_id"]
        assert player_id in processor.player_stats["early_game"]
        stats = processor.player_stats["early_game"][player_id]
        assert stats.goals == 1
        assert stats.points == 1

    def test_process_game_events(self, sample_game_events):
        """Test processing all events from a game."""
        from src.processors.segment_analysis import SegmentProcessor

        processor = SegmentProcessor.__new__(SegmentProcessor)
        processor.config = {
            "segments": {
                "early_game": {
                    "time_ranges": [
                        {"period": 1, "start_minute": 0, "end_minute": 20},
                        {"period": 2, "start_minute": 0, "end_minute": 10},
                    ],
                    "total_minutes": 30,
                    "characteristics": [],
                },
                "mid_game": {
                    "time_ranges": [
                        {"period": 2, "start_minute": 10, "end_minute": 20},
                        {"period": 3, "start_minute": 0, "end_minute": 10},
                    ],
                    "total_minutes": 20,
                    "characteristics": [],
                },
                "late_game": {
                    "time_ranges": [
                        {"period": 3, "start_minute": 10, "end_minute": 20},
                    ],
                    "total_minutes": 10,
                    "characteristics": [],
                },
            }
        }
        processor.segments = processor._build_segment_definitions()
        processor.player_stats = {
            "early_game": {},
            "mid_game": {},
            "late_game": {},
        }
        processor.team_stats = {
            "early_game": {},
            "mid_game": {},
            "late_game": {},
        }
        processor.games_processed = set()

        processor.process_game_events(
            game_id="2023020001",
            events=sample_game_events,
            home_team_id=22,
            away_team_id=10,
        )

        # Should mark game as processed
        assert "2023020001" in processor.games_processed


class TestFatigueAndClutchMetrics:
    """Tests for fatigue and clutch performance calculations."""

    def test_fatigue_indicator_decline(self):
        """Test fatigue indicator showing performance decline."""
        from src.processors.segment_analysis import (
            PlayerSegmentStats,
            SegmentProcessor,
        )

        processor = SegmentProcessor.__new__(SegmentProcessor)
        processor.player_stats = {
            "early_game": {
                8478402: PlayerSegmentStats(
                    player_id=8478402,
                    player_name="Connor McDavid",
                    games=10,
                    points=15,  # 1.5 PPG
                )
            },
            "late_game": {
                8478402: PlayerSegmentStats(
                    player_id=8478402,
                    player_name="Connor McDavid",
                    games=10,
                    points=10,  # 1.0 PPG
                )
            },
        }
        processor.segments = {"early_game": None, "mid_game": None, "late_game": None}

        fatigue = processor.calculate_fatigue_indicator(8478402)

        # Late game PPG (1.0) / Early game PPG (1.5) = 0.67
        assert fatigue == pytest.approx(1.0 / 1.5)
        assert fatigue < 1.0  # Indicates decline

    def test_clutch_rating(self):
        """Test clutch performance rating calculation."""
        from src.processors.segment_analysis import (
            PlayerSegmentStats,
            SegmentProcessor,
        )

        processor = SegmentProcessor.__new__(SegmentProcessor)
        processor.player_stats = {
            "late_game": {
                8478402: PlayerSegmentStats(
                    player_id=8478402,
                    player_name="Connor McDavid",
                    games=20,
                    points=15,
                    game_winning_goals=3,
                    game_tying_goals=2,
                )
            },
        }
        processor.segments = {"early_game": None, "mid_game": None, "late_game": None}

        clutch_rating = processor.calculate_clutch_rating(8478402)

        # Expected: (3 * 5.0 + 2 * 3.0 + 15 * 1.0) / 20 = (15 + 6 + 15) / 20 = 1.8
        assert clutch_rating == pytest.approx(1.8)


class TestSegmentLeaders:
    """Tests for segment leader calculations."""

    def test_get_segment_leaders(self):
        """Test getting top performers in a segment."""
        from src.processors.segment_analysis import (
            PlayerSegmentStats,
            SegmentProcessor,
        )

        processor = SegmentProcessor.__new__(SegmentProcessor)
        processor.player_stats = {
            "late_game": {
                1: PlayerSegmentStats(player_id=1, player_name="P1", points=10),
                2: PlayerSegmentStats(player_id=2, player_name="P2", points=15),
                3: PlayerSegmentStats(player_id=3, player_name="P3", points=8),
            },
        }
        processor.segments = {"late_game": None}

        leaders = processor.get_segment_leaders("late_game", "points", limit=2)

        assert len(leaders) == 2
        assert leaders[0] == (2, 15)  # P2 with 15 points
        assert leaders[1] == (1, 10)  # P1 with 10 points
