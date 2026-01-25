# Phase 4b: Interactive Local Interface - Context Capsule

## Purpose

Phase 4b adds a usable entry point for running game simulations without writing Python code. This enables testing, iteration, and hands-on exploration during development.

## Problem Statement

The platform currently exists as a library-only implementation:
- No CLI scripts, no `main.py`, no `__main__` blocks
- Must be used programmatically via direct imports
- No way to quickly test a prediction without writing code

## Goals

1. **Testability**: Run simulations interactively to validate the engine
2. **Iteration Speed**: Quickly try different team matchups during development
3. **Zero Architecture Impact**: Add functionality without modifying existing code
4. **Future-Proof**: Design for easy replacement with web interface later

## Scope

### In Scope
- Service orchestrator to coordinate existing modules
- Data caching layer to avoid repeated API calls
- Interactive CLI for team selection and simulation
- Basic result display (win probability, key factors)

### Out of Scope
- Web interface (future phase)
- Real-time data streaming
- User authentication
- Persistent result storage beyond cache

## Architecture

### New Components

```
src/service/
├── __init__.py
├── orchestrator.py     # Workflow coordination
└── data_loader.py      # Data bootstrap and caching

cli/
├── __init__.py
└── main.py             # Interactive menu entry point
```

### Data Flow

```
User Input (CLI)
    ↓
Orchestrator
    ↓
Data Loader (check cache → fetch if needed)
    ↓
Collectors (NHL API, rate-limited)
    ↓
Processors (zone analysis, synergy, matchups)
    ↓
Simulation Engine (Monte Carlo)
    ↓
Results Display (CLI output)
```

### Integration Points

| Component | Integrates With | Notes |
|-----------|-----------------|-------|
| Orchestrator | All collectors, processors, simulation | Thin wrapper, dependency injection |
| Data Loader | diskcache, NHL API client | Uses existing cache infrastructure |
| CLI | Orchestrator only | Single dependency, clean interface |

## Implementation Tasks

### 1. Service Orchestrator (~150-200 lines)
**File**: `src/service/orchestrator.py`

Responsibilities:
- Initialize collectors with configuration
- Load or fetch team/player data via data loader
- Feed data through processors
- Run simulation with processed metrics
- Return `SimulationResult` objects

Key methods:
- `predict_game(home_team, away_team, options)` → `SimulationResult`
- `get_available_teams()` → `List[Team]`
- `refresh_data(team_ids)` → None

### 2. Data Loader (~100 lines)
**File**: `src/service/data_loader.py`

Responsibilities:
- Cache current season rosters locally
- Store recent game stats (configurable depth, default: last 20 games)
- Provide refresh command for manual data updates
- Fall back to cached data when offline/rate-limited

Key methods:
- `load_team(team_id)` → `Team`
- `load_roster(team_id)` → `List[Player]`
- `refresh_team_data(team_id)` → None
- `get_cache_status()` → `CacheStatus`

### 3. Interactive CLI (~100-150 lines)
**File**: `cli/main.py`

Responsibilities:
- Display menu of available teams
- Accept team selection (home/away)
- Optional: adjust simulation parameters
- Run simulation via orchestrator
- Display results in readable format
- Loop for multiple simulations

User flow:
```
1. Welcome message
2. List teams (with abbreviations)
3. Select home team
4. Select away team
5. [Optional] Adjust parameters
6. Run simulation
7. Display results
8. Run another? (Y/N)
```

### 4. Integration Tests
**Location**: `tests/test_integration/`

Test scenarios:
- End-to-end simulation with mock data
- Cache hit/miss behavior
- Offline mode with cached data
- Error handling for API failures

## Dependencies

### Existing (No Changes)
- `diskcache` - Already used for API caching
- `pydantic` - Models already JSON-serializable
- All collectors, processors, simulation modules

### New (Optional)
- `rich` - For prettier CLI output (tables, colors)
  - Can use plain `print()` statements if preferred

## Configuration

No new config files required. Uses existing:
- `config/api_config.yaml` - API settings
- `config/weights.yaml` - Simulation parameters

Optional additions to existing configs:
- Cache TTL for roster data
- Default simulation iterations for CLI

## Success Criteria

1. Can run `python -m cli.main` and get an interactive prompt
2. Can select two teams and see win probability within 30 seconds
3. Works offline with cached data
4. No modifications to existing src/ or simulation/ code

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| API rate limiting during testing | Slow iteration | Data caching layer |
| Large data fetches on first run | Poor UX | Progress indicators, background fetch |
| Incomplete roster data | Simulation errors | Graceful fallbacks, clear error messages |

## Future Considerations

This phase intentionally creates a clean interface layer that can be:
- Wrapped by FastAPI/Flask for web access
- Extended with additional CLI commands
- Replaced entirely without touching core logic

The orchestrator pattern enables future features like:
- Batch predictions
- Scheduled data refreshes
- Result persistence to database
