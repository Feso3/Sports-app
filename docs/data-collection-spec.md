# Technical Specification: Player Data Collection System

**Date:** January 28, 2026
**Duration:** 1 Day Implementation
**Goal:** Collect all NHL players, their games played, and per-game performance metrics into a local SQLite database

---

## Overview

This specification outlines a focused 1-day effort to establish the foundational data infrastructure: a SQLite database containing every active NHL player, every game they've played, and their performance metrics for each game.

---

## Phase 1: Database Setup (2 hours)

### Objective
Create a SQLite database with normalized schema for players, games, and player-game statistics.

### Schema

```sql
-- Core player information
CREATE TABLE players (
    player_id INTEGER PRIMARY KEY,        -- NHL API player ID
    full_name TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    position TEXT,                        -- C, LW, RW, D, G
    shoots_catches TEXT,                  -- L, R
    height_inches INTEGER,
    weight_lbs INTEGER,
    birth_date TEXT,
    birth_city TEXT,
    birth_country TEXT,
    current_team_id INTEGER,
    current_team_abbrev TEXT,
    jersey_number INTEGER,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Game information
CREATE TABLE games (
    game_id INTEGER PRIMARY KEY,          -- NHL API game ID (e.g., 2024020001)
    season INTEGER NOT NULL,              -- e.g., 20242025
    game_type INTEGER,                    -- 2=regular, 3=playoffs
    game_date TEXT NOT NULL,
    home_team_id INTEGER,
    home_team_abbrev TEXT,
    away_team_id INTEGER,
    away_team_abbrev TEXT,
    home_score INTEGER,
    away_score INTEGER,
    game_state TEXT,                      -- FINAL, LIVE, etc.
    venue TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Player performance per game (the core table)
CREATE TABLE player_game_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    game_id INTEGER NOT NULL,
    team_abbrev TEXT,
    opponent_abbrev TEXT,
    is_home BOOLEAN,

    -- Skater stats
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0,
    plus_minus INTEGER DEFAULT 0,
    pim INTEGER DEFAULT 0,               -- Penalty minutes
    shots INTEGER DEFAULT 0,
    hits INTEGER DEFAULT 0,
    blocked_shots INTEGER DEFAULT 0,
    power_play_goals INTEGER DEFAULT 0,
    power_play_points INTEGER DEFAULT 0,
    shorthanded_goals INTEGER DEFAULT 0,
    shorthanded_points INTEGER DEFAULT 0,
    game_winning_goals INTEGER DEFAULT 0,
    overtime_goals INTEGER DEFAULT 0,
    toi_seconds INTEGER DEFAULT 0,       -- Time on ice in seconds
    faceoff_wins INTEGER DEFAULT 0,
    faceoff_losses INTEGER DEFAULT 0,

    -- Goalie stats (NULL for skaters)
    games_started INTEGER,
    wins INTEGER,
    losses INTEGER,
    ot_losses INTEGER,
    saves INTEGER,
    shots_against INTEGER,
    goals_against INTEGER,
    save_percentage REAL,
    gaa REAL,                            -- Goals against average
    shutouts INTEGER,

    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id),
    UNIQUE(player_id, game_id)
);

-- Indexes for common queries
CREATE INDEX idx_player_game_stats_player ON player_game_stats(player_id);
CREATE INDEX idx_player_game_stats_game ON player_game_stats(game_id);
CREATE INDEX idx_games_date ON games(game_date);
CREATE INDEX idx_games_season ON games(season);
CREATE INDEX idx_players_team ON players(current_team_abbrev);

-- Progress tracking for resumable collection
CREATE TABLE collection_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_type TEXT NOT NULL,       -- 'roster', 'player_games', 'game_details'
    entity_id TEXT NOT NULL,             -- player_id or team_abbrev
    season INTEGER,
    status TEXT DEFAULT 'pending',       -- 'pending', 'in_progress', 'complete', 'error'
    last_error TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(collection_type, entity_id, season)
);
```

### Deliverables
- `src/database/schema.sql` - Schema definition
- `src/database/db.py` - Database connection and helper functions
- Database file: `data/nhl_players.db`

---

## Phase 2: Player Collection (2 hours)

### Objective
Collect all active NHL players from all 32 team rosters.

### Process
1. Fetch list of all 32 NHL teams from `/stats/rest/en/team`
2. For each team, fetch current roster from `/v1/roster/{team_abbrev}/current`
3. For each player, fetch detailed profile from `/v1/player/{player_id}/landing`
4. Insert into `players` table

### API Endpoints Used
```
GET https://api.nhle.com/stats/rest/en/team
GET https://api-web.nhle.com/v1/roster/{team_abbrev}/current
GET https://api-web.nhle.com/v1/player/{player_id}/landing
```

### Rate Limiting Strategy
- 60 requests/minute max (existing config)
- 0.5 second delay between requests
- Exponential backoff on failures (3 retries)

### Expected Volume
- 32 teams
- ~25 players per roster = ~800 players
- ~850 API calls total
- Estimated time: ~15 minutes

### Deliverables
- `src/collectors/player_collector.py` - Player collection logic
- All ~800 players in database

---

## Phase 3: Game Log Collection (4 hours)

### Objective
For each player, collect their game-by-game statistics for the current season (expandable to multiple seasons).

### Process
1. Query all player_ids from database
2. For each player, fetch game log from `/v1/player/{player_id}/game-log/{season}/2`
3. Parse game log entries into `player_game_stats` records
4. Create `games` records as encountered (deduplication via game_id)

### API Endpoint
```
GET https://api-web.nhle.com/v1/player/{player_id}/game-log/20242025/2
```
- Season format: `20242025` for 2024-25 season
- Game type: `2` = regular season, `3` = playoffs

### Expected Volume (Current Season)
- ~800 players
- ~800 API calls for game logs
- ~40-50 games per player so far = ~35,000 player-game records
- Estimated time: ~20-30 minutes

### Resumability
- Track progress in `collection_progress` table
- On restart, skip players already marked 'complete'
- Mark 'error' status with message for failed players

### Deliverables
- `src/collectors/game_log_collector.py` - Game log collection logic
- All player-game records in database

---

## Phase 4: Collection Orchestrator (1.5 hours)

### Objective
Create a command-line tool to run and monitor data collection.

### Commands
```bash
# Full collection (players + game logs for current season)
python -m src.collectors.run collect --full

# Players only
python -m src.collectors.run collect --players

# Game logs only (requires players first)
python -m src.collectors.run collect --game-logs --season 20242025

# Check progress
python -m src.collectors.run status

# Resume interrupted collection
python -m src.collectors.run collect --resume

# Historical seasons (run overnight)
python -m src.collectors.run collect --game-logs --season 20232024
python -m src.collectors.run collect --game-logs --season 20222023
```

### Progress Display
```
Collecting players...
[████████████████████████████████] 32/32 teams complete
Players collected: 812

Collecting game logs for season 20242025...
[████████████░░░░░░░░░░░░░░░░░░░░] 312/812 players
Current: Connor McDavid (8478402)
Records inserted: 14,230
Estimated time remaining: 12 minutes
```

### Deliverables
- `src/collectors/run.py` - CLI entry point
- Progress tracking and resume capability

---

## Phase 5: Verification & Queries (0.5 hours)

### Objective
Verify data integrity and provide example queries.

### Verification Queries
```sql
-- Count totals
SELECT COUNT(*) as player_count FROM players;
SELECT COUNT(*) as game_count FROM games;
SELECT COUNT(*) as stat_records FROM player_game_stats;

-- Check for missing data
SELECT p.full_name, p.player_id
FROM players p
LEFT JOIN player_game_stats pgs ON p.player_id = pgs.player_id
WHERE pgs.id IS NULL AND p.is_active = 1;

-- Top scorers
SELECT p.full_name, SUM(pgs.goals) as total_goals, SUM(pgs.assists) as assists
FROM players p
JOIN player_game_stats pgs ON p.player_id = pgs.player_id
GROUP BY p.player_id
ORDER BY total_goals DESC
LIMIT 10;
```

### Example Use Case Queries
```sql
-- All games for a specific player with stats
SELECT g.game_date, pgs.opponent_abbrev, pgs.goals, pgs.assists,
       pgs.shots, pgs.toi_seconds/60.0 as toi_minutes
FROM player_game_stats pgs
JOIN games g ON pgs.game_id = g.game_id
JOIN players p ON pgs.player_id = p.player_id
WHERE p.full_name = 'Connor McDavid'
ORDER BY g.game_date DESC;

-- Player performance against specific team
SELECT p.full_name, COUNT(*) as games,
       SUM(pgs.goals) as goals, SUM(pgs.assists) as assists
FROM player_game_stats pgs
JOIN players p ON pgs.player_id = p.player_id
WHERE pgs.opponent_abbrev = 'TOR'
GROUP BY p.player_id
ORDER BY goals DESC;
```

### Deliverables
- `src/database/queries.py` - Common query functions
- Verified data integrity

---

## File Structure (New Files)

```
Sports-app/
├── data/
│   └── nhl_players.db              # SQLite database (created)
│
└── src/
    ├── database/
    │   ├── __init__.py
    │   ├── schema.sql              # Database schema
    │   ├── db.py                   # Connection & helpers
    │   └── queries.py              # Common queries
    │
    └── collectors/
        ├── player_collector.py     # Player collection
        ├── game_log_collector.py   # Game log collection
        └── run.py                  # CLI orchestrator
```

---

## Timeline Summary

| Phase | Task | Duration |
|-------|------|----------|
| 1 | Database Setup | 2 hours |
| 2 | Player Collection | 2 hours |
| 3 | Game Log Collection | 4 hours |
| 4 | Collection Orchestrator | 1.5 hours |
| 5 | Verification | 0.5 hours |
| **Total** | | **10 hours** |

---

## Data Volume Estimates

### Current Season Only
- Players: ~800
- Games: ~700 (season so far)
- Player-game records: ~35,000
- Database size: ~10-15 MB

### With 3 Seasons History
- Players: ~1,200 (including retired/traded)
- Games: ~4,000
- Player-game records: ~200,000
- Database size: ~50-80 MB

### Full Historical (5+ seasons)
- Player-game records: ~400,000+
- Database size: ~150-200 MB
- Collection time: Run overnight (~4-6 hours)

---

## Future Extensions (Not in Scope for Day 1)

1. **Play-by-play events** - Individual shots, hits, faceoffs per game
2. **Advanced metrics** - Corsi, Fenwick, xG per game
3. **Scheduled updates** - Cron job for daily data refresh
4. **Historical backfill** - 10+ seasons of data
5. **Integration** - Connect to existing simulation engine

---

## Success Criteria

At end of day:
- [ ] SQLite database created with schema
- [ ] All ~800 active players collected
- [ ] Game logs for current season collected
- [ ] CLI tool working for collection and status
- [ ] Sample queries verified working
- [ ] Collection is resumable if interrupted
