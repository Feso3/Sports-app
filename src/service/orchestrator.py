"""
Orchestrator Service

Coordinates the prediction workflow by integrating data loading,
processing, simulation, and result generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from simulation import (
    GameSimulationEngine,
    PredictionGenerator,
    PredictionSummary,
    SimulationConfig,
    SimulationMode,
    SimulationResult,
)
from src.analytics import ClutchAnalyzer, StaminaAnalyzer, SynergyAnalyzer
from src.models.player import Player
from src.models.team import Team
from src.service.data_loader import CacheStatus, DataLoader


@dataclass
class PredictionOptions:
    """Options for configuring a prediction run."""

    iterations: int = 10000
    use_synergy: bool = True
    use_clutch: bool = True
    use_fatigue: bool = True
    mode: SimulationMode = SimulationMode.SINGLE_GAME
    quick_mode: bool = False  # Use fewer iterations for faster results

    def __post_init__(self) -> None:
        """Apply quick mode settings."""
        if self.quick_mode:
            self.iterations = 1000


@dataclass
class TeamInfo:
    """Simplified team info for display."""

    team_id: int
    name: str
    abbreviation: str
    division: str = ""
    conference: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TeamInfo":
        """Create from dictionary."""
        return cls(
            team_id=data["team_id"],
            name=data["name"],
            abbreviation=data["abbreviation"],
            division=data.get("division", ""),
            conference=data.get("conference", ""),
        )


@dataclass
class PredictionResult:
    """Complete result from a prediction run."""

    home_team: TeamInfo
    away_team: TeamInfo
    simulation_result: SimulationResult
    prediction: PredictionSummary
    report: str
    players_loaded: int = 0
    cache_hits: int = 0


class Orchestrator:
    """
    Main service orchestrator for game predictions.

    Coordinates data loading, simulation, and result generation
    through a simple, clean interface.
    """

    def __init__(
        self,
        data_loader: DataLoader | None = None,
        synergy_analyzer: SynergyAnalyzer | None = None,
        clutch_analyzer: ClutchAnalyzer | None = None,
        stamina_analyzer: StaminaAnalyzer | None = None,
    ) -> None:
        """
        Initialize the orchestrator.

        Args:
            data_loader: Data loading service (creates one if not provided)
            synergy_analyzer: Optional synergy analyzer
            clutch_analyzer: Optional clutch performance analyzer
            stamina_analyzer: Optional stamina/fatigue analyzer
        """
        self.data_loader = data_loader or DataLoader()
        self.synergy_analyzer = synergy_analyzer
        self.clutch_analyzer = clutch_analyzer
        self.stamina_analyzer = stamina_analyzer

        # Initialize simulation engine
        self.engine = GameSimulationEngine(
            synergy_analyzer=synergy_analyzer,
            clutch_analyzer=clutch_analyzer,
            stamina_analyzer=stamina_analyzer,
        )

        # Initialize prediction generator
        self.prediction_generator = PredictionGenerator()

        logger.info("Orchestrator initialized")

    def get_available_teams(self) -> list[TeamInfo]:
        """
        Get list of all available teams for selection.

        Returns:
            List of TeamInfo objects
        """
        teams_data = self.data_loader.get_available_teams()
        return [TeamInfo.from_dict(t) for t in teams_data]

    def predict_game(
        self,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
        home_team_abbrev: str | None = None,
        away_team_abbrev: str | None = None,
        options: PredictionOptions | None = None,
    ) -> PredictionResult:
        """
        Run a complete game prediction.

        Args:
            home_team_id: Home team ID
            away_team_id: Away team ID
            home_team_abbrev: Home team abbreviation (alternative to ID)
            away_team_abbrev: Away team abbreviation (alternative to ID)
            options: Prediction configuration options

        Returns:
            PredictionResult with complete analysis
        """
        options = options or PredictionOptions()

        logger.info(
            f"Starting prediction: "
            f"{home_team_id or home_team_abbrev} vs {away_team_id or away_team_abbrev}"
        )

        # Load teams
        home_team = self.data_loader.load_team(
            team_id=home_team_id, team_abbrev=home_team_abbrev
        )
        away_team = self.data_loader.load_team(
            team_id=away_team_id, team_abbrev=away_team_abbrev
        )

        logger.info(f"Loaded teams: {home_team.name} vs {away_team.name}")

        # Load players for both teams
        home_players = self.data_loader.load_team_players(home_team)
        away_players = self.data_loader.load_team_players(away_team)

        # Merge player dictionaries
        all_players: dict[int, Player] = {}
        all_players.update(home_players)
        all_players.update(away_players)

        logger.info(f"Loaded {len(all_players)} players total")

        # Build simulation config
        config = SimulationConfig(
            home_team_id=home_team.team_id,
            away_team_id=away_team.team_id,
            iterations=options.iterations,
            mode=options.mode,
            use_synergy_adjustments=options.use_synergy and self.synergy_analyzer is not None,
            use_clutch_adjustments=options.use_clutch and self.clutch_analyzer is not None,
            use_fatigue_adjustments=options.use_fatigue and self.stamina_analyzer is not None,
        )

        # Run simulation
        logger.info(f"Running simulation with {config.iterations} iterations...")
        sim_result = self.engine.simulate(
            config=config,
            home_team=home_team,
            away_team=away_team,
            players=all_players,
        )

        # Generate prediction summary
        prediction = self.prediction_generator.generate_prediction(
            result=sim_result,
            home_team_name=home_team.name,
            away_team_name=away_team.name,
        )

        # Generate report
        report = self.prediction_generator.generate_report(prediction)

        # Build result
        result = PredictionResult(
            home_team=TeamInfo(
                team_id=home_team.team_id,
                name=home_team.name,
                abbreviation=home_team.abbreviation,
                division=home_team.division,
                conference=home_team.conference,
            ),
            away_team=TeamInfo(
                team_id=away_team.team_id,
                name=away_team.name,
                abbreviation=away_team.abbreviation,
                division=away_team.division,
                conference=away_team.conference,
            ),
            simulation_result=sim_result,
            prediction=prediction,
            report=report,
            players_loaded=len(all_players),
        )

        logger.info(
            f"Prediction complete: {prediction.predicted_winner_name} "
            f"({prediction.win_probability.home_win_pct:.1%} vs "
            f"{prediction.win_probability.away_win_pct:.1%})"
        )

        return result

    def predict_by_abbreviation(
        self,
        home_abbrev: str,
        away_abbrev: str,
        quick: bool = False,
    ) -> PredictionResult:
        """
        Convenience method to predict using team abbreviations.

        Args:
            home_abbrev: Home team abbreviation (e.g., "TOR", "NYR")
            away_abbrev: Away team abbreviation
            quick: Use quick mode (fewer iterations)

        Returns:
            PredictionResult
        """
        options = PredictionOptions(quick_mode=quick)
        return self.predict_game(
            home_team_abbrev=home_abbrev,
            away_team_abbrev=away_abbrev,
            options=options,
        )

    def refresh_data(
        self,
        team_id: int | None = None,
        team_abbrev: str | None = None,
    ) -> None:
        """
        Refresh cached data for a team.

        Args:
            team_id: Team ID to refresh
            team_abbrev: Team abbreviation to refresh
        """
        self.data_loader.refresh_team_data(team_id=team_id, team_abbrev=team_abbrev)

    def refresh_all_data(self) -> None:
        """Refresh data for all teams."""
        teams = self.get_available_teams()
        for team in teams:
            try:
                self.data_loader.refresh_team_data(team_id=team.team_id)
            except Exception as e:
                logger.warning(f"Failed to refresh {team.name}: {e}")

    def get_cache_status(self) -> CacheStatus:
        """
        Get current cache status.

        Returns:
            CacheStatus with cache statistics
        """
        return self.data_loader.get_cache_status()

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self.data_loader.clear_cache()

    def get_quick_prediction(
        self,
        home_abbrev: str,
        away_abbrev: str,
    ) -> dict[str, Any]:
        """
        Get a quick prediction with minimal output.

        Args:
            home_abbrev: Home team abbreviation
            away_abbrev: Away team abbreviation

        Returns:
            Dictionary with key prediction metrics
        """
        result = self.predict_by_abbreviation(home_abbrev, away_abbrev, quick=True)

        return {
            "home_team": result.home_team.name,
            "away_team": result.away_team.name,
            "home_win_probability": round(result.prediction.win_probability.home_win_pct, 3),
            "away_win_probability": round(result.prediction.win_probability.away_win_pct, 3),
            "predicted_winner": result.prediction.predicted_winner_name,
            "confidence": result.prediction.win_confidence,
            "most_likely_score": result.prediction.most_likely_score,
            "overtime_chance": round(result.prediction.win_probability.overtime_pct, 3),
        }

    def close(self) -> None:
        """Clean up resources."""
        self.data_loader.close()

    def __enter__(self) -> "Orchestrator":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
