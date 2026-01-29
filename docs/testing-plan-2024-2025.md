# Feature Testing Plan - 2024-2025 Season Data

This document outlines the comprehensive testing plan for all features in the NHL Analytics Platform using 2024-2025 season data.

## Data Available
- **Player Data**: Player profiles, positions, career stats for 2024-2025
- **Player Game Data**: Per-game statistics, TOI, points for 2024-2025
- **Player Shot Data**: Shot locations, outcomes, xG data for 2024-2025

---

## 1. Data Collection Tests

### 1.1 Player Data Collection
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_player_profile_loading` | Load player profiles from 2024-2025 data | All player profiles parse correctly with required fields |
| `test_player_position_classification` | Verify position codes (C, LW, RW, D, G) | Positions map correctly to enum values |
| `test_player_team_association` | Verify players linked to correct teams | Team IDs match current roster |
| `test_goalie_specific_fields` | Validate goalie stats (save %, GAA) | Goalie profiles include all goalie-specific metrics |
| `test_player_id_uniqueness` | Ensure no duplicate player IDs | All player_id values unique |

### 1.2 Player Game Data Collection
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_game_log_parsing` | Parse individual game logs | All game events parse with timestamps |
| `test_game_stats_aggregation` | Aggregate stats across games | Totals match sum of individual games |
| `test_toi_calculation` | Verify time-on-ice calculations | TOI in valid ranges (0-30+ minutes) |
| `test_point_tracking` | Track goals, assists per game | Points = Goals + Assists |
| `test_plus_minus_calculation` | Verify +/- calculations | +/- matches event-level data |
| `test_game_date_ordering` | Games ordered chronologically | Game dates in ascending order |

### 1.3 Shot Data Collection
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_shot_coordinate_validity` | Verify x,y coords within rink bounds | -100 ≤ x ≤ 100, -42.5 ≤ y ≤ 42.5 |
| `test_shot_type_mapping` | Map shot types to standard values | All shot types normalize correctly |
| `test_goal_is_shot_subset` | All goals are also shots | Every goal has corresponding shot event |
| `test_shooter_player_exists` | Shooter IDs exist in player data | All shooter_id values have player profiles |
| `test_strength_state_parsing` | Parse PP/EV/SH situations | Strength codes map to enum values |
| `test_shot_distance_calculation` | Distance from net calculated correctly | Distance = sqrt((89-x)² + y²) |
| `test_empty_net_flagging` | Empty net goals flagged correctly | empty_net=True when no goalie |

---

## 2. Analytics Tests

### 2.1 Synergy Analysis
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_pairwise_synergy_with_real_data` | Calculate synergy for known line combos | Synergy scores reflect actual on-ice performance |
| `test_line_chemistry_top_lines` | Analyze top-6 forward chemistry | Top lines have higher chemistry scores |
| `test_defense_pair_compatibility` | Analyze D-pair compatibility | Established pairs show positive synergy |
| `test_synergy_event_weighting` | Goals weighted higher than shots | Goal events contribute more to synergy |
| `test_segment_weighted_synergy` | Late-game synergy weighted higher | Clutch combos show elevated late-game synergy |
| `test_compatibility_matrix_symmetry` | Matrix is symmetric | matrix[A][B] == matrix[B][A] |

### 2.2 Clutch Analysis
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_clutch_rating_calculation` | Calculate clutch ratings from late-game performance | Ratings reflect 3rd period + OT performance |
| `test_game_winning_goal_tracking` | Track GWG leaders | GWG counts match official stats |
| `test_comeback_performance` | Performance when trailing | Identifies comeback specialists |
| `test_high_leverage_situations` | Performance in close games | Clutch players perform better in 1-goal games |
| `test_overtime_performance` | OT goal and assist rates | OT specialists identified correctly |

### 2.3 Stamina/Fatigue Analysis
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_toi_fatigue_correlation` | High TOI correlates with performance drop | Performance degrades with excessive TOI |
| `test_back_to_back_impact` | Performance in back-to-back games | B2B games show measurable impact |
| `test_period_performance_decay` | Performance by period | 3rd period shows fatigue patterns |
| `test_shift_length_analysis` | Long shifts reduce effectiveness | Shot quality drops after 60+ sec shifts |
| `test_games_played_fatigue` | Cumulative season fatigue | Performance dips in 70+ game stretches |

### 2.4 Pattern Detection
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_shooting_pattern_detection` | Identify preferred shot locations | Heat maps match player tendencies |
| `test_playmaker_vs_scorer_patterns` | Classify player types | Assists:Goals ratio identifies playmakers |
| `test_power_play_specialist_detection` | PP specialists identified | High PP point rates flagged |
| `test_defensive_forward_patterns` | Two-way players identified | High takeaways + responsible defensive zone starts |

### 2.5 Metrics Calculation
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_corsi_calculation` | Calculate Corsi (CF, CA, CF%) | CF% = CF / (CF + CA) |
| `test_fenwick_calculation` | Calculate Fenwick (excludes blocks) | FF% excludes blocked shots |
| `test_expected_goals_calculation` | Calculate xG from shot data | xG correlates with actual goals |
| `test_shots_on_goal_reporting` | SOG matches official counts | SOG totals validated |
| `test_pdo_calculation` | PDO = shooting% + save% | PDO regression towards 100 |

---

## 3. Processor Tests

### 3.1 Zone Analysis
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_zone_classification` | Shots classified by ice zone | All shots mapped to valid zones |
| `test_slot_shot_identification` | High-danger shots identified | Slot shots have higher xG |
| `test_point_shot_identification` | Blue line shots identified | Point shots have lower xG |
| `test_zone_xg_values` | Zone-specific xG values | xG varies by zone (slot > point) |
| `test_left_right_zone_splitting` | Left/right zones differentiated | Handedness affects zone preference |

### 3.2 Segment Analysis
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_early_game_segment` | Period 1 + first 10 min P2 | Early game events classified correctly |
| `test_mid_game_segment` | Mid-period 2 + early P3 | Mid-game segment boundaries correct |
| `test_late_game_segment` | Final 10 minutes of P3 | Late-game events weighted appropriately |
| `test_overtime_segment` | OT as separate segment | OT treated as high-leverage |
| `test_segment_stat_aggregation` | Stats aggregated by segment | Segment totals sum to game totals |

### 3.3 Heat Map Generation
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_offensive_heat_map` | Generate offensive zone heat map | Shot density reflects player tendencies |
| `test_defensive_heat_map` | Generate defensive zone heat map | Shows defensive zone coverage |
| `test_heat_map_normalization` | Heat maps normalized 0-1 | All values between 0 and 1 |
| `test_team_aggregate_heat_map` | Team-level heat map from players | Team map = weighted sum of players |
| `test_heat_map_comparison` | Compare two players' heat maps | Identifies style differences |

---

## 4. Simulation Tests

### 4.1 Monte Carlo Engine
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_simulation_convergence` | Results stabilize with iterations | 10K iterations produce stable results |
| `test_seed_determinism` | Same seed = same results | Reproducible simulations |
| `test_win_probability_range` | Win prob between 0-1 | 0 ≤ P(win) ≤ 1 |
| `test_probabilities_sum_to_one` | P(home) + P(away) = 1 | Total probability = 100% |
| `test_score_distribution_validity` | Scores are non-negative integers | No negative or fractional scores |
| `test_overtime_frequency` | OT occurs at realistic rates | ~10-15% of games go to OT |

### 4.2 Expected Goals (xG)
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_zone_weighted_xg` | xG varies by shot location | Slot shots > point shots |
| `test_shot_type_xg_adjustment` | Shot type affects xG | Deflections have different xG |
| `test_rebound_xg_bonus` | Rebound shots have higher xG | Second-chance xG elevated |
| `test_empty_net_xg` | Empty net has high xG | xG ≈ 0.95 for empty net |
| `test_xg_vs_actual_goals` | xG correlates with goals | R² > 0.5 for xG vs actual |

### 4.3 Matchup Analysis
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_line_matchup_scoring` | Line vs line effectiveness | Better lines have higher scores |
| `test_goalie_matchup_factor` | Goalie quality affects matchup | Better goalies reduce opponent xG |
| `test_special_teams_matchup` | PP vs PK matchup analysis | PP% vs PK% determines edge |
| `test_home_ice_advantage` | Home team bonus applied | ~3-5% home ice advantage |

### 4.4 Prediction Accuracy
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_historical_accuracy` | Backtest against completed games | Predicted winner > 55% accurate |
| `test_score_prediction_accuracy` | Predicted scores near actual | MAE < 1.5 goals per team |
| `test_upset_detection` | Upsets predicted occasionally | Underdog wins happen at predicted rate |
| `test_confidence_calibration` | High confidence = more accurate | 80% confidence = 80% correct |

---

## 5. Integration Tests

### 5.1 Data Loader Integration
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_cache_hit_performance` | Cached data loads fast | Cache hit < 100ms |
| `test_cache_miss_fallback` | Missing cache triggers fetch | API called on cache miss |
| `test_cache_expiry` | Stale data refreshed | 24hr+ data triggers refresh |
| `test_offline_mode` | Works with expired cache | Uses stale data when API unavailable |

### 5.2 Orchestrator Integration
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_end_to_end_prediction` | Full prediction workflow | Home vs Away prediction completes |
| `test_team_data_loading` | Load complete team data | Rosters, stats, lines all loaded |
| `test_player_enrichment` | Player profiles enriched | Zone stats, synergies added |
| `test_error_handling` | Graceful error recovery | Partial failures don't crash |

### 5.3 CLI Integration
| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| `test_team_selection` | Select teams by ID/name | All 32 teams selectable |
| `test_iteration_options` | 1K/10K/50K iterations | User can select iteration count |
| `test_result_display` | Results formatted correctly | Win prob, scores displayed |
| `test_cache_status_command` | View cache status | Shows cache size, age |

---

## Test Execution Plan

### Phase 1: Data Validation (Priority: High)
1. Run all data collection tests with 2024-2025 data
2. Verify data completeness and accuracy
3. Fix any parsing or normalization issues

### Phase 2: Analytics Validation (Priority: High)
1. Run analytics tests with validated data
2. Compare outputs to expected ranges
3. Tune weights and thresholds if needed

### Phase 3: Simulation Validation (Priority: Medium)
1. Run Monte Carlo tests with real team data
2. Backtest predictions against known outcomes
3. Calibrate confidence scores

### Phase 4: Integration Testing (Priority: Medium)
1. End-to-end workflow testing
2. Performance benchmarking
3. Error handling verification

### Phase 5: Regression Testing (Priority: Low)
1. Ensure all existing tests pass
2. Document any breaking changes
3. Update fixtures if needed

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test category
pytest tests/test_collectors/ -v
pytest tests/test_analytics/ -v
pytest tests/test_processors/ -v
pytest tests/test_simulation/ -v
pytest tests/test_integration/ -v

# Run with coverage
pytest tests/ --cov=src --cov=simulation --cov-report=html

# Run specific test file
pytest tests/test_collectors/test_shot_data.py -v
```

---

## Success Criteria

| Category | Criteria |
|----------|----------|
| Data Collection | 100% of required fields populated |
| Analytics | Outputs within expected ranges |
| Simulation | Results reproducible with seed |
| Integration | End-to-end workflow completes <30s |
| Overall | All tests pass with no errors |
