#!/usr/bin/env python3
"""CLI for running analysis pipelines.

Usage:
    python -m src.processors.run_analysis season-segments --season 20242025
    python -m src.processors.run_analysis season-segments --season 20242025 --validate-only
    python -m src.processors.run_analysis season-segments --season 20242025 --player 8478402

    python -m src.processors.run_analysis shot-locations --season 20242025
    python -m src.processors.run_analysis shot-locations --season 20242025 --player 8478402
    python -m src.processors.run_analysis shot-locations --season 20242025 --min-shots 20
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

from src.database import get_database
from src.processors.season_segment_pipeline import (
    SeasonSegmentPipeline,
    run_pipeline,
)
from src.processors.player_shot_location_pipeline import (
    PlayerShotLocationPipeline,
    run_pipeline as run_shot_location_pipeline,
)


CURRENT_SEASON = 20242025


def cmd_season_segments(args: argparse.Namespace) -> int:
    """Run season + game segment aggregation pipeline."""
    db = get_database()

    if not db.is_initialized():
        print("ERROR: Database not initialized. Run data collection first.")
        return 1

    season = args.season or CURRENT_SEASON
    output_dir = Path(args.output) if args.output else Path("data/exports")

    print("=" * 60)
    print(f"Season Segment Pipeline (Season {season})")
    print("=" * 60)
    print()

    pipeline = SeasonSegmentPipeline(db=db)

    # Build and display season phase mapping
    print("Building season phase mapping...")
    mapping = pipeline.build_season_phase_mapping(season)
    print(f"  Early season: {len(mapping.early_season_games)} games")
    print(f"  Mid season: {len(mapping.mid_season_games)} games")
    print(f"  Late season: {len(mapping.late_season_games)} games")
    print(f"  Playoffs: {len(mapping.playoff_games)} games")
    print()

    if args.player:
        # Single player mode
        player_id = args.player
        player = db.get_player(player_id)
        player_name = player["full_name"] if player else f"Player {player_id}"

        print(f"Aggregating stats for: {player_name}")
        print()

        phase_stats = pipeline.aggregate_player_stats(player_id, season)

        # Display results
        print("Results by (Season Phase × Game Phase):")
        print("-" * 80)
        print(f"{'Season Phase':<15} {'Game Phase':<12} {'GP':<5} {'G':<5} {'A':<5} {'P':<5} {'Shots':<6} {'SH%':<6}")
        print("-" * 80)

        for (season_phase, game_phase), stats in sorted(phase_stats.items()):
            if stats.goals > 0 or stats.assists > 0 or stats.shots > 0:
                print(
                    f"{season_phase:<15} {game_phase:<12} "
                    f"{stats.games:<5} {stats.goals:<5} {stats.assists:<5} "
                    f"{stats.points:<5} {stats.shots:<6} {stats.shooting_percentage:<6.1f}"
                )

        print()

        # Validate
        print("Validating against per-game totals...")
        result = pipeline.validate_player(player_id, season)
        if result.is_valid:
            print(f"  ✓ Totals reconcile (G={result.expected_goals}, A={result.expected_assists})")
        else:
            print(f"  ✗ Discrepancy detected: {result.discrepancy}")

        return 0

    if args.validate_only:
        # Validation only mode
        print("Running validation...")
        print()

        sample_size = args.sample or 50
        results = pipeline.validate_season(season, sample_size=sample_size)

        passed = sum(1 for r in results if r.is_valid)
        failed = sum(1 for r in results if not r.is_valid)

        print()
        print(f"Validation Results: {passed}/{len(results)} passed ({100*passed/len(results):.1f}%)")

        if failed > 0:
            print()
            print("Failed validations:")
            for r in results:
                if not r.is_valid:
                    print(f"  - {r.player_name}: {r.discrepancy}")

        # Export validation report
        pipeline.export_validation_report(
            results,
            output_dir / f"validation_{season}.json",
        )

        return 0 if failed == 0 else 1

    # Full pipeline
    print("Running full aggregation pipeline...")
    print("(This may take a while for large datasets)")
    print()

    all_stats = run_pipeline(
        season=season,
        output_dir=output_dir,
        validate=not args.skip_validation,
        db=db,
    )

    print()
    print(f"Processed {len(all_stats)} players with data")
    print(f"Output files saved to: {output_dir}")
    print(f"  - player_phase_stats_{season}.json")
    print(f"  - player_phase_stats_{season}.csv")
    if not args.skip_validation:
        print(f"  - validation_{season}.json")

    return 0


def cmd_query_player(args: argparse.Namespace) -> int:
    """Query a player's segment stats."""
    db = get_database()

    if not db.is_initialized():
        print("ERROR: Database not initialized.")
        return 1

    season = args.season or CURRENT_SEASON
    player_id = args.player

    pipeline = SeasonSegmentPipeline(db=db)

    player = db.get_player(player_id)
    if player:
        print(f"Player: {player['full_name']}")
    else:
        print(f"Player ID: {player_id} (not in database)")
        return 1

    print(f"Season: {season}")
    print()

    phase_stats = pipeline.aggregate_player_stats(player_id, season)

    # Calculate totals for comparison
    total_goals = sum(s.goals for s in phase_stats.values())
    total_assists = sum(s.assists for s in phase_stats.values())

    print("=" * 80)
    print("Performance by Season Phase × Game Phase")
    print("=" * 80)
    print()

    # Group by season phase
    from src.processors.season_segment_pipeline import SeasonPhase, GamePhase

    for season_phase in SeasonPhase:
        phase_data = [
            (gp, phase_stats[(season_phase.value, gp.value)])
            for gp in GamePhase
        ]

        total_g = sum(s.goals for _, s in phase_data)
        total_a = sum(s.assists for _, s in phase_data)

        print(f"{season_phase.value.upper().replace('_', ' ')}:")
        print(f"  Games: {phase_data[0][1].games}")
        print(f"  Totals: {total_g}G, {total_a}A, {total_g + total_a}P")
        print()

        for game_phase, stats in phase_data:
            if stats.goals > 0 or stats.assists > 0:
                print(f"    {game_phase.value}: {stats.goals}G, {stats.assists}A ({stats.shooting_percentage:.1f}% SH)")

        print()

    print("-" * 80)
    print(f"Season Total: {total_goals}G, {total_assists}A, {total_goals + total_assists}P")

    return 0


def cmd_shot_locations(args: argparse.Namespace) -> int:
    """Run player shot location pipeline."""
    db = get_database()

    if not db.is_initialized():
        print("ERROR: Database not initialized. Run data collection first.")
        return 1

    season = args.season or CURRENT_SEASON
    output_dir = Path(args.output) if args.output else Path("data/exports")
    min_shots = args.min_shots or 10

    print("=" * 60)
    print(f"Player Shot Location Pipeline (Season {season})")
    print("=" * 60)
    print()

    pipeline = PlayerShotLocationPipeline(db=db)

    if args.player:
        # Single player mode
        player_id = args.player
        player = db.get_player(player_id)
        player_name = player["full_name"] if player else f"Player {player_id}"

        print(f"Building shot location profile for: {player_name}")
        print()

        profile = pipeline.build_player_profile(player_id, season)

        # Display results
        print(f"Total Shots: {profile.total_shots}")
        print(f"Total Goals: {profile.total_goals}")
        print(f"Shooting %: {profile.shooting_percentage:.1f}%")
        print(f"Goals Above Expected: {profile.goals_above_expected:+.2f}")
        print(f"High Danger Shot Rate: {profile.high_danger_shot_rate:.1%}")
        print(f"Preferred Zones: {', '.join(profile.preferred_zones)}")
        print()

        # Show zone breakdown
        print("Shot Distribution by Zone:")
        print("-" * 60)
        print(f"{'Zone':<20} {'Shots':<8} {'Goals':<8} {'SH%':<8} {'xG':<8}")
        print("-" * 60)

        sorted_zones = sorted(
            profile.overall_zone_stats.items(),
            key=lambda x: x[1].shots,
            reverse=True
        )

        for zone, stats in sorted_zones:
            if stats.shots > 0:
                print(
                    f"{zone:<20} {stats.shots:<8} {stats.goals:<8} "
                    f"{stats.shooting_percentage:<8.1f} {stats.expected_goals:<8.2f}"
                )

        print()

        # Show segment breakdown (summarized)
        print("Performance by Segment (Goals/Shots):")
        print("-" * 60)

        from src.processors.season_segment_pipeline import SeasonPhase, GamePhase

        print(f"{'Season Phase':<15}", end="")
        for gp in GamePhase:
            print(f"{gp.value:<15}", end="")
        print()

        for sp in SeasonPhase:
            print(f"{sp.value:<15}", end="")
            for gp in GamePhase:
                seg = profile.segment_stats.get((sp.value, gp.value))
                if seg and seg.total_shots > 0:
                    print(f"{seg.total_goals}/{seg.total_shots:<12}", end="")
                else:
                    print(f"{'0/0':<15}", end="")
            print()

        return 0

    # Full pipeline for all players
    print(f"Running full pipeline (min shots: {min_shots})...")
    print("(This may take a while for large datasets)")
    print()

    profiles = run_shot_location_pipeline(
        season=season,
        output_dir=output_dir,
        min_shots=min_shots,
        db=db,
    )

    print()
    print(f"Processed {len(profiles)} players with {min_shots}+ shots")
    print(f"Output files saved to: {output_dir}")
    print(f"  - player_shot_locations_{season}.json")
    print(f"  - player_shot_locations_{season}.csv")
    print(f"  - player_shot_heatmaps_{season}.json")
    print(f"  - player_shot_simulation_{season}.json")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="NHL Data Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full pipeline for a season
  python -m src.processors.run_analysis season-segments --season 20242025

  # Validate only (no export)
  python -m src.processors.run_analysis season-segments --season 20242025 --validate-only

  # Single player analysis
  python -m src.processors.run_analysis season-segments --season 20242025 --player 8478402

  # Query player stats
  python -m src.processors.run_analysis query --player 8478402 --season 20242025

  # Shot location analysis
  python -m src.processors.run_analysis shot-locations --season 20242025
  python -m src.processors.run_analysis shot-locations --season 20242025 --player 8478402
  python -m src.processors.run_analysis shot-locations --season 20242025 --min-shots 20
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Season segments command
    seg_parser = subparsers.add_parser(
        "season-segments",
        help="Run season + game segment aggregation pipeline"
    )
    seg_parser.add_argument(
        "--season",
        type=int,
        default=None,
        help=f"Season to analyze (default: {CURRENT_SEASON})",
    )
    seg_parser.add_argument(
        "--player",
        type=int,
        default=None,
        help="Single player ID for targeted analysis",
    )
    seg_parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run validation only, no export",
    )
    seg_parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip validation step",
    )
    seg_parser.add_argument(
        "--sample",
        type=int,
        default=50,
        help="Number of players to sample for validation (default: 50)",
    )
    seg_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory (default: data/exports/)",
    )

    # Query command
    query_parser = subparsers.add_parser(
        "query",
        help="Query a player's segment stats"
    )
    query_parser.add_argument(
        "--player",
        type=int,
        required=True,
        help="Player ID to query",
    )
    query_parser.add_argument(
        "--season",
        type=int,
        default=None,
        help=f"Season to query (default: {CURRENT_SEASON})",
    )

    # Shot locations command
    shot_parser = subparsers.add_parser(
        "shot-locations",
        help="Run player shot location analysis pipeline"
    )
    shot_parser.add_argument(
        "--season",
        type=int,
        default=None,
        help=f"Season to analyze (default: {CURRENT_SEASON})",
    )
    shot_parser.add_argument(
        "--player",
        type=int,
        default=None,
        help="Single player ID for targeted analysis",
    )
    shot_parser.add_argument(
        "--min-shots",
        type=int,
        default=10,
        help="Minimum shots required to include player (default: 10)",
    )
    shot_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory (default: data/exports/)",
    )

    args = parser.parse_args()

    # Set up logging
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<level>{level}</level>: {message}",
    )

    if args.command == "season-segments":
        return cmd_season_segments(args)
    elif args.command == "query":
        return cmd_query_player(args)
    elif args.command == "shot-locations":
        return cmd_shot_locations(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
