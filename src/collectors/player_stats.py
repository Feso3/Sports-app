"""
Player Stats Collector

Collects individual player statistics from NHL API.
Builds player profile database with career and season statistics.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.collectors.nhl_api import NHLApiClient


@dataclass
class PlayerProfile:
    """Comprehensive player profile with biographical and statistical data."""

    player_id: int
    full_name: str
    first_name: str
    last_name: str
    birth_date: str | None
    birth_city: str | None
    birth_country: str | None
    nationality: str | None
    height_inches: int | None
    weight_pounds: int | None
    position: str
    position_code: str
    shoots_catches: str | None
    current_team_id: int | None = None
    current_team_abbrev: str | None = None
    jersey_number: int | None = None
    is_active: bool = True
    rookie: bool = False
    draft_year: int | None = None
    draft_round: int | None = None
    draft_pick: int | None = None
    career_stats: dict[str, Any] = field(default_factory=dict)
    season_stats: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class GameLogEntry:
    """Single game entry from a player's game log."""

    game_id: str
    game_date: str
    opponent_abbrev: str
    home_road: str
    goals: int
    assists: int
    points: int
    plus_minus: int
    pim: int  # Penalties in minutes
    shots: int
    toi: str  # Time on ice
    power_play_goals: int = 0
    power_play_points: int = 0
    shorthanded_goals: int = 0
    shorthanded_points: int = 0
    game_winning_goals: int = 0
    ot_goals: int = 0
    shifts: int = 0


class PlayerStatsCollector:
    """
    Collector for individual player statistics.

    Provides methods to:
    - Fetch player biographical information
    - Collect season and career statistics
    - Build game-by-game logs for detailed analysis
    - Aggregate stats across multiple seasons
    """

    def __init__(self, api_client: NHLApiClient | None = None):
        """
        Initialize the player stats collector.

        Args:
            api_client: NHL API client instance. Creates one if not provided.
        """
        self.api_client = api_client or NHLApiClient()
        self._owns_client = api_client is None
        self._player_cache: dict[int, PlayerProfile] = {}

    def get_player_profile(
        self, player_id: int, use_cache: bool = True
    ) -> PlayerProfile | None:
        """
        Get comprehensive player profile.

        Args:
            player_id: NHL player ID
            use_cache: Whether to use cached data

        Returns:
            PlayerProfile object or None if not found
        """
        if use_cache and player_id in self._player_cache:
            return self._player_cache[player_id]

        try:
            data = self.api_client.get_player_landing(player_id)
        except Exception as e:
            logger.error(f"Failed to fetch player {player_id}: {e}")
            return None

        profile = self._parse_player_data(data)
        if profile:
            self._player_cache[player_id] = profile

        return profile

    def get_player_game_log(
        self,
        player_id: int,
        season: str,
        game_type: int = 2,
    ) -> list[GameLogEntry]:
        """
        Get player's game-by-game statistics for a season.

        Args:
            player_id: NHL player ID
            season: Season in YYYYYYYY format (e.g., "20232024")
            game_type: Game type (2=regular season, 3=playoffs)

        Returns:
            List of GameLogEntry objects
        """
        try:
            data = self.api_client.get_player_game_log(player_id, season, game_type)
        except Exception as e:
            logger.error(
                f"Failed to fetch game log for player {player_id}, "
                f"season {season}: {e}"
            )
            return []

        return self._parse_game_log(data)

    def get_player_seasons(
        self,
        player_id: int,
        seasons: list[str],
        game_type: int = 2,
    ) -> dict[str, list[GameLogEntry]]:
        """
        Get player statistics across multiple seasons.

        Args:
            player_id: NHL player ID
            seasons: List of seasons in YYYYYYYY format
            game_type: Game type (2=regular season, 3=playoffs)

        Returns:
            Dictionary mapping season to list of game log entries
        """
        season_data = {}
        for season in seasons:
            game_log = self.get_player_game_log(player_id, season, game_type)
            if game_log:
                season_data[season] = game_log

        return season_data

    def collect_team_roster_profiles(
        self, team_abbrev: str
    ) -> list[PlayerProfile]:
        """
        Collect profiles for all players on a team's current roster.

        Args:
            team_abbrev: Team abbreviation (e.g., "TOR", "NYR")

        Returns:
            List of PlayerProfile objects for the team
        """
        logger.info(f"Collecting roster profiles for {team_abbrev}")

        try:
            roster_data = self.api_client.get_team_roster(team_abbrev)
        except Exception as e:
            logger.error(f"Failed to fetch roster for {team_abbrev}: {e}")
            return []

        profiles = []

        # Process forwards, defensemen, and goalies
        for group in ["forwards", "defensemen", "goalies"]:
            players = roster_data.get(group, [])
            for player in players:
                player_id = player.get("id")
                if player_id:
                    profile = self.get_player_profile(player_id)
                    if profile:
                        profiles.append(profile)

        logger.info(f"Collected {len(profiles)} player profiles for {team_abbrev}")
        return profiles

    def collect_all_active_players(self) -> list[PlayerProfile]:
        """
        Collect profiles for all active NHL players.

        Returns:
            List of all active player profiles
        """
        logger.info("Collecting all active player profiles")

        teams_data = self.api_client.get_all_teams()
        teams = teams_data.get("teams", [])

        all_profiles = []
        seen_ids = set()

        for team in teams:
            team_abbrev = team.get("abbreviation")
            if team_abbrev:
                profiles = self.collect_team_roster_profiles(team_abbrev)
                for profile in profiles:
                    if profile.player_id not in seen_ids:
                        all_profiles.append(profile)
                        seen_ids.add(profile.player_id)

        logger.info(f"Collected {len(all_profiles)} total active player profiles")
        return all_profiles

    def _parse_player_data(self, data: dict[str, Any]) -> PlayerProfile | None:
        """
        Parse API response into PlayerProfile.

        Args:
            data: Raw API response data

        Returns:
            PlayerProfile object or None
        """
        try:
            player_id = data.get("playerId")
            if not player_id:
                return None

            # Parse biographical info
            first_name = data.get("firstName", {}).get("default", "")
            last_name = data.get("lastName", {}).get("default", "")

            # Parse birth info
            birth_date = data.get("birthDate")
            birth_city = data.get("birthCity", {}).get("default")
            birth_country = data.get("birthCountry")

            # Parse physical attributes
            height_str = data.get("heightInInches")
            height_inches = int(height_str) if height_str else None
            weight_pounds = data.get("weightInPounds")

            # Parse position
            position = data.get("position", "Unknown")
            position_code = data.get("positionCode", "U")

            # Parse current team
            current_team_id = data.get("currentTeamId")
            current_team_abbrev = data.get("currentTeamAbbrev")

            # Parse draft info
            draft_details = data.get("draftDetails", {})

            # Parse career stats if available
            career_stats = {}
            career_totals = data.get("careerTotals", {})
            if career_totals:
                regular_season = career_totals.get("regularSeason", {})
                playoffs = career_totals.get("playoffs", {})
                career_stats = {
                    "regular_season": regular_season,
                    "playoffs": playoffs,
                }

            # Parse season stats
            season_stats = {}
            season_totals = data.get("seasonTotals", [])
            for season_entry in season_totals:
                season = str(season_entry.get("season", ""))
                if season:
                    season_stats[season] = season_entry

            profile = PlayerProfile(
                player_id=player_id,
                full_name=f"{first_name} {last_name}".strip(),
                first_name=first_name,
                last_name=last_name,
                birth_date=birth_date,
                birth_city=birth_city,
                birth_country=birth_country,
                nationality=data.get("nationality"),
                height_inches=height_inches,
                weight_pounds=weight_pounds,
                position=position,
                position_code=position_code,
                shoots_catches=data.get("shootsCatches"),
                current_team_id=current_team_id,
                current_team_abbrev=current_team_abbrev,
                jersey_number=data.get("sweaterNumber"),
                is_active=data.get("isActive", True),
                rookie=data.get("rookie", False),
                draft_year=draft_details.get("year"),
                draft_round=draft_details.get("round"),
                draft_pick=draft_details.get("pickInRound"),
                career_stats=career_stats,
                season_stats=season_stats,
            )

            return profile

        except Exception as e:
            logger.warning(f"Failed to parse player data: {e}")
            return None

    def _parse_game_log(self, data: dict[str, Any]) -> list[GameLogEntry]:
        """
        Parse game log API response into list of GameLogEntry objects.

        Args:
            data: Raw API response data

        Returns:
            List of GameLogEntry objects
        """
        entries = []
        game_log = data.get("gameLog", [])

        for game in game_log:
            try:
                entry = GameLogEntry(
                    game_id=str(game.get("gameId", "")),
                    game_date=game.get("gameDate", ""),
                    opponent_abbrev=game.get("opponentAbbrev", ""),
                    home_road=game.get("homeRoadFlag", ""),
                    goals=game.get("goals", 0),
                    assists=game.get("assists", 0),
                    points=game.get("points", 0),
                    plus_minus=game.get("plusMinus", 0),
                    pim=game.get("pim", 0),
                    shots=game.get("shots", 0),
                    toi=game.get("toi", "0:00"),
                    power_play_goals=game.get("powerPlayGoals", 0),
                    power_play_points=game.get("powerPlayPoints", 0),
                    shorthanded_goals=game.get("shorthandedGoals", 0),
                    shorthanded_points=game.get("shorthandedPoints", 0),
                    game_winning_goals=game.get("gameWinningGoals", 0),
                    ot_goals=game.get("otGoals", 0),
                    shifts=game.get("shifts", 0),
                )
                entries.append(entry)
            except Exception as e:
                logger.warning(f"Failed to parse game log entry: {e}")

        return entries

    def save_profiles(self, profiles: list[PlayerProfile], path: Path | str) -> None:
        """
        Save player profiles to JSON file.

        Args:
            profiles: List of PlayerProfile objects
            path: File path to save to
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        profiles_data = []
        for profile in profiles:
            profile_dict = {
                "player_id": profile.player_id,
                "full_name": profile.full_name,
                "first_name": profile.first_name,
                "last_name": profile.last_name,
                "birth_date": profile.birth_date,
                "birth_city": profile.birth_city,
                "birth_country": profile.birth_country,
                "nationality": profile.nationality,
                "height_inches": profile.height_inches,
                "weight_pounds": profile.weight_pounds,
                "position": profile.position,
                "position_code": profile.position_code,
                "shoots_catches": profile.shoots_catches,
                "current_team_id": profile.current_team_id,
                "current_team_abbrev": profile.current_team_abbrev,
                "jersey_number": profile.jersey_number,
                "is_active": profile.is_active,
                "rookie": profile.rookie,
                "draft_year": profile.draft_year,
                "draft_round": profile.draft_round,
                "draft_pick": profile.draft_pick,
                "career_stats": profile.career_stats,
                "season_stats": profile.season_stats,
            }
            profiles_data.append(profile_dict)

        with open(path, "w") as f:
            json.dump(profiles_data, f, indent=2)

        logger.info(f"Saved {len(profiles)} player profiles to {path}")

    def load_profiles(self, path: Path | str) -> list[PlayerProfile]:
        """
        Load player profiles from JSON file.

        Args:
            path: File path to load from

        Returns:
            List of PlayerProfile objects
        """
        path = Path(path)

        with open(path) as f:
            profiles_data = json.load(f)

        profiles = []
        for profile_dict in profiles_data:
            profile = PlayerProfile(
                player_id=profile_dict["player_id"],
                full_name=profile_dict["full_name"],
                first_name=profile_dict["first_name"],
                last_name=profile_dict["last_name"],
                birth_date=profile_dict.get("birth_date"),
                birth_city=profile_dict.get("birth_city"),
                birth_country=profile_dict.get("birth_country"),
                nationality=profile_dict.get("nationality"),
                height_inches=profile_dict.get("height_inches"),
                weight_pounds=profile_dict.get("weight_pounds"),
                position=profile_dict["position"],
                position_code=profile_dict["position_code"],
                shoots_catches=profile_dict.get("shoots_catches"),
                current_team_id=profile_dict.get("current_team_id"),
                current_team_abbrev=profile_dict.get("current_team_abbrev"),
                jersey_number=profile_dict.get("jersey_number"),
                is_active=profile_dict.get("is_active", True),
                rookie=profile_dict.get("rookie", False),
                draft_year=profile_dict.get("draft_year"),
                draft_round=profile_dict.get("draft_round"),
                draft_pick=profile_dict.get("draft_pick"),
                career_stats=profile_dict.get("career_stats", {}),
                season_stats=profile_dict.get("season_stats", {}),
            )
            profiles.append(profile)
            self._player_cache[profile.player_id] = profile

        logger.info(f"Loaded {len(profiles)} player profiles from {path}")
        return profiles

    def close(self) -> None:
        """Close resources if we own the API client."""
        if self._owns_client:
            self.api_client.close()

    def __enter__(self) -> "PlayerStatsCollector":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
