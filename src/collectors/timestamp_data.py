"""
Timestamp Data Collector

Collects event timing data for game segment analysis.
Extracts timestamps from play-by-play data for time-based analytics.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.collectors.nhl_api import NHLApiClient


@dataclass
class TimedEvent:
    """Represents a game event with timing information."""

    game_id: str
    event_id: int
    event_type: str
    period: int
    time_in_period: str
    time_remaining: str
    game_seconds: int  # Total seconds elapsed in game
    segment: str | None = None  # early_game, mid_game, late_game
    team_id: int | None = None
    team_abbrev: str | None = None
    player_id: int | None = None
    player_name: str | None = None
    x_coord: float | None = None
    y_coord: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GameSegmentData:
    """Aggregated data for a game segment."""

    game_id: str
    segment: str
    events: list[TimedEvent]
    start_seconds: int
    end_seconds: int
    duration_seconds: int
    home_goals: int = 0
    away_goals: int = 0
    home_shots: int = 0
    away_shots: int = 0


class TimestampDataCollector:
    """
    Collector for event timing data.

    Extracts timestamps and assigns events to game segments:
    - Early game: Period 1 + first 10 min of Period 2
    - Mid game: Minutes 10-20 of Period 2 + first 10 min of Period 3
    - Late game: Final 10 minutes of regulation + overtime
    """

    # Event types to track
    TRACKED_EVENTS = {
        "goal",
        "shot-on-goal",
        "missed-shot",
        "blocked-shot",
        "hit",
        "takeaway",
        "giveaway",
        "faceoff",
        "penalty",
        "stoppage",
    }

    def __init__(
        self,
        api_client: NHLApiClient | None = None,
        segments_config_path: str | Path | None = None,
    ):
        """
        Initialize the timestamp data collector.

        Args:
            api_client: NHL API client instance. Creates one if not provided.
            segments_config_path: Path to segments configuration file.
        """
        self.api_client = api_client or NHLApiClient()
        self._owns_client = api_client is None
        self.segments_config = self._load_segments_config(segments_config_path)

    def _load_segments_config(
        self, config_path: str | Path | None
    ) -> dict[str, Any]:
        """Load segment definitions from configuration."""
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
                    ]
                },
                "mid_game": {
                    "time_ranges": [
                        {"period": 2, "start_minute": 10, "end_minute": 20},
                        {"period": 3, "start_minute": 0, "end_minute": 10},
                    ]
                },
                "late_game": {
                    "time_ranges": [
                        {"period": 3, "start_minute": 10, "end_minute": 20},
                        {"period": 4, "start_minute": 0, "end_minute": 5},
                    ]
                },
            }
        }

    def collect_game_events(self, game_id: int | str) -> list[TimedEvent]:
        """
        Collect all timed events from a game.

        Args:
            game_id: NHL game ID

        Returns:
            List of TimedEvent objects with segment assignments
        """
        logger.info(f"Collecting timestamp data for game {game_id}")

        try:
            play_by_play = self.api_client.get_game_play_by_play(game_id)
        except Exception as e:
            logger.error(f"Failed to get play-by-play for game {game_id}: {e}")
            return []

        events = []
        plays = play_by_play.get("plays", [])

        for play in plays:
            event_type = play.get("typeDescKey", "").lower()

            if event_type in self.TRACKED_EVENTS:
                event = self._parse_timed_event(play, str(game_id))
                if event:
                    events.append(event)

        logger.info(f"Collected {len(events)} timed events from game {game_id}")
        return events

    def collect_game_segments(self, game_id: int | str) -> dict[str, GameSegmentData]:
        """
        Collect events grouped by game segment.

        Args:
            game_id: NHL game ID

        Returns:
            Dictionary mapping segment name to GameSegmentData
        """
        events = self.collect_game_events(game_id)

        segments: dict[str, list[TimedEvent]] = {
            "early_game": [],
            "mid_game": [],
            "late_game": [],
        }

        for event in events:
            if event.segment and event.segment in segments:
                segments[event.segment].append(event)

        # Build GameSegmentData objects
        result = {}
        for segment_name, segment_events in segments.items():
            segment_config = self.segments_config["segments"].get(segment_name, {})
            time_ranges = segment_config.get("time_ranges", [])

            # Calculate segment boundaries
            start_seconds = self._calculate_segment_start(time_ranges)
            end_seconds = self._calculate_segment_end(time_ranges)

            # Count goals and shots
            home_goals = 0
            away_goals = 0
            home_shots = 0
            away_shots = 0

            # Would need game context to determine home/away properly
            # For now, just count totals
            for event in segment_events:
                if event.event_type == "goal":
                    # Placeholder - would need team context
                    home_goals += 1
                elif event.event_type in {"shot-on-goal", "goal"}:
                    home_shots += 1

            result[segment_name] = GameSegmentData(
                game_id=str(game_id),
                segment=segment_name,
                events=segment_events,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                duration_seconds=end_seconds - start_seconds,
                home_goals=home_goals,
                away_goals=away_goals,
                home_shots=home_shots,
                away_shots=away_shots,
            )

        return result

    def collect_season_timestamp_data(
        self,
        season: str,
        game_types: list[int] | None = None,
        save_path: Path | str | None = None,
    ) -> list[TimedEvent]:
        """
        Collect timestamp data for an entire season.

        Args:
            season: Season in YYYYYYYY format (e.g., "20232024")
            game_types: Game types to include
            save_path: Optional path to save collected data

        Returns:
            List of all timed events from the season
        """
        logger.info(f"Collecting timestamp data for season {season}")

        games = self.api_client.get_season_games(season, game_types)
        all_events = []

        for i, game in enumerate(games):
            game_id = game.get("gamePk")
            if game_id:
                events = self.collect_game_events(game_id)
                all_events.extend(events)

                if (i + 1) % 100 == 0:
                    logger.info(f"Processed {i + 1}/{len(games)} games")

        logger.info(f"Collected {len(all_events)} timed events for season {season}")

        if save_path:
            self.save_events(all_events, save_path)

        return all_events

    def _parse_timed_event(
        self, play: dict[str, Any], game_id: str
    ) -> TimedEvent | None:
        """
        Parse a play-by-play event into a TimedEvent object.

        Args:
            play: Play event data from API
            game_id: NHL game ID

        Returns:
            TimedEvent object or None if parsing fails
        """
        try:
            event_type = play.get("typeDescKey", "").lower()

            # Get period and time info
            period_descriptor = play.get("periodDescriptor", {})
            period = period_descriptor.get("number", 0)
            time_in_period = play.get("timeInPeriod", "00:00")
            time_remaining = play.get("timeRemaining", "20:00")

            # Calculate total game seconds
            game_seconds = self._calculate_game_seconds(period, time_in_period)

            # Determine segment
            segment = self._determine_segment(period, time_in_period)

            # Get details
            details = play.get("details", {})
            event_owner_team_id = details.get("eventOwnerTeamId")

            # Get coordinates
            x_coord = details.get("xCoord")
            y_coord = details.get("yCoord")

            # Get player info (varies by event type)
            player_id = None
            player_name = None
            if event_type == "goal":
                player_id = details.get("scoringPlayerId")
                player_name = details.get("scoringPlayerName")
            elif event_type in {"shot-on-goal", "missed-shot"}:
                player_id = details.get("shootingPlayerId")
            elif event_type in {"hit", "takeaway", "giveaway"}:
                player_id = details.get("playerId")

            event = TimedEvent(
                game_id=game_id,
                event_id=play.get("eventId", 0),
                event_type=event_type,
                period=period,
                time_in_period=time_in_period,
                time_remaining=time_remaining,
                game_seconds=game_seconds,
                segment=segment,
                team_id=event_owner_team_id,
                team_abbrev=details.get("eventOwnerTeamAbbrev"),
                player_id=player_id,
                player_name=player_name,
                x_coord=x_coord,
                y_coord=y_coord,
                details=details,
            )

            return event

        except Exception as e:
            logger.warning(f"Failed to parse timed event: {e}")
            return None

    def _calculate_game_seconds(self, period: int, time_in_period: str) -> int:
        """
        Calculate total seconds elapsed in the game.

        Args:
            period: Period number (1-4+)
            time_in_period: Time in MM:SS format

        Returns:
            Total seconds elapsed from game start
        """
        try:
            parts = time_in_period.split(":")
            minutes = int(parts[0])
            seconds = int(parts[1]) if len(parts) > 1 else 0

            # Each period is 20 minutes (1200 seconds)
            period_seconds = (period - 1) * 1200
            elapsed_in_period = minutes * 60 + seconds

            return period_seconds + elapsed_in_period
        except (ValueError, IndexError):
            return 0

    def _determine_segment(self, period: int, time_in_period: str) -> str | None:
        """
        Determine which game segment an event belongs to.

        Args:
            period: Period number
            time_in_period: Time in MM:SS format

        Returns:
            Segment name or None
        """
        try:
            parts = time_in_period.split(":")
            minutes = int(parts[0])
        except (ValueError, IndexError):
            return None

        segments_config = self.segments_config.get("segments", {})

        for segment_name, segment_def in segments_config.items():
            time_ranges = segment_def.get("time_ranges", [])
            for time_range in time_ranges:
                range_period = time_range.get("period")
                start_minute = time_range.get("start_minute", 0)
                end_minute = time_range.get("end_minute", 20)

                if period == range_period and start_minute <= minutes < end_minute:
                    return segment_name

        return None

    def _calculate_segment_start(self, time_ranges: list[dict]) -> int:
        """Calculate the starting game seconds for a segment."""
        if not time_ranges:
            return 0

        first_range = time_ranges[0]
        period = first_range.get("period", 1)
        start_minute = first_range.get("start_minute", 0)

        return (period - 1) * 1200 + start_minute * 60

    def _calculate_segment_end(self, time_ranges: list[dict]) -> int:
        """Calculate the ending game seconds for a segment."""
        if not time_ranges:
            return 0

        last_range = time_ranges[-1]
        period = last_range.get("period", 1)
        end_minute = last_range.get("end_minute", 20)

        return (period - 1) * 1200 + end_minute * 60

    def get_segment_statistics(
        self, events: list[TimedEvent]
    ) -> dict[str, dict[str, int]]:
        """
        Calculate statistics by segment.

        Args:
            events: List of timed events

        Returns:
            Dictionary with segment-level statistics
        """
        stats: dict[str, dict[str, int]] = {
            "early_game": {"goals": 0, "shots": 0, "hits": 0, "takeaways": 0},
            "mid_game": {"goals": 0, "shots": 0, "hits": 0, "takeaways": 0},
            "late_game": {"goals": 0, "shots": 0, "hits": 0, "takeaways": 0},
        }

        for event in events:
            segment = event.segment
            if segment not in stats:
                continue

            if event.event_type == "goal":
                stats[segment]["goals"] += 1
            elif event.event_type in {"shot-on-goal", "goal"}:
                stats[segment]["shots"] += 1
            elif event.event_type == "hit":
                stats[segment]["hits"] += 1
            elif event.event_type == "takeaway":
                stats[segment]["takeaways"] += 1

        return stats

    def save_events(self, events: list[TimedEvent], path: Path | str) -> None:
        """
        Save timed events to JSON file.

        Args:
            events: List of TimedEvent objects
            path: File path to save to
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        events_data = []
        for event in events:
            event_dict = {
                "game_id": event.game_id,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "period": event.period,
                "time_in_period": event.time_in_period,
                "time_remaining": event.time_remaining,
                "game_seconds": event.game_seconds,
                "segment": event.segment,
                "team_id": event.team_id,
                "team_abbrev": event.team_abbrev,
                "player_id": event.player_id,
                "player_name": event.player_name,
                "x_coord": event.x_coord,
                "y_coord": event.y_coord,
                "details": event.details,
            }
            events_data.append(event_dict)

        with open(path, "w") as f:
            json.dump(events_data, f, indent=2)

        logger.info(f"Saved {len(events)} timed events to {path}")

    def load_events(self, path: Path | str) -> list[TimedEvent]:
        """
        Load timed events from JSON file.

        Args:
            path: File path to load from

        Returns:
            List of TimedEvent objects
        """
        path = Path(path)

        with open(path) as f:
            events_data = json.load(f)

        events = []
        for event_dict in events_data:
            event = TimedEvent(
                game_id=event_dict["game_id"],
                event_id=event_dict["event_id"],
                event_type=event_dict["event_type"],
                period=event_dict["period"],
                time_in_period=event_dict["time_in_period"],
                time_remaining=event_dict["time_remaining"],
                game_seconds=event_dict["game_seconds"],
                segment=event_dict.get("segment"),
                team_id=event_dict.get("team_id"),
                team_abbrev=event_dict.get("team_abbrev"),
                player_id=event_dict.get("player_id"),
                player_name=event_dict.get("player_name"),
                x_coord=event_dict.get("x_coord"),
                y_coord=event_dict.get("y_coord"),
                details=event_dict.get("details", {}),
            )
            events.append(event)

        logger.info(f"Loaded {len(events)} timed events from {path}")
        return events

    def close(self) -> None:
        """Close resources if we own the API client."""
        if self._owns_client:
            self.api_client.close()

    def __enter__(self) -> "TimestampDataCollector":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
