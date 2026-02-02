# Hockey Game Simulation Design

## Overview

This document outlines the simulation flow for predicting hockey game outcomes using player-level, line-level, and team-level data with historical matchup weighting.

---

## Part 1: What We Have

### Database Tables
| Table | Purpose | Status |
|-------|---------|--------|
| `players` | All NHL players (bio, position, team, status) | Have |
| `games` | Game metadata (teams, scores, venue, date) | Have |
| `player_game_stats` | Per-game stats (goals, assists, TOI, faceoffs, etc.) | Have |
| `shots` | Individual shot events (location, type, result, strength) | Have |

### Data Models Ready for Simulation
| Model | Key Data | Status |
|-------|----------|--------|
| Player stats by zone | 13 zones with shots, goals, shooting %, xG | Have |
| Player stats by game segment | Early/mid/late game performance | Have |
| Player stats by season phase | Early/mid/late season + playoffs | Have |
| Goalie profiles | Save % by zone and shot type | Have |
| Player shot profiles | Where each player shoots from, success rates | Have |
| Faceoff stats | Wins/losses per player per game | Have |
| Team line configurations | Forward lines 1-4, defense pairs 1-3 | Model exists |
| Player synergy scores | Chemistry between player pairs | Model exists |
| Clutch ratings | Late-game performance metrics | Have |
| Fatigue indicators | Performance decline tracking | Have |

### Existing Simulation Infrastructure
- Monte Carlo engine (10,000+ iterations)
- Expected goals calculator (zone-based)
- Matchup analyzer (line vs line, zone advantages)
- Segment-based simulation (early/mid/late)

---

## Part 2: What We Need

### Data Gaps to Fill

| Need | Description | Priority |
|------|-------------|----------|
| **Actual line data** | Current team line configurations (who plays with who) | HIGH |
| **Offensive zone time** | Time each player/line spends in offensive zone with puck | HIGH |
| **Historical team-vs-team matchups** | Aggregated stats when Team A plays Team B | HIGH |
| **Puck possession time** | Individual player puck possession metrics | MEDIUM |
| **Line deployment patterns** | Which lines coaches use against which opponent lines | MEDIUM |
| **Face-off zone wins** | Faceoff success by zone (offensive/neutral/defensive) | MEDIUM |

### Logic to Build

| Component | Description | Priority |
|-----------|-------------|----------|
| **Line aggregator** | Combine individual player stats into line-level stats | HIGH |
| **Historical matchup comparator** | Compare team-vs-team data to general team data | HIGH |
| **Dynamic weighting calculator** | Determine when to use matchup data vs general data | HIGH |
| **Line strength calculator** | Per-phase strength scores for each line | MEDIUM |

---

## Part 3: Simulation Flow

### Step 1: Load Player-Level Foundation

```
For each player in the league:
  Load:
    - Heat map (where they shoot from, where they score)
    - Game segment stats (early/mid/late game performance)
    - Season phase stats (early/mid/late season + playoffs)
    - Faceoff win rate (overall, ideally by zone)
    - Offensive metrics (shots, goals, xG by zone)
    - Defensive metrics (blocked shots, takeaways, +/-)
```

**Output**: Complete player profiles with phase-aware performance data

---

### Step 2: Build Line-Level Profiles

```
For each team:
  For each line (forward lines 1-4, defense pairs 1-3):
    Aggregate player stats:
      - Combined heat map (where this line generates offense)
      - Combined zone strength (slot, circles, point, etc.)
      - Combined game segment performance
      - Combined season phase performance
      - Line faceoff strength (center's faceoff %)
      - Synergy modifier (how well these players play together)

    Calculate:
      - Offensive zone time estimate (avg time in O-zone per shift)
      - Primary shooting zones (where this line is dangerous)
      - Weak zones (where this line struggles)
```

**Output**: Line profiles with aggregated strengths by phase and zone

---

### Step 3: Prepare Game-Specific Context

```
Input: Team A vs Team B, Game Date

Determine:
  - Season phase (early/mid/late season or playoffs)
  - Home/away assignment
  - Starting goalies
  - Active rosters and line configurations
```

**Output**: Game context for weighting adjustments

---

### Step 4: Load Historical Matchup Data

```
Query: All games between Team A and Team B (last 5 seasons)

Build matchup profile:
  - Team A heat map vs Team B specifically
  - Team A game segment performance vs Team B
  - Team A offensive tendencies vs Team B
  - Head-to-head goal differential
  - Special teams performance in this matchup
```

**Output**: Historical matchup profile (if sufficient games exist)

---

### Step 5: Calculate Matchup Relevance Weight

This is the key innovation - determining when historical matchup data is more predictive than general data.

```
Compare:
  Team A general heat map vs Team A heat map against Team B

Calculate divergence:
  For each zone:
    divergence[zone] = |general_rate[zone] - matchup_rate[zone]|

  total_divergence = weighted_sum(divergence, zone_importance)

Determine weight:
  IF total_divergence < LOW_THRESHOLD:
    # Heat maps are similar - matchup data isn't special
    matchup_weight = 0.1  (mostly use general data)

  ELIF total_divergence > HIGH_THRESHOLD:
    # Heat maps are different - matchup data is meaningful
    matchup_weight = 0.7  (heavily weight matchup data)

  ELSE:
    # Scale linearly between thresholds
    matchup_weight = interpolate(total_divergence)

Also factor in:
  - Sample size (more games = higher confidence in matchup weight)
  - Recency (recent games weighted more than older games)
  - Roster similarity (how much have rosters changed?)
```

**Output**: `matchup_weight` between 0.0 and 1.0

---

### Step 6: Generate Weighted Team Profiles

```
For each team:
  For each metric (heat map zones, segment performance, etc.):

    weighted_value = (
      (1 - matchup_weight) * general_value +
      matchup_weight * matchup_value
    )
```

**Output**: Final weighted profiles for simulation

---

### Step 7: Run Simulation

```
For each iteration (10,000+):

  Simulate game by segments:

    EARLY GAME (Period 1 + first 10min P2):
      - Use early_game player/line stats
      - Simulate faceoffs, zone time, shots, goals

    MID GAME (P2 10-20min + P3 first 10min):
      - Use mid_game stats
      - Apply fatigue modifiers starting

    LATE GAME (Final 10min + OT):
      - Use late_game stats
      - Apply clutch modifiers
      - Apply full fatigue modifiers

  For each segment:
    For each line matchup:
      - Calculate xG based on zone strengths
      - Apply synergy modifier
      - Apply segment-specific weights
      - Generate goals via Poisson distribution

  Record:
    - Final score
    - Segment-by-segment results
    - Key player performances
```

**Output**: Distribution of outcomes across all iterations

---

## Part 4: Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PLAYER LEVEL (Foundation)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Heat Maps   │  │ Game Segment │  │Season Segment│  │   Faceoffs   │    │
│  │  (by zone)   │  │   Stats      │  │    Stats     │  │  (win rate)  │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         │                 │                 │                 │            │
│         └────────────┬────┴────────┬────────┴────────┬────────┘            │
│                      ▼             ▼                 ▼                     │
│              ┌─────────────────────────────────────────┐                   │
│              │        PLAYER PROFILE (per player)      │                   │
│              │  - Zone strengths (offense/defense)     │                   │
│              │  - Phase performance (game + season)    │                   │
│              │  - Faceoff ability                      │                   │
│              │  - Clutch rating                        │                   │
│              └─────────────────┬───────────────────────┘                   │
└────────────────────────────────┼────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LINE LEVEL (Aggregation)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Player 1 ──┐                                                              │
│   Player 2 ──┼──► LINE PROFILE                                             │
│   Player 3 ──┘      │                                                       │
│                     ├─► Combined heat map                                   │
│                     ├─► Combined zone strengths                             │
│                     ├─► Combined phase performance                          │
│                     ├─► Line synergy score                                  │
│                     └─► Offensive zone time estimate                        │
│                                                                             │
│   Repeat for: Fwd Line 1, 2, 3, 4 | Def Pair 1, 2, 3                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TEAM LEVEL (Assembly)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────┐         ┌─────────────────────┐                  │
│   │   GENERAL PROFILE   │         │   MATCHUP PROFILE   │                  │
│   │  (all games data)   │         │  (vs specific team) │                  │
│   └──────────┬──────────┘         └──────────┬──────────┘                  │
│              │                               │                              │
│              │      ┌──────────────────┐     │                              │
│              └─────►│ COMPARE & WEIGHT │◄────┘                              │
│                     │                  │                                    │
│                     │  If similar:     │                                    │
│                     │   use general    │                                    │
│                     │                  │                                    │
│                     │  If different:   │                                    │
│                     │   weight toward  │                                    │
│                     │   matchup data   │                                    │
│                     └────────┬─────────┘                                    │
│                              │                                              │
│                              ▼                                              │
│                     ┌──────────────────┐                                    │
│                     │  WEIGHTED TEAM   │                                    │
│                     │     PROFILE      │                                    │
│                     └──────────────────┘                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SIMULATION (Execution)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Team A Weighted Profile ──┐                                               │
│                             ├──► MONTE CARLO ENGINE (10,000+ iterations)   │
│   Team B Weighted Profile ──┘           │                                   │
│                                         ▼                                   │
│   For each iteration:                                                       │
│     ├─► EARLY GAME segment (use early_game stats)                          │
│     │     └─► Line matchups → xG → Goals (Poisson)                         │
│     │                                                                       │
│     ├─► MID GAME segment (use mid_game stats + fatigue)                    │
│     │     └─► Line matchups → xG → Goals (Poisson)                         │
│     │                                                                       │
│     └─► LATE GAME segment (use late_game stats + clutch + fatigue)         │
│           └─► Line matchups → xG → Goals (Poisson)                         │
│                                                                             │
│   Output: Win probabilities, score distributions, key factors              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 5: Data Collection Checklist

### Already Have (Verified in Database)
- [x] All NHL players with biographical data
- [x] Shot data with x,y coordinates
- [x] Shot data with zone classification
- [x] Shot data with game segment (early/mid/late)
- [x] Player game stats (goals, assists, TOI, faceoffs)
- [x] Goalie stats (saves, GAA, save %)
- [x] Team game results

### Have Processing For (Pipelines Exist)
- [x] Player heat maps from shot data
- [x] Zone-based shot profiles
- [x] Game segment performance
- [x] Season phase performance
- [x] Goalie shot profiles by zone/type
- [x] Synergy scores between players

### Need to Build/Collect
- [ ] **Current team line configurations** (who is on Line 1, 2, 3, 4)
- [ ] **Offensive zone time by player/line** (time with puck in O-zone)
- [ ] **Historical team-vs-team aggregated stats**
- [ ] **Line deployment patterns** (which lines face which)
- [ ] **Faceoff stats by zone** (O-zone vs D-zone vs neutral)
- [ ] **Puck possession metrics** (individual carry time)

### Logic to Implement
- [ ] **Line aggregation function** (combine player stats → line stats)
- [ ] **Matchup divergence calculator** (compare general vs matchup heat maps)
- [ ] **Dynamic weight function** (determine matchup_weight)
- [ ] **Roster change detector** (is matchup data still relevant?)

---

## Part 6: Key Decisions Still Needed

### 1. Matchup Divergence Thresholds
```
What values for LOW_THRESHOLD and HIGH_THRESHOLD?

Proposed starting point:
  LOW_THRESHOLD = 0.05 (5% divergence = essentially same)
  HIGH_THRESHOLD = 0.20 (20% divergence = meaningfully different)

Need to validate with real data.
```

### 2. Sample Size Requirements
```
Minimum games for matchup data to be considered:
  - Absolute minimum: 5 games (any weight)
  - Recommended: 10+ games (full weight eligible)
  - High confidence: 20+ games

Also: How far back? Last 3 seasons? 5 seasons?
```

### 3. Roster Similarity Factor
```
If Team A has 60% roster turnover since last matchup,
should matchup weight be reduced?

Proposed:
  roster_similarity = (players_still_on_team / players_in_matchup_data)
  adjusted_matchup_weight = matchup_weight * roster_similarity
```

### 4. Line Configuration Source
```
Options:
  A) Manual input before each simulation
  B) Scrape from NHL.com / Daily Faceoff
  C) Infer from player_game_stats (who played together)

Recommendation: Start with (C), add (B) for accuracy
```

### 5. Offensive Zone Time
```
Options:
  A) Estimate from existing shot data (more shots = more O-zone time)
  B) Collect from NHL API (if available)
  C) Use TOI as proxy with position-based adjustments

Recommendation: Start with (A), validate against (B) if available
```

---

## Part 7: Implementation Order

### Phase 1: Line Data Infrastructure
1. Build line configuration model (who plays on which line)
2. Create line aggregation function (player stats → line stats)
3. Test with known line configurations

### Phase 2: Historical Matchup Pipeline
1. Create team-vs-team query function
2. Build matchup profile aggregator
3. Calculate matchup heat maps

### Phase 3: Dynamic Weighting
1. Implement divergence calculation
2. Implement weight interpolation
3. Add sample size and recency factors

### Phase 4: Integration
1. Wire weighted profiles into existing simulation engine
2. Add line-level simulation (vs current team-level)
3. Validate against historical game outcomes

---

## Notes

- Current simulation engine already handles segments, zones, and Monte Carlo
- Main gap is line-level aggregation and matchup-specific weighting
- Goalie data is solid with zone and shot-type profiles
- Faceoff data exists per-game but needs zone breakdown
