"""
Synergy Analytics Module

Calculates player combination synergy, line chemistry, and compatibility matrices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Iterable


@dataclass(frozen=True)
class SynergyEvent:
    """Represents a shared on-ice event for synergy calculations."""

    event_type: str
    period: int
    game_seconds: int
    player_ids: list[int]
    team_id: int | None = None
    segment: str | None = None
    shot_quality: float | None = None
    time_on_ice_seconds: int | None = None


@dataclass
class PlayerSynergyStats:
    """Aggregated synergy stats for a player pair."""

    player_a: int
    player_b: int
    shared_events: int = 0
    shared_shots: int = 0
    shared_goals: int = 0
    shared_xg: float = 0.0
    segment_points: dict[str, int] = field(default_factory=dict)
    time_on_ice_seconds: int = 0

    def record_event(self, event: SynergyEvent) -> None:
        """Update the stats based on a synergy event."""
        self.shared_events += 1
        if event.event_type in {"goal"}:
            self.shared_goals += 1
        if event.event_type in {"shot", "goal", "missed_shot", "blocked_shot"}:
            self.shared_shots += 1
        if event.shot_quality is not None:
            self.shared_xg += event.shot_quality
        if event.segment:
            self.segment_points[event.segment] = self.segment_points.get(event.segment, 0) + 1
        if event.time_on_ice_seconds:
            self.time_on_ice_seconds += event.time_on_ice_seconds


class SynergyAnalyzer:
    """
    Analyze player combinations and line chemistry.

    Inputs:
        - SynergyEvent: on-ice events containing player groups and optional xG/segment info.
    Outputs:
        - Pairwise synergy scores
        - Line chemistry scores
        - Compatibility matrices
    """

    DEFAULT_WEIGHTS = {
        "goal": 2.5,
        "shot": 0.4,
        "xg": 1.3,
        "event": 0.1,
        "toi_per_minute": 0.02,
    }

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        segment_weights: dict[str, float] | None = None,
    ) -> None:
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}
        self.segment_weights = segment_weights or {
            "early_game": 0.8,
            "mid_game": 1.0,
            "late_game": 1.2,
        }
        self.pair_stats: dict[tuple[int, int], PlayerSynergyStats] = {}

    def ingest_events(self, events: Iterable[SynergyEvent]) -> None:
        """Ingest a batch of synergy events."""
        for event in events:
            self.record_event(event)

    def record_event(self, event: SynergyEvent) -> None:
        """Record a single synergy event across all player pairs involved."""
        unique_players = sorted(set(event.player_ids))
        if len(unique_players) < 2:
            return
        for player_a, player_b in combinations(unique_players, 2):
            key = (player_a, player_b)
            if key not in self.pair_stats:
                self.pair_stats[key] = PlayerSynergyStats(player_a=player_a, player_b=player_b)
            self.pair_stats[key].record_event(event)

    def get_pair_stats(self, player_a: int, player_b: int) -> PlayerSynergyStats | None:
        """Return stored synergy stats for a player pair."""
        key = tuple(sorted((player_a, player_b)))
        return self.pair_stats.get(key)

    def synergy_score(self, player_a: int, player_b: int) -> float:
        """Compute the synergy score for a player pair."""
        stats = self.get_pair_stats(player_a, player_b)
        if not stats:
            return 0.0
        return self._score_from_stats(stats)

    def line_synergy(self, player_ids: Iterable[int]) -> float:
        """Compute aggregate synergy for a line configuration."""
        players = sorted(set(player_ids))
        if len(players) < 2:
            return 0.0
        pair_scores = [self.synergy_score(a, b) for a, b in combinations(players, 2)]
        return sum(pair_scores) / len(pair_scores) if pair_scores else 0.0

    def compatibility_matrix(self, player_ids: Iterable[int]) -> dict[int, dict[int, float]]:
        """Build a pairwise compatibility matrix for a group of players."""
        players = sorted(set(player_ids))
        matrix: dict[int, dict[int, float]] = {player: {} for player in players}
        for player in players:
            for other in players:
                if player == other:
                    matrix[player][other] = 1.0
                else:
                    matrix[player][other] = self.synergy_score(player, other)
        return matrix

    def _score_from_stats(self, stats: PlayerSynergyStats) -> float:
        """Calculate a weighted synergy score from stats."""
        goal_component = stats.shared_goals * self.weights["goal"]
        shot_component = stats.shared_shots * self.weights["shot"]
        xg_component = stats.shared_xg * self.weights["xg"]
        event_component = stats.shared_events * self.weights["event"]

        segment_component = 0.0
        for segment, count in stats.segment_points.items():
            segment_component += count * self.segment_weights.get(segment, 1.0)

        toi_component = (stats.time_on_ice_seconds / 60) * self.weights["toi_per_minute"]

        total = goal_component + shot_component + xg_component + event_component
        total += segment_component + toi_component

        activity = max(stats.shared_events, 1)
        return total / activity
