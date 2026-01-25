"""
Simulation Module - Phase 4

This module contains the Monte Carlo game simulation engine for NHL analytics.

Components:
    - models: Data models for simulation configuration and results
    - expected_goals: Zone-based expected goals calculator
    - matchups: Line matchup logic with synergy integration
    - engine: Core Monte Carlo simulation framework
    - adjustments: Segment-specific weighting with clutch/stamina adjustments
    - predictions: Win probability and prediction output

Usage:
    from simulation import GameSimulationEngine, SimulationConfig
    from simulation.predictions import PredictionGenerator

    # Configure simulation
    config = SimulationConfig(
        home_team_id=1,
        away_team_id=2,
        iterations=10000,
    )

    # Run simulation
    engine = GameSimulationEngine()
    result = engine.simulate(config, home_team, away_team, players)

    # Generate prediction
    generator = PredictionGenerator()
    prediction = generator.generate_prediction(result, "Home Team", "Away Team")
    print(generator.generate_report(prediction))
"""

from simulation.models import (
    GameSegment,
    GameSituation,
    LineMatchup,
    MatchupAnalysis,
    ScoreDistribution,
    SegmentResult,
    SeriesResult,
    SimulatedGame,
    SimulationConfig,
    SimulationMode,
    SimulationResult,
)
from simulation.expected_goals import (
    ExpectedGoalsCalculator,
    LineExpectedGoals,
    TeamExpectedGoals,
    ZoneExpectedGoals,
)
from simulation.matchups import (
    MatchupAnalyzer,
    MatchupStrength,
)
from simulation.engine import (
    GameSimulationEngine,
    SegmentContext,
)
from simulation.adjustments import (
    AdjustmentCalculator,
    MomentumTracker,
    SegmentAdjustment,
    TeamAdjustments,
)
from simulation.predictions import (
    PredictionGenerator,
    PredictionSummary,
    WinProbability,
)

__all__ = [
    # Models
    "GameSegment",
    "GameSituation",
    "LineMatchup",
    "MatchupAnalysis",
    "ScoreDistribution",
    "SegmentResult",
    "SeriesResult",
    "SimulatedGame",
    "SimulationConfig",
    "SimulationMode",
    "SimulationResult",
    # Expected Goals
    "ExpectedGoalsCalculator",
    "LineExpectedGoals",
    "TeamExpectedGoals",
    "ZoneExpectedGoals",
    # Matchups
    "MatchupAnalyzer",
    "MatchupStrength",
    # Engine
    "GameSimulationEngine",
    "SegmentContext",
    # Adjustments
    "AdjustmentCalculator",
    "MomentumTracker",
    "SegmentAdjustment",
    "TeamAdjustments",
    # Predictions
    "PredictionGenerator",
    "PredictionSummary",
    "WinProbability",
]
