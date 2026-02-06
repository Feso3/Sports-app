#!/usr/bin/env python3
"""
Interactive CLI for NHL Game Prediction

Provides a menu-driven interface for selecting teams and running
game simulations with the Monte Carlo prediction engine.

Usage:
    python -m cli.main
"""

from __future__ import annotations

import sys
from typing import Any

from loguru import logger

from diagnostics import DiagConfig, diag
from src.service.orchestrator import Orchestrator, PredictionOptions, TeamInfo


def configure_logging(verbose: bool = False) -> None:
    """Configure logging for CLI usage."""
    logger.remove()
    if verbose:
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stderr, level="WARNING")


def print_header() -> None:
    """Print welcome header."""
    print()
    print("=" * 60)
    print("   NHL Game Prediction Engine")
    print("   Monte Carlo Simulation System")
    print("=" * 60)
    print()


def print_teams(teams: list[TeamInfo]) -> None:
    """Print formatted list of teams."""
    print("\nAvailable Teams:")
    print("-" * 50)

    # Group by conference
    eastern = [t for t in teams if t.conference == "Eastern"]
    western = [t for t in teams if t.conference == "Western"]
    other = [t for t in teams if t.conference not in ("Eastern", "Western")]

    if eastern:
        print("\nEastern Conference:")
        for team in sorted(eastern, key=lambda t: t.name):
            print(f"  [{team.abbreviation:>3}] {team.name}")

    if western:
        print("\nWestern Conference:")
        for team in sorted(western, key=lambda t: t.name):
            print(f"  [{team.abbreviation:>3}] {team.name}")

    if other:
        print("\nOther:")
        for team in sorted(other, key=lambda t: t.name):
            print(f"  [{team.abbreviation:>3}] {team.name}")

    print()


def get_team_selection(
    teams: list[TeamInfo],
    prompt: str,
    exclude_abbrev: str | None = None,
) -> TeamInfo | None:
    """
    Get team selection from user.

    Args:
        teams: List of available teams
        prompt: Selection prompt message
        exclude_abbrev: Team abbreviation to exclude (already selected)

    Returns:
        Selected TeamInfo or None for cancel
    """
    # Build lookup
    abbrev_map = {t.abbreviation.upper(): t for t in teams}

    while True:
        user_input = input(f"{prompt} (abbreviation or 'list' or 'q' to quit): ").strip()

        if not user_input:
            continue

        if user_input.lower() == "q":
            return None

        if user_input.lower() == "list":
            print_teams(teams)
            continue

        abbrev = user_input.upper()

        if abbrev == exclude_abbrev:
            print("  Cannot select the same team twice. Please choose a different team.")
            continue

        if abbrev in abbrev_map:
            team = abbrev_map[abbrev]
            print(f"  Selected: {team.name}")
            return team

        # Try partial match on name
        matches = [t for t in teams if abbrev in t.name.upper()]
        if len(matches) == 1:
            team = matches[0]
            print(f"  Selected: {team.name} ({team.abbreviation})")
            return team
        elif len(matches) > 1:
            print(f"  Multiple matches found:")
            for t in matches:
                print(f"    [{t.abbreviation}] {t.name}")
            continue

        print(f"  Team '{user_input}' not found. Type 'list' to see all teams.")


def get_simulation_options() -> PredictionOptions:
    """Get simulation options from user."""
    print("\nSimulation Options:")
    print("  [1] Quick mode (1,000 iterations) - Faster, less precise")
    print("  [2] Standard mode (10,000 iterations) - Balanced")
    print("  [3] High precision (50,000 iterations) - Slower, more precise")
    print("  [Enter] Use default (Standard mode)")
    print()

    while True:
        choice = input("Select option (1-3 or Enter for default): ").strip()

        if not choice or choice == "2":
            return PredictionOptions(iterations=10000)
        elif choice == "1":
            return PredictionOptions(quick_mode=True)
        elif choice == "3":
            return PredictionOptions(iterations=50000)
        else:
            print("  Invalid option. Please choose 1, 2, or 3.")


def display_result(result: Any) -> None:
    """Display prediction result."""
    print()
    print(result.report)
    print()


def display_quick_summary(result: Any) -> None:
    """Display a quick summary of the result."""
    pred = result.prediction
    print()
    print("-" * 50)
    print(f"QUICK RESULT: {pred.home_team_name} vs {pred.away_team_name}")
    print("-" * 50)
    print(f"  Winner:     {pred.predicted_winner_name} ({pred.win_confidence.upper()} confidence)")
    print(f"  Home Win:   {pred.win_probability.home_win_pct:.1%}")
    print(f"  Away Win:   {pred.win_probability.away_win_pct:.1%}")
    print(f"  Likely Score: {pred.most_likely_score[0]}-{pred.most_likely_score[1]}")
    print("-" * 50)
    print()


def run_interactive() -> None:
    """Run the interactive CLI session."""
    print_header()

    print("Initializing prediction engine...")

    try:
        with Orchestrator() as orchestrator:
            print("Loading teams...")
            teams = orchestrator.get_available_teams()

            if not teams:
                print("Error: Could not load team list. Check your network connection.")
                return

            print(f"Loaded {len(teams)} teams.\n")

            # Main interaction loop
            while True:
                print("\n" + "=" * 50)
                print("MAIN MENU")
                print("=" * 50)
                print("  [1] Run game prediction")
                print("  [2] Quick prediction (fewer iterations)")
                print("  [3] View all teams")
                print("  [4] View cache status")
                print("  [5] Refresh team data")
                print("  [q] Quit")
                print()

                choice = input("Select option: ").strip().lower()

                if choice == "q" or choice == "quit":
                    print("\nThank you for using NHL Game Prediction Engine!")
                    break

                elif choice == "1":
                    # Full prediction
                    run_prediction(orchestrator, teams, quick=False)

                elif choice == "2":
                    # Quick prediction
                    run_prediction(orchestrator, teams, quick=True)

                elif choice == "3":
                    # Show teams
                    print_teams(teams)

                elif choice == "4":
                    # Cache status
                    show_cache_status(orchestrator)

                elif choice == "5":
                    # Refresh data
                    refresh_team_data(orchestrator, teams)

                else:
                    print("  Invalid option. Please choose 1-5 or 'q'.")

    except KeyboardInterrupt:
        print("\n\nInterrupted. Exiting...")
    except Exception as e:
        print(f"\nError: {e}")
        logger.exception("CLI error")
        raise


def run_prediction(
    orchestrator: Orchestrator,
    teams: list[TeamInfo],
    quick: bool = False,
) -> None:
    """Run a game prediction."""
    mode_name = "QUICK" if quick else "FULL"
    print(f"\n--- {mode_name} PREDICTION ---\n")

    # Select home team
    home_team = get_team_selection(teams, "Select HOME team")
    if home_team is None:
        print("  Cancelled.")
        return

    # Select away team
    away_team = get_team_selection(
        teams, "Select AWAY team", exclude_abbrev=home_team.abbreviation
    )
    if away_team is None:
        print("  Cancelled.")
        return

    # Get options (skip for quick mode)
    if quick:
        options = PredictionOptions(quick_mode=True)
    else:
        options = get_simulation_options()

    # Run prediction
    print(f"\nRunning simulation: {home_team.name} vs {away_team.name}")
    print(f"Iterations: {options.iterations:,}")
    print("Please wait...")
    print()

    try:
        result = orchestrator.predict_game(
            home_team_id=home_team.team_id,
            away_team_id=away_team.team_id,
            options=options,
        )

        if quick:
            display_quick_summary(result)
        else:
            display_result(result)

        # Ask for another with same teams
        again = input("Run another simulation with different options? (y/N): ").strip().lower()
        if again == "y":
            options = get_simulation_options()
            result = orchestrator.predict_game(
                home_team_id=home_team.team_id,
                away_team_id=away_team.team_id,
                options=options,
            )
            display_result(result)

    except Exception as e:
        print(f"\nError during prediction: {e}")
        logger.exception("Prediction error")


def show_cache_status(orchestrator: Orchestrator) -> None:
    """Display cache status."""
    status = orchestrator.get_cache_status()

    print("\n--- CACHE STATUS ---")
    print(f"  Teams cached:   {status.teams_cached}")
    print(f"  Players cached: {status.players_cached}")
    print(f"  Cache size:     {status.cache_size_mb:.1f} MB")
    if status.last_refresh:
        print(f"  Last refresh:   {status.last_refresh.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print("  Last refresh:   Never")
    if status.is_stale:
        print("  Status:         STALE (consider refreshing)")
    else:
        print("  Status:         Fresh")
    print()

    if input("Clear cache? (y/N): ").strip().lower() == "y":
        orchestrator.clear_cache()
        print("  Cache cleared.")


def refresh_team_data(orchestrator: Orchestrator, teams: list[TeamInfo]) -> None:
    """Refresh team data from API."""
    print("\n--- REFRESH DATA ---")
    print("  [1] Refresh specific team")
    print("  [2] Refresh all teams (slow)")
    print("  [Enter] Cancel")
    print()

    choice = input("Select option: ").strip()

    if choice == "1":
        team = get_team_selection(teams, "Select team to refresh")
        if team:
            print(f"Refreshing data for {team.name}...")
            try:
                orchestrator.refresh_data(team_id=team.team_id)
                print("  Done!")
            except Exception as e:
                print(f"  Error: {e}")

    elif choice == "2":
        confirm = input("This will refresh all 32 teams. Continue? (y/N): ").strip().lower()
        if confirm == "y":
            print("Refreshing all teams (this may take a while)...")
            orchestrator.refresh_all_data()
            print("  Done!")


def configure_diagnostics() -> None:
    """Configure diagnostics from CLI flags."""
    enabled = "--diagnostics" in sys.argv
    level = "lite"
    strict = "--strict" in sys.argv

    for i, arg in enumerate(sys.argv):
        if arg == "--diag-level" and i + 1 < len(sys.argv):
            level = sys.argv[i + 1]

    if enabled:
        jsonl_path = None
        for i, arg in enumerate(sys.argv):
            if arg == "--diag-log" and i + 1 < len(sys.argv):
                jsonl_path = sys.argv[i + 1]

        diag.configure(DiagConfig(
            enabled=True,
            level=level,
            strict=strict,
            jsonl_path=jsonl_path,
        ))
        print(f"[DIAG] Diagnostics enabled (level={level}, strict={strict})")


def main() -> int:
    """Main entry point."""
    # Check for command line flags
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    configure_logging(verbose)
    configure_diagnostics()

    try:
        run_interactive()
        # Print diagnostics checklist at end if enabled
        diag.print_checklist()
        return 0
    except Exception as e:
        print(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
