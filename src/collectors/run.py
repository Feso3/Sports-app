#!/usr/bin/env python3
"""CLI orchestrator for NHL data collection.

Usage:
    python -m src.collectors.run collect --full
    python -m src.collectors.run collect --players
    python -m src.collectors.run collect --game-logs --season 20242025
    python -m src.collectors.run status
    python -m src.collectors.run status --season 20232024
"""

import argparse
import signal
import sys
from typing import Optional

from loguru import logger

from src.database import get_database
from src.collectors.player_collector import (
    PlayerCollector,
    collect_players_with_progress,
)
from src.collectors.game_log_collector import (
    GameLogCollector,
    collect_game_logs_with_progress,
    CURRENT_SEASON,
)


# Global collectors for signal handling
_player_collector: Optional[PlayerCollector] = None
_game_log_collector: Optional[GameLogCollector] = None


def signal_handler(signum: int, frame) -> None:
    """Handle interrupt signals gracefully."""
    print("\n\nInterrupt received, stopping gracefully...")
    print("(Press Ctrl+C again to force quit)\n")

    if _player_collector:
        _player_collector.stop()
    if _game_log_collector:
        _game_log_collector.stop()

    # Reset handler to allow force quit
    signal.signal(signal.SIGINT, signal.SIG_DFL)


def cmd_collect(args: argparse.Namespace) -> int:
    """Run data collection."""
    global _player_collector, _game_log_collector

    db = get_database()

    # Ensure database is initialized
    if not db.is_initialized():
        db.initialize()
        print("Database initialized.")

    resume = not args.no_resume
    season = args.season or CURRENT_SEASON

    if args.full or args.players:
        print("=" * 60)
        print("PHASE 1: Collecting Players")
        print("=" * 60)
        print()

        _player_collector = PlayerCollector(db=db)
        collect_players_with_progress(db=db, resume=resume, fetch_details=True)
        _player_collector = None
        print()

    if args.full or args.game_logs:
        print("=" * 60)
        print(f"PHASE 2: Collecting Game Logs (Season {season})")
        print("=" * 60)
        print()

        # Check we have players first
        player_count = db.get_player_count()
        if player_count == 0:
            print("ERROR: No players in database. Run --players first.")
            return 1

        print(f"Found {player_count} players in database.")
        print()

        _game_log_collector = GameLogCollector(db=db)
        collect_game_logs_with_progress(season=season, db=db, resume=resume)
        _game_log_collector = None

    print()
    print("=" * 60)
    print("Collection finished!")
    print("=" * 60)

    # Show final stats
    stats = db.get_database_stats()
    print(f"\nDatabase Summary:")
    print(f"  Players: {stats['active_players']} active ({stats['total_players']} total)")
    print(f"  Games: {stats['total_games']}")
    print(f"  Player-game records: {stats['total_player_game_stats']:,}")
    print(f"  Seasons: {stats['seasons']}")

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show collection status."""
    db = get_database()

    if not db.is_initialized():
        print("Database not initialized. Run 'collect' first.")
        return 1

    season = args.season or CURRENT_SEASON

    print("=" * 60)
    print("Collection Status")
    print("=" * 60)
    print()

    # Database stats
    stats = db.get_database_stats()
    print("Database:")
    print(f"  Players: {stats['active_players']} active ({stats['total_players']} total)")
    print(f"  Games: {stats['total_games']}")
    print(f"  Player-game records: {stats['total_player_game_stats']:,}")
    print(f"  Seasons: {stats['seasons'] or 'None'}")
    print()

    # Player collection status
    player_collector = PlayerCollector(db=db)
    player_status = player_collector.get_collection_status()

    print("Player Collection (Rosters):")
    print(f"  Complete: {player_status['complete']}/{player_status['total_teams']} teams")
    if player_status["pending_teams"]:
        print(f"  Pending: {', '.join(player_status['pending_teams'][:10])}")
        if len(player_status["pending_teams"]) > 10:
            print(f"           ... and {len(player_status['pending_teams']) - 10} more")
    if player_status["error_teams"]:
        print(f"  Errors: {len(player_status['error_teams'])}")
        for team, error in player_status["error_teams"][:3]:
            print(f"    - {team}: {error[:40]}")
    print()

    # Game log collection status
    game_log_collector = GameLogCollector(db=db)
    game_status = game_log_collector.get_collection_status(season)

    print(f"Game Log Collection (Season {season}):")
    print(f"  Complete: {game_status['complete']}/{game_status['total_players']} players")
    print(f"  Pending: {game_status['pending']}")
    print(f"  Game records: {game_status['total_game_records']:,}")
    if game_status["errors"]:
        print(f"  Errors: {len(game_status['errors'])}")

    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    """Reset collection progress (not data)."""
    db = get_database()

    if not db.is_initialized():
        print("Database not initialized.")
        return 1

    confirm = input(
        "This will reset collection progress, allowing re-collection. "
        "Data will NOT be deleted.\nContinue? [y/N]: "
    )

    if confirm.lower() != "y":
        print("Cancelled.")
        return 0

    with db.cursor() as cur:
        if args.players:
            cur.execute("DELETE FROM collection_progress WHERE collection_type = 'roster'")
            print("Player collection progress reset.")
        elif args.game_logs:
            season = args.season or CURRENT_SEASON
            cur.execute(
                "DELETE FROM collection_progress WHERE collection_type = 'player_games' AND season = ?",
                (season,),
            )
            print(f"Game log collection progress reset for season {season}.")
        else:
            cur.execute("DELETE FROM collection_progress")
            print("All collection progress reset.")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="NHL Player Data Collection Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.collectors.run collect --full           # Collect everything
  python -m src.collectors.run collect --players        # Just collect players
  python -m src.collectors.run collect --game-logs      # Just collect game logs
  python -m src.collectors.run status                   # Show collection status
  python -m src.collectors.run reset --game-logs        # Reset game log progress
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Collect command
    collect_parser = subparsers.add_parser("collect", help="Run data collection")
    collect_parser.add_argument(
        "--full", action="store_true", help="Full collection (players + game logs)"
    )
    collect_parser.add_argument(
        "--players", action="store_true", help="Collect players only"
    )
    collect_parser.add_argument(
        "--game-logs", action="store_true", help="Collect game logs only"
    )
    collect_parser.add_argument(
        "--season",
        type=int,
        default=None,
        help=f"Season to collect (default: {CURRENT_SEASON})",
    )
    collect_parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Don't resume, start fresh (will update existing records)",
    )

    # Status command
    status_parser = subparsers.add_parser("status", help="Show collection status")
    status_parser.add_argument(
        "--season",
        type=int,
        default=None,
        help=f"Season to check (default: {CURRENT_SEASON})",
    )

    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset collection progress")
    reset_parser.add_argument(
        "--players", action="store_true", help="Reset player collection only"
    )
    reset_parser.add_argument(
        "--game-logs", action="store_true", help="Reset game log collection only"
    )
    reset_parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="Season to reset (for game logs)",
    )

    args = parser.parse_args()

    # Set up logging
    logger.remove()
    logger.add(
        sys.stderr,
        level="WARNING",
        format="<level>{level}</level>: {message}",
    )

    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    if args.command == "collect":
        if not (args.full or args.players or args.game_logs):
            print("ERROR: Specify --full, --players, or --game-logs")
            return 1
        return cmd_collect(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "reset":
        return cmd_reset(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
