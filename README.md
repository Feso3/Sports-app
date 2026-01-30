# NHL Analytics Platform

A focused analytics platform for NHL player-level insights, matchup evaluation, and game simulation.

## Overview

Key capabilities include:
- Player-level heat maps and zone metrics
- Matchup and synergy analysis
- Segment-aware simulation and prediction
- Local CLI for running predictions

## Project Structure

```
Sports-app/
├── data/                    # Data storage
│   ├── raw/                 # Raw API data (JSON)
│   ├── processed/           # Processed analytics data
│   └── cache/               # API response cache
├── src/                     # Source code
│   ├── collectors/          # Data collection modules
│   ├── database/            # Database layer
│   ├── processors/          # Data processing modules
│   ├── models/              # Data models
│   ├── analytics/           # Analytics calculations
│   ├── service/             # Orchestration layer
│   └── visualization/       # Visualization components
├── simulation/              # Game simulation engine
├── cli/                     # Interactive command-line interface
├── config/                  # Configuration files
├── docs/                    # Historical context
├── tests/                   # Test suite
├── pyproject.toml           # Project configuration
└── requirements.txt         # Python dependencies
```

## Documentation

- [Technical Specification](Technical%20Specification.md)
- [Project History](docs/project-history.md)

## Installation

### Prerequisites
- Python 3.10+
- pip or conda

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd Sports-app
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

### Interactive CLI (Recommended)

```bash
python -m cli.main
```

Use the menu to select teams, run predictions, and view results.

### Programmatic Usage

```python
from src.service import Orchestrator, PredictionOptions

with Orchestrator() as orch:
    result = orch.predict_by_abbreviation("TOR", "BOS", quick=True)
    print(result.report)

    options = PredictionOptions(iterations=50000)
    detailed = orch.predict_game(
        home_team_abbrev="EDM",
        away_team_abbrev="VGK",
        options=options,
    )
    print(detailed.report)
```

## Data Collection

Data is stored in `data/nhl_players.db` (SQLite). The collectors are resumable, so rerun the same command after interruptions.

```bash
# Collect players + game logs for the current season
python -m src.collectors.run collect --full

# Check collection status
python -m src.collectors.run status

# Collect shot data for a season (2015-16 onward)
python -m src.collectors.run shots --season 20242025
```

## Configuration

Configuration files are located in `config/`:
- `api_config.yaml`: NHL API endpoints and rate limiting
- `zones.yaml`: Ice zone definitions for heat maps
- `segments.yaml`: Game time segment definitions
- `weights.yaml`: Metric weighting parameters

## Testing

```bash
pytest
```

## License

MIT License - see LICENSE file for details.
