"""
Synergy Processor

Transforms game events into synergy analytics and line chemistry outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from loguru import logger

from src.analytics.synergy import SynergyAnalyzer, SynergyEvent
from src.models.game import GameEvent, EventType
from src.models.player import Player
from src.models.team import LineConfiguration


@dataclass
class SynergySummary:
    """Summary output for synergy and chemistry tracking."""

    pair_scores: dict[tuple[int, int], float]
    line_scores: dict[int, float]
    compatibility_matrix: dict[int, dict[int, float]]


class ChemistryTracker:
    """
    Processor that builds synergy metrics from game events and line configs.

    Inputs:
        - GameEvent list from Game model
        - LineConfiguration list from Team model
    Outputs:
        - Pairwise synergy scores
        - Line chemistry scores
        - Compatibility matrix
    """

    def __init__(self, analyzer: SynergyAnalyzer | None = None) -> None:
        self.analyzer = analyzer or SynergyAnalyzer()

    def ingest_game_events(self, events: Iterable[GameEvent]) -> None:
        """Convert game events into synergy events and ingest them."""
        converted = []
        for event in events:
            player_ids = self._extract_player_ids(event)
            if len(player_ids) < 2:
                continue
            converted.append(
                SynergyEvent(
                    event_type=event.event_type.value,
                    period=event.period,
                    game_seconds=event.game_seconds,
                    player_ids=player_ids,
                    team_id=event.team_id,
                    segment=event.segment,
                    shot_quality=event.details.get("shot_quality"),
                    time_on_ice_seconds=event.details.get("time_on_ice_seconds"),
                )
            )
        if converted:
            self.analyzer.ingest_events(converted)
            logger.debug(f"Ingested {len(converted)} synergy events.")

    def analyze_lines(self, lines: Iterable[LineConfiguration]) -> dict[int, float]:
        """Compute chemistry scores for a list of line configurations."""
        line_scores: dict[int, float] = {}
        for line in lines:
            line_scores[line.line_number] = self.analyzer.line_synergy(line.player_ids)
        return line_scores

    def populate_player_synergies(self, players: Iterable[Player]) -> None:
        """Populate each player's synergy map using current analyzer data."""
        player_list = list(players)
        player_ids = [player.player_id for player in player_list]
        compatibility = self.analyzer.compatibility_matrix(player_ids)
        for player in player_list:
            player.synergies = {
                other_id: score
                for other_id, score in compatibility.get(player.player_id, {}).items()
                if other_id != player.player_id
            }

    def populate_line_chemistry(self, lines: Iterable[LineConfiguration]) -> None:
        """Populate chemistry scores on line configurations."""
        for line in lines:
            line.chemistry_score = self.analyzer.line_synergy(line.player_ids)

    def apply_synergy_updates(
        self,
        players: Iterable[Player],
        lines: Iterable[LineConfiguration],
    ) -> None:
        """Update player synergies and line chemistry deterministically."""
        self.populate_player_synergies(players)
        self.populate_line_chemistry(lines)

    def build_summary(self, players: Iterable[int], lines: Iterable[LineConfiguration]) -> SynergySummary:
        """Build a summary of synergy and chemistry metrics."""
        pair_scores = {
            pair: self.analyzer.synergy_score(*pair) for pair in self.analyzer.pair_stats.keys()
        }
        line_scores = self.analyze_lines(lines)
        compatibility_matrix = self.analyzer.compatibility_matrix(players)
        return SynergySummary(
            pair_scores=pair_scores,
            line_scores=line_scores,
            compatibility_matrix=compatibility_matrix,
        )

    def _extract_player_ids(self, event: GameEvent) -> list[int]:
        """Extract involved player IDs from a game event."""
        ids = set()
        if event.player_id is not None:
            ids.add(event.player_id)
        for assist in event.assists:
            assist_id = assist.get("player_id")
            if assist_id is not None:
                ids.add(assist_id)
        for participant in event.details.get("participants", []):
            participant_id = participant.get("player_id")
            if participant_id is not None:
                ids.add(participant_id)
        if event.event_type == EventType.FACEOFF:
            for key in ("winner_id", "loser_id"):
                participant_id = event.details.get(key)
                if participant_id is not None:
                    ids.add(participant_id)
        return list(ids)
