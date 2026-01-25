"""
Shot Data Collector

Collects shot location and outcome data from NHL games.
Extracts coordinates, shot types, shooter information, and results.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.collectors.nhl_api import NHLApiClient


@dataclass
class Shot:
    """Represents a single shot event."""

    game_id: str
    event_id: int
    period: int
    time_in_period: str
    time_remaining: str
    shooter_id: int
    shooter_name: str
    team_id: int
    team_abbrev: str
    shot_type: str | None
    x_coord: float | None
    y_coord: float | None
    distance: float | None
    is_goal: bool
    goalie_id: int | None = None
    goalie_name: str | None = None
    assists: list[dict[str, Any]] = field(default_factory=list)
    strength: str | None = None  # even, pp, sh
    empty_net: bool = False
    game_winning_goal: bool = False
    event_description: str | None = None


class ShotDataCollector:
    """
    Collector for shot location and outcome data.

    Extracts shot events from play-by-play data including:
    - Shot coordinates (x, y)
    - Shot type (wrist, slap, snap, etc.)
    - Shooter identity
    - Shot result (goal, save, miss, blocked)
    - Goalie information
    - Strength state (even, power play, shorthanded)
    """

    # Shot event types to capture
    SHOT_EVENT_TYPES = {"shot-on-goal", "goal", "missed-shot", "blocked-shot"}

    # Map API shot types to standardized names
    SHOT_TYPE_MAP = {
        "wrist": "wrist",
        "slap": "slap",
        "snap": "snap",
        "backhand": "backhand",
        "deflected": "deflection",
        "tip-in": "tip_in",
        "wrap-around": "wrap_around",
        "bat": "bat",
        "poke": "poke",
        "cradle": "cradle",
    }

    def __init__(self, api_client: NHLApiClient | None = None):
        """
        Initialize the shot data collector.

        Args:
            api_client: NHL API client instance. Creates one if not provided.
        """
        self.api_client = api_client or NHLApiClient()
        self._owns_client = api_client is None

    def collect_game_shots(self, game_id: int | str) -> list[Shot]:
        """
        Collect all shot data from a single game.

        Args:
            game_id: NHL game ID

        Returns:
            List of Shot objects for all shots in the game
        """
        logger.info(f"Collecting shot data for game {game_id}")

        try:
            play_by_play = self.api_client.get_game_play_by_play(game_id)
        except Exception as e:
            logger.error(f"Failed to get play-by-play for game {game_id}: {e}")
            return []

        shots = []
        plays = play_by_play.get("plays", [])

        for play in plays:
            event_type = play.get("typeDescKey", "").lower()

            if event_type in self.SHOT_EVENT_TYPES:
                shot = self._parse_shot_event(play, str(game_id))
                if shot:
                    shots.append(shot)

        logger.info(f"Collected {len(shots)} shots from game {game_id}")
        return shots

    def collect_season_shots(
        self,
        season: str,
        game_types: list[int] | None = None,
        save_path: Path | str | None = None,
    ) -> list[Shot]:
        """
        Collect all shot data for a season.

        Args:
            season: Season in YYYYYYYY format (e.g., "20232024")
            game_types: Game types to include (default: regular season + playoffs)
            save_path: Optional path to save collected data

        Returns:
            List of all shots from the season
        """
        logger.info(f"Collecting shot data for season {season}")

        games = self.api_client.get_season_games(season, game_types)
        all_shots = []

        for i, game in enumerate(games):
            # Handle both old API (gamePk) and new API (id) field names
            game_id = game.get("id", game.get("gamePk"))
            if game_id:
                shots = self.collect_game_shots(game_id)
                all_shots.extend(shots)

                if (i + 1) % 100 == 0:
                    logger.info(f"Processed {i + 1}/{len(games)} games")

        logger.info(f"Collected {len(all_shots)} total shots for season {season}")

        if save_path:
            self.save_shots(all_shots, save_path)

        return all_shots

    def _parse_shot_event(self, play: dict[str, Any], game_id: str) -> Shot | None:
        """
        Parse a play-by-play event into a Shot object.

        Args:
            play: Play event data from API
            game_id: NHL game ID

        Returns:
            Shot object or None if parsing fails
        """
        try:
            event_type = play.get("typeDescKey", "").lower()
            is_goal = event_type == "goal"

            # Get shooter information
            details = play.get("details", {})
            shooter_id = details.get("shootingPlayerId") or details.get("scoringPlayerId")
            if not shooter_id:
                return None

            # Get coordinates
            x_coord = details.get("xCoord")
            y_coord = details.get("yCoord")

            # Get period and time info
            period_descriptor = play.get("periodDescriptor", {})
            period = period_descriptor.get("number", 0)
            time_in_period = play.get("timeInPeriod", "00:00")
            time_remaining = play.get("timeRemaining", "20:00")

            # Get shot type
            shot_type_raw = details.get("shotType", "").lower()
            shot_type = self.SHOT_TYPE_MAP.get(shot_type_raw, shot_type_raw)

            # Get team info
            event_owner_team_id = details.get("eventOwnerTeamId")

            # Get goalie info
            goalie_id = details.get("goalieInNetId")

            # Get situation (strength)
            situation = play.get("situationCode", "")
            strength = self._determine_strength(situation, event_owner_team_id, play)

            # Get assists for goals
            assists = []
            if is_goal:
                assist1_id = details.get("assist1PlayerId")
                assist2_id = details.get("assist2PlayerId")
                if assist1_id:
                    assists.append({"player_id": assist1_id, "assist_type": "primary"})
                if assist2_id:
                    assists.append({"player_id": assist2_id, "assist_type": "secondary"})

            shot = Shot(
                game_id=game_id,
                event_id=play.get("eventId", 0),
                period=period,
                time_in_period=time_in_period,
                time_remaining=time_remaining,
                shooter_id=shooter_id,
                shooter_name=details.get("scoringPlayerName", ""),
                team_id=event_owner_team_id or 0,
                team_abbrev=details.get("eventOwnerTeamAbbrev", ""),
                shot_type=shot_type if shot_type else None,
                x_coord=x_coord,
                y_coord=y_coord,
                distance=details.get("shotDistance"),
                is_goal=is_goal,
                goalie_id=goalie_id,
                goalie_name=None,  # Would need additional lookup
                assists=assists,
                strength=strength,
                empty_net=details.get("emptyNet", False),
                game_winning_goal=details.get("gameWinningGoal", False),
                event_description=play.get("typeDescKey"),
            )

            return shot

        except Exception as e:
            logger.warning(f"Failed to parse shot event: {e}")
            return None

    def _determine_strength(
        self, situation_code: str, team_id: int | None, play: dict[str, Any]
    ) -> str | None:
        """
        Determine the strength state (even, pp, sh) from situation code.

        Args:
            situation_code: Situation code from play data
            team_id: Team ID of the shooting team
            play: Full play data

        Returns:
            Strength state string or None
        """
        if not situation_code or len(situation_code) < 4:
            return None

        try:
            # Situation code format: HHAA where HH=home skaters, AA=away skaters
            home_skaters = int(situation_code[:2])
            away_skaters = int(situation_code[2:4])

            # Determine if shooting team is home or away
            home_team_id = play.get("homeTeamId")
            is_home_team = team_id == home_team_id

            if is_home_team:
                own_skaters = home_skaters
                opp_skaters = away_skaters
            else:
                own_skaters = away_skaters
                opp_skaters = home_skaters

            if own_skaters > opp_skaters:
                return "pp"  # Power play
            elif own_skaters < opp_skaters:
                return "sh"  # Shorthanded
            else:
                return "even"

        except (ValueError, IndexError):
            return None

    def save_shots(self, shots: list[Shot], path: Path | str) -> None:
        """
        Save shot data to JSON file.

        Args:
            shots: List of Shot objects
            path: File path to save to
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Convert dataclass instances to dictionaries
        shots_data = []
        for shot in shots:
            shot_dict = {
                "game_id": shot.game_id,
                "event_id": shot.event_id,
                "period": shot.period,
                "time_in_period": shot.time_in_period,
                "time_remaining": shot.time_remaining,
                "shooter_id": shot.shooter_id,
                "shooter_name": shot.shooter_name,
                "team_id": shot.team_id,
                "team_abbrev": shot.team_abbrev,
                "shot_type": shot.shot_type,
                "x_coord": shot.x_coord,
                "y_coord": shot.y_coord,
                "distance": shot.distance,
                "is_goal": shot.is_goal,
                "goalie_id": shot.goalie_id,
                "goalie_name": shot.goalie_name,
                "assists": shot.assists,
                "strength": shot.strength,
                "empty_net": shot.empty_net,
                "game_winning_goal": shot.game_winning_goal,
                "event_description": shot.event_description,
            }
            shots_data.append(shot_dict)

        with open(path, "w") as f:
            json.dump(shots_data, f, indent=2)

        logger.info(f"Saved {len(shots)} shots to {path}")

    def load_shots(self, path: Path | str) -> list[Shot]:
        """
        Load shot data from JSON file.

        Args:
            path: File path to load from

        Returns:
            List of Shot objects
        """
        path = Path(path)

        with open(path) as f:
            shots_data = json.load(f)

        shots = []
        for shot_dict in shots_data:
            shot = Shot(
                game_id=shot_dict["game_id"],
                event_id=shot_dict["event_id"],
                period=shot_dict["period"],
                time_in_period=shot_dict["time_in_period"],
                time_remaining=shot_dict["time_remaining"],
                shooter_id=shot_dict["shooter_id"],
                shooter_name=shot_dict["shooter_name"],
                team_id=shot_dict["team_id"],
                team_abbrev=shot_dict["team_abbrev"],
                shot_type=shot_dict.get("shot_type"),
                x_coord=shot_dict.get("x_coord"),
                y_coord=shot_dict.get("y_coord"),
                distance=shot_dict.get("distance"),
                is_goal=shot_dict["is_goal"],
                goalie_id=shot_dict.get("goalie_id"),
                goalie_name=shot_dict.get("goalie_name"),
                assists=shot_dict.get("assists", []),
                strength=shot_dict.get("strength"),
                empty_net=shot_dict.get("empty_net", False),
                game_winning_goal=shot_dict.get("game_winning_goal", False),
                event_description=shot_dict.get("event_description"),
            )
            shots.append(shot)

        logger.info(f"Loaded {len(shots)} shots from {path}")
        return shots

    def close(self) -> None:
        """Close resources if we own the API client."""
        if self._owns_client:
            self.api_client.close()

    def __enter__(self) -> "ShotDataCollector":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
