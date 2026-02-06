#!/usr/bin/env python3
"""
NHL Simulator Smoke Test with Diagnostics

Runs a single small simulation pass and prints the full 4-stage
"film reel" diagnostics log.

Usage:
    python run_smoke.py --home TOR --away EDM --diagnostics
    python run_smoke.py --home TOR --away EDM --diagnostics --diag-level verbose
    python run_smoke.py --home TOR --away EDM --diagnostics --diag-level normal --strict
    python run_smoke.py --home TOR --away EDM --diagnostics --diag-log diag_output.jsonl
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger


def main() -> int:
    parser = argparse.ArgumentParser(
        description="NHL Simulator Smoke Test with Diagnostics"
    )
    parser.add_argument("--home", required=True, help="Home team abbreviation (e.g. TOR)")
    parser.add_argument("--away", required=True, help="Away team abbreviation (e.g. EDM)")
    parser.add_argument(
        "--iterations", type=int, default=100,
        help="Number of simulation iterations (default: 100 for smoke test)",
    )
    parser.add_argument("--diagnostics", action="store_true", default=True, help="Enable diagnostics (default: on for smoke test)")
    parser.add_argument(
        "--diag-level", choices=["lite", "normal", "verbose"], default="lite",
        help="Diagnostics verbosity level (default: lite)",
    )
    parser.add_argument("--diag-log", default=None, help="Path to write JSONL diagnostics log")
    parser.add_argument("--strict", action="store_true", help="Raise on sanity check failures")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose application logging")

    args = parser.parse_args()

    # Configure application logging
    logger.remove()
    if args.verbose:
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stderr, level="WARNING")

    # Configure diagnostics
    from diagnostics import DiagConfig, diag

    diag.configure(DiagConfig(
        enabled=args.diagnostics,
        level=args.diag_level,
        strict=args.strict,
        jsonl_path=args.diag_log,
    ))

    print()
    print("=" * 62)
    print("  NHL SIMULATOR - SMOKE TEST")
    print("=" * 62)
    print(f"  Matchup:      {args.home} vs {args.away}")
    print(f"  Iterations:   {args.iterations}")
    print(f"  Diagnostics:  {'ON' if args.diagnostics else 'OFF'} (level={args.diag_level})")
    print(f"  Strict mode:  {'ON' if args.strict else 'OFF'}")
    if args.diag_log:
        print(f"  JSONL log:    {args.diag_log}")
    print("=" * 62)
    print()

    # Run the prediction
    from src.service.orchestrator import Orchestrator, PredictionOptions

    try:
        with Orchestrator() as orchestrator:
            options = PredictionOptions(iterations=args.iterations)
            result = orchestrator.predict_game(
                home_team_abbrev=args.home.upper(),
                away_team_abbrev=args.away.upper(),
                options=options,
            )

            # Print the report
            print(result.report)

            # Record output and print checklist
            if args.diag_log:
                diag.record_output(args.diag_log)
            diag.print_checklist()

    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 1
    except Exception as e:
        print(f"\nError: {e}")
        logger.exception("Smoke test error")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
