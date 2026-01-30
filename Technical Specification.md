# Technical Specification: NHL Analytics Platform

## Objectives
- Collect and analyze NHL game data at the player level.
- Generate zone-based offense/defense profiles and heat maps.
- Detect player synergies and matchup-specific patterns.
- Model segment-aware performance (early/mid/late game).
- Simulate game outcomes and report win probabilities.

## Data Collection & Constraints

### Primary Sources
- NHL Stats API for shot locations, outcomes, and player identities.
- Game logs for per-game player stats and team context.

### Limitations
- No public pass-tracking or interception locations.
- Historical data coverage varies by season.
- Rate limits and inconsistent coordinate precision require retries and normalization.

## Core Features

### Player-Level Analytics
- Zone-specific shot generation and prevention.
- Segment-based performance splits.
- Matchup history and situational trends.

### Synergy & Context
- Line chemistry analysis based on shared performance deltas.
- Clutch and stamina indicators to model late-game variance.

### Simulation Engine
- Monte Carlo simulation using zone-based expected goals.
- Segment weighting and adjustments for synergy, clutch, and fatigue.
- Prediction reporting with win probability and confidence signals.

## Current Implementation Snapshot
- SQLite-backed data collection for players, game logs, and shots.
- Processing pipeline for zones, segments, matchups, and synergy signals.
- Simulation engine and CLI workflows for running predictions locally.

## Known Gaps & Next Work
- Historical backtesting harness and calibration metrics.
- Expanded multi-season data backfill.
- Richer visualization outputs beyond current heat maps and charts.

*Last updated: 2026-01-28.*
