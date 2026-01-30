# Technical Specification: NHL Analytics Platform

## Objectives
- Collect and analyze NHL game data at individual player level.
- Generate offensive/defensive heat maps by zone.
- Identify player synergies and anti-synergies through historical matchup analysis.
- Detect strategic mismatches between teams based on spatial performance patterns.
- Track performance across game segments (early/mid/late game).
- Build a simulation engine for game outcome prediction.
- Support pre-game matchup analysis and post-game pattern validation.

## Data Collection Requirements

### Available Data Sources
- NHL Stats API for shot location, shot type, shooter identity.
- Goal events with primary/secondary assists.
- Goalie-on-ice for goals against.
- Zone start/exit data where available.
- Takeaways, blocked shots, hits.
- Corsi/Fenwick metrics.
- Expected goals (xG) and expected goals against (xGA).
- Timestamp data for game segment analysis.

### Data Not Publicly Available
- Pass completion data.
- Pass origin/destination coordinates.
- Interception events and locations.
- Requires manual tracking or computer vision if needed.

### Historical Data Depth
- Pull multiple seasons of data for pattern detection.
- Track player performance across teams/seasons.
- Maintain player identity across trades/team changes.
- Segment all metrics by game time periods.

## Core Features

### Player-Level Analytics
- Individual offensive heat maps by zone.
- Individual defensive performance by zone.
- Shot type distribution and accuracy.
- Shooting percentage by zone.
- Save percentage by zone (goalies).
- Zone-specific xG generation and prevention.
- Positional strength profiling.
- Performance metrics segmented by game time (early/mid/late).

### Game Segment Analysis
Segment definitions are driven by `config/segments.yaml`:
- **Early game**: Period 1 + first 10 minutes of Period 2.
- **Mid game**: Minutes 10-20 of Period 2 + first 10 minutes of Period 3.
- **Late game**: Final 10 minutes of regulation + overtime.

Segment-specific metrics include:
- Goal scoring distribution by segment.
- Shooting percentage by segment.
- Shot quality trends across game time.
- Defensive performance degradation/improvement.
- Stamina indicators (performance decay).
- Clutch performance identification.
- Momentum pattern detection.

### Matchup Analysis
- Player vs player historical performance.
- Player + player synergy detection.
- Line combination effectiveness metrics.
- Defensive pairing complement analysis.
- Team vs team historical outcomes by zone.
- Time-segment specific matchup performance.

### Team-Level Aggregation
- Offensive strength heat maps (aggregate player data).
- Defensive vulnerability maps (aggregate player data).
- Special teams performance by zone.
- Overall team tendencies and patterns.
- Game segment performance profiles.

### Pattern Detection
- Spatial mismatch identification (offensive strength vs defensive weakness).
- Play style classification (cross-ice reliance, dump-and-chase frequency).
- Contextual performance patterns (Player X vs Team Y).
- Synergy emergence through statistical correlation.
- Late-game collapse vs resilience patterns.
- Clutch performer identification.
- Fatigue-based vulnerability detection.

### Visualization
- Heat maps for shooting locations and success rates.
- Heat maps for shot prevention and goalie positioning.
- Zone-based performance overlays.
- Line combination performance charts.
- Player comparison visualizations.
- Game segment performance timelines.

## Simulation Engine
- Probabilistic game outcome prediction.
- Line matchup modeling.
- Zone-based expected goals calculation.
- Time-segment weighted performance modeling.
- Monte Carlo simulation (10,000+ iterations per matchup).
- Confidence scoring for predictions.

### Simulation Logic (High Level)
For each simulation iteration:
1. For each game segment (early/mid/late):
   - Determine line matchups.
   - Apply segment-specific performance weights.
   - Calculate offensive strength by zone (Team A).
   - Calculate defensive strength by zone (Team B).
   - Adjust for time-of-game factors (stamina, clutch).
   - Compute expected goals for Team A and Team B.
   - Apply variance/randomness.
2. Record game outcome.

After N iterations:
- Calculate win probability.
- Generate score distribution.
- Analyze segment-specific outcomes.
- Compute confidence intervals.

### Matchup Weighting Inputs
- Zone-specific performance (slot, perimeter, point).
- Historical head-to-head data.
- Line chemistry adjustments.
- Goalie matchup factors.
- Special teams probability.
- Game segment performance modifiers.
- Clutch/stamina adjustments.

### Output Metrics
- Win probability percentage.
- Expected score distribution.
- Segment-specific scoring predictions.
- High-variance vs low-variance matchup classification.
- Key mismatch identification.
- Late-game advantage analysis.
- Confidence score based on data quality and sample size.

## Constraints

### Technical Limitations
- No real-time pass tracking without custom computer vision.
- API rate limits on NHL data sources.
- Historical data availability varies by season.
- Some advanced metrics proprietary (NHL Edge IQ).
- Timestamp precision varies by data source.

### Data Quality
- Coordinate precision varies by data source.
- Earlier seasons may have incomplete tracking data.
- Manual validation required for computer vision approaches.
- Player identity tracking across trades/name changes.
- Game segment boundaries require consistent source data.

### Modeling Assumptions
- Individual player metrics aggregate linearly for line performance (initial approximation).
- Historical performance is predictive of future performance.
- Zone-based analysis captures sufficient spatial granularity.
- Synergy effects detectable through statistical correlation.
- Game segments capture fatigue and momentum effects.
- Three-segment division sufficient for time-based analysis.

## Current Implementation Snapshot

### Data Collection & Storage
- SQLite schema, connection helpers, and query utilities in `src/database/`.
- Collectors for players, game logs, shots, and timestamps in `src/collectors/`.
- CLI entry point for collection workflows in `src/collectors/run.py`.

### Processing & Analytics
- Zone, segment, matchup, and synergy processors in `src/processors/`.
- Analytics modules for metrics, patterns, synergy, clutch, and stamina in `src/analytics/`.

### Simulation & Prediction
- Simulation engine, adjustments, and prediction output in `simulation/`.
- Prediction orchestration via `src/service/orchestrator.py`.

### Interfaces & Visualization
- Interactive CLI via `cli/main.py`.
- Visualization helpers in `src/visualization/` (heat maps and charts).

## File Structure (Current)

```
Sports-app/
├── data/
│   ├── raw/
│   ├── processed/
│   └── cache/
├── src/
│   ├── collectors/
│   │   ├── nhl_api.py
│   │   ├── shot_data.py
│   │   ├── player_stats.py
│   │   ├── timestamp_data.py
│   │   ├── player_collector.py
│   │   ├── game_log_collector.py
│   │   ├── shot_collector.py
│   │   └── run.py
│   ├── processors/
│   │   ├── heat_map.py
│   │   ├── zone_analysis.py
│   │   ├── segment_analysis.py
│   │   ├── matchup.py
│   │   └── synergy.py
│   ├── analytics/
│   │   ├── metrics.py
│   │   ├── patterns.py
│   │   ├── synergy.py
│   │   └── clutch_analysis.py
│   ├── models/
│   │   ├── player.py
│   │   ├── team.py
│   │   ├── game.py
│   │   └── segment.py
│   ├── service/
│   │   ├── orchestrator.py
│   │   └── data_loader.py
│   └── visualization/
│       ├── heat_maps.py
│       └── charts.py
├── simulation/
│   ├── models.py
│   ├── expected_goals.py
│   ├── matchups.py
│   ├── adjustments.py
│   ├── engine.py
│   └── predictions.py
├── cli/
│   └── main.py
├── config/
│   ├── api_config.yaml
│   ├── zones.yaml
│   ├── segments.yaml
│   └── weights.yaml
└── tests/
    ├── test_collectors/
    ├── test_processors/
    ├── test_analytics/
    ├── test_simulation/
    └── test_integration/
```

## Implementation Phases (Status)

### Phase 1: Data Foundation (Complete)
- NHL API integration and collection workflows.
- Player, game log, and shot storage in SQLite.
- Zone-based aggregation and timestamp capture.

### Phase 2: Analytics Layer (Complete)
- Heat map generation and zone-specific metrics.
- Matchup history tracking and pattern detection.
- Segment analysis processing.

### Phase 3: Synergy Detection (Complete)
- Player combination analysis and chemistry tracking.
- Compatibility matrices.
- Clutch performance and stamina analysis.

### Phase 4: Simulation Engine (Complete)
- Zone-based expected goals model.
- Line matchup logic with synergy integration.
- Monte Carlo simulation with segment weighting and adjustments.
- Win probability predictions with confidence scoring.

### Phase 4b: Interactive Local Interface (Complete)
- Service orchestrator and data loader for prediction workflows.
- Interactive CLI for team selection and simulation.
- Integration test coverage for end-to-end workflow.

### Phase 5: Validation & Refinement (Planned)
- Historical backtesting.
- Parameter optimization.
- Confidence scoring refinement.

## Known Gaps & Future Work
- Historical backtesting suite for simulation outputs.
- Expanded validation on historical seasons (multi-season backfill).
- Optional web interface for broader accessibility.
- Enhanced visualization outputs (dashboards or richer CLI output).

## Related Documentation
- [Implementation History](docs/implementation-history.md)
- [Development History](docs/development-history.md)
- [Product Roadmap](docs/roadmap.md)
- [Data Collection Spec](docs/data-collection-spec.md)
- [Phase 4b Context](docs/phase-4b-context.md)

*Last updated: 2026-01-28 (aligns with Phase 4b completion notes).*
