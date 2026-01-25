"""
Data Loader Service

Manages data caching and loading for team and player information.
Provides offline fallback capability and refresh commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from diskcache import Cache
from loguru import logger

from src.collectors.nhl_api import NHLApiClient
from src.models.player import Player, PlayerPosition, PlayerStats
from src.models.team import Team, TeamRoster, TeamStats


@dataclass
class CacheStatus:
    """Status information about cached data."""

    teams_cached: int = 0
    players_cached: int = 0
    last_refresh: datetime | None = None
    cache_size_mb: float = 0.0
    is_stale: bool = False
    stale_teams: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for display."""
        return {
            "teams_cached": self.teams_cached,
            "players_cached": self.players_cached,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "cache_size_mb": round(self.cache_size_mb, 2),
            "is_stale": self.is_stale,
            "stale_teams": self.stale_teams,
        }


class DataLoader:
    """
    Data loading service with caching layer.

    Manages fetching and caching of team/player data from NHL API,
    with offline fallback capability.
    """

    # Cache TTL in seconds
    TEAM_CACHE_TTL = 86400  # 24 hours
    ROSTER_CACHE_TTL = 43200  # 12 hours
    PLAYER_CACHE_TTL = 86400  # 24 hours

    # Cache key prefixes
    TEAM_PREFIX = "team:"
    ROSTER_PREFIX = "roster:"
    PLAYER_PREFIX = "player:"
    TEAMS_LIST_KEY = "all_teams"
    LAST_REFRESH_KEY = "last_refresh"

    def __init__(
        self,
        api_client: NHLApiClient | None = None,
        cache_dir: str | Path = "data/service_cache",
    ) -> None:
        """
        Initialize the data loader.

        Args:
            api_client: NHL API client (creates one if not provided)
            cache_dir: Directory for service-level cache
        """
        self.api_client = api_client or NHLApiClient()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache = Cache(str(self.cache_dir))

        # In-memory cache for current session
        self._teams: dict[int, Team] = {}
        self._players: dict[int, Player] = {}

        logger.info(f"DataLoader initialized with cache at {self.cache_dir}")

    def get_available_teams(self) -> list[dict[str, Any]]:
        """
        Get list of all available NHL teams.

        Returns:
            List of team info dicts with id, name, abbreviation
        """
        # Check cache first
        cached = self.cache.get(self.TEAMS_LIST_KEY)
        if cached is not None:
            logger.debug("Using cached teams list")
            return cached

        try:
            # Fetch from API
            data = self.api_client.get_all_teams()
            teams = []

            for team_data in data.get("teams", []):
                teams.append({
                    "team_id": team_data["id"],
                    "name": team_data["name"],
                    "abbreviation": team_data.get("abbreviation", ""),
                    "division": team_data.get("division", {}).get("name", ""),
                    "conference": team_data.get("conference", {}).get("name", ""),
                })

            # Cache the list
            self.cache.set(
                self.TEAMS_LIST_KEY, teams, expire=self.TEAM_CACHE_TTL
            )

            logger.info(f"Loaded {len(teams)} teams from API")
            return teams

        except Exception as e:
            logger.warning(f"Failed to fetch teams from API: {e}")
            # Return cached if available (even if expired)
            cached = self.cache.get(self.TEAMS_LIST_KEY)
            if cached is not None:
                logger.info("Using expired cache for teams list")
                return cached
            raise

    def load_team(self, team_id: int | None = None, team_abbrev: str | None = None) -> Team:
        """
        Load a team with full data.

        Args:
            team_id: Team ID
            team_abbrev: Team abbreviation (alternative to team_id)

        Returns:
            Team object with roster and stats
        """
        if team_id is None and team_abbrev is None:
            raise ValueError("Must provide either team_id or team_abbrev")

        # Resolve team_id from abbreviation if needed
        if team_id is None:
            teams = self.get_available_teams()
            for t in teams:
                if t["abbreviation"].upper() == team_abbrev.upper():
                    team_id = t["team_id"]
                    break
            if team_id is None:
                raise ValueError(f"Team not found: {team_abbrev}")

        # Check in-memory cache
        if team_id in self._teams:
            return self._teams[team_id]

        # Check disk cache
        cache_key = f"{self.TEAM_PREFIX}{team_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            team = Team.model_validate(cached)
            self._teams[team_id] = team
            logger.debug(f"Loaded team {team_id} from cache")
            return team

        # Fetch from API
        team = self._fetch_team(team_id)
        self._teams[team_id] = team

        # Cache it
        self.cache.set(cache_key, team.model_dump(), expire=self.TEAM_CACHE_TTL)

        return team

    def _fetch_team(self, team_id: int) -> Team:
        """Fetch team data from API."""
        # Get team info from teams list
        teams = self.get_available_teams()
        team_info = next((t for t in teams if t["team_id"] == team_id), None)

        if team_info is None:
            raise ValueError(f"Team not found: {team_id}")

        team_abbrev = team_info["abbreviation"]

        # Load roster
        roster = self.load_roster(team_abbrev)

        # Build team object
        team = Team(
            team_id=team_id,
            name=team_info["name"],
            abbreviation=team_abbrev,
            division=team_info.get("division", ""),
            conference=team_info.get("conference", ""),
            roster=roster,
            current_season_stats=TeamStats(),  # Would be populated from standings/stats API
        )

        logger.info(f"Fetched team {team.name} ({team.abbreviation})")
        return team

    def load_roster(self, team_abbrev: str) -> TeamRoster:
        """
        Load team roster.

        Args:
            team_abbrev: Team abbreviation

        Returns:
            TeamRoster with player IDs
        """
        cache_key = f"{self.ROSTER_PREFIX}{team_abbrev.upper()}"

        # Check cache
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using cached roster for {team_abbrev}")
            return TeamRoster.model_validate(cached)

        try:
            # Fetch from API
            data = self.api_client.get_team_roster(team_abbrev)

            forwards = []
            defensemen = []
            goalies = []

            for player_data in data.get("forwards", []):
                forwards.append(player_data["id"])

            for player_data in data.get("defensemen", []):
                defensemen.append(player_data["id"])

            for player_data in data.get("goalies", []):
                goalies.append(player_data["id"])

            roster = TeamRoster(
                forwards=forwards,
                defensemen=defensemen,
                goalies=goalies,
            )

            # Cache it
            self.cache.set(cache_key, roster.model_dump(), expire=self.ROSTER_CACHE_TTL)

            logger.info(
                f"Loaded roster for {team_abbrev}: "
                f"{len(forwards)}F, {len(defensemen)}D, {len(goalies)}G"
            )
            return roster

        except Exception as e:
            logger.warning(f"Failed to fetch roster: {e}")
            # Try expired cache
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.info(f"Using expired cache for {team_abbrev} roster")
                return TeamRoster.model_validate(cached)
            raise

    def load_player(self, player_id: int) -> Player:
        """
        Load player data.

        Args:
            player_id: NHL player ID

        Returns:
            Player object with stats
        """
        # Check in-memory cache
        if player_id in self._players:
            return self._players[player_id]

        # Check disk cache
        cache_key = f"{self.PLAYER_PREFIX}{player_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            player = Player.model_validate(cached)
            self._players[player_id] = player
            return player

        # Fetch from API
        player = self._fetch_player(player_id)
        self._players[player_id] = player

        # Cache it
        self.cache.set(cache_key, player.model_dump(), expire=self.PLAYER_CACHE_TTL)

        return player

    def _fetch_player(self, player_id: int) -> Player:
        """Fetch player data from API."""
        try:
            data = self.api_client.get_player_landing(player_id)

            # Parse position
            position_code = data.get("position", "U")
            position_map = {
                "C": PlayerPosition.CENTER,
                "L": PlayerPosition.LEFT_WING,
                "LW": PlayerPosition.LEFT_WING,
                "R": PlayerPosition.RIGHT_WING,
                "RW": PlayerPosition.RIGHT_WING,
                "D": PlayerPosition.DEFENSEMAN,
                "G": PlayerPosition.GOALIE,
            }
            position = position_map.get(position_code, PlayerPosition.UNKNOWN)

            # Build career stats from featured stats
            career_stats = PlayerStats()
            featured = data.get("featuredStats", {})
            if "regularSeason" in featured:
                career = featured["regularSeason"].get("career", {})
                career_stats.games_played = career.get("gamesPlayed", 0)
                career_stats.goals = career.get("goals", 0)
                career_stats.assists = career.get("assists", 0)
                career_stats.points = career.get("points", 0)

            player = Player(
                player_id=player_id,
                full_name=f"{data.get('firstName', {}).get('default', '')} {data.get('lastName', {}).get('default', '')}".strip(),
                first_name=data.get("firstName", {}).get("default", ""),
                last_name=data.get("lastName", {}).get("default", ""),
                position=position,
                position_code=position_code,
                current_team_id=data.get("currentTeamId"),
                current_team_abbrev=data.get("currentTeamAbbrev"),
                jersey_number=data.get("sweaterNumber"),
                height_inches=data.get("heightInInches"),
                weight_pounds=data.get("weightInPounds"),
                shoots_catches=data.get("shootsCatches"),
                birth_date=data.get("birthDate"),
                birth_city=data.get("birthCity", {}).get("default"),
                birth_country=data.get("birthCountry"),
                career_stats=career_stats,
            )

            logger.debug(f"Fetched player {player.full_name}")
            return player

        except Exception as e:
            logger.warning(f"Failed to fetch player {player_id}: {e}")
            # Return minimal player object
            return Player(
                player_id=player_id,
                full_name=f"Player {player_id}",
            )

    def load_team_players(self, team: Team) -> dict[int, Player]:
        """
        Load all players for a team.

        Args:
            team: Team object

        Returns:
            Dict mapping player_id to Player
        """
        players = {}

        for player_id in team.roster.all_players:
            try:
                player = self.load_player(player_id)
                players[player_id] = player
            except Exception as e:
                logger.warning(f"Failed to load player {player_id}: {e}")

        logger.info(f"Loaded {len(players)} players for {team.name}")
        return players

    def refresh_team_data(self, team_id: int | None = None, team_abbrev: str | None = None) -> None:
        """
        Force refresh of team data from API.

        Args:
            team_id: Team ID to refresh
            team_abbrev: Team abbreviation to refresh
        """
        # Resolve both team_id and team_abbrev from teams list
        teams = self.get_available_teams()
        resolved_id = team_id
        resolved_abbrev = team_abbrev

        if team_id is not None:
            # Find abbreviation for this team_id
            for t in teams:
                if t["team_id"] == team_id:
                    resolved_abbrev = t["abbreviation"]
                    break
        elif team_abbrev is not None:
            # Find team_id for this abbreviation
            for t in teams:
                if t["abbreviation"].upper() == team_abbrev.upper():
                    resolved_id = t["team_id"]
                    resolved_abbrev = t["abbreviation"]
                    break

        if resolved_id is None:
            raise ValueError("Team not found")

        # Clear team from caches
        cache_key = f"{self.TEAM_PREFIX}{resolved_id}"
        self.cache.delete(cache_key)
        self._teams.pop(resolved_id, None)

        # Clear roster from cache
        if resolved_abbrev:
            roster_key = f"{self.ROSTER_PREFIX}{resolved_abbrev.upper()}"
            self.cache.delete(roster_key)

        # Get current player IDs before refresh (if we have them cached)
        old_player_ids = []
        if resolved_id in self._teams:
            old_player_ids = self._teams[resolved_id].roster.all_players

        # Reload team (this will fetch fresh roster)
        team = self.load_team(team_id=resolved_id)

        # Clear and refresh players
        player_ids_to_refresh = set(old_player_ids) | set(team.roster.all_players)
        for player_id in player_ids_to_refresh:
            player_key = f"{self.PLAYER_PREFIX}{player_id}"
            self.cache.delete(player_key)
            self._players.pop(player_id, None)

        self.load_team_players(team)

        # Update refresh timestamp
        self.cache.set(self.LAST_REFRESH_KEY, datetime.now().isoformat())

        logger.info(f"Refreshed data for team {team.name}")

    def get_cache_status(self) -> CacheStatus:
        """
        Get current cache status.

        Returns:
            CacheStatus with cache statistics
        """
        status = CacheStatus()

        # Count cached items
        for key in self.cache.iterkeys():
            if key.startswith(self.TEAM_PREFIX):
                status.teams_cached += 1
            elif key.startswith(self.PLAYER_PREFIX):
                status.players_cached += 1

        # Get last refresh
        last_refresh = self.cache.get(self.LAST_REFRESH_KEY)
        if last_refresh:
            status.last_refresh = datetime.fromisoformat(last_refresh)

        # Calculate cache size
        cache_path = self.cache_dir / "cache.db"
        if cache_path.exists():
            status.cache_size_mb = cache_path.stat().st_size / (1024 * 1024)

        # Check staleness (older than 24 hours)
        if status.last_refresh:
            age = datetime.now() - status.last_refresh
            if age.total_seconds() > self.TEAM_CACHE_TTL:
                status.is_stale = True

        return status

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self.cache.clear()
        self._teams.clear()
        self._players.clear()
        logger.info("Cache cleared")

    def close(self) -> None:
        """Close resources."""
        self.cache.close()
        self.api_client.close()

    def __enter__(self) -> "DataLoader":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
