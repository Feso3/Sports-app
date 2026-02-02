"""
CLI for running simulation data pipelines.

Run all pipelines to prepare data for simulation:
    python -m src.processors.run_simulation_pipelines --season 20242025

Run individual pipelines:
    python -m src.processors.run_simulation_pipelines --season 20242025 --pipeline schedule
    python -m src.processors.run_simulation_pipelines --season 20242025 --pipeline matchup
    python -m src.processors.run_simulation_pipelines --season 20242025 --pipeline momentum
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
        choices=["schedule", "matchup", "momentum", "all"],
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
    else:
        results = run_all_pipelines(args.season, args.date)

    logger.info(f"Pipeline results: {results}")


if __name__ == "__main__":
    main()
