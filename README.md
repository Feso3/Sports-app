# NHL Analytics Platform

A comprehensive analytics platform for NHL player-level analysis, heat map generation, synergy detection, and game simulation.

## Overview

This platform provides tools for:
- **Player-Level Analytics**: Individual offensive/defensive heat maps, shot analysis, zone-specific metrics
- **Game Segment Analysis**: Performance tracking across early/mid/late game periods
- **Matchup Analysis**: Player vs player and team vs team historical performance
- **Synergy Detection**: Identify player combinations that work well together
- **Game Simulation**: Monte Carlo simulation for outcome prediction

## Project Structure

```
nhl-analytics/
├── data/                    # Data storage
│   ├── raw/                 # Raw API data
│   ├── processed/           # Processed analytics data
│   └── cache/               # API response cache
├── src/                     # Source code
│   ├── collectors/          # Data collection modules
│   ├── processors/          # Data processing modules
│   ├── models/              # Data models
│   ├── analytics/           # Analytics calculations
│   └── visualization/       # Visualization components
├── simulation/              # Game simulation engine
├── config/                  # Configuration files
├── tests/                   # Test suite
└── notebooks/               # Jupyter notebooks for exploration
```

## Installation

### Prerequisites
- Python 3.10+
- pip or conda

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd nhl-analytics
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

Or install with development dependencies:
```bash
pip install -e ".[dev]"
```

## Quick Start

### Collecting Shot Data

```python
from src.collectors import NHLApiClient, ShotDataCollector

# Initialize collectors
with ShotDataCollector() as collector:
    # Collect shots from a single game
    shots = collector.collect_game_shots("2023020001")

    # Save to file
    collector.save_shots(shots, "data/raw/shots/game_2023020001.json")
```

### Collecting Player Data

```python
from src.collectors import PlayerStatsCollector

with PlayerStatsCollector() as collector:
    # Get a player profile
    profile = collector.get_player_profile(8478402)  # Connor McDavid

    # Get game log for a season
    game_log = collector.get_player_game_log(8478402, "20232024")
```

### Zone Analysis

```python
from src.processors import ZoneAnalyzer

analyzer = ZoneAnalyzer()

# Process shot data
for shot in shots:
    analyzer.process_shot(
        x=shot.x_coord,
        y=shot.y_coord,
        is_goal=shot.is_goal,
        shot_type=shot.shot_type,
        player_id=shot.shooter_id,
        player_name=shot.shooter_name,
        team_id=shot.team_id,
        team_abbrev=shot.team_abbrev,
        opponent_team_id=opponent_id,
    )

# Get player heat map
profile = analyzer.get_player_profile(8478402)
heat_map = profile.get_heat_map()
```

### Segment Analysis

```python
from src.processors import SegmentProcessor

processor = SegmentProcessor()

# Process game events
processor.process_game_events(
    game_id="2023020001",
    events=game_events,
    home_team_id=22,
    away_team_id=10,
)

# Get player stats by segment
early_stats = processor.get_player_segment_stats(8478402, "early_game")
late_stats = processor.get_player_segment_stats(8478402, "late_game")

# Calculate fatigue indicator
fatigue = processor.calculate_fatigue_indicator(8478402)
```

## Configuration

Configuration files are located in the `config/` directory:

- `api_config.yaml`: NHL API endpoints and rate limiting
- `zones.yaml`: Ice zone definitions for heat maps
- `segments.yaml`: Game time segment definitions
- `weights.yaml`: Metric weighting parameters

## Testing

Run the test suite:

```bash
pytest
```

With coverage:

```bash
pytest --cov=src --cov=simulation --cov-report=term-missing
```

## Implementation Phases

### Phase 1: Data Foundation (Complete)
- [x] NHL API integration
- [x] Shot data collection
- [x] Player stats collection
- [x] Timestamp data collection
- [x] Zone-based aggregation system
- [x] Segment analysis processing

### Phase 2: Analytics Layer (Complete)
- [x] Heat map generation
- [x] Zone-specific metrics (xG, Corsi, Fenwick)
- [x] Matchup history tracking
- [x] Pattern detection

### Phase 3: Synergy Detection
- [ ] Player combination analysis
- [ ] Line chemistry tracking
- [ ] Compatibility matrix

### Phase 4: Simulation Engine
- [ ] Zone-based expected goals model
- [ ] Line matchup logic
- [ ] Monte Carlo simulation
- [ ] Win probability predictions

### Phase 5: Validation & Refinement
- [ ] Historical backtesting
- [ ] Parameter optimization
- [ ] Confidence scoring

## API Reference

### Collectors

- `NHLApiClient`: Core API client for NHL Stats API
- `ShotDataCollector`: Shot location and outcome collection
- `PlayerStatsCollector`: Player statistics collection
- `TimestampDataCollector`: Event timing collection

### Processors

- `ZoneAnalyzer`: Zone-based shot analysis and heat maps
- `SegmentProcessor`: Game segment analysis
- `HeatMapProcessor`: Spatial heat map generation with xG integration
- `MatchupProcessor`: Player vs player and team vs team matchup tracking

### Analytics

- `MetricsCalculator`: Statistical calculations (xG, Corsi, Fenwick, PDO)
- `PatternDetector`: Play style classification and pattern detection

### Visualization

- `HeatMapVisualizer`: Renders shot and performance heat maps
- `ChartVisualizer`: Statistical charts and player comparisons

### Models

- `Player`: Player data and statistics
- `Team`: Team composition and configuration
- `Game`: Game state and events
- `Segment`: Game time segment definitions

## License

MIT License - see LICENSE file for details.
