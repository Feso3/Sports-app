"""Game log collector for NHL data collection.

Collects game-by-game statistics for all players and stores in database.
"""

import sys
from typing import Any, Callable, Optional

from loguru import logger

from src.collectors.nhl_api import NHLApiClient
from src.database import get_database
from src.database.db import Database


# Current season (update as needed)
CURRENT_SEASON = 20242025


def parse_toi_to_seconds(toi_str: str) -> int:
    """Parse time on ice string (MM:SS) to seconds.

    Args:
        toi_str: Time string like "21:34"

    Returns:
        Total seconds
    """
    if not toi_str:
        return 0
    try:
        parts = toi_str.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return int(parts[0]) * 60
    except (ValueError, AttributeError):
        return 0


class GameLogCollector:
    """Collects game logs for all NHL players."""

    def __init__(
        self,
        db: Optional[Database] = None,
        api_client: Optional[NHLApiClient] = None,
    ):
        """Initialize game log collector.

        Args:
            db: Database instance (creates new if not provided)
            api_client: NHL API client (creates new if not provided)
        """
        self.db = db or get_database()
        self.api = api_client or NHLApiClient()
        self._stop_requested = False

    def stop(self) -> None:
        """Request graceful stop of collection."""
        self._stop_requested = True
        logger.info("Stop requested, will finish current player...")

    def _parse_skater_game(
        self,
        game_data: dict[str, Any],
        player_id: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Parse a skater's game log entry.

        Args:
            game_data: Raw game data from API
            player_id: Player ID

        Returns:
            Tuple of (game_record, stats_record)
        """
        game_id = game_data.get("gameId")
        opponent = game_data.get("opponentAbbrev")
        is_home = game_data.get("homeRoadFlag") == "H"
        team_abbrev = game_data.get("teamAbbrev")

        game_record = {
            "game_id": game_id,
            "season": CURRENT_SEASON,  # Will be set by caller
            "game_type": 2,  # Regular season
            "game_date": game_data.get("gameDate"),
            "home_team_abbrev": team_abbrev if is_home else opponent,
            "away_team_abbrev": opponent if is_home else team_abbrev,
            "game_state": "FINAL",
        }

        stats_record = {
            "player_id": player_id,
            "game_id": game_id,
            "team_abbrev": team_abbrev,
            "opponent_abbrev": opponent,
            "is_home": is_home,
            "goals": game_data.get("goals", 0),
            "assists": game_data.get("assists", 0),
            "points": game_data.get("points", 0),
            "plus_minus": game_data.get("plusMinus", 0),
            "pim": game_data.get("pim", 0),
            "shots": game_data.get("shots", 0),
            "hits": game_data.get("hits", 0),
            "blocked_shots": game_data.get("blockedShots", 0),
            "power_play_goals": game_data.get("powerPlayGoals", 0),
            "power_play_points": game_data.get("powerPlayPoints", 0),
            "shorthanded_goals": game_data.get("shorthandedGoals", 0),
            "shorthanded_points": game_data.get("shorthandedPoints", 0),
            "game_winning_goals": game_data.get("gameWinningGoals", 0),
            "overtime_goals": game_data.get("otGoals", 0),
            "toi_seconds": parse_toi_to_seconds(game_data.get("toi", "0:00")),
            "faceoff_wins": game_data.get("faceoffWinningPctg", 0),  # Note: API gives percentage
            "faceoff_losses": 0,  # Not directly available
        }

        return game_record, stats_record

    def _parse_goalie_game(
        self,
        game_data: dict[str, Any],
        player_id: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Parse a goalie's game log entry.

        Args:
            game_data: Raw game data from API
            player_id: Player ID

        Returns:
            Tuple of (game_record, stats_record)
        """
        game_id = game_data.get("gameId")
        opponent = game_data.get("opponentAbbrev")
        is_home = game_data.get("homeRoadFlag") == "H"
        team_abbrev = game_data.get("teamAbbrev")

        game_record = {
            "game_id": game_id,
            "season": CURRENT_SEASON,
            "game_type": 2,
            "game_date": game_data.get("gameDate"),
            "home_team_abbrev": team_abbrev if is_home else opponent,
            "away_team_abbrev": opponent if is_home else team_abbrev,
            "game_state": "FINAL",
        }

        # Calculate saves from shots against and goals against
        shots_against = game_data.get("shotsAgainst", 0)
        goals_against = game_data.get("goalsAgainst", 0)
        saves = shots_against - goals_against if shots_against else 0

        stats_record = {
            "player_id": player_id,
            "game_id": game_id,
            "team_abbrev": team_abbrev,
            "opponent_abbrev": opponent,
            "is_home": is_home,
            # Skater stats (0 for goalies)
            "goals": 0,
            "assists": game_data.get("assists", 0),
            "points": game_data.get("assists", 0),
            "plus_minus": 0,
            "pim": game_data.get("pim", 0),
            "shots": 0,
            "hits": 0,
            "blocked_shots": 0,
            "power_play_goals": 0,
            "power_play_points": 0,
            "shorthanded_goals": 0,
            "shorthanded_points": 0,
            "game_winning_goals": 0,
            "overtime_goals": 0,
            "toi_seconds": parse_toi_to_seconds(game_data.get("toi", "0:00")),
            "faceoff_wins": 0,
            "faceoff_losses": 0,
            # Goalie stats
            "games_started": 1 if game_data.get("gamesStarted", 0) else 0,
            "wins": 1 if game_data.get("decision") == "W" else 0,
            "losses": 1 if game_data.get("decision") == "L" else 0,
            "ot_losses": 1 if game_data.get("decision") == "O" else 0,
            "saves": saves,
            "shots_against": shots_against,
            "goals_against": goals_against,
            "save_percentage": game_data.get("savePctg", 0),
            "gaa": game_data.get("goalsAgainstAverage", 0),
            "shutouts": 1 if goals_against == 0 and game_data.get("gamesStarted") else 0,
        }

        return game_record, stats_record

    def collect_player_game_log(
        self,
        player_id: int,
        season: int = CURRENT_SEASON,
        game_type: int = 2,
    ) -> int:
        """Collect game log for a single player.

        Args:
            player_id: NHL player ID
            season: Season to collect (e.g., 20242025)
            game_type: Game type (2=regular, 3=playoffs)

        Returns:
            Number of games collected
        """
        logger.debug(f"Collecting game log for player {player_id}, season {season}")
        self.db.set_collection_progress(
            "player_games", str(player_id), "in_progress", season=season
        )

        try:
            # Get player position to determine parsing method
            player = self.db.get_player(player_id)
            is_goalie = player and player.get("position") == "G"

            # Fetch game log from API
            season_str = str(season)
            game_log_data = self.api.get_player_game_log(player_id, season_str, game_type)

            # Parse and insert games
            games = game_log_data.get("gameLog", [])
            games_collected = 0

            for game_data in games:
                if is_goalie:
                    game_record, stats_record = self._parse_goalie_game(game_data, player_id)
                else:
                    game_record, stats_record = self._parse_skater_game(game_data, player_id)

                # Set correct season
                game_record["season"] = season

                # Insert game (upsert)
                self.db.insert_game(game_record)

                # Insert player stats (upsert)
                self.db.insert_player_game_stats(stats_record)
                games_collected += 1

            self.db.set_collection_progress(
                "player_games", str(player_id), "complete", season=season
            )
            logger.debug(f"Collected {games_collected} games for player {player_id}")
            return games_collected

        except Exception as e:
            self.db.set_collection_progress(
                "player_games", str(player_id), "error", season=season, error=str(e)
            )
            logger.error(f"Error collecting game log for player {player_id}: {e}")
            raise

    def collect_all_game_logs(
        self,
        season: int = CURRENT_SEASON,
        game_type: int = 2,
        resume: bool = True,
        progress_callback: Optional[Callable[[str, int, int, int, int], None]] = None,
    ) -> tuple[int, int]:
        """Collect game logs for all players in database.

        Args:
            season: Season to collect
            game_type: Game type (2=regular, 3=playoffs)
            resume: Skip players already marked as complete
            progress_callback: Optional callback(player_name, current, total, games_so_far, total_games)

        Returns:
            Tuple of (players_processed, total_games_collected)
        """
        # Get all active players
        all_player_ids = self.db.get_all_player_ids(active_only=True)

        if not all_player_ids:
            logger.warning("No players in database. Run player collection first.")
            return 0, 0

        # Filter out completed players if resuming
        if resume:
            incomplete = self.db.get_incomplete_players(season)
            player_ids = [p for p in all_player_ids if p in incomplete]
            skipped = len(all_player_ids) - len(player_ids)
            if skipped:
                logger.info(f"Resuming: skipping {skipped} completed players")
        else:
            player_ids = all_player_ids

        total_players = len(player_ids)
        players_processed = 0
        total_games = 0

        for idx, player_id in enumerate(player_ids):
            if self._stop_requested:
                logger.info("Stop requested, halting collection")
                break

            player = self.db.get_player(player_id)
            player_name = player["full_name"] if player else f"Player {player_id}"

            try:
                games = self.collect_player_game_log(player_id, season, game_type)
                total_games += games
                players_processed += 1

                if progress_callback:
                    progress_callback(
                        player_name, idx + 1, total_players, games, total_games
                    )

            except Exception as e:
                logger.error(f"Failed to collect {player_name}: {e}")
                # Continue with next player

        return players_processed, total_games

    def get_collection_status(self, season: int = CURRENT_SEASON) -> dict[str, Any]:
        """Get current collection status.

        Args:
            season: Season to check

        Returns:
            Status summary
        """
        all_players = self.db.get_all_player_ids(active_only=True)
        progress = self.db.get_collection_progress("player_games")

        # Filter by season
        season_progress = [p for p in progress if p["season"] == season]

        complete = [p for p in season_progress if p["status"] == "complete"]
        in_progress = [p for p in season_progress if p["status"] == "in_progress"]
        errors = [p for p in season_progress if p["status"] == "error"]

        complete_ids = {int(p["entity_id"]) for p in complete}
        pending = [p for p in all_players if p not in complete_ids]

        return {
            "season": season,
            "total_players": len(all_players),
            "complete": len(complete),
            "in_progress": len(in_progress),
            "errors": len(errors),
            "pending": len(pending),
            "total_game_records": self.db.get_player_game_stats_count(season=season),
            "error_players": [
                (int(p["entity_id"]), p["last_error"][:50] if p["last_error"] else "")
                for p in errors
            ],
        }


def print_progress_bar(
    current: int, total: int, prefix: str = "", suffix: str = "", length: int = 30
) -> None:
    """Print a progress bar to stdout."""
    if total == 0:
        return
    percent = current / total
    filled = int(length * percent)
    bar = "█" * filled + "░" * (length - filled)
    sys.stdout.write(f"\r{prefix} [{bar}] {current}/{total} {suffix}")
    sys.stdout.flush()


def collect_game_logs_with_progress(
    season: int = CURRENT_SEASON,
    db: Optional[Database] = None,
    resume: bool = True,
) -> tuple[int, int]:
    """Collect all game logs with console progress display.

    Args:
        season: Season to collect
        db: Database instance
        resume: Whether to resume from previous collection

    Returns:
        Tuple of (players_processed, total_games)
    """
    collector = GameLogCollector(db=db)

    def progress(
        player: str,
        current: int,
        total: int,
        games: int,
        total_games: int,
    ) -> None:
        print_progress_bar(
            current,
            total,
            prefix=f"Players",
            suffix=f"| {player[:25]:<25} | Games: {total_games:,}",
        )

    print(f"Collecting game logs for season {season}...")
    print()

    players, games = collector.collect_all_game_logs(
        season=season,
        resume=resume,
        progress_callback=progress,
    )

    print()  # New line after progress bar
    print()

    status = collector.get_collection_status(season)
    print(f"Collection complete!")
    print(f"  Players processed: {status['complete']}/{status['total_players']}")
    print(f"  Game records: {status['total_game_records']:,}")

    if status["errors"]:
        print(f"  Errors: {len(status['errors'])}")
        for player_id, error in status["error_players"][:5]:
            print(f"    - Player {player_id}: {error}")
        if len(status["error_players"]) > 5:
            print(f"    ... and {len(status['error_players']) - 5} more")

    return players, games
