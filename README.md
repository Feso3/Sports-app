# NHL Player Cards

Player card profiles built from real NHL data. Collectors pull data from the NHL API into a local SQLite database. Player cards surface that data per player, per game, and per season phase.

## Project Structure

```
Sports-app/
├── data/                    # Data storage
│   ├── raw/                 # Raw API data
│   ├── processed/           # Player card output
│   └── cache/               # API response cache
├── src/                     # Source code
│   ├── collectors/          # NHL API data collectors
│   ├── database/            # SQLite database layer
│   └── models/              # Data models
├── config/                  # Configuration files
├── tests/                   # Test suite
├── pyproject.toml           # Project configuration
└── requirements.txt         # Python dependencies
```

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Data Collection

Data is stored in `data/nhl_players.db` (SQLite). Collectors are resumable.

```bash
# Collect players + game logs for the current season
python -m src.collectors.run collect --full

# Check collection status
python -m src.collectors.run status

# Collect shot data for a season
python -m src.collectors.run shots --season 20242025
```

## Testing

```bash
pytest
```
