"""
CLI for running simulation data pipelines.

Run all pipelines to prepare data for simulation:
    python -m src.processors.run_simulation_pipelines --season 20242025

Run individual pipelines:
    python -m src.processors.run_simulation_pipelines --season 20242025 --pipeline schedule
    python -m src.processors.run_simulation_pipelines --season 20242025 --pipeline matchup
    python -m src.processors.run_simulation_pipelines --season 20242025 --pipeline momentum
    python -m src.processors.run_simulation_pipelines --season 20242025 --pipeline shots
    python -m src.processors.run_simulation_pipelines --season 20242025 --pipeline goalie
"""

import argparse
from datetime import datetime

from loguru import logger

from ..database.db import get_database


def run_schedule_pipeline(season: int) -> dict:
    """Run the schedule context pipeline."""
    from .schedule_context_pipeline import run_pipeline
    logger.info(f"Running schedule context pipeline for season {season}")
    return run_pipeline(season)


def run_matchup_pipeline(season: int) -> dict:
    """Run the matchup history pipeline."""
    from .matchup_history_pipeline import run_pipeline
    logger.info(f"Running matchup history pipeline for season {season}")
    return run_pipeline(season)


def run_momentum_pipeline(season: int, as_of_date: str = None) -> dict:
    """Run the momentum detection pipeline."""
    from .momentum_pipeline import run_pipeline
    logger.info(f"Running momentum pipeline for season {season}")
    return run_pipeline(season, as_of_date=as_of_date)


def run_shot_location_pipeline(season: int) -> dict:
    """Run the player shot location pipeline."""
    from .player_shot_location_pipeline import PlayerShotLocationPipeline
    logger.info(f"Running player shot location pipeline for season {season}")

    db = get_database()
    pipeline = PlayerShotLocationPipeline(db=db)

    # Get all players with shot data for the season
    players = db.fetch_dataframe("""
        SELECT DISTINCT player_id FROM shots
        WHERE season = ?
    """, [season])

    profiles_built = 0
    for player_id in players['player_id'].tolist():
        try:
            profile = pipeline.build_player_profile(player_id, season)
            if profile.total_shots > 0:
                profiles_built += 1
        except Exception as e:
            logger.warning(f"Failed to build shot profile for player {player_id}: {e}")

    return {"players_processed": len(players), "profiles_built": profiles_built}


def run_goalie_profile_pipeline(season: int) -> dict:
    """Run the goalie shot profile pipeline."""
    from .goalie_shot_profile_pipeline import GoalieShotProfilePipeline
    logger.info(f"Running goalie shot profile pipeline for season {season}")

    db = get_database()
    pipeline = GoalieShotProfilePipeline(db=db)

    # Get all goalies with shot data for the season
    goalies = db.fetch_dataframe("""
        SELECT DISTINCT goalie_id FROM shots
        WHERE season = ? AND goalie_id IS NOT NULL
    """, [season])

    profiles_built = 0
    for goalie_id in goalies['goalie_id'].tolist():
        try:
            profile = pipeline.build_goalie_profile(goalie_id, season)
            if profile.total_shots_faced > 0:
                profiles_built += 1
        except Exception as e:
            logger.warning(f"Failed to build goalie profile for {goalie_id}: {e}")

    return {"goalies_processed": len(goalies), "profiles_built": profiles_built}


def run_all_pipelines(season: int, as_of_date: str = None) -> dict:
    """
    Run all simulation pipelines in order.

    Args:
        season: Season identifier (e.g., 20242025)
        as_of_date: Date for momentum calculation (default: today)

    Returns:
        Combined results from all pipelines
    """
    results = {}

    # Ensure database has new tables
    db = get_database()
    db.upgrade_schema()

    # 1. Schedule context (needs to run first for streak data)
    logger.info("=" * 60)
    logger.info("PHASE 1: Schedule Context Analysis")
    logger.info("=" * 60)
    results["schedule"] = run_schedule_pipeline(season)

    # 2. Matchup history
    logger.info("=" * 60)
    logger.info("PHASE 2: Matchup History Extraction")
    logger.info("=" * 60)
    results["matchup"] = run_matchup_pipeline(season)

    # 3. Momentum detection
    logger.info("=" * 60)
    logger.info("PHASE 3: Momentum Detection")
    logger.info("=" * 60)
    results["momentum"] = run_momentum_pipeline(season, as_of_date)

    # 4. Player shot location profiles
    logger.info("=" * 60)
    logger.info("PHASE 4: Player Shot Location Profiles")
    logger.info("=" * 60)
    results["shots"] = run_shot_location_pipeline(season)

    # 5. Goalie shot profiles
    logger.info("=" * 60)
    logger.info("PHASE 5: Goalie Shot Profiles")
    logger.info("=" * 60)
    results["goalie"] = run_goalie_profile_pipeline(season)

    logger.info("=" * 60)
    logger.info("ALL PIPELINES COMPLETE")
    logger.info("=" * 60)

    return results


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Run simulation data preparation pipelines"
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season identifier (e.g., 20242025)",
    )
    parser.add_argument(
        "--pipeline",
        choices=["schedule", "matchup", "momentum", "shots", "goalie", "all"],
        default="all",
        help="Which pipeline to run (default: all)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date for momentum calculation (default: today)",
    )

    args = parser.parse_args()

    if args.pipeline == "schedule":
        results = run_schedule_pipeline(args.season)
    elif args.pipeline == "matchup":
        results = run_matchup_pipeline(args.season)
    elif args.pipeline == "momentum":
        results = run_momentum_pipeline(args.season, args.date)
    elif args.pipeline == "shots":
        results = run_shot_location_pipeline(args.season)
    elif args.pipeline == "goalie":
        results = run_goalie_profile_pipeline(args.season)
    else:
        results = run_all_pipelines(args.season, args.date)

    logger.info(f"Pipeline results: {results}")


if __name__ == "__main__":
    main()
