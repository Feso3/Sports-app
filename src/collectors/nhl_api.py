"""
NHL API Client

Core client for interacting with the NHL Stats API.
Handles authentication, rate limiting, caching, and request management.
"""

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import yaml
from diskcache import Cache
from loguru import logger


class RateLimiter:
    """Simple rate limiter to prevent API throttling."""

    def __init__(self, requests_per_minute: int = 60, request_delay: float = 0.5):
        self.requests_per_minute = requests_per_minute
        self.request_delay = request_delay
        self.last_request_time: float = 0
        self.request_count: int = 0
        self.window_start: float = time.time()

    def wait_if_needed(self) -> None:
        """Wait if we're hitting rate limits."""
        current_time = time.time()

        # Reset window if a minute has passed
        if current_time - self.window_start >= 60:
            self.request_count = 0
            self.window_start = current_time

        # Check if we've hit the rate limit
        if self.request_count >= self.requests_per_minute:
            sleep_time = 60 - (current_time - self.window_start)
            if sleep_time > 0:
                logger.debug(f"Rate limit reached, sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)
            self.request_count = 0
            self.window_start = time.time()

        # Ensure minimum delay between requests
        elapsed = current_time - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)

        self.last_request_time = time.time()
        self.request_count += 1


class NHLApiClient:
    """
    Client for NHL Stats API.

    Provides methods to fetch game data, player statistics, schedules,
    and play-by-play information from the NHL API.
    """

    def __init__(self, config_path: str | Path | None = None):
        """
        Initialize the NHL API client.

        Args:
            config_path: Path to API configuration file. Defaults to config/api_config.yaml
        """
        self.config = self._load_config(config_path)
        self.base_url = self.config["api"]["base_url"]
        self.stats_base_url = self.config["api"]["stats_base_url"]
        self.legacy_base_url = self.config["api"]["legacy_base_url"]
        self.timeout = self.config["api"]["timeout"]

        # Set up rate limiting
        rate_config = self.config["api"]["rate_limit"]
        self.rate_limiter = RateLimiter(
            requests_per_minute=rate_config["requests_per_minute"],
            request_delay=rate_config["request_delay"],
        )
        self.max_retries = rate_config["max_retries"]
        self.retry_delay = rate_config["retry_delay"]
        self.retry_backoff = rate_config["retry_backoff"]

        # Set up caching
        cache_config = self.config["collection"]["cache"]
        self.cache_enabled = cache_config["enabled"]
        self.cache_ttl = timedelta(hours=cache_config["ttl_hours"])
        if self.cache_enabled:
            cache_dir = Path(cache_config["directory"])
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache = Cache(str(cache_dir))
        else:
            self.cache = None

        # Set up HTTP client
        self.client = httpx.Client(timeout=self.timeout)

        logger.info("NHL API client initialized")

    def _load_config(self, config_path: str | Path | None) -> dict[str, Any]:
        """Load configuration from YAML file."""
        if config_path is None:
            config_path = Path("config/api_config.yaml")
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path) as f:
            return yaml.safe_load(f)

    def _get_cache_key(self, endpoint: str, params: dict[str, Any] | None = None) -> str:
        """Generate a cache key for the request."""
        key = endpoint
        if params:
            sorted_params = sorted(params.items())
            key += "?" + "&".join(f"{k}={v}" for k, v in sorted_params)
        return key

    def _make_request(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Make an HTTP request with rate limiting, caching, and retry logic.

        Args:
            url: Full URL to request
            params: Query parameters
            use_cache: Whether to use caching for this request

        Returns:
            JSON response data

        Raises:
            httpx.HTTPError: If request fails after all retries
        """
        cache_key = self._get_cache_key(url, params)

        # Check cache first
        if use_cache and self.cache is not None:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {url}")
                return cached

        # Make request with retry logic
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                self.rate_limiter.wait_if_needed()
                response = self.client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                # Cache the response
                if use_cache and self.cache is not None:
                    self.cache.set(
                        cache_key, data, expire=self.cache_ttl.total_seconds()
                    )

                return data

            except httpx.HTTPError as e:
                last_error = e
                if attempt < self.max_retries:
                    sleep_time = self.retry_delay * (self.retry_backoff**attempt)
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.max_retries + 1}), "
                        f"retrying in {sleep_time}s: {e}"
                    )
                    time.sleep(sleep_time)

        logger.error(f"Request failed after {self.max_retries + 1} attempts: {url}")
        raise last_error  # type: ignore

    def _build_url(self, endpoint: str, **kwargs: Any) -> str:
        """Build full URL from endpoint template."""
        formatted_endpoint = endpoint.format(**kwargs)
        return f"{self.base_url}{formatted_endpoint}"

    def _build_legacy_url(self, endpoint: str, **kwargs: Any) -> str:
        """Build full URL from legacy endpoint template."""
        formatted_endpoint = endpoint.format(**kwargs)
        return f"{self.legacy_base_url}{formatted_endpoint}"

    def _build_stats_url(self, endpoint: str, **kwargs: Any) -> str:
        """Build full URL from stats API endpoint template."""
        formatted_endpoint = endpoint.format(**kwargs)
        return f"{self.stats_base_url}{formatted_endpoint}"

    # Schedule Methods
    def get_schedule(self, date: str | datetime) -> dict[str, Any]:
        """
        Get schedule for a specific date.

        Args:
            date: Date in YYYY-MM-DD format or datetime object

        Returns:
            Schedule data including all games for the date
        """
        if isinstance(date, datetime):
            date = date.strftime("%Y-%m-%d")

        endpoint = self.config["endpoints"]["schedule"]
        url = self._build_url(endpoint, date=date)
        return self._make_request(url)

    def get_schedule_range(
        self, start_date: str | datetime, end_date: str | datetime
    ) -> dict[str, Any]:
        """
        Get schedule for a date range using legacy API.

        Args:
            start_date: Start date in YYYY-MM-DD format or datetime
            end_date: End date in YYYY-MM-DD format or datetime

        Returns:
            Schedule data for the date range
        """
        if isinstance(start_date, datetime):
            start_date = start_date.strftime("%Y-%m-%d")
        if isinstance(end_date, datetime):
            end_date = end_date.strftime("%Y-%m-%d")

        endpoint = self.config["endpoints"]["legacy"]["schedule"]
        url = self._build_legacy_url(
            endpoint, start_date=start_date, end_date=end_date
        )
        return self._make_request(url)

    # Game Methods
    def get_game_landing(self, game_id: int | str) -> dict[str, Any]:
        """
        Get landing page data for a game.

        Args:
            game_id: NHL game ID

        Returns:
            Game landing data including scores, teams, etc.
        """
        endpoint = self.config["endpoints"]["game_landing"]
        url = self._build_url(endpoint, game_id=game_id)
        return self._make_request(url)

    def get_game_boxscore(self, game_id: int | str) -> dict[str, Any]:
        """
        Get boxscore data for a game.

        Args:
            game_id: NHL game ID

        Returns:
            Complete boxscore including player stats
        """
        endpoint = self.config["endpoints"]["game_boxscore"]
        url = self._build_url(endpoint, game_id=game_id)
        return self._make_request(url)

    def get_game_play_by_play(self, game_id: int | str) -> dict[str, Any]:
        """
        Get play-by-play data for a game.

        Args:
            game_id: NHL game ID

        Returns:
            Detailed play-by-play data including all events
        """
        endpoint = self.config["endpoints"]["game_play_by_play"]
        url = self._build_url(endpoint, game_id=game_id)
        return self._make_request(url)

    def get_game_feed(self, game_id: int | str) -> dict[str, Any]:
        """
        Get full game feed using legacy API.

        Args:
            game_id: NHL game ID

        Returns:
            Complete game feed with play-by-play and boxscore
        """
        endpoint = self.config["endpoints"]["legacy"]["game"]
        url = self._build_legacy_url(endpoint, game_id=game_id)
        return self._make_request(url)

    # Player Methods
    def get_player_landing(self, player_id: int | str) -> dict[str, Any]:
        """
        Get player landing page data.

        Args:
            player_id: NHL player ID

        Returns:
            Player biographical and current stats data
        """
        endpoint = self.config["endpoints"]["player_landing"]
        url = self._build_url(endpoint, player_id=player_id)
        return self._make_request(url)

    def get_player_game_log(
        self, player_id: int | str, season: str, game_type: int = 2
    ) -> dict[str, Any]:
        """
        Get player's game log for a season.

        Args:
            player_id: NHL player ID
            season: Season in YYYYYYYY format (e.g., "20232024")
            game_type: Game type (2=regular season, 3=playoffs)

        Returns:
            Game-by-game statistics for the player
        """
        endpoint = self.config["endpoints"]["player_game_log"]
        url = self._build_url(
            endpoint, player_id=player_id, season=season, game_type=game_type
        )
        return self._make_request(url)

    def get_player_info(self, player_id: int | str) -> dict[str, Any]:
        """
        Get player information using legacy API.

        Args:
            player_id: NHL player ID

        Returns:
            Player biographical information
        """
        endpoint = self.config["endpoints"]["legacy"]["player"]
        url = self._build_legacy_url(endpoint, player_id=player_id)
        return self._make_request(url)

    # Team Methods
    def get_team_roster(self, team_abbrev: str) -> dict[str, Any]:
        """
        Get current team roster.

        Args:
            team_abbrev: Team abbreviation (e.g., "TOR", "NYR")

        Returns:
            Current roster data
        """
        endpoint = self.config["endpoints"]["team_roster"]
        url = self._build_url(endpoint, team_abbrev=team_abbrev)
        return self._make_request(url)

    def get_team_schedule(
        self, team_abbrev: str, date: str | datetime | None = None
    ) -> dict[str, Any]:
        """
        Get team schedule for a week.

        Args:
            team_abbrev: Team abbreviation
            date: Date for the week (defaults to current week)

        Returns:
            Weekly schedule for the team
        """
        if date is None:
            date = datetime.now()
        if isinstance(date, datetime):
            date = date.strftime("%Y-%m-%d")

        endpoint = self.config["endpoints"]["team_schedule"]
        url = self._build_url(endpoint, team_abbrev=team_abbrev, date=date)
        return self._make_request(url)

    def get_all_teams(self) -> dict[str, Any]:
        """
        Get list of all NHL teams using stats API.

        Returns:
            List of all teams with basic information
        """
        endpoint = self.config["endpoints"]["stats"]["teams"]
        url = self._build_stats_url(endpoint)
        return self._make_request(url)

    # Standings Methods
    def get_standings(self, date: str | datetime | None = None) -> dict[str, Any]:
        """
        Get league standings for a date.

        Args:
            date: Date for standings (defaults to current)

        Returns:
            League standings data
        """
        if date is None:
            date = datetime.now()
        if isinstance(date, datetime):
            date = date.strftime("%Y-%m-%d")

        endpoint = self.config["endpoints"]["standings"]
        url = self._build_url(endpoint, date=date)
        return self._make_request(url)

    # Utility Methods
    def get_season_games(
        self, season: str, game_types: list[int] | None = None
    ) -> list[dict[str, Any]]:
        """
        Get all games for a season.

        Args:
            season: Season in YYYYYYYY format (e.g., "20232024")
            game_types: List of game types to include (default from config)

        Returns:
            List of all games in the season
        """
        if game_types is None:
            game_types = self.config["collection"]["game_types"]

        # Calculate season date range
        start_year = int(season[:4])
        start_date = f"{start_year}-09-01"
        end_date = f"{start_year + 1}-07-01"

        schedule_data = self.get_schedule_range(start_date, end_date)

        games = []
        for date_entry in schedule_data.get("dates", []):
            for game in date_entry.get("games", []):
                if game.get("gameType") in game_types:
                    games.append(game)

        logger.info(f"Found {len(games)} games for season {season}")
        return games

    def clear_cache(self) -> None:
        """Clear the request cache."""
        if self.cache is not None:
            self.cache.clear()
            logger.info("Cache cleared")

    def close(self) -> None:
        """Close the HTTP client and cache."""
        self.client.close()
        if self.cache is not None:
            self.cache.close()

    def __enter__(self) -> "NHLApiClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
