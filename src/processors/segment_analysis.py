"""
Segment Analysis Processor

Processes game events into segment-based analytics for time-based performance tracking.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger


@dataclass
class SegmentDefinition:
    """Definition of a game segment."""

    name: str
    time_ranges: list[dict[str, int]]
    total_minutes: int
    characteristics: list[str]

    def contains_time(self, period: int, minute: int) -> bool:
        """Check if a time falls within this segment."""
        for time_range in self.time_ranges:
            if (
                time_range["period"] == period
                and time_range["start_minute"] <= minute < time_range["end_minute"]
            ):
                return True
        return False

    def contains_game_seconds(self, game_seconds: int) -> bool:
        """Check if game seconds falls within this segment."""
        for time_range in self.time_ranges:
            period = time_range["period"]
            start = (period - 1) * 1200 + time_range["start_minute"] * 60
            end = (period - 1) * 1200 + time_range["end_minute"] * 60
            if start <= game_seconds < end:
                return True
        return False


@dataclass
class PlayerSegmentStats:
    """Player statistics within a segment."""

    player_id: int
    player_name: str
    games: int = 0
    goals: int = 0
    assists: int = 0
    points: int = 0
    shots: int = 0
    hits: int = 0
    blocked_shots: int = 0
    takeaways: int = 0
    giveaways: int = 0
    plus_minus: int = 0
    game_winning_goals: int = 0
    game_tying_goals: int = 0

    @property
    def points_per_game(self) -> float:
        """Calculate points per game in this segment."""
        return self.points / self.games if self.games > 0 else 0.0

    @property
    def shooting_percentage(self) -> float:
        """Calculate shooting percentage."""
        return self.goals / self.shots if self.shots > 0 else 0.0


@dataclass
class TeamSegmentStats:
    """Team statistics within a segment."""

    team_id: int
    team_abbrev: str
    games: int = 0
    goals_for: int = 0
    goals_against: int = 0
    shots_for: int = 0
    shots_against: int = 0
    hits: int = 0
    blocked_shots: int = 0
    takeaways: int = 0
    giveaways: int = 0
    faceoff_wins: int = 0
    faceoff_total: int = 0
    power_play_goals: int = 0
    power_play_opportunities: int = 0

    @property
    def goal_differential(self) -> int:
        """Calculate goal differential."""
        return self.goals_for - self.goals_against

    @property
    def shooting_percentage(self) -> float:
        """Calculate team shooting percentage."""
        return self.goals_for / self.shots_for if self.shots_for > 0 else 0.0

    @property
    def save_percentage(self) -> float:
        """Calculate save percentage."""
        return 1 - (self.goals_against / self.shots_against) if self.shots_against > 0 else 1.0

    @property
    def faceoff_percentage(self) -> float:
        """Calculate faceoff win percentage."""
        return self.faceoff_wins / self.faceoff_total if self.faceoff_total > 0 else 0.5


class SegmentProcessor:
    """
    Processor for game segment analysis.

    Segments games into time periods and tracks performance metrics:
    - Early game: Period 1 + first 10 min of Period 2
    - Mid game: Minutes 10-20 of Period 2 + first 10 min of Period 3
    - Late game: Final 10 minutes of regulation + overtime
    """

    def __init__(self, segments_config_path: str | Path | None = None):
        """
        Initialize the segment processor.

        Args:
            segments_config_path: Path to segments configuration file.
        """
        self.config = self._load_config(segments_config_path)
        self.segments = self._build_segment_definitions()

        # Storage for statistics
        self.player_stats: dict[str, dict[int, PlayerSegmentStats]] = {
            "early_game": {},
            "mid_game": {},
            "late_game": {},
        }
        self.team_stats: dict[str, dict[int, TeamSegmentStats]] = {
            "early_game": {},
            "mid_game": {},
            "late_game": {},
        }

        # Track games processed
        self.games_processed: set[str] = set()

    def _load_config(self, config_path: str | Path | None) -> dict[str, Any]:
        """Load segment configuration from YAML file."""
        if config_path is None:
            config_path = Path("config/segments.yaml")
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            logger.warning(f"Segments config not found at {config_path}, using defaults")
            return self._default_segments_config()

        with open(config_path) as f:
            return yaml.safe_load(f)

    def _default_segments_config(self) -> dict[str, Any]:
        """Return default segment configuration."""
        return {
            "segments": {
                "early_game": {
                    "time_ranges": [
                        {"period": 1, "start_minute": 0, "end_minute": 20},
                        {"period": 2, "start_minute": 0, "end_minute": 10},
                    ],
                    "total_minutes": 30,
                    "characteristics": ["Fresh legs", "Testing opponent"],
                },
                "mid_game": {
                    "time_ranges": [
                        {"period": 2, "start_minute": 10, "end_minute": 20},
                        {"period": 3, "start_minute": 0, "end_minute": 10},
                    ],
                    "total_minutes": 20,
                    "characteristics": ["Adjustments", "Fatigue beginning"],
                },
                "late_game": {
                    "time_ranges": [
                        {"period": 3, "start_minute": 10, "end_minute": 20},
                        {"period": 4, "start_minute": 0, "end_minute": 5},
                    ],
                    "total_minutes": 15,
                    "characteristics": ["Clutch time", "Score-dependent play"],
                },
            }
        }

    def _build_segment_definitions(self) -> dict[str, SegmentDefinition]:
        """Build segment definitions from configuration."""
        segments = {}
        for seg_name, seg_config in self.config.get("segments", {}).items():
            segments[seg_name] = SegmentDefinition(
                name=seg_name,
                time_ranges=seg_config.get("time_ranges", []),
                total_minutes=seg_config.get("total_minutes", 0),
                characteristics=seg_config.get("characteristics", []),
            )
        return segments

    def identify_segment(self, period: int, time_in_period: str) -> str | None:
        """
        Identify which segment a time belongs to.

        Args:
            period: Period number
            time_in_period: Time string in MM:SS format

        Returns:
            Segment name or None
        """
        try:
            parts = time_in_period.split(":")
            minutes = int(parts[0])
        except (ValueError, IndexError):
            return None

        for seg_name, seg_def in self.segments.items():
            if seg_def.contains_time(period, minutes):
                return seg_name

        return None

    def identify_segment_by_seconds(self, game_seconds: int) -> str | None:
        """
        Identify segment by total game seconds.

        Args:
            game_seconds: Total seconds elapsed in game

        Returns:
            Segment name or None
        """
        for seg_name, seg_def in self.segments.items():
            if seg_def.contains_game_seconds(game_seconds):
                return seg_name
        return None

    def process_event(
        self,
        event: dict[str, Any],
        game_context: dict[str, Any],
    ) -> None:
        """
        Process a single game event into segment statistics.

        Args:
            event: Event dictionary with type, time, player, team info
            game_context: Game context with team IDs and current score
        """
        segment = self.identify_segment(
            event.get("period", 0),
            event.get("time_in_period", "00:00"),
        )
        if not segment:
            return

        event_type = event.get("event_type", "").lower()
        team_id = event.get("team_id")
        player_id = event.get("player_id")
        player_name = event.get("player_name", "")

        # Update player stats if player involved
        if player_id:
            self._update_player_stats(
                segment, player_id, player_name, event_type, event, game_context
            )

        # Update team stats
        if team_id:
            self._update_team_stats(
                segment, team_id, event.get("team_abbrev", ""), event_type, event, game_context
            )

    def _update_player_stats(
        self,
        segment: str,
        player_id: int,
        player_name: str,
        event_type: str,
        event: dict[str, Any],
        game_context: dict[str, Any],
    ) -> None:
        """Update player statistics for a segment."""
        if player_id not in self.player_stats[segment]:
            self.player_stats[segment][player_id] = PlayerSegmentStats(
                player_id=player_id,
                player_name=player_name,
            )

        stats = self.player_stats[segment][player_id]

        if event_type == "goal":
            stats.goals += 1
            stats.points += 1
            stats.shots += 1

            # Check for clutch goals
            if self._is_game_winning_goal(event, game_context):
                stats.game_winning_goals += 1
            if self._is_game_tying_goal(event, game_context):
                stats.game_tying_goals += 1

        elif event_type in {"shot-on-goal", "shot"}:
            stats.shots += 1

        elif event_type == "hit":
            stats.hits += 1

        elif event_type == "blocked-shot":
            stats.blocked_shots += 1

        elif event_type == "takeaway":
            stats.takeaways += 1

        elif event_type == "giveaway":
            stats.giveaways += 1

        # Handle assists
        assists = event.get("assists", [])
        for assist in assists:
            assist_player_id = assist.get("player_id")
            if assist_player_id:
                if assist_player_id not in self.player_stats[segment]:
                    self.player_stats[segment][assist_player_id] = PlayerSegmentStats(
                        player_id=assist_player_id,
                        player_name=assist.get("player_name", ""),
                    )
                self.player_stats[segment][assist_player_id].assists += 1
                self.player_stats[segment][assist_player_id].points += 1

    def _update_team_stats(
        self,
        segment: str,
        team_id: int,
        team_abbrev: str,
        event_type: str,
        event: dict[str, Any],
        game_context: dict[str, Any],
    ) -> None:
        """Update team statistics for a segment."""
        if team_id not in self.team_stats[segment]:
            self.team_stats[segment][team_id] = TeamSegmentStats(
                team_id=team_id,
                team_abbrev=team_abbrev,
            )

        stats = self.team_stats[segment][team_id]
        opponent_id = self._get_opponent_id(team_id, game_context)

        if event_type == "goal":
            stats.goals_for += 1
            stats.shots_for += 1

            # Update opponent goals against
            if opponent_id and opponent_id in self.team_stats[segment]:
                self.team_stats[segment][opponent_id].goals_against += 1

        elif event_type in {"shot-on-goal", "shot"}:
            stats.shots_for += 1

            # Update opponent shots against
            if opponent_id and opponent_id in self.team_stats[segment]:
                self.team_stats[segment][opponent_id].shots_against += 1

        elif event_type == "hit":
            stats.hits += 1

        elif event_type == "blocked-shot":
            stats.blocked_shots += 1

        elif event_type == "takeaway":
            stats.takeaways += 1

        elif event_type == "giveaway":
            stats.giveaways += 1

        elif event_type == "faceoff":
            stats.faceoff_total += 1
            if event.get("winner_team_id") == team_id:
                stats.faceoff_wins += 1

    def _get_opponent_id(self, team_id: int, game_context: dict[str, Any]) -> int | None:
        """Get opponent team ID from game context."""
        home_id = game_context.get("home_team_id")
        away_id = game_context.get("away_team_id")

        if team_id == home_id:
            return away_id
        elif team_id == away_id:
            return home_id
        return None

    def _is_game_winning_goal(
        self, event: dict[str, Any], game_context: dict[str, Any]
    ) -> bool:
        """Check if goal was the game-winning goal."""
        return event.get("game_winning_goal", False)

    def _is_game_tying_goal(
        self, event: dict[str, Any], game_context: dict[str, Any]
    ) -> bool:
        """Check if goal tied the game."""
        # Would need score state tracking for accurate detection
        return False

    def process_game_events(
        self,
        game_id: str,
        events: list[dict[str, Any]],
        home_team_id: int,
        away_team_id: int,
    ) -> None:
        """
        Process all events from a game.

        Args:
            game_id: Game identifier
            events: List of event dictionaries
            home_team_id: Home team ID
            away_team_id: Away team ID
        """
        if game_id in self.games_processed:
            logger.debug(f"Game {game_id} already processed, skipping")
            return

        game_context = {
            "game_id": game_id,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "home_score": 0,
            "away_score": 0,
        }

        # Initialize team stats for both teams in all segments
        for segment in self.segments:
            if home_team_id not in self.team_stats[segment]:
                self.team_stats[segment][home_team_id] = TeamSegmentStats(
                    team_id=home_team_id, team_abbrev=""
                )
            if away_team_id not in self.team_stats[segment]:
                self.team_stats[segment][away_team_id] = TeamSegmentStats(
                    team_id=away_team_id, team_abbrev=""
                )

        for event in events:
            # Update score tracking
            if event.get("event_type", "").lower() == "goal":
                if event.get("team_id") == home_team_id:
                    game_context["home_score"] += 1
                elif event.get("team_id") == away_team_id:
                    game_context["away_score"] += 1

            self.process_event(event, game_context)

        # Mark game as processed and increment game counts
        self.games_processed.add(game_id)

        for segment in self.segments:
            for team_id in [home_team_id, away_team_id]:
                if team_id in self.team_stats[segment]:
                    self.team_stats[segment][team_id].games += 1

        logger.debug(f"Processed {len(events)} events from game {game_id}")

    def get_player_segment_stats(
        self, player_id: int, segment: str
    ) -> PlayerSegmentStats | None:
        """Get player statistics for a specific segment."""
        return self.player_stats.get(segment, {}).get(player_id)

    def get_team_segment_stats(
        self, team_id: int, segment: str
    ) -> TeamSegmentStats | None:
        """Get team statistics for a specific segment."""
        return self.team_stats.get(segment, {}).get(team_id)

    def get_player_all_segments(
        self, player_id: int
    ) -> dict[str, PlayerSegmentStats | None]:
        """Get player statistics across all segments."""
        return {
            segment: self.player_stats[segment].get(player_id)
            for segment in self.segments
        }

    def get_team_all_segments(
        self, team_id: int
    ) -> dict[str, TeamSegmentStats | None]:
        """Get team statistics across all segments."""
        return {
            segment: self.team_stats[segment].get(team_id)
            for segment in self.segments
        }

    def calculate_fatigue_indicator(self, player_id: int) -> float:
        """
        Calculate fatigue indicator comparing early vs late game performance.

        Args:
            player_id: Player ID

        Returns:
            Fatigue indicator (< 1.0 indicates decline, > 1.0 indicates improvement)
        """
        early_stats = self.get_player_segment_stats(player_id, "early_game")
        late_stats = self.get_player_segment_stats(player_id, "late_game")

        if not early_stats or not late_stats:
            return 1.0

        if early_stats.games == 0 or late_stats.games == 0:
            return 1.0

        early_ppg = early_stats.points_per_game
        late_ppg = late_stats.points_per_game

        if early_ppg == 0:
            return 1.0

        return late_ppg / early_ppg

    def calculate_clutch_rating(self, player_id: int) -> float:
        """
        Calculate clutch performance rating.

        Args:
            player_id: Player ID

        Returns:
            Clutch rating based on late game performance
        """
        late_stats = self.get_player_segment_stats(player_id, "late_game")

        if not late_stats or late_stats.games == 0:
            return 0.0

        # Weight factors
        gwg_weight = 5.0
        gtg_weight = 3.0
        points_weight = 1.0

        rating = (
            late_stats.game_winning_goals * gwg_weight
            + late_stats.game_tying_goals * gtg_weight
            + late_stats.points * points_weight
        )

        return rating / late_stats.games

    def get_segment_leaders(
        self, segment: str, stat: str = "points", limit: int = 10
    ) -> list[tuple[int, float]]:
        """
        Get leaders for a specific stat in a segment.

        Args:
            segment: Segment name
            stat: Statistic to rank by
            limit: Number of results

        Returns:
            List of (player_id, stat_value) tuples
        """
        segment_stats = self.player_stats.get(segment, {})
        leaders = []

        for player_id, stats in segment_stats.items():
            value = getattr(stats, stat, 0)
            leaders.append((player_id, value))

        leaders.sort(key=lambda x: x[1], reverse=True)
        return leaders[:limit]

    def reset(self) -> None:
        """Reset all statistics."""
        for segment in self.segments:
            self.player_stats[segment].clear()
            self.team_stats[segment].clear()
        self.games_processed.clear()
