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
│   ├── service/             # Orchestration layer (Phase 4b)
│   └── visualization/       # Visualization components
├── simulation/              # Game simulation engine
├── cli/                     # Interactive command-line interface (Phase 4b)
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

### Game Simulation

```python
from simulation import GameSimulationEngine, SimulationConfig, PredictionGenerator

# Configure simulation
config = SimulationConfig(
    home_team_id=22,  # Edmonton Oilers
    away_team_id=10,  # Toronto Maple Leafs
    iterations=10000,
    use_synergy_adjustments=True,
    use_clutch_adjustments=True,
    use_fatigue_adjustments=True,
)

# Run simulation
engine = GameSimulationEngine()
result = engine.simulate(config, home_team, away_team, players)

# Generate prediction report
generator = PredictionGenerator()
prediction = generator.generate_prediction(
    result,
    home_team_name="Edmonton Oilers",
    away_team_name="Toronto Maple Leafs",
)

# Print formatted report
print(generator.generate_report(prediction))

# Get JSON output for API integration
json_output = generator.generate_json_output(prediction)
```

### Synergy Analysis

```python
from src.analytics.synergy import SynergyAnalyzer
from src.analytics.clutch_analysis import ClutchAnalyzer, StaminaAnalyzer

# Analyze player synergies
synergy = SynergyAnalyzer()
score = synergy.calculate_synergy(player_id_1, player_id_2)
line_chemistry = synergy.line_synergy([player_1, player_2, player_3])

# Clutch performance analysis
clutch = ClutchAnalyzer()
metrics = clutch.get_metrics(player_id)
print(f"Clutch score: {metrics.clutch_score}")
print(f"Classification: {metrics.clutch_level}")

# Stamina/fatigue analysis
stamina = StaminaAnalyzer()
fatigue = stamina.calculate_fatigue_indicator(player_id)
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

### Phase 3: Synergy Detection (Complete)
- [x] Player combination analysis
- [x] Line chemistry tracking
- [x] Compatibility matrix
- [x] Clutch performer identification
- [x] Stamina/fatigue analysis

### Phase 4: Simulation Engine (Complete)
- [x] Zone-based expected goals model
- [x] Line matchup logic with synergy integration
- [x] Monte Carlo simulation (10,000+ iterations)
- [x] Segment-specific weighting with clutch/stamina adjustments
- [x] Win probability predictions with confidence scoring

### Phase 4b: Interactive Local Interface
- [ ] Service orchestrator (connects collectors → processors → simulation)
- [ ] Data loader/cache manager (bootstrap team rosters and stats)
- [ ] Interactive CLI (team selection, run simulations, view results)
- [ ] Integration testing for end-to-end workflow

### Phase 5: Validation & Refinement
- [ ] Historical backtesting
- [ ] Parameter optimization
- [ ] Confidence scoring refinement

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
- `ChemistryTracker`: Synergy ingestion and line chemistry tracking

### Analytics

- `MetricsCalculator`: Statistical calculations (xG, Corsi, Fenwick, PDO)
- `PatternDetector`: Play style classification and pattern detection
- `SynergyAnalyzer`: Player combination synergy and compatibility matrices
- `ClutchAnalyzer`: Clutch performance scoring and classification
- `StaminaAnalyzer`: Fatigue indicators and late-game performance tracking

### Simulation

- `SimulationConfig`: Configuration for simulation runs (iterations, adjustments, weights)
- `GameSimulationEngine`: Monte Carlo simulation engine with segment-based modeling
- `ExpectedGoalsCalculator`: Zone-based expected goals for teams and lines
- `MatchupAnalyzer`: Line-on-line matchup analysis with synergy integration
- `AdjustmentCalculator`: Clutch, fatigue, and segment-specific modifiers
- `PredictionGenerator`: Win probability and formatted prediction output
- `SimulationResult`: Complete results with score distributions and confidence metrics

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
