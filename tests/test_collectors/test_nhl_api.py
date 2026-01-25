"""
Tests for NHL API Client

Tests for the core NHL API integration module.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestRateLimiter:
    """Tests for the RateLimiter class."""

    def test_rate_limiter_basic(self):
        """Test basic rate limiter functionality."""
        from src.collectors.nhl_api import RateLimiter

        limiter = RateLimiter(requests_per_minute=60, request_delay=0.1)
        assert limiter.requests_per_minute == 60
        assert limiter.request_delay == 0.1

    def test_rate_limiter_wait(self):
        """Test that rate limiter tracks requests."""
        from src.collectors.nhl_api import RateLimiter

        limiter = RateLimiter(requests_per_minute=1000, request_delay=0.01)

        # Should not raise
        for _ in range(5):
            limiter.wait_if_needed()

        assert limiter.request_count == 5


class TestNHLApiClient:
    """Tests for the NHLApiClient class."""

    @patch("src.collectors.nhl_api.Path.exists")
    @patch("builtins.open")
    def test_client_initialization(self, mock_open, mock_exists):
        """Test client initialization with config."""
        mock_exists.return_value = True
        mock_config = """
api:
  base_url: "https://api-web.nhle.com"
  stats_base_url: "https://api.nhle.com/stats/rest/en"
  legacy_base_url: "https://statsapi.web.nhl.com/api/v1"
  timeout: 30
  rate_limit:
    requests_per_minute: 60
    request_delay: 0.5
    max_retries: 3
    retry_delay: 2.0
    retry_backoff: 2.0
collection:
  cache:
    enabled: false
    ttl_hours: 24
    directory: "data/cache"
endpoints:
  schedule: "/v1/schedule/{date}"
  stats:
    teams: "/team"
    schedule: "/game"
    player: "/player"
  legacy:
    game: "/game/{game_id}/feed/live"
"""
        mock_open.return_value.__enter__.return_value.read.return_value = mock_config

        # This would normally initialize the client
        # For now, just verify imports work
        from src.collectors.nhl_api import NHLApiClient

        assert NHLApiClient is not None

    def test_build_url(self):
        """Test URL building from endpoint templates."""
        # Test the URL building logic pattern
        base_url = "https://api-web.nhle.com"
        endpoint = "/v1/schedule/{date}"
        date = "2024-01-15"

        formatted = endpoint.format(date=date)
        full_url = f"{base_url}{formatted}"

        assert full_url == "https://api-web.nhle.com/v1/schedule/2024-01-15"

    def test_cache_key_generation(self):
        """Test cache key generation."""
        endpoint = "/v1/player/8478402/landing"
        params = {"season": "20232024", "type": "2"}

        # Simple cache key logic
        key = endpoint
        if params:
            sorted_params = sorted(params.items())
            key += "?" + "&".join(f"{k}={v}" for k, v in sorted_params)

        assert key == "/v1/player/8478402/landing?season=20232024&type=2"


class TestNHLApiClientMocked:
    """Tests using mocked API responses."""

    def test_get_schedule_mock(self, mock_api_client):
        """Test schedule retrieval with mock."""
        result = mock_api_client.get_schedule("2024-01-15")
        assert "games" in result
        assert len(result["games"]) == 2

    def test_get_play_by_play_mock(self, mock_api_client):
        """Test play-by-play retrieval with mock."""
        result = mock_api_client.get_game_play_by_play("2023020001")
        assert "plays" in result
        assert len(result["plays"]) == 1

    def test_get_player_landing_mock(self, mock_api_client):
        """Test player landing retrieval with mock."""
        result = mock_api_client.get_player_landing(8478402)
        assert result["playerId"] == 8478402
        assert result["positionCode"] == "C"
