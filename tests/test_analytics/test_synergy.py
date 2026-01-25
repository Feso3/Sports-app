"""
Tests for Synergy Analytics

Validates pairwise synergy scores, line chemistry, and compatibility matrices.
"""

import pytest

from src.analytics.synergy import SynergyAnalyzer, SynergyEvent


def test_pairwise_synergy_score_computation():
    """Compute a deterministic pairwise synergy score."""
    analyzer = SynergyAnalyzer(
        weights={
            "goal": 2.0,
            "shot": 1.0,
            "xg": 1.0,
            "event": 0.5,
            "toi_per_minute": 0.1,
        },
        segment_weights={
            "early_game": 0.5,
            "late_game": 1.5,
        },
    )

    events = [
        SynergyEvent(
            event_type="goal",
            period=1,
            game_seconds=100,
            player_ids=[1, 2],
            shot_quality=0.3,
            segment="early_game",
            time_on_ice_seconds=30,
        ),
        SynergyEvent(
            event_type="shot",
            period=1,
            game_seconds=140,
            player_ids=[1, 2],
            shot_quality=0.1,
            segment="late_game",
            time_on_ice_seconds=30,
        ),
    ]

    analyzer.ingest_events(events)

    expected_score = 3.75
    assert analyzer.synergy_score(1, 2) == pytest.approx(expected_score)


def test_line_chemistry_aggregation():
    """Average pairwise synergy scores for a line configuration."""
    analyzer = SynergyAnalyzer(weights={"goal": 2.0, "shot": 1.0, "xg": 0.0, "event": 0.0})

    analyzer.ingest_events(
        [
            SynergyEvent(
                event_type="goal",
                period=1,
                game_seconds=50,
                player_ids=[1, 2],
            ),
            SynergyEvent(
                event_type="shot",
                period=1,
                game_seconds=80,
                player_ids=[1, 3],
            ),
            SynergyEvent(
                event_type="goal",
                period=1,
                game_seconds=110,
                player_ids=[2, 3],
            ),
            SynergyEvent(
                event_type="shot",
                period=1,
                game_seconds=135,
                player_ids=[2, 3],
            ),
        ]
    )

    # Pairwise scores: (1,2)=3.0, (1,3)=1.0, (2,3)=2.0 -> average = 2.0
    assert analyzer.line_synergy([1, 2, 3]) == pytest.approx(2.0)


def test_compatibility_matrix_construction():
    """Build a compatibility matrix for a player set."""
    analyzer = SynergyAnalyzer(weights={"goal": 2.0, "shot": 1.0, "xg": 0.0, "event": 0.0})

    analyzer.ingest_events(
        [
            SynergyEvent(
                event_type="goal",
                period=1,
                game_seconds=50,
                player_ids=[1, 2],
            ),
            SynergyEvent(
                event_type="shot",
                period=1,
                game_seconds=80,
                player_ids=[1, 3],
            ),
            SynergyEvent(
                event_type="goal",
                period=1,
                game_seconds=110,
                player_ids=[2, 3],
            ),
            SynergyEvent(
                event_type="shot",
                period=1,
                game_seconds=135,
                player_ids=[2, 3],
            ),
        ]
    )

    matrix = analyzer.compatibility_matrix([1, 2, 3])

    assert matrix[1][1] == 1.0
    assert matrix[2][2] == 1.0
    assert matrix[3][3] == 1.0

    assert matrix[1][2] == pytest.approx(3.0)
    assert matrix[2][1] == pytest.approx(3.0)
    assert matrix[1][3] == pytest.approx(1.0)
    assert matrix[3][1] == pytest.approx(1.0)
    assert matrix[2][3] == pytest.approx(2.0)
    assert matrix[3][2] == pytest.approx(2.0)
