# Product Roadmap: Player-First Simulation Engine

This roadmap builds from the current codebase (aggregate team xG + Monte Carlo simulation) toward a player-first, context-aware simulation system that uses historical data, lineup synergy, and matchup-specific performance.

## Guiding Principles
- **Player-first data model**: Players are the primary unit of analysis; team/line outputs are derived.
- **Historical context**: Support queries by season, opponent, and game segment.
- **Context-aware adjustments**: Time-in-game, time-in-season, opponent matchups, and line synergy.
- **Incremental delivery**: Each phase delivers useful artifacts while preparing for the next.

---

## Phase 0 — Baseline (Current State)
**Goal**: Establish a stable baseline to evolve from.

**Current capabilities**
- Team-level expected goals by zone, aggregated across current roster stats.
- Monte Carlo simulation of game outcomes using segment weights and variance.
- Confidence metrics based on data availability and win-probability clarity.

**Deliverables**
- Document baseline data sources (current season team stats, line data, optional player data).
- Add a “known gaps” section to the Technical Specification.

---

## Phase 1 — Data Foundation
**Goal**: Create the historical data pipeline and storage foundation.

**Data sources**
- NHL Stats API + historical season pulls.
- Player game logs, shot location events, and time-stamped play-by-play data.

**Data storage**
- Historical player records (per season + career aggregate).
- Event-level tables (shots, goals, assists, line deployments, goalie on ice).

**Deliverables**
- Storage schema for player events and season splits.
- Ingestion jobs (initial backfill + incremental updates).
- Data validation rules (missing seasons, trades, identity merges).

---

## Phase 2 — Player Profiles & Context Features
**Goal**: Build player-centric statistical profiles.

**Profiles**
- Zone scoring efficiency (shots by zone vs goals by zone).
- Segment performance (early/mid/late game splits).
- Time-in-season adjustments (fatigue/form trends).

**Deliverables**
- Player baseline vectors (career + season).
- Segment and zone breakdowns per player.
- API/query surfaces for player profile retrieval by season.

---

## Phase 3 — Line Synergy & Matchup Modeling
**Goal**: Detect player synergies and opponent-specific effects.

**Synergy detection**
- Compare player baseline vs performance with specific line-mates.
- Produce synergy coefficients for offensive/defensive outputs.

**Matchup effects**
- Player/line performance against specific opponents.
- Zone-specific suppression/boost factors from opponent defenses.

**Deliverables**
- Synergy coefficient tables.
- Opponent matchup multipliers.
- Line configuration scoring based on player baselines + synergy.

---

## Phase 4 — Feature Engine + Aggregation Layer
**Goal**: Turn player-level features into team/line expected outputs.

**Feature engine**
- Compose player outputs into line outputs using deployment, TOI, and chemistry.
- Apply opponent and segment modifiers.

**Aggregation**
- Team-level expected goals by segment and zone derived from player outputs.

**Deliverables**
- Deterministic “feature engine” module producing matchup-ready xG inputs.
- Auditable feature logs explaining why a matchup is favored.

---

## Phase 5 — Simulation Upgrade
**Goal**: Replace aggregate team xG with player-driven, context-aware simulation inputs.

**Simulation changes**
- Use player/line outputs per segment instead of flat team xG.
- Apply dynamic variance based on matchup stability and data confidence.
- Expand output metrics (player impact, line contribution, segment dominance).

**Deliverables**
- Updated simulation pipeline with feature-engine inputs.
- Detailed prediction report with matchup-specific explanations.

---

## Phase 6 — Productization & UX
**Goal**: Provide a user-facing workflow for exploration and validation.

**User workflows**
- Player lookup by season / career.
- Line composition builder with synergy highlights.
- Team-vs-team comparison by zone and segment.

**Deliverables**
- CLI or UI panels for player, line, and matchup exploration.
- Validation suite (backtest against historical outcomes).

---

## Cross-Cutting Workstreams (All Phases)
- **Data quality scoring**: Track coverage levels per player/season.
- **Model validation**: Backtest against historical games.
- **Documentation**: Keep Technical Specification and Roadmap aligned.

---

## Success Criteria
- High data coverage across multiple seasons (player and event data).
- Measurable improvements in prediction variance and confidence.
- Clear, explainable matchup insights grounded in player-level evidence.
