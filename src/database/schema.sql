-- NHL Player Data Collection Schema
-- SQLite database for storing players, games, and per-game performance metrics

-- Core player information
CREATE TABLE IF NOT EXISTS players (
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
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Game information
CREATE TABLE IF NOT EXISTS games (
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Player performance per game (the core table)
CREATE TABLE IF NOT EXISTS player_game_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    game_id INTEGER NOT NULL,
    team_abbrev TEXT,
    opponent_abbrev TEXT,
    is_home INTEGER,

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

-- Progress tracking for resumable collection
CREATE TABLE IF NOT EXISTS collection_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_type TEXT NOT NULL,       -- 'roster', 'player_games', 'game_details'
    entity_id TEXT NOT NULL,             -- player_id or team_abbrev
    season INTEGER,
    status TEXT DEFAULT 'pending',       -- 'pending', 'in_progress', 'complete', 'error'
    last_error TEXT,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(collection_type, entity_id, season)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_player_game_stats_player ON player_game_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_game_stats_game ON player_game_stats(game_id);
CREATE INDEX IF NOT EXISTS idx_player_game_stats_team ON player_game_stats(team_abbrev);
CREATE INDEX IF NOT EXISTS idx_player_game_stats_opponent ON player_game_stats(opponent_abbrev);
CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date);
CREATE INDEX IF NOT EXISTS idx_games_season ON games(season);
CREATE INDEX IF NOT EXISTS idx_players_team ON players(current_team_abbrev);
CREATE INDEX IF NOT EXISTS idx_players_position ON players(position);
CREATE INDEX IF NOT EXISTS idx_players_active ON players(is_active);
CREATE INDEX IF NOT EXISTS idx_collection_progress_status ON collection_progress(status);
CREATE INDEX IF NOT EXISTS idx_collection_progress_type ON collection_progress(collection_type);
