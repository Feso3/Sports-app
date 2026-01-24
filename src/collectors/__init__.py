"""
Data Collectors Module

This module contains collectors for fetching data from various NHL data sources.

Collectors:
    - NHLApiClient: Core API client for NHL Stats API
    - ShotDataCollector: Collects shot location and outcome data
    - PlayerStatsCollector: Collects individual player statistics
    - TimestampDataCollector: Collects event timing data for segment analysis
"""

from src.collectors.nhl_api import NHLApiClient
from src.collectors.shot_data import ShotDataCollector
from src.collectors.player_stats import PlayerStatsCollector
from src.collectors.timestamp_data import TimestampDataCollector

__all__ = [
    "NHLApiClient",
    "ShotDataCollector",
    "PlayerStatsCollector",
    "TimestampDataCollector",
]
