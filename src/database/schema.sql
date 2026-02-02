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

-- Individual shot events (for detailed shot analysis)
-- Note: No foreign key constraints because shots include all players in a game,
-- not just those in our players table (opponents, historical players, etc.)
CREATE TABLE IF NOT EXISTS shots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,           -- Shooter
    team_abbrev TEXT,
    goalie_id INTEGER,                    -- Goalie faced

    -- Location and timing
    period INTEGER,
    time_in_period TEXT,                  -- MM:SS format
    time_remaining TEXT,
    x_coord REAL,                         -- Ice coordinates
    y_coord REAL,
    distance REAL,                        -- Distance from net

    -- Shot details
    shot_type TEXT,                       -- wrist, slap, snap, backhand, etc.
    is_goal INTEGER DEFAULT 0,
    strength TEXT,                        -- even, pp, sh
    empty_net INTEGER DEFAULT 0,
    game_winning_goal INTEGER DEFAULT 0,

    -- Assists (for goals)
    assist1_player_id INTEGER,
    assist2_player_id INTEGER,

    -- Metadata
    season INTEGER,
    event_description TEXT,

    UNIQUE(game_id, event_id)
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

-- Shot indexes for player-centric queries
CREATE INDEX IF NOT EXISTS idx_shots_player ON shots(player_id);
CREATE INDEX IF NOT EXISTS idx_shots_game ON shots(game_id);
CREATE INDEX IF NOT EXISTS idx_shots_season ON shots(season);
CREATE INDEX IF NOT EXISTS idx_shots_goalie ON shots(goalie_id);
CREATE INDEX IF NOT EXISTS idx_shots_player_season ON shots(player_id, season);
CREATE INDEX IF NOT EXISTS idx_shots_is_goal ON shots(is_goal);

-- ============================================================================
-- SIMULATION SUPPORT TABLES
-- ============================================================================

-- Schedule context for fatigue analysis
CREATE TABLE IF NOT EXISTS schedule_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_abbrev TEXT NOT NULL,
    game_id INTEGER NOT NULL,
    game_date TEXT NOT NULL,
    days_rest INTEGER,                    -- Days since last game (NULL if first game)
    is_back_to_back INTEGER DEFAULT 0,    -- 1 if playing second game in 2 days
    is_first_of_back_to_back INTEGER DEFAULT 0,  -- 1 if playing first game of back-to-back
    games_in_3_days INTEGER DEFAULT 1,    -- Number of games in 3-day window
    games_in_5_days INTEGER DEFAULT 1,    -- Number of games in 5-day window
    games_in_7_days INTEGER DEFAULT 1,    -- Number of games in 7-day window
    is_home INTEGER,                      -- 1 if home game
    previous_game_id INTEGER,             -- Reference to previous game
    win_streak INTEGER DEFAULT 0,         -- Current win streak (0 if none)
    loss_streak INTEGER DEFAULT 0,        -- Current loss streak (0 if none)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(team_abbrev, game_id)
);

-- Player matchup history (aggregated stats vs specific teams)
CREATE TABLE IF NOT EXISTS player_matchup_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    opponent_team_abbrev TEXT NOT NULL,
    season INTEGER NOT NULL,
    -- Sample size
    games_played INTEGER DEFAULT 0,
    -- Raw stats
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0,
    shots INTEGER DEFAULT 0,
    toi_seconds INTEGER DEFAULT 0,
    power_play_goals INTEGER DEFAULT 0,
    game_winning_goals INTEGER DEFAULT 0,
    -- Calculated rates
    goals_per_game REAL,
    assists_per_game REAL,
    points_per_game REAL,
    shots_per_game REAL,
    shooting_pct REAL,
    toi_per_game_seconds REAL,
    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, opponent_team_abbrev, season)
);

-- Goalie matchup history (performance vs specific teams)
CREATE TABLE IF NOT EXISTS goalie_matchup_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goalie_id INTEGER NOT NULL,
    opponent_team_abbrev TEXT NOT NULL,
    season INTEGER NOT NULL,
    -- Sample size
    games_played INTEGER DEFAULT 0,
    games_started INTEGER DEFAULT 0,
    -- Raw stats
    shots_against INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    ot_losses INTEGER DEFAULT 0,
    shutouts INTEGER DEFAULT 0,
    toi_seconds INTEGER DEFAULT 0,
    -- Calculated rates
    save_pct REAL,
    gaa REAL,
    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(goalie_id, opponent_team_abbrev, season)
);

-- Player general stats (season aggregates for comparison)
CREATE TABLE IF NOT EXISTS player_season_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    -- Sample size
    games_played INTEGER DEFAULT 0,
    -- Raw stats
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0,
    shots INTEGER DEFAULT 0,
    toi_seconds INTEGER DEFAULT 0,
    power_play_goals INTEGER DEFAULT 0,
    game_winning_goals INTEGER DEFAULT 0,
    -- Calculated rates
    goals_per_game REAL,
    assists_per_game REAL,
    points_per_game REAL,
    shots_per_game REAL,
    shooting_pct REAL,
    toi_per_game_seconds REAL,
    -- Standard deviations for similarity scoring
    goals_per_game_std REAL,
    points_per_game_std REAL,
    shots_per_game_std REAL,
    shooting_pct_std REAL,
    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, season)
);

-- Goalie season stats (for comparison with matchup stats)
CREATE TABLE IF NOT EXISTS goalie_season_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goalie_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    -- Sample size
    games_played INTEGER DEFAULT 0,
    games_started INTEGER DEFAULT 0,
    -- Raw stats
    shots_against INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    saves INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    ot_losses INTEGER DEFAULT 0,
    shutouts INTEGER DEFAULT 0,
    toi_seconds INTEGER DEFAULT 0,
    -- Calculated rates
    save_pct REAL,
    gaa REAL,
    -- Standard deviations
    save_pct_std REAL,
    gaa_std REAL,
    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(goalie_id, season)
);

-- Player momentum tracking (hot streaks / slumps)
CREATE TABLE IF NOT EXISTS player_momentum (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    calculated_date TEXT NOT NULL,
    season INTEGER NOT NULL,
    -- Window configuration
    window_games INTEGER NOT NULL,        -- 5, 10, or 20 game window
    games_in_window INTEGER,              -- Actual games available in window
    -- Recent performance (within window)
    recent_goals INTEGER DEFAULT 0,
    recent_assists INTEGER DEFAULT 0,
    recent_points INTEGER DEFAULT 0,
    recent_shots INTEGER DEFAULT 0,
    recent_ppg REAL,                      -- Points per game in window
    recent_gpg REAL,                      -- Goals per game in window
    recent_shooting_pct REAL,
    -- Season baseline
    season_ppg REAL,
    season_gpg REAL,
    season_shooting_pct REAL,
    -- Deviation analysis
    ppg_deviation REAL,                   -- (recent - season) / season
    gpg_deviation REAL,
    shooting_pct_deviation REAL,
    -- Momentum state
    momentum_state TEXT,                  -- 'hot', 'cold', 'neutral'
    momentum_score REAL,                  -- -1.0 to 1.0 (negative=slump, positive=hot)
    confidence REAL,                      -- 0.0 to 1.0
    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id, calculated_date, window_games)
);

-- Indexes for simulation tables
CREATE INDEX IF NOT EXISTS idx_schedule_context_team ON schedule_context(team_abbrev);
CREATE INDEX IF NOT EXISTS idx_schedule_context_game ON schedule_context(game_id);
CREATE INDEX IF NOT EXISTS idx_schedule_context_date ON schedule_context(game_date);
CREATE INDEX IF NOT EXISTS idx_schedule_context_b2b ON schedule_context(is_back_to_back);

CREATE INDEX IF NOT EXISTS idx_player_matchup_player ON player_matchup_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_matchup_opponent ON player_matchup_stats(opponent_team_abbrev);
CREATE INDEX IF NOT EXISTS idx_player_matchup_season ON player_matchup_stats(season);

CREATE INDEX IF NOT EXISTS idx_goalie_matchup_goalie ON goalie_matchup_stats(goalie_id);
CREATE INDEX IF NOT EXISTS idx_goalie_matchup_opponent ON goalie_matchup_stats(opponent_team_abbrev);
CREATE INDEX IF NOT EXISTS idx_goalie_matchup_season ON goalie_matchup_stats(season);

CREATE INDEX IF NOT EXISTS idx_player_season_player ON player_season_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_season_season ON player_season_stats(season);

CREATE INDEX IF NOT EXISTS idx_goalie_season_goalie ON goalie_season_stats(goalie_id);
CREATE INDEX IF NOT EXISTS idx_goalie_season_season ON goalie_season_stats(season);

CREATE INDEX IF NOT EXISTS idx_player_momentum_player ON player_momentum(player_id);
CREATE INDEX IF NOT EXISTS idx_player_momentum_date ON player_momentum(calculated_date);
CREATE INDEX IF NOT EXISTS idx_player_momentum_state ON player_momentum(momentum_state);
CREATE INDEX IF NOT EXISTS idx_player_momentum_season ON player_momentum(season);
