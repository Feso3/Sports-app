"""Shot collector for NHL data collection.

Collects historical shot data and stores in database, linked to players.
"""

import sys
from typing import Any, Callable, Optional

from loguru import logger

from src.collectors.nhl_api import NHLApiClient
from src.collectors.shot_data import ShotDataCollector, Shot
from src.database import get_database
from src.database.db import Database


# Seasons available for shot data (2015-16 to present)
AVAILABLE_SEASONS = [
    20152016, 20162017, 20172018, 20182019, 20192020,
    20202021, 20212022, 20222023, 20232024, 20242025,
]


class ShotDatabaseCollector:
    """Collects shot data and stores in database."""

    def __init__(
        self,
        db: Optional[Database] = None,
        api_client: Optional[NHLApiClient] = None,
    ):
        """Initialize shot collector.

        Args:
            db: Database instance
            api_client: NHL API client
        """
        self.db = db or get_database()
        self.api = api_client or NHLApiClient()
        self.shot_collector = ShotDataCollector(api_client=self.api)
        self._stop_requested = False

    def stop(self) -> None:
        """Request graceful stop of collection."""
        self._stop_requested = True
        logger.info("Stop requested, will finish current game...")

    def _shot_to_dict(self, shot: Shot, season: int) -> dict[str, Any]:
        """Convert Shot dataclass to database dict.

        Args:
            shot: Shot dataclass instance
            season: Season for this shot

        Returns:
            Dict ready for database insertion
        """
        # Extract assist player IDs
        assist1 = None
        assist2 = None
        if shot.assists:
            if len(shot.assists) > 0:
                assist1 = shot.assists[0].get("player_id")
            if len(shot.assists) > 1:
                assist2 = shot.assists[1].get("player_id")

        return {
            "game_id": int(shot.game_id),
            "event_id": shot.event_id,
            "player_id": shot.shooter_id,
            "team_abbrev": shot.team_abbrev,
            "goalie_id": shot.goalie_id,
            "period": shot.period,
            "time_in_period": shot.time_in_period,
            "time_remaining": shot.time_remaining,
            "x_coord": shot.x_coord,
            "y_coord": shot.y_coord,
            "distance": shot.distance,
            "shot_type": shot.shot_type,
            "is_goal": shot.is_goal,
            "strength": shot.strength,
            "empty_net": shot.empty_net,
            "game_winning_goal": shot.game_winning_goal,
            "assist1_player_id": assist1,
            "assist2_player_id": assist2,
            "season": season,
            "event_description": shot.event_description,
        }

    def collect_game_shots(self, game_id: int, season: int) -> int:
        """Collect shots from a single game and store in database.

        Args:
            game_id: NHL game ID
            season: Season for this game

        Returns:
            Number of shots collected
        """
        # First, ensure the game record exists (foreign key requirement)
        existing_game = self.db.get_game(game_id)
        if not existing_game:
            # Fetch game info and insert it
            try:
                game_data = self.api.get_game_landing(game_id)
                game_record = {
                    "game_id": game_id,
                    "season": season,
                    "game_type": game_data.get("gameType", 2),
                    "game_date": game_data.get("gameDate", ""),
                    "home_team_id": game_data.get("homeTeam", {}).get("id"),
                    "home_team_abbrev": game_data.get("homeTeam", {}).get("abbrev"),
                    "away_team_id": game_data.get("awayTeam", {}).get("id"),
                    "away_team_abbrev": game_data.get("awayTeam", {}).get("abbrev"),
                    "home_score": game_data.get("homeTeam", {}).get("score"),
                    "away_score": game_data.get("awayTeam", {}).get("score"),
                    "game_state": game_data.get("gameState", "FINAL"),
                    "venue": game_data.get("venue", {}).get("default", ""),
                }
                self.db.insert_game(game_record)
            except Exception as e:
                logger.warning(f"Could not fetch game info for {game_id}: {e}")
                # Create minimal game record to satisfy foreign key
                game_record = {
                    "game_id": game_id,
                    "season": season,
                    "game_type": 2,
                    "game_date": "",
                    "game_state": "UNKNOWN",
                }
                self.db.insert_game(game_record)

        shots = self.shot_collector.collect_game_shots(game_id)

        if not shots:
            return 0

        # Convert to database format
        shot_dicts = [self._shot_to_dict(s, season) for s in shots]

        # Batch insert
        count = self.db.insert_shots_batch(shot_dicts)
        return count

    def collect_season_shots(
        self,
        season: int,
        resume: bool = True,
        progress_callback: Optional[Callable[[int, int, int, int], None]] = None,
    ) -> tuple[int, int]:
        """Collect all shots for a season.

        Args:
            season: Season to collect (e.g., 20242025)
            resume: Skip games already in database
            progress_callback: Optional callback(game_idx, total_games, shots_this_game, total_shots)

        Returns:
            Tuple of (games_processed, total_shots)
        """
        logger.info(f"Collecting shot data for season {season}")
        self.db.set_collection_progress("shots", str(season), "in_progress", season=season)

        try:
            # Get all games for season
            season_str = str(season)
            games = self.api.get_season_games(season_str)

            if not games:
                logger.warning(f"No games found for season {season}")
                return 0, 0

            # Filter out games already collected if resuming
            if resume:
                existing_games = self.db.get_games_with_shots(season)
                games = [g for g in games if g.get("id", g.get("gamePk")) not in existing_games]
                if existing_games:
                    logger.info(f"Resuming: skipping {len(existing_games)} games already collected")

            total_games = len(games)
            games_processed = 0
            total_shots = 0

            for idx, game in enumerate(games):
                if self._stop_requested:
                    logger.info("Stop requested, halting collection")
                    break

                game_id = game.get("id", game.get("gamePk"))
                if not game_id:
                    continue

                try:
                    shots = self.collect_game_shots(game_id, season)
                    total_shots += shots
                    games_processed += 1

                    if progress_callback:
                        progress_callback(idx + 1, total_games, shots, total_shots)

                except Exception as e:
                    logger.warning(f"Failed to collect shots for game {game_id}: {e}")
                    # Continue with next game

            self.db.set_collection_progress("shots", str(season), "complete", season=season)
            logger.info(f"Collected {total_shots} shots from {games_processed} games")
            return games_processed, total_shots

        except Exception as e:
            self.db.set_collection_progress(
                "shots", str(season), "error", season=season, error=str(e)
            )
            logger.error(f"Error collecting shots for season {season}: {e}")
            raise

    def collect_player_shots_for_season(
        self,
        player_id: int,
        season: int,
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
    ) -> int:
        """Collect shots for a specific player in a season.

        This is more efficient than collecting the whole season if you only
        need one player. It finds games the player appeared in and collects
        shots from those games.

        Args:
            player_id: NHL player ID
            season: Season to collect
            progress_callback: Optional callback(game_idx, total_games, total_shots)

        Returns:
            Number of shots collected for this player
        """
        logger.info(f"Collecting shots for player {player_id}, season {season}")

        # Get player's games from game log
        season_str = str(season)
        try:
            game_log = self.api.get_player_game_log(player_id, season_str, game_type=2)
        except Exception as e:
            logger.error(f"Failed to get game log for player {player_id}: {e}")
            return 0

        games = game_log.get("gameLog", [])
        if not games:
            logger.info(f"No games found for player {player_id} in season {season}")
            return 0

        # Check which games already have shot data
        existing_games = self.db.get_games_with_shots(season)

        total_games = len(games)
        total_shots = 0
        player_shots = 0

        for idx, game_entry in enumerate(games):
            if self._stop_requested:
                break

            game_id = game_entry.get("gameId")
            if not game_id:
                continue

            # Collect shots for this game if not already done
            if game_id not in existing_games:
                try:
                    shots = self.collect_game_shots(game_id, season)
                    total_shots += shots
                    existing_games.add(game_id)  # Mark as collected
                except Exception as e:
                    logger.warning(f"Failed to collect shots for game {game_id}: {e}")

            # Count this player's shots from database
            player_shots = self.db.get_shot_count(player_id=player_id, season=season)

            if progress_callback:
                progress_callback(idx + 1, total_games, player_shots)

        return player_shots

    def get_collection_status(self, season: Optional[int] = None) -> dict[str, Any]:
        """Get shot collection status.

        Args:
            season: Optional season to check

        Returns:
            Status summary
        """
        if season:
            shot_counts = self.db.get_shot_counts(season=season)
            games_with_shots = len(self.db.get_games_with_shots(season))

            return {
                "season": season,
                "games_with_shots": games_with_shots,
                "total_shots": shot_counts["total_attempts"],
                "shots_on_goal": shot_counts["shots_on_goal"],
                "total_goals": shot_counts["goals"],
            }
        else:
            shot_counts = self.db.get_shot_counts()

            return {
                "total_shots": shot_counts["total_attempts"],
                "shots_on_goal": shot_counts["shots_on_goal"],
                "total_goals": shot_counts["goals"],
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


def collect_season_shots_with_progress(
    season: int,
    db: Optional[Database] = None,
    resume: bool = True,
) -> tuple[int, int]:
    """Collect season shots with console progress.

    Args:
        season: Season to collect
        db: Database instance
        resume: Whether to resume

    Returns:
        Tuple of (games, shots)
    """
    collector = ShotDatabaseCollector(db=db)

    def progress(game_idx: int, total: int, shots: int, total_shots: int) -> None:
        print_progress_bar(
            game_idx,
            total,
            prefix="Games",
            suffix=f"| Shots: {total_shots:,}",
        )

    print(f"Collecting shots for season {season}...")
    print()

    games, shots = collector.collect_season_shots(
        season=season,
        resume=resume,
        progress_callback=progress,
    )

    print()
    print()

    status = collector.get_collection_status(season)
    print(f"Collection complete!")
    print(f"  Games processed: {games}")
    print(f"  Total shots: {status['total_shots']:,}")
    print(f"  Shots on goal: {status['shots_on_goal']:,}")
    print(f"  Total goals: {status['total_goals']:,}")

    return games, shots


def collect_player_shots_with_progress(
    player_id: int,
    season: int,
    db: Optional[Database] = None,
) -> int:
    """Collect shots for one player with console progress.

    Args:
        player_id: Player ID
        season: Season to collect
        db: Database instance

    Returns:
        Number of shots for this player
    """
    db = db or get_database()
    collector = ShotDatabaseCollector(db=db)

    # Get player name
    player = db.get_player(player_id)
    player_name = player["full_name"] if player else f"Player {player_id}"

    def progress(game_idx: int, total: int, shots: int) -> None:
        print_progress_bar(
            game_idx,
            total,
            prefix="Games",
            suffix=f"| {player_name}'s shots: {shots}",
        )

    print(f"Collecting shots for {player_name} (season {season})...")
    print()

    total_shots = collector.collect_player_shots_for_season(
        player_id=player_id,
        season=season,
        progress_callback=progress,
    )

    print()
    print()

    # Get player-specific stats
    shot_counts = db.get_shot_counts(player_id=player_id, season=season)

    print(f"Collection complete for {player_name}!")
    print(f"  Total shots: {shot_counts['total_attempts']}")
    print(f"  Shots on goal: {shot_counts['shots_on_goal']}")
    print(f"  Goals: {shot_counts['goals']}")

    # Show shot breakdown
    shots = db.get_player_shots(player_id, season=season)
    if shots:
        shot_types = {}
        for s in shots:
            st = s.get("shot_type") or "unknown"
            shot_types[st] = shot_types.get(st, 0) + 1

        print(f"  Shot types:")
        for st, count in sorted(shot_types.items(), key=lambda x: -x[1])[:5]:
            print(f"    - {st}: {count}")

    return total_shots
