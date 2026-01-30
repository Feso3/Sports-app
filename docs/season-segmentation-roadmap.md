# Season & Game Segmentation Spec + Roadmap

> Status: Active (remove this file after the season-phase + game-segment pipeline ships.)

## 1) Specification Sheet

### 1.1 Objective
Build player-level performance splits across:
- **Season phases**: early season, mid-season, late season, playoffs.
- **Game phases** (within each season phase): period 1, period 2, period 3 (or early/mid/late game segments).

The output will be used to calibrate simulation baselines, enable player comparisons, and feed heat-map + synergy analytics.

### 1.2 Data Sources (Current)
- `games` table: season, game_type, game_date, score, etc. (used to assign season phase + playoffs). 
- `player_game_stats` table: per-game player stats (used for per-phase aggregation).
- `shots` table: period/time for event-level splits (used for per-period or per-segment splits when event data is required).
- `Segment` model: definitions for early/mid/late game time ranges.

### 1.3 Phase Definitions
**Season phases (regular season only):**
- Early season: first ~1/3 of games (ordered by `game_date`).
- Mid-season: middle ~1/3.
- Late season: final ~1/3.

**Playoffs:**
- All games with `game_type = 3` (postseason).

**Future-ready playoffs sub-phases (not implemented yet):**
- Early/Mid/Late playoffs based on game order or round when round metadata is available.

### 1.4 Game Phase Definitions
**Option A (simple period split):**
- Period 1, Period 2, Period 3.

**Option B (existing segment split):**
- Early game, mid game, late game using `Segment` time ranges.

Note: Use Option B if we want continuity with the existing segment model and metrics.

### 1.5 Required Outputs
For each player, compute stats for each **season phase × game phase** combination:
- Counting stats: goals, assists, points, shots, hits, TOI, etc.
- Derived rates: per game, per 60, shooting %, etc.
- Store in a structured output format that can be used by visualization + simulation modules.

### 1.6 Acceptance Criteria
- A function (or processor) produces correct phase tags for any game in the DB.
- Aggregation outputs match validation counts from a known season dataset.
- Outputs can be queried for a single player and return all phase/segment splits.

---

## 2) Roadmap (Implementation Plan)

### Phase 1: Foundation (Day 1)
1) **Define season phase tagging**
   - Sort games by `game_date` for a season.
   - Compute early/mid/late boundaries and map game_id -> phase.
2) **Define game phase tagging**
   - Choose period splits or segment splits.
   - Implement helpers to map event/TOI to game phase.
3) **Create aggregation workflow**
   - Aggregate per-player stats by (season phase × game phase).

### Phase 2: Validation (Day 1–2)
4) **Validation against known season**
   - Load 1 season DB locally.
   - Run the aggregation pipeline; verify totals match per-game sums.
5) **Refine metrics**
   - Add per-60, rolling comparisons, and sample-size thresholds.

### Phase 3: Visualization & Simulation Inputs (Day 2+)
6) **Add output tables / export format**
   - Create export to JSON/CSV for UI and simulation layers.
7) **Visualization integration**
   - Generate heat maps and compare players by phase/segment.
8) **Simulation calibration**
   - Feed segmented baselines into simulation engine.

---

## 3) Cleanup Reminder
This file is temporary and should be **deleted once the season-phase + game-segment pipeline is fully implemented and validated**.
