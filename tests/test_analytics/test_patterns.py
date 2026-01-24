"""
Tests for Pattern Detection Module

Tests for play style classification and pattern detection.
"""

import pytest

from src.analytics.patterns import (
    PatternDetector,
    PatternStrength,
    PlayStyle,
    SpatialPattern,
    TemporalPattern,
)


class TestSpatialPattern:
    """Tests for SpatialPattern dataclass."""

    def test_spatial_pattern_creation(self):
        """Test creating a spatial pattern."""
        pattern = SpatialPattern(
            entity_id=100,
            entity_type="player",
            primary_zone="slot",
            secondary_zone="left_circle",
            zone_diversity=0.6,
            slot_preference=0.4,
            perimeter_preference=0.3,
            left_side_bias=0.55,
        )

        assert pattern.entity_id == 100
        assert pattern.primary_zone == "slot"
        assert pattern.zone_diversity == 0.6


class TestTemporalPattern:
    """Tests for TemporalPattern dataclass."""

    def test_temporal_pattern_creation(self):
        """Test creating a temporal pattern."""
        pattern = TemporalPattern(
            entity_id=100,
            entity_type="player",
            early_game_strength=1.1,
            mid_game_strength=1.0,
            late_game_strength=0.85,
            fatigue_indicator=0.77,
            clutch_rating=0.3,
        )

        assert pattern.fatigue_indicator == pytest.approx(0.77)
        assert pattern.late_game_strength < pattern.early_game_strength


class TestPatternDetector:
    """Tests for PatternDetector class."""

    @pytest.fixture
    def detector(self):
        """Create a pattern detector instance."""
        return PatternDetector()

    def test_analyze_shot_distribution_slot_preference(self, detector):
        """Test detection of slot preference."""
        zone_shots = {
            "slot": 50,
            "inner_slot": 20,
            "left_circle": 10,
            "right_circle": 10,
            "high_slot": 5,
            "left_point": 3,
            "right_point": 2,
        }

        pattern = detector.analyze_shot_distribution(100, "player", zone_shots)

        assert pattern.primary_zone == "slot"
        assert pattern.slot_preference > 0.5  # High slot preference

    def test_analyze_shot_distribution_diversity(self, detector):
        """Test zone diversity calculation."""
        # Low diversity (all shots from one zone)
        low_diversity_shots = {
            "slot": 100,
            "left_circle": 0,
            "right_circle": 0,
        }

        pattern_low = detector.analyze_shot_distribution(100, "player", low_diversity_shots)

        # High diversity (even distribution)
        high_diversity_shots = {
            "slot": 20,
            "left_circle": 20,
            "right_circle": 20,
            "high_slot": 20,
            "left_point": 10,
            "right_point": 10,
        }

        pattern_high = detector.analyze_shot_distribution(101, "player", high_diversity_shots)

        assert pattern_high.zone_diversity > pattern_low.zone_diversity

    def test_analyze_segment_performance(self, detector):
        """Test segment performance analysis."""
        early_stats = {"points_per_60": 3.0, "games": 20}
        mid_stats = {"points_per_60": 2.5, "games": 20}
        late_stats = {"points_per_60": 2.0, "games": 20, "game_winning_goals": 2}

        pattern = detector.analyze_segment_performance(
            100, "player", early_stats, mid_stats, late_stats
        )

        # Should detect fatigue (late game worse than early)
        assert pattern.fatigue_indicator < 1.0
        assert pattern.early_game_strength > pattern.late_game_strength

    def test_classify_play_style_offensive(self, detector):
        """Test offensive play style classification."""
        offensive_metrics = {"xg_for": 3.0, "shots_for": 35}
        defensive_metrics = {"xg_against": 1.5, "shots_against": 20}

        style = detector.classify_play_style(
            100, offensive_metrics, defensive_metrics
        )

        assert style == PlayStyle.OFFENSIVE_HEAVY

    def test_classify_play_style_defensive(self, detector):
        """Test defensive play style classification."""
        offensive_metrics = {"xg_for": 1.5, "shots_for": 20}
        defensive_metrics = {"xg_against": 3.0, "shots_against": 35}

        style = detector.classify_play_style(
            100, offensive_metrics, defensive_metrics
        )

        assert style == PlayStyle.DEFENSIVE_HEAVY

    def test_classify_play_style_slot_focused(self, detector):
        """Test slot-focused play style classification."""
        spatial = SpatialPattern(
            entity_id=100,
            entity_type="player",
            primary_zone="slot",
            secondary_zone="inner_slot",
            zone_diversity=0.3,
            slot_preference=0.7,
            perimeter_preference=0.1,
            left_side_bias=0.5,
        )

        style = detector.classify_play_style(
            100,
            {"xg_for": 2.5, "shots_for": 30},
            {"xg_against": 2.5, "shots_against": 30},
            spatial_pattern=spatial,
        )

        assert style == PlayStyle.SLOT_FOCUSED

    def test_detect_fatigue_pattern(self, detector):
        """Test fatigue pattern detection."""
        temporal = TemporalPattern(
            entity_id=100,
            entity_type="player",
            early_game_strength=1.2,
            mid_game_strength=1.0,
            late_game_strength=0.7,
            fatigue_indicator=0.58,  # Significant decline
            clutch_rating=0.1,
        )

        pattern = detector.detect_fatigue_pattern(100, temporal)

        assert pattern is not None
        assert pattern.pattern_type == "fatigue"
        assert pattern.strength in [PatternStrength.STRONG, PatternStrength.VERY_STRONG]

    def test_detect_clutch_pattern_positive(self, detector):
        """Test positive clutch pattern detection."""
        temporal = TemporalPattern(
            entity_id=100,
            entity_type="player",
            early_game_strength=1.0,
            mid_game_strength=1.0,
            late_game_strength=1.3,
            fatigue_indicator=1.3,
            clutch_rating=0.5,
        )

        late_stats = {"game_winning_goals": 5, "games": 20}

        pattern = detector.detect_clutch_pattern(100, temporal, late_stats)

        assert pattern is not None
        assert pattern.pattern_type == "clutch_positive"

    def test_detect_zone_preference_pattern(self, detector):
        """Test zone preference pattern detection."""
        spatial = SpatialPattern(
            entity_id=100,
            entity_type="player",
            primary_zone="slot",
            secondary_zone="inner_slot",
            zone_diversity=0.3,
            slot_preference=0.7,
            perimeter_preference=0.1,
            left_side_bias=0.5,
        )

        pattern = detector.detect_zone_preference_pattern(100, spatial)

        assert pattern is not None
        assert pattern.pattern_type == "zone_preference"
        assert "slot" in pattern.description.lower()

    def test_run_full_analysis(self, detector):
        """Test full analysis pipeline."""
        zone_shots = {"slot": 40, "left_circle": 20, "right_circle": 20, "high_slot": 10, "left_point": 10}
        early_stats = {"points_per_60": 2.5, "games": 20}
        mid_stats = {"points_per_60": 2.3, "games": 20}
        late_stats = {"points_per_60": 2.0, "games": 20, "game_winning_goals": 1}
        offensive_metrics = {"xg_for": 2.5, "shots_for": 30}
        defensive_metrics = {"xg_against": 2.0, "shots_against": 25}

        result = detector.run_full_analysis(
            entity_id=100,
            entity_type="player",
            zone_shots=zone_shots,
            early_stats=early_stats,
            mid_stats=mid_stats,
            late_stats=late_stats,
            offensive_metrics=offensive_metrics,
            defensive_metrics=defensive_metrics,
        )

        assert result["entity_id"] == 100
        assert "play_style" in result
        assert "spatial_pattern" in result
        assert "temporal_pattern" in result
        assert "detected_patterns" in result

    def test_reset(self, detector):
        """Test reset clears all patterns."""
        zone_shots = {"slot": 50}
        detector.analyze_shot_distribution(100, "player", zone_shots)

        detector.reset()

        assert detector.get_spatial_pattern(100) is None
        assert len(detector.detected_patterns) == 0
