# Hockey Simulation Logic Design

## Overview

This document outlines the simulation logic for predicting NHL game outcomes. The system uses layered data analysis combining individual player profiles, goalie profiles, team matchup history, and temporal segmentation to produce weighted, context-aware predictions.

---

## Core Simulation Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SIMULATION PIPELINE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. COLLECT          2. SEGMENT           3. ANALYZE                     │
│  ─────────────       ──────────────       ──────────────                 │
│  General Stats  ──►  Split by Phase  ──►  Build Profiles                 │
│  • Career data       • Season phase       • Shot patterns                │
│  • Season data       • Game phase         • Opportunity rates            │
│  • Game logs         • Schedule context   • Performance curves           │
│                                                                          │
│                                                                          │
│  4. COMPARE          5. WEIGHT            6. SIMULATE                    │
│  ─────────────       ──────────────       ──────────────                 │
│  Matchup vs  ──────► Confidence    ─────► Monte Carlo                    │
│  General Data        Scoring              Execution                      │
│  • Head-to-head      • Sample size        • Generate shots               │
│  • Similarity test   • Recency            • Apply weights                │
│  • Context match     • Variance           • Resolve outcomes             │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: Player Data Model

### 1.1 Core Player Metrics

| Metric Category | Data Points | Purpose |
|-----------------|-------------|---------|
| **Time on Ice** | TOI per game, per period, per phase | Determines opportunity window |
| **Opportunities** | Shots per 60 min by phase | Expected shot volume |
| **Shot Locations** | Zone distribution heat map | Where player shoots from |
| **Shot Outcomes** | Goal / SOG / Missed / Blocked rates | Outcome probabilities |
| **Shot Types** | Wrist/Slap/Snap/Backhand/Tip/Wrap distribution | Type weighting |
| **Phase Performance** | Stats split by game & season phase | Context adjustment |
| **Schedule Effects** | Back-to-back, rest, streak impact | Fatigue/momentum |
| **Momentum** | Hot streak / slump indicators | Recent form adjustment |

### 1.2 Player Profile Structure

```
PlayerSimulationProfile
├── identity
│   ├── player_id
│   ├── position (C/LW/RW/D)
│   └── shoots (L/R)
│
├── opportunity_rates (per phase)
│   ├── toi_per_game_seconds
│   ├── shots_per_60
│   ├── scoring_chances_per_60
│   └── high_danger_chances_per_60
│
├── shot_location_profile
│   ├── zone_distribution: {zone → % of shots}
│   ├── zone_outcomes: {zone → {goal%, sog%, miss%, block%}}
│   └── zone_shot_types: {zone → {type → %}}
│
├── shot_type_profile
│   ├── type_distribution: {type → %} (overall)
│   ├── type_effectiveness: {type → shooting%}
│   └── preferred_type_by_zone: {zone → type}
│
├── phase_splits
│   ├── season: {early/mid/late/playoffs → stats}
│   ├── game: {early/mid/late → stats}
│   └── combined: {(season_phase, game_phase) → stats}
│
├── schedule_effects
│   ├── back_to_back: {day1_stats, day2_stats}
│   ├── rest_days: {0, 1, 2, 3+ days → stats}
│   └── streak_impact: {win_streak, loss_streak → stats}
│
└── momentum
    ├── recent_form (last 5/10 games)
    ├── hot_streak_indicator (bool, confidence)
    └── slump_indicator (bool, confidence)
```

### 1.3 Why This Data Matters for Simulation

**Opportunity Prediction:**
> "We can know that this player will likely have 6 shooting opportunities in the late phase of the game mid-season"

- Use `shots_per_60` × `expected_toi` to predict shot attempts
- Adjust by phase: late-game might mean fewer minutes for non-clutch players

**Shot Location Selection:**
> "We have a heat map grid showing where he's likely to shoot from"

- Sample from `zone_distribution` weighted by historical tendency
- Each zone has inherent danger level (slot > point)

**Shot Type Selection:**
> "Selects from a random list of shot types weighted by his own history"

- Sample from `type_distribution` or `zone_shot_types[selected_zone]`
- Player preference + zone context determines type

**Outcome Resolution:**
> "Each location also has a scoring weight built in"

- Base probability: `zone_outcomes[zone]['goal%']`
- Adjusted by: shot type effectiveness, goalie weakness, phase modifiers
- If shooting from "scoring spot" → bonus to conversion

---

## Part 2: Goalie Data Model

### 2.1 Core Goalie Metrics

| Metric Category | Data Points | Purpose |
|-----------------|-------------|---------|
| **Zone Vulnerabilities** | Save% by zone | Where goalie is weak |
| **Shot Type Weaknesses** | Save% by shot type | What beats this goalie |
| **Phase Performance** | Stats by game & season phase | Context adjustment |
| **Schedule Effects** | Workload impact | Fatigue modeling |
| **Momentum** | Hot/cold indicators | Recent form |

### 2.2 Goalie Profile Structure

```
GoalieSimulationProfile
├── identity
│   ├── player_id
│   ├── catches (L/R)
│   └── team_id
│
├── zone_profile
│   ├── zone_save_pct: {zone → save%}
│   ├── zone_shots_faced: {zone → count} (sample size)
│   ├── zone_xGA: {zone → expected goals against}
│   └── zone_GSAE: {zone → goals saved above expected}
│
├── shot_type_profile
│   ├── type_save_pct: {type → save%}
│   ├── type_shots_faced: {type → count}
│   └── weak_types: [types where save% below average]
│
├── phase_splits
│   ├── season: {early/mid/late/playoffs → save%, GAA}
│   ├── game: {early/mid/late → save%, GAA}
│   └── combined: {(season_phase, game_phase) → stats}
│
├── schedule_effects
│   ├── games_in_7_days: {count → save%}
│   ├── back_to_back: {day1_stats, day2_stats}
│   └── rest_impact: {days_rest → stats}
│
└── momentum
    ├── recent_form (last 5/10 starts)
    ├── hot_streak_indicator
    └── slump_indicator
```

### 2.3 Why This Data Matters for Simulation

**Adjusting Scoring Chances:**
> "This will help us adjust the weights for individual scoring chances"

When a shot is generated:
1. Get base goal probability from shooter's zone + type
2. Look up goalie's `zone_save_pct[zone]` and `type_save_pct[type]`
3. If goalie is weak in that zone/type → increase goal probability
4. If goalie is strong → decrease goal probability

**Example Adjustment Formula:**
```
base_goal_prob = 0.10 (10% from slot, wrist shot)
league_avg_save_pct = 0.920
goalie_zone_save_pct = 0.880  (weak in slot)
goalie_type_save_pct = 0.915  (slightly weak vs wrist)

zone_adjustment = (league_avg - goalie_zone) / league_avg = +0.043
type_adjustment = (league_avg - goalie_type) / league_avg = +0.005

adjusted_goal_prob = base_goal_prob × (1 + zone_adj + type_adj)
                   = 0.10 × 1.048
                   = 0.1048 (~10.5%)
```

---

## Part 3: Matchup Data (Player vs Team)

### 3.1 The Matchup Principle

> "If we take the same data but only for the past matchups against this team, then we compare them."

**Key Insight:** Some players have historically performed differently against specific teams. We need to detect when this matters.

### 3.2 Matchup Profile Structure

```
PlayerMatchupProfile
├── opponent_team_id
├── sample_size (games played vs this team)
│
├── general_stats (career/season averages)
│   ├── goals_per_game
│   ├── shots_per_game
│   ├── shooting_pct
│   └── toi_per_game
│
├── matchup_stats (vs this specific team)
│   ├── goals_per_game
│   ├── shots_per_game
│   ├── shooting_pct
│   └── toi_per_game
│
├── similarity_analysis
│   ├── goals_deviation (matchup - general)
│   ├── shots_deviation
│   ├── shooting_pct_deviation
│   └── overall_similarity_score (0-1)
│
└── weight_recommendation
    ├── general_weight (0-1)
    ├── matchup_weight (0-1)
    └── confidence_level
```

### 3.3 Similarity Test & Weighting Logic

**Decision Rule:**

```
IF matchup history is SIMILAR to general data:
    → Weight outcomes MORE toward general data (reliable, larger sample)

IF matchup history is DIFFERENT from general data:
    → Weight outcomes MORE toward matchup data (opponent-specific effect)
```

**Similarity Scoring:**

```python
def calculate_similarity(general_stats, matchup_stats, sample_size):
    """
    Returns 0-1 score where:
    - 1.0 = identical (use general data)
    - 0.0 = completely different (use matchup data)
    """

    # Calculate deviations (normalized by variance)
    deviations = []
    for stat in ['goals_per_game', 'shots_per_game', 'shooting_pct']:
        diff = abs(matchup_stats[stat] - general_stats[stat])
        std = general_stats[f'{stat}_std']  # historical variance
        z_score = diff / std if std > 0 else 0
        deviations.append(z_score)

    avg_deviation = mean(deviations)

    # Convert to similarity (higher deviation = lower similarity)
    raw_similarity = max(0, 1 - (avg_deviation / 2))

    # Penalize for small sample size
    sample_confidence = min(1.0, sample_size / 10)  # full confidence at 10+ games

    return raw_similarity * sample_confidence
```

**Weight Calculation:**

```python
def calculate_weights(similarity_score, sample_size):
    """
    Determine how much to weight general vs matchup data.
    """

    MIN_SAMPLE = 3   # minimum games for any matchup weight
    FULL_SAMPLE = 10 # full confidence threshold

    if sample_size < MIN_SAMPLE:
        return {'general': 1.0, 'matchup': 0.0}

    # Base matchup weight inversely related to similarity
    # Different = high matchup weight, Similar = low matchup weight
    base_matchup_weight = 1.0 - similarity_score

    # Scale by sample confidence
    sample_confidence = min(1.0, sample_size / FULL_SAMPLE)
    matchup_weight = base_matchup_weight * sample_confidence

    # Ensure weights sum to 1
    general_weight = 1.0 - matchup_weight

    return {
        'general': general_weight,
        'matchup': matchup_weight
    }
```

**Example Scenarios:**

| Scenario | Similarity | Sample | General Wt | Matchup Wt |
|----------|------------|--------|------------|------------|
| Similar, large sample | 0.85 | 12 | 0.85 | 0.15 |
| Similar, small sample | 0.85 | 4 | 0.94 | 0.06 |
| Different, large sample | 0.30 | 15 | 0.30 | 0.70 |
| Different, small sample | 0.30 | 5 | 0.65 | 0.35 |
| Very few games | any | 2 | 1.00 | 0.00 |

---

## Part 4: Time Frame Segmentation

### 4.1 Multi-Dimensional Time Analysis

The simulation uses **two orthogonal time dimensions**:

```
                    SEASON PHASE
                    ─────────────────────────────────────────
                    │ Early     │ Mid       │ Late      │ Playoffs │
    ────────────────┼───────────┼───────────┼───────────┼──────────┤
    G  │ Early      │ EE        │ ME        │ LE        │ PE       │
    A  │ (P1-P2a)   │           │           │           │          │
    M  ├────────────┼───────────┼───────────┼───────────┼──────────┤
    E  │ Mid        │ EM        │ MM        │ LM        │ PM       │
       │ (P2b-P3a)  │           │           │           │          │
    P  ├────────────┼───────────┼───────────┼───────────┼──────────┤
    H  │ Late       │ EL        │ ML        │ LL        │ PL       │
    A  │ (P3b-OT)   │           │           │           │          │
    S  └────────────┴───────────┴───────────┴───────────┴──────────┘
    E
```

Each cell represents a unique context with potentially different performance patterns.

### 4.2 Season Phase Definitions

| Phase | Definition | Characteristics |
|-------|------------|-----------------|
| **Early Season** | Games 1-27 (~Oct-Nov) | Rust, line experimentation, systems adjustments |
| **Mid Season** | Games 28-55 (~Dec-Feb) | Peak form, established patterns, trade deadline approaching |
| **Late Season** | Games 56-82 (~Mar-Apr) | Playoff push, rest management, intensity increase |
| **Playoffs** | game_type = 3 | Maximum intensity, different rules, heightened stakes |

### 4.3 Game Phase Definitions

| Phase | Time Range | Characteristics |
|-------|------------|-----------------|
| **Early Game** | P1 (0-20) + P2 (0-10) | Fresh legs, testing systems, establishing pace |
| **Mid Game** | P2 (10-20) + P3 (0-10) | Adjustments, momentum swings, fatigue emerging |
| **Late Game** | P3 (10-20) + OT | Score effects, desperation, clutch moments, peak fatigue |

### 4.4 Schedule Context Factors

**Back-to-Back Analysis:**
```
Schedule Pattern          │ Expected Impact
──────────────────────────┼───────────────────────────
Game 1 of back-to-back    │ Normal baseline
Game 2 of back-to-back    │ -5% to -15% performance
3 games in 4 nights       │ Cumulative fatigue
After 4+ days rest        │ Possible rust (-3% initially)
```

**Win/Loss Streak Context:**
```
Context                   │ Analysis
──────────────────────────┼───────────────────────────
2+ game win streak        │ Check for confidence boost
2+ game loss streak       │ Check for pressing/frustration
After loss                │ Bounce-back patterns
After big win             │ Letdown risk
```

### 4.5 Hot Streak / Slump Detection

**Detection Algorithm:**

```python
def detect_momentum_state(recent_games: List[GameStats], window: int = 10):
    """
    Analyze recent performance to detect hot streaks or slumps.
    """

    if len(recent_games) < 5:
        return MomentumState.UNKNOWN

    # Calculate recent vs season average
    recent_ppg = mean([g.points for g in recent_games[-window:]])
    season_ppg = mean([g.points for g in recent_games])

    recent_shooting = mean([g.goals/g.shots for g in recent_games[-window:] if g.shots > 0])
    season_shooting = mean([g.goals/g.shots for g in recent_games if g.shots > 0])

    # Check for significant deviation (>1 std or >20% difference)
    ppg_deviation = (recent_ppg - season_ppg) / season_ppg if season_ppg > 0 else 0
    shooting_deviation = (recent_shooting - season_shooting) / season_shooting if season_shooting > 0 else 0

    # Hot streak: sustained above-average performance
    if ppg_deviation > 0.20 and shooting_deviation > 0.15:
        confidence = min(1.0, (ppg_deviation + shooting_deviation) / 0.5)
        return MomentumState.HOT_STREAK, confidence

    # Slump: sustained below-average performance
    if ppg_deviation < -0.20 and shooting_deviation < -0.15:
        confidence = min(1.0, abs(ppg_deviation + shooting_deviation) / 0.5)
        return MomentumState.SLUMP, confidence

    return MomentumState.NEUTRAL, 0.5
```

**Momentum Adjustment:**

| State | Adjustment | Notes |
|-------|------------|-------|
| Hot Streak (high confidence) | +5% to +10% | Boost shooting%, xG |
| Hot Streak (low confidence) | +2% to +5% | Minor boost |
| Neutral | 0% | No adjustment |
| Slump (low confidence) | -2% to -5% | Minor penalty |
| Slump (high confidence) | -5% to -10% | Reduce effectiveness |

---

## Part 5: Simulation Execution

### 5.1 Pre-Game Setup

```python
def prepare_simulation(home_team, away_team, game_context):
    """
    Build complete simulation context before running iterations.
    """

    # 1. Determine current phases
    season_phase = determine_season_phase(game_context.date)
    schedule_context = analyze_schedule(
        home_team, away_team, game_context.date
    )

    # 2. Load player profiles with phase-specific stats
    home_profiles = load_player_profiles(
        home_team.roster,
        season_phase=season_phase,
        opponent=away_team.id
    )
    away_profiles = load_player_profiles(
        away_team.roster,
        season_phase=season_phase,
        opponent=home_team.id
    )

    # 3. Load goalie profiles
    home_goalie = load_goalie_profile(
        home_team.starting_goalie,
        season_phase=season_phase,
        opponent=away_team.id
    )
    away_goalie = load_goalie_profile(
        away_team.starting_goalie,
        season_phase=season_phase,
        opponent=home_team.id
    )

    # 4. Calculate matchup weights for each player
    for profile in home_profiles + away_profiles:
        profile.matchup_weights = calculate_matchup_weights(profile)

    # 5. Detect momentum states
    for profile in home_profiles + away_profiles:
        profile.momentum = detect_momentum_state(profile.recent_games)

    return SimulationContext(
        home_profiles=home_profiles,
        away_profiles=away_profiles,
        home_goalie=home_goalie,
        away_goalie=away_goalie,
        season_phase=season_phase,
        schedule_context=schedule_context
    )
```

### 5.2 Single Game Iteration

```python
def simulate_game_iteration(context: SimulationContext):
    """
    Run one iteration of the game simulation.
    Returns final score and event log.
    """

    game_state = GameState(home_score=0, away_score=0)
    events = []

    for game_phase in [GamePhase.EARLY, GamePhase.MID, GamePhase.LATE]:

        # Simulate each line for each team
        for team in ['home', 'away']:
            profiles = context.home_profiles if team == 'home' else context.away_profiles
            opponent_goalie = context.away_goalie if team == 'home' else context.home_goalie

            for line in get_lines(profiles):
                # 1. Determine opportunities for this line in this phase
                opportunities = generate_opportunities(
                    line=line,
                    phase=game_phase,
                    context=context
                )

                for opp in opportunities:
                    # 2. Select shooter from line (weighted by opportunity rates)
                    shooter = select_shooter(line, phase=game_phase)

                    # 3. Generate shot location
                    zone = sample_shot_zone(shooter.shot_location_profile)

                    # 4. Generate shot type
                    shot_type = sample_shot_type(
                        shooter.shot_type_profile,
                        zone=zone
                    )

                    # 5. Calculate base goal probability
                    base_prob = calculate_base_goal_prob(
                        shooter=shooter,
                        zone=zone,
                        shot_type=shot_type,
                        phase=game_phase,
                        context=context
                    )

                    # 6. Adjust for goalie
                    adjusted_prob = adjust_for_goalie(
                        base_prob=base_prob,
                        goalie=opponent_goalie,
                        zone=zone,
                        shot_type=shot_type,
                        phase=game_phase
                    )

                    # 7. Apply matchup weighting
                    final_prob = apply_matchup_weight(
                        adjusted_prob,
                        shooter.matchup_weights,
                        shooter.general_shooting_pct,
                        shooter.matchup_shooting_pct
                    )

                    # 8. Apply momentum adjustment
                    final_prob = apply_momentum(
                        final_prob,
                        shooter.momentum
                    )

                    # 9. Resolve outcome
                    outcome = resolve_shot(final_prob)

                    if outcome == ShotOutcome.GOAL:
                        if team == 'home':
                            game_state.home_score += 1
                        else:
                            game_state.away_score += 1

                    events.append(ShotEvent(
                        shooter=shooter,
                        zone=zone,
                        shot_type=shot_type,
                        outcome=outcome,
                        phase=game_phase
                    ))

    # Handle overtime if tied
    if game_state.home_score == game_state.away_score:
        game_state = simulate_overtime(context, game_state)

    return game_state, events
```

### 5.3 Weighting Integration Points

The simulation applies weights at multiple stages:

```
┌──────────────────────────────────────────────────────────────────┐
│                    WEIGHTING INTEGRATION                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  OPPORTUNITY GENERATION                                           │
│  ├─ Phase weight: early (0.9) / mid (1.0) / late (1.1)           │
│  ├─ Schedule weight: back-to-back (-10%), rested (+2%)           │
│  └─ Line TOI weight: top line (35%) vs 4th line (10%)            │
│                                                                   │
│  SHOT LOCATION SELECTION                                          │
│  ├─ Player zone history weight (primary)                          │
│  ├─ Matchup zone history weight (if different, confident)        │
│  └─ Phase zone tendency (some players more aggressive late)      │
│                                                                   │
│  SHOT TYPE SELECTION                                              │
│  ├─ Player type preference weight                                 │
│  ├─ Zone-specific type weight (slots favor wrist shots)          │
│  └─ Goalie weakness weight (if weak vs slap, prefer slap)        │
│                                                                   │
│  GOAL PROBABILITY                                                 │
│  ├─ Zone danger weight (crease 3.5x, point 0.3x)                 │
│  ├─ Shot type effectiveness weight                                │
│  ├─ Player shooting % (general × matchup blend)                  │
│  ├─ Goalie save % (zone × type combined)                         │
│  ├─ Phase modifier (clutch situations)                           │
│  ├─ Momentum modifier (hot streak / slump)                       │
│  └─ Schedule fatigue modifier                                     │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Part 6: Data Requirements & Gaps

### 6.1 What We Have (Existing)

| Data | Location | Status |
|------|----------|--------|
| Player game stats | `player_game_stats` table | Complete |
| Shot locations (x,y) | `shots` table | Complete |
| Shot types | `shots` table | Complete |
| Shot outcomes | `shots.is_goal` + blocked detection | Complete |
| Zone classification | `zone_analysis.py` | Complete |
| Game phase stats | `segment_analysis.py` | Complete |
| Season phase stats | `season_segment_pipeline.py` | Complete |
| Goalie zone profiles | `goalie_shot_profile_pipeline.py` | Complete |
| Player shot location profiles | `player_shot_location_pipeline.py` | Complete |

### 6.2 What We Need to Build

| Feature | Priority | Description |
|---------|----------|-------------|
| **Schedule Context Analyzer** | HIGH | Detect back-to-back, rest days, calculate fatigue factors |
| **Matchup History Pipeline** | HIGH | Extract player vs specific team stats, similarity scoring |
| **Momentum Detection** | MEDIUM | Hot streak / slump detection from recent games |
| **Matchup Weight Calculator** | HIGH | Blend general vs matchup stats based on similarity |
| **Win/Loss Streak Impact** | MEDIUM | Track how players perform after wins/losses |
| **Integrated Simulation Runner** | HIGH | Connect all profiles into execution engine |

### 6.3 Database Additions Needed

```sql
-- Schedule context for fatigue analysis
CREATE TABLE IF NOT EXISTS schedule_context (
    team_abbrev TEXT NOT NULL,
    game_date DATE NOT NULL,
    days_rest INTEGER,              -- days since last game
    is_back_to_back INTEGER,        -- 0/1
    games_in_7_days INTEGER,        -- workload indicator
    games_in_3_days INTEGER,
    travel_distance_km REAL,        -- optional
    PRIMARY KEY (team_abbrev, game_date)
);

-- Player matchup history
CREATE TABLE IF NOT EXISTS player_matchup_stats (
    player_id INTEGER NOT NULL,
    opponent_team_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    games_played INTEGER,
    goals INTEGER,
    assists INTEGER,
    points INTEGER,
    shots INTEGER,
    toi_seconds INTEGER,
    -- Calculated fields
    goals_per_game REAL,
    points_per_game REAL,
    shots_per_game REAL,
    shooting_pct REAL,
    PRIMARY KEY (player_id, opponent_team_id, season),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

-- Goalie matchup history
CREATE TABLE IF NOT EXISTS goalie_matchup_stats (
    goalie_id INTEGER NOT NULL,
    opponent_team_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    games_played INTEGER,
    shots_against INTEGER,
    goals_against INTEGER,
    saves INTEGER,
    save_pct REAL,
    PRIMARY KEY (goalie_id, opponent_team_id, season),
    FOREIGN KEY (goalie_id) REFERENCES players(player_id)
);

-- Player momentum tracking
CREATE TABLE IF NOT EXISTS player_momentum (
    player_id INTEGER NOT NULL,
    calculated_date DATE NOT NULL,
    window_games INTEGER,           -- 5, 10, or 20 game window
    recent_ppg REAL,
    season_ppg REAL,
    ppg_deviation REAL,
    recent_shooting_pct REAL,
    season_shooting_pct REAL,
    shooting_deviation REAL,
    momentum_state TEXT,            -- 'hot', 'cold', 'neutral'
    confidence REAL,
    PRIMARY KEY (player_id, calculated_date, window_games)
);
```

---

## Part 7: Implementation Roadmap

### Phase 1: Schedule & Fatigue (Week 1)
- [ ] Create `schedule_context` table
- [ ] Build schedule analyzer to populate table
- [ ] Add fatigue modifiers to simulation adjustments
- [ ] Test with back-to-back game scenarios

### Phase 2: Matchup Analysis (Week 2)
- [ ] Create matchup stats tables
- [ ] Build matchup history extraction pipeline
- [ ] Implement similarity scoring algorithm
- [ ] Implement weight calculation
- [ ] Add matchup profiles to simulation context

### Phase 3: Momentum Detection (Week 3)
- [ ] Create momentum tracking table
- [ ] Build hot streak / slump detection
- [ ] Add momentum state to player profiles
- [ ] Apply momentum modifiers in simulation

### Phase 4: Integration (Week 4)
- [ ] Connect all components in simulation engine
- [ ] Build complete simulation runner
- [ ] Add logging and debugging output
- [ ] Validate against historical games

### Phase 5: Refinement (Ongoing)
- [ ] Tune weights based on backtesting
- [ ] Add confidence intervals to predictions
- [ ] Build reporting dashboard
- [ ] Optimize performance for batch predictions

---

## Summary

The simulation logic follows this flow:

1. **COLLECT** - Gather general stats for players and goalies
2. **SEGMENT** - Split by season phase, game phase, and schedule context
3. **ANALYZE** - Build comprehensive profiles (location, type, phase performance)
4. **COMPARE** - Test if matchup history differs from general patterns
5. **WEIGHT** - Calculate confidence-based weights for general vs matchup data
6. **SIMULATE** - Run Monte Carlo with all weights applied at each decision point

The key innovation is the **adaptive weighting** between general and matchup-specific data based on measured similarity and sample size, combined with multi-dimensional phase analysis to capture contextual performance variations.
