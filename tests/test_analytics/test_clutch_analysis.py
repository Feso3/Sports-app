"""
Tests for Clutch and Stamina Analysis Module

Validates clutch scoring, stamina analysis, and team resilience detection.
"""

import pytest

from src.analytics.clutch_analysis import (
    ClutchAnalyzer,
    ClutchLevel,
    ClutchMetrics,
    FatigueLevel,
    StaminaAnalyzer,
    StaminaMetrics,
    TeamResilienceAnalyzer,
    TeamResilienceMetrics,
)


class TestClutchMetrics:
    """Tests for ClutchMetrics dataclass."""

    def test_clutch_metrics_creation(self):
        """Test creating clutch metrics."""
        metrics = ClutchMetrics(
            player_id=100,
            games_played=50,
            game_winning_goals=5,
            game_tying_goals=3,
            overtime_goals=2,
            late_game_goals=10,
            late_game_assists=8,
        )

        assert metrics.player_id == 100
        assert metrics.game_winning_goals == 5
        assert metrics.late_game_points == 18  # 10 goals + 8 assists

    def test_clutch_metrics_defaults(self):
        """Test default values for clutch metrics."""
        metrics = ClutchMetrics(player_id=100)

        assert metrics.games_played == 0
        assert metrics.clutch_score == 0.0
        assert metrics.clutch_level == ClutchLevel.AVERAGE


class TestStaminaMetrics:
    """Tests for StaminaMetrics dataclass."""

    def test_stamina_metrics_creation(self):
        """Test creating stamina metrics."""
        metrics = StaminaMetrics(
            player_id=100,
            games_analyzed=40,
            early_game_points_per_60=3.0,
            mid_game_points_per_60=2.5,
            late_game_points_per_60=2.0,
        )

        assert metrics.player_id == 100
        assert metrics.early_game_points_per_60 == 3.0
        assert metrics.fatigue_level == FatigueLevel.MINIMAL

    def test_stamina_metrics_defaults(self):
        """Test default values for stamina metrics."""
        metrics = StaminaMetrics(player_id=100)

        assert metrics.games_analyzed == 0
        assert metrics.fatigue_indicator == 1.0
        assert metrics.stamina_score == 0.0


class TestClutchAnalyzer:
    """Tests for ClutchAnalyzer class."""

    @pytest.fixture
    def analyzer(self):
        """Create a clutch analyzer instance."""
        return ClutchAnalyzer()

    def test_record_game_winning_goal(self, analyzer):
        """Test recording game-winning goals."""
        analyzer.record_game_winning_goal(100)
        analyzer.record_game_winning_goal(100)

        metrics = analyzer.get_metrics(100)
        assert metrics is not None
        assert metrics.game_winning_goals == 2

    def test_record_late_game_points(self, analyzer):
        """Test recording late game points."""
        analyzer.record_late_game_point(100, goals=2, assists=3)
        analyzer.record_late_game_point(100, goals=1, assists=1)

        metrics = analyzer.get_metrics(100)
        assert metrics.late_game_goals == 3
        assert metrics.late_game_assists == 4
        assert metrics.late_game_points == 7

    def test_calculate_clutch_score(self, analyzer):
        """Test clutch score calculation."""
        metrics = ClutchMetrics(
            player_id=100,
            games_played=20,
            game_winning_goals=4,
            game_tying_goals=2,
            overtime_goals=1,
            late_game_goals=6,
            late_game_assists=4,
        )
        analyzer.ingest_player_metrics(metrics)

        score = analyzer.calculate_clutch_score(100)

        # Manual calculation:
        # GWG: 4 * 5.0 = 20
        # GTG: 2 * 4.0 = 8
        # OTG: 1 * 4.5 = 4.5
        # LG goals: 6 * 2.5 = 15
        # LG assists: 4 * 1.5 = 6
        # Total: 53.5 / 20 games = 2.675
        assert score == pytest.approx(2.675)

    def test_classify_player_elite(self, analyzer):
        """Test elite clutch player classification."""
        metrics = ClutchMetrics(
            player_id=100,
            games_played=10,
            game_winning_goals=5,
            overtime_goals=3,
            late_game_goals=8,
        )
        analyzer.ingest_player_metrics(metrics)

        level = analyzer.classify_player(100)
        assert level == ClutchLevel.ELITE

    def test_classify_player_average(self, analyzer):
        """Test average clutch player classification."""
        # Score calculation: GWG(2*5) + LG_goals(4*2.5) + LG_assists(2*1.5) / 20 games
        # = (10 + 10 + 3) / 20 = 1.15 -> AVERAGE (threshold: 1.0-2.0)
        metrics = ClutchMetrics(
            player_id=100,
            games_played=20,
            game_winning_goals=2,
            late_game_goals=4,
            late_game_assists=2,
        )
        analyzer.ingest_player_metrics(metrics)

        level = analyzer.classify_player(100)
        assert level == ClutchLevel.AVERAGE

    def test_classify_player_poor(self, analyzer):
        """Test poor clutch player classification."""
        metrics = ClutchMetrics(
            player_id=100,
            games_played=50,
            game_winning_goals=1,
            late_game_goals=2,
        )
        analyzer.ingest_player_metrics(metrics)

        level = analyzer.classify_player(100)
        assert level == ClutchLevel.POOR

    def test_get_clutch_rankings(self, analyzer):
        """Test clutch performer rankings."""
        # Add multiple players with different clutch scores
        for i, (gwg, otg) in enumerate([(5, 3), (2, 1), (8, 4), (1, 0)]):
            metrics = ClutchMetrics(
                player_id=100 + i,
                games_played=20,
                game_winning_goals=gwg,
                overtime_goals=otg,
            )
            analyzer.ingest_player_metrics(metrics)

        rankings = analyzer.get_clutch_rankings([100, 101, 102, 103], limit=3)

        assert len(rankings) == 3
        assert rankings[0].player_id == 102  # Highest GWG + OTG
        assert rankings[1].player_id == 100
        assert rankings[0].clutch_score > rankings[1].clutch_score

    def test_custom_weights(self):
        """Test analyzer with custom weights."""
        custom_weights = {
            "game_winning_goal": 10.0,  # Double the default
        }
        analyzer = ClutchAnalyzer(weights=custom_weights)

        metrics = ClutchMetrics(
            player_id=100, games_played=10, game_winning_goals=2
        )
        analyzer.ingest_player_metrics(metrics)

        score = analyzer.calculate_clutch_score(100)
        # 2 GWG * 10.0 / 10 games = 2.0
        assert score == pytest.approx(2.0)


class TestStaminaAnalyzer:
    """Tests for StaminaAnalyzer class."""

    @pytest.fixture
    def analyzer(self):
        """Create a stamina analyzer instance."""
        return StaminaAnalyzer()

    def test_ingest_segment_stats(self, analyzer):
        """Test ingesting segment statistics."""
        early_stats = {"points_per_60": 3.0, "games": 20}
        mid_stats = {"points_per_60": 2.5, "games": 20}
        late_stats = {"points_per_60": 2.0, "games": 20}

        analyzer.ingest_segment_stats(100, early_stats, mid_stats, late_stats)

        metrics = analyzer.get_metrics(100)
        assert metrics is not None
        assert metrics.early_game_points_per_60 == 3.0
        assert metrics.late_game_points_per_60 == 2.0

    def test_calculate_fatigue_indicator(self, analyzer):
        """Test fatigue indicator calculation."""
        metrics = StaminaMetrics(
            player_id=100,
            early_game_points_per_60=3.0,
            late_game_points_per_60=2.1,
        )
        analyzer.ingest_player_metrics(metrics)

        fatigue = analyzer.calculate_fatigue_indicator(100)

        # 2.1 / 3.0 = 0.7
        assert fatigue == pytest.approx(0.7)

    def test_calculate_stamina_score(self, analyzer):
        """Test stamina score calculation."""
        metrics = StaminaMetrics(
            player_id=100,
            early_game_points_per_60=3.0,
            mid_game_points_per_60=2.8,
            late_game_points_per_60=2.7,
            early_game_corsi_pct=52.0,
            late_game_corsi_pct=50.0,
            early_game_xg_per_60=0.8,
            late_game_xg_per_60=0.72,
        )
        analyzer.ingest_player_metrics(metrics)

        score = analyzer.calculate_stamina_score(100)

        # Should be high (low fatigue)
        assert score > 40

    def test_classify_fatigue_minimal(self, analyzer):
        """Test minimal fatigue classification."""
        metrics = StaminaMetrics(
            player_id=100,
            early_game_points_per_60=3.0,
            late_game_points_per_60=2.9,
        )
        analyzer.ingest_player_metrics(metrics)

        level = analyzer.classify_fatigue(100)
        assert level == FatigueLevel.MINIMAL

    def test_classify_fatigue_severe(self, analyzer):
        """Test severe fatigue classification."""
        metrics = StaminaMetrics(
            player_id=100,
            early_game_points_per_60=3.0,
            late_game_points_per_60=1.5,  # 50% decline
        )
        analyzer.ingest_player_metrics(metrics)

        level = analyzer.classify_fatigue(100)
        assert level == FatigueLevel.SEVERE

    def test_identify_fatigue_vulnerable_players(self, analyzer):
        """Test identifying fatigue-vulnerable players."""
        # Strong stamina player
        analyzer.ingest_player_metrics(
            StaminaMetrics(
                player_id=100,
                early_game_points_per_60=3.0,
                late_game_points_per_60=2.9,
            )
        )
        # Moderate fatigue player
        analyzer.ingest_player_metrics(
            StaminaMetrics(
                player_id=101,
                early_game_points_per_60=3.0,
                late_game_points_per_60=2.1,  # 30% decline
            )
        )
        # High fatigue player
        analyzer.ingest_player_metrics(
            StaminaMetrics(
                player_id=102,
                early_game_points_per_60=3.0,
                late_game_points_per_60=1.8,  # 40% decline
            )
        )

        vulnerable = analyzer.identify_fatigue_vulnerable_players(
            [100, 101, 102], threshold=FatigueLevel.MODERATE
        )

        # Should include 101 (0.7) and 102 (0.6)
        assert len(vulnerable) == 2
        # 102 should be first (more fatigued)
        assert vulnerable[0][0] == 102

    def test_get_late_game_recommendations(self, analyzer):
        """Test late game usage recommendations."""
        # High fatigue player
        metrics = StaminaMetrics(
            player_id=100,
            early_game_points_per_60=3.0,
            late_game_points_per_60=1.5,
        )
        analyzer.ingest_player_metrics(metrics)

        recommendations = analyzer.get_late_game_recommendations(100)

        assert len(recommendations) > 0
        assert any("third period" in r.lower() for r in recommendations)


class TestTeamResilienceAnalyzer:
    """Tests for TeamResilienceAnalyzer class."""

    @pytest.fixture
    def analyzer(self):
        """Create a team resilience analyzer instance."""
        return TeamResilienceAnalyzer()

    def test_record_lead_result(self, analyzer):
        """Test recording lead protection results."""
        analyzer.record_lead_result(1, held=True)
        analyzer.record_lead_result(1, held=True)
        analyzer.record_lead_result(1, held=False)

        metrics = analyzer.get_metrics(1)
        assert metrics.leads_held == 2
        assert metrics.leads_blown == 1
        assert metrics.lead_protection_rate == pytest.approx(2 / 3)

    def test_record_comeback_result(self, analyzer):
        """Test recording comeback results."""
        analyzer.record_comeback_result(1, completed=True)
        analyzer.record_comeback_result(1, completed=False)
        analyzer.record_comeback_result(1, completed=False)

        metrics = analyzer.get_metrics(1)
        assert metrics.comebacks_completed == 1
        assert metrics.comeback_opportunities == 3
        assert metrics.comeback_rate == pytest.approx(1 / 3)

    def test_record_third_period_goals(self, analyzer):
        """Test recording third period goals."""
        analyzer.record_third_period_goals(1, goals_for=3, goals_against=1)
        analyzer.record_third_period_goals(1, goals_for=2, goals_against=2)

        metrics = analyzer.get_metrics(1)
        assert metrics.third_period_goals_for == 5
        assert metrics.third_period_goals_against == 3
        assert metrics.third_period_goal_differential == 2

    def test_is_resilient(self, analyzer):
        """Test resilient team classification."""
        metrics = TeamResilienceMetrics(
            team_id=1, leads_held=8, leads_blown=2  # 80% lead protection
        )
        analyzer.ingest_team_metrics(metrics)

        assert analyzer.is_resilient(1) is True
        assert analyzer.is_collapse_prone(1) is False

    def test_is_collapse_prone(self, analyzer):
        """Test collapse-prone team classification."""
        metrics = TeamResilienceMetrics(
            team_id=1, leads_held=4, leads_blown=6  # 40% lead protection
        )
        analyzer.ingest_team_metrics(metrics)

        assert analyzer.is_resilient(1) is False
        assert analyzer.is_collapse_prone(1) is True

    def test_get_resilient_teams(self, analyzer):
        """Test getting list of resilient teams."""
        analyzer.ingest_team_metrics(
            TeamResilienceMetrics(team_id=1, leads_held=8, leads_blown=2)
        )
        analyzer.ingest_team_metrics(
            TeamResilienceMetrics(team_id=2, leads_held=5, leads_blown=5)
        )
        analyzer.ingest_team_metrics(
            TeamResilienceMetrics(team_id=3, leads_held=7, leads_blown=3)
        )

        resilient = analyzer.get_resilient_teams([1, 2, 3])

        assert 1 in resilient  # 80%
        assert 2 not in resilient  # 50%
        assert 3 in resilient  # 70%

    def test_get_collapse_prone_teams(self, analyzer):
        """Test getting list of collapse-prone teams."""
        analyzer.ingest_team_metrics(
            TeamResilienceMetrics(team_id=1, leads_held=8, leads_blown=2)
        )
        analyzer.ingest_team_metrics(
            TeamResilienceMetrics(team_id=2, leads_held=4, leads_blown=6)
        )
        analyzer.ingest_team_metrics(
            TeamResilienceMetrics(team_id=3, leads_held=3, leads_blown=7)
        )

        collapse_prone = analyzer.get_collapse_prone_teams([1, 2, 3])

        assert 1 not in collapse_prone  # 80%
        assert 2 in collapse_prone  # 40%
        assert 3 in collapse_prone  # 30%


class TestClutchStaminaIntegration:
    """Integration tests for clutch and stamina analysis."""

    def test_elite_clutch_with_good_stamina(self):
        """Test identifying players who are both clutch and have good stamina."""
        clutch_analyzer = ClutchAnalyzer()
        stamina_analyzer = StaminaAnalyzer()

        # Player with elite clutch AND good stamina
        # Score: GWG(6*5) + OTG(4*4.5) + LG_goals(10*2.5) / 15 games
        # = (30 + 18 + 25) / 15 = 4.87 -> ELITE (threshold: >= 3.0)
        clutch_analyzer.ingest_player_metrics(
            ClutchMetrics(
                player_id=100,
                games_played=15,
                game_winning_goals=6,
                overtime_goals=4,
                late_game_goals=10,
            )
        )
        stamina_analyzer.ingest_player_metrics(
            StaminaMetrics(
                player_id=100,
                early_game_points_per_60=3.0,
                late_game_points_per_60=3.2,  # Better late game!
            )
        )

        clutch_level = clutch_analyzer.classify_player(100)
        fatigue_level = stamina_analyzer.classify_fatigue(100)

        assert clutch_level == ClutchLevel.ELITE
        assert fatigue_level == FatigueLevel.MINIMAL

    def test_clutch_player_with_fatigue_issues(self):
        """Test identifying clutch players who struggle with fatigue."""
        clutch_analyzer = ClutchAnalyzer()
        stamina_analyzer = StaminaAnalyzer()

        # Player with clutch performance but fatigue issues
        clutch_analyzer.ingest_player_metrics(
            ClutchMetrics(
                player_id=100,
                games_played=30,
                game_winning_goals=6,
                overtime_goals=2,
                late_game_goals=5,  # Lower late game production
            )
        )
        stamina_analyzer.ingest_player_metrics(
            StaminaMetrics(
                player_id=100,
                early_game_points_per_60=4.0,
                late_game_points_per_60=2.0,  # Significant decline
            )
        )

        clutch_level = clutch_analyzer.classify_player(100)
        fatigue_level = stamina_analyzer.classify_fatigue(100)

        assert clutch_level in (ClutchLevel.STRONG, ClutchLevel.AVERAGE)
        assert fatigue_level in (FatigueLevel.HIGH, FatigueLevel.SEVERE)
