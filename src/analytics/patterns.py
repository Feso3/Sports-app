"""
Pattern Detection Module

Identifies and analyzes playing patterns including:
- Play style classification
- Spatial patterns (shot locations, zone preferences)
- Temporal patterns (performance by game segment)
- Mismatch detection
- Clutch performance patterns
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
from loguru import logger


class PlayStyle(Enum):
    """Classification of team or player play styles."""

    OFFENSIVE_HEAVY = "offensive_heavy"
    DEFENSIVE_HEAVY = "defensive_heavy"
    BALANCED = "balanced"
    HIGH_TEMPO = "high_tempo"
    GRINDING = "grinding"
    PERIMETER = "perimeter"
    SLOT_FOCUSED = "slot_focused"
    TRANSITION = "transition"


class PatternStrength(Enum):
    """Strength of a detected pattern."""

    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


@dataclass
class PatternMatch:
    """Represents a detected pattern."""

    pattern_type: str
    description: str
    strength: PatternStrength
    confidence: float  # 0-1
    evidence: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class SpatialPattern:
    """Pattern in spatial shot/event distribution."""

    entity_id: int
    entity_type: str  # "player" or "team"
    primary_zone: str
    secondary_zone: str | None
    zone_diversity: float  # 0-1, higher = more diverse shot locations
    slot_preference: float  # 0-1, higher = more slot shots
    perimeter_preference: float  # 0-1, higher = more perimeter shots
    left_side_bias: float  # >0.5 = prefers left, <0.5 = prefers right


@dataclass
class TemporalPattern:
    """Pattern in performance across time."""

    entity_id: int
    entity_type: str
    early_game_strength: float  # Relative performance
    mid_game_strength: float
    late_game_strength: float
    fatigue_indicator: float  # <1.0 = performance declines
    clutch_rating: float  # Higher = better in close games


@dataclass
class MismatchOpportunity:
    """Identified mismatch between offensive/defensive capabilities."""

    zone: str
    offensive_entity_id: int
    defensive_entity_id: int
    offensive_strength: float
    defensive_weakness: float
    opportunity_score: float
    description: str


class PatternDetector:
    """
    Detector for playing patterns and tendencies.

    Analyzes shot data, events, and statistics to identify:
    - Play style classifications
    - Spatial patterns (where players/teams generate offense)
    - Temporal patterns (performance by game segment)
    - Mismatch opportunities
    - Fatigue and clutch patterns
    """

    # Zone classification
    SLOT_ZONES = {"slot", "inner_slot", "crease"}
    PERIMETER_ZONES = {"left_point", "right_point", "left_wing", "right_wing", "high_slot"}
    HIGH_DANGER_ZONES = {"slot", "inner_slot", "crease", "left_circle", "right_circle"}

    # Thresholds for pattern detection
    STRONG_PATTERN_THRESHOLD = 0.65
    MODERATE_PATTERN_THRESHOLD = 0.55
    DIVERSITY_LOW_THRESHOLD = 0.3
    DIVERSITY_HIGH_THRESHOLD = 0.7

    def __init__(self) -> None:
        """Initialize the pattern detector."""
        self.detected_patterns: dict[int, list[PatternMatch]] = {}
        self.spatial_patterns: dict[int, SpatialPattern] = {}
        self.temporal_patterns: dict[int, TemporalPattern] = {}

    def analyze_shot_distribution(
        self,
        entity_id: int,
        entity_type: str,
        zone_shots: dict[str, int],
    ) -> SpatialPattern:
        """
        Analyze shot distribution to identify spatial patterns.

        Args:
            entity_id: Player or team ID
            entity_type: "player" or "team"
            zone_shots: Dictionary mapping zone names to shot counts

        Returns:
            SpatialPattern with analysis results
        """
        total_shots = sum(zone_shots.values())
        if total_shots == 0:
            return SpatialPattern(
                entity_id=entity_id,
                entity_type=entity_type,
                primary_zone="unknown",
                secondary_zone=None,
                zone_diversity=0.0,
                slot_preference=0.0,
                perimeter_preference=0.0,
                left_side_bias=0.5,
            )

        # Find primary and secondary zones
        sorted_zones = sorted(zone_shots.items(), key=lambda x: x[1], reverse=True)
        primary_zone = sorted_zones[0][0] if sorted_zones else "unknown"
        secondary_zone = sorted_zones[1][0] if len(sorted_zones) > 1 else None

        # Calculate zone diversity (entropy-based)
        proportions = [count / total_shots for count in zone_shots.values() if count > 0]
        diversity = -sum(p * np.log2(p) for p in proportions if p > 0)
        max_entropy = np.log2(len(zone_shots)) if len(zone_shots) > 1 else 1
        normalized_diversity = diversity / max_entropy if max_entropy > 0 else 0

        # Calculate slot preference
        slot_shots = sum(zone_shots.get(z, 0) for z in self.SLOT_ZONES)
        slot_preference = slot_shots / total_shots

        # Calculate perimeter preference
        perimeter_shots = sum(zone_shots.get(z, 0) for z in self.PERIMETER_ZONES)
        perimeter_preference = perimeter_shots / total_shots

        # Calculate left/right bias
        left_zones = {"left_point", "left_wing", "left_circle"}
        right_zones = {"right_point", "right_wing", "right_circle"}
        left_shots = sum(zone_shots.get(z, 0) for z in left_zones)
        right_shots = sum(zone_shots.get(z, 0) for z in right_zones)
        total_sided = left_shots + right_shots
        left_bias = left_shots / total_sided if total_sided > 0 else 0.5

        pattern = SpatialPattern(
            entity_id=entity_id,
            entity_type=entity_type,
            primary_zone=primary_zone,
            secondary_zone=secondary_zone,
            zone_diversity=normalized_diversity,
            slot_preference=slot_preference,
            perimeter_preference=perimeter_preference,
            left_side_bias=left_bias,
        )

        self.spatial_patterns[entity_id] = pattern
        return pattern

    def analyze_segment_performance(
        self,
        entity_id: int,
        entity_type: str,
        early_stats: dict[str, float],
        mid_stats: dict[str, float],
        late_stats: dict[str, float],
    ) -> TemporalPattern:
        """
        Analyze performance across game segments.

        Args:
            entity_id: Player or team ID
            entity_type: "player" or "team"
            early_stats: Stats from early game
            mid_stats: Stats from mid game
            late_stats: Stats from late game

        Returns:
            TemporalPattern with analysis results
        """
        # Use points/goals per 60 as primary metric
        early_rate = early_stats.get("points_per_60", early_stats.get("goals_per_60", 0))
        mid_rate = mid_stats.get("points_per_60", mid_stats.get("goals_per_60", 0))
        late_rate = late_stats.get("points_per_60", late_stats.get("goals_per_60", 0))

        # Normalize to average
        avg_rate = (early_rate + mid_rate + late_rate) / 3 if (early_rate + mid_rate + late_rate) > 0 else 1

        early_strength = early_rate / avg_rate if avg_rate > 0 else 1.0
        mid_strength = mid_rate / avg_rate if avg_rate > 0 else 1.0
        late_strength = late_rate / avg_rate if avg_rate > 0 else 1.0

        # Fatigue indicator: late game vs early game
        fatigue_indicator = late_strength / early_strength if early_strength > 0 else 1.0

        # Clutch rating based on late game performance and close game stats
        clutch_goals = late_stats.get("game_winning_goals", 0) + late_stats.get("game_tying_goals", 0)
        games = late_stats.get("games", 1)
        clutch_rating = clutch_goals / games if games > 0 else 0

        pattern = TemporalPattern(
            entity_id=entity_id,
            entity_type=entity_type,
            early_game_strength=early_strength,
            mid_game_strength=mid_strength,
            late_game_strength=late_strength,
            fatigue_indicator=fatigue_indicator,
            clutch_rating=clutch_rating,
        )

        self.temporal_patterns[entity_id] = pattern
        return pattern

    def classify_play_style(
        self,
        entity_id: int,
        offensive_metrics: dict[str, float],
        defensive_metrics: dict[str, float],
        spatial_pattern: SpatialPattern | None = None,
    ) -> PlayStyle:
        """
        Classify play style based on metrics and patterns.

        Args:
            entity_id: Player or team ID
            offensive_metrics: Dict with xg_for, shots_for, etc.
            defensive_metrics: Dict with xg_against, shots_against, etc.
            spatial_pattern: Optional spatial pattern data

        Returns:
            PlayStyle classification
        """
        # Calculate offensive/defensive balance
        off_score = offensive_metrics.get("xg_for", 0) + offensive_metrics.get("shots_for", 0) * 0.1
        def_score = defensive_metrics.get("xg_against", 0) + defensive_metrics.get("shots_against", 0) * 0.1

        total = off_score + def_score
        if total == 0:
            return PlayStyle.BALANCED

        off_ratio = off_score / total

        # Determine primary style
        if off_ratio > 0.6:
            primary_style = PlayStyle.OFFENSIVE_HEAVY
        elif off_ratio < 0.4:
            primary_style = PlayStyle.DEFENSIVE_HEAVY
        else:
            primary_style = PlayStyle.BALANCED

        # Refine based on spatial pattern
        if spatial_pattern:
            if spatial_pattern.slot_preference > self.STRONG_PATTERN_THRESHOLD:
                return PlayStyle.SLOT_FOCUSED
            elif spatial_pattern.perimeter_preference > self.STRONG_PATTERN_THRESHOLD:
                return PlayStyle.PERIMETER

        # Check for tempo style
        shot_volume = offensive_metrics.get("shots_for", 0) + defensive_metrics.get("shots_against", 0)
        if shot_volume > offensive_metrics.get("avg_shots_league", 60) * 1.2:
            return PlayStyle.HIGH_TEMPO
        elif shot_volume < offensive_metrics.get("avg_shots_league", 60) * 0.8:
            return PlayStyle.GRINDING

        return primary_style

    def detect_mismatch(
        self,
        offensive_id: int,
        defensive_id: int,
        offensive_spatial: SpatialPattern,
        defensive_spatial: SpatialPattern,
        zone_strengths: dict[str, float],
        zone_weaknesses: dict[str, float],
    ) -> list[MismatchOpportunity]:
        """
        Detect mismatches between offensive and defensive tendencies.

        Args:
            offensive_id: Offensive entity ID
            defensive_id: Defensive entity ID
            offensive_spatial: Spatial pattern for offensive entity
            defensive_spatial: Spatial pattern for defensive entity
            zone_strengths: Offensive strength by zone
            zone_weaknesses: Defensive weakness by zone (higher = weaker)

        Returns:
            List of MismatchOpportunity objects
        """
        mismatches = []

        for zone in self.HIGH_DANGER_ZONES:
            off_strength = zone_strengths.get(zone, 0)
            def_weakness = zone_weaknesses.get(zone, 0)

            # Calculate opportunity score
            opportunity = off_strength * def_weakness

            if opportunity > 0.1:  # Threshold for significant mismatch
                mismatches.append(MismatchOpportunity(
                    zone=zone,
                    offensive_entity_id=offensive_id,
                    defensive_entity_id=defensive_id,
                    offensive_strength=off_strength,
                    defensive_weakness=def_weakness,
                    opportunity_score=opportunity,
                    description=f"Strong offensive presence in {zone} vs weak defense"
                ))

        return sorted(mismatches, key=lambda m: m.opportunity_score, reverse=True)

    def detect_fatigue_pattern(
        self,
        entity_id: int,
        temporal_pattern: TemporalPattern,
    ) -> PatternMatch | None:
        """
        Detect fatigue patterns based on performance degradation.

        Args:
            entity_id: Entity ID
            temporal_pattern: Temporal performance pattern

        Returns:
            PatternMatch if fatigue pattern detected, None otherwise
        """
        fatigue = temporal_pattern.fatigue_indicator

        if fatigue < 0.7:
            strength = PatternStrength.VERY_STRONG
            confidence = 0.9
        elif fatigue < 0.85:
            strength = PatternStrength.STRONG
            confidence = 0.75
        elif fatigue < 0.95:
            strength = PatternStrength.MODERATE
            confidence = 0.6
        else:
            return None  # No significant fatigue pattern

        return PatternMatch(
            pattern_type="fatigue",
            description=f"Performance declines {(1 - fatigue) * 100:.1f}% from early to late game",
            strength=strength,
            confidence=confidence,
            evidence={
                "early_strength": temporal_pattern.early_game_strength,
                "late_strength": temporal_pattern.late_game_strength,
                "fatigue_indicator": fatigue,
            },
            recommendations=[
                "Limit late-game ice time",
                "Deploy fresh legs in third period",
                "Consider line matching to avoid tough matchups late",
            ],
        )

    def detect_clutch_pattern(
        self,
        entity_id: int,
        temporal_pattern: TemporalPattern,
        late_game_stats: dict[str, Any],
    ) -> PatternMatch | None:
        """
        Detect clutch performance patterns.

        Args:
            entity_id: Entity ID
            temporal_pattern: Temporal performance pattern
            late_game_stats: Statistics from late game situations

        Returns:
            PatternMatch if clutch pattern detected, None otherwise
        """
        clutch_rating = temporal_pattern.clutch_rating
        late_strength = temporal_pattern.late_game_strength

        # Check for positive clutch pattern
        if clutch_rating > 0.3 and late_strength > 1.1:
            return PatternMatch(
                pattern_type="clutch_positive",
                description="Excels in clutch situations and late game",
                strength=PatternStrength.STRONG if clutch_rating > 0.5 else PatternStrength.MODERATE,
                confidence=0.8,
                evidence={
                    "clutch_rating": clutch_rating,
                    "late_game_strength": late_strength,
                    "game_winning_goals": late_game_stats.get("game_winning_goals", 0),
                },
                recommendations=[
                    "Deploy in late-game situations",
                    "Use on power play in close games",
                    "Consider for shootout/overtime",
                ],
            )

        # Check for negative clutch pattern
        if late_strength < 0.8:
            return PatternMatch(
                pattern_type="clutch_negative",
                description="Struggles in late game situations",
                strength=PatternStrength.MODERATE,
                confidence=0.7,
                evidence={
                    "clutch_rating": clutch_rating,
                    "late_game_strength": late_strength,
                },
                recommendations=[
                    "Limit ice time in crucial late-game moments",
                    "Use primarily in early and mid game",
                ],
            )

        return None

    def detect_zone_preference_pattern(
        self,
        entity_id: int,
        spatial_pattern: SpatialPattern,
    ) -> PatternMatch | None:
        """
        Detect strong zone preferences.

        Args:
            entity_id: Entity ID
            spatial_pattern: Spatial pattern data

        Returns:
            PatternMatch if strong preference detected, None otherwise
        """
        if spatial_pattern.slot_preference > self.STRONG_PATTERN_THRESHOLD:
            return PatternMatch(
                pattern_type="zone_preference",
                description=f"Strong slot preference ({spatial_pattern.slot_preference:.1%} of shots)",
                strength=PatternStrength.STRONG,
                confidence=0.85,
                evidence={
                    "slot_preference": spatial_pattern.slot_preference,
                    "primary_zone": spatial_pattern.primary_zone,
                },
                recommendations=[
                    "High-danger shooter, get them the puck in scoring areas",
                    "Effective on net-front power play",
                ],
            )

        if spatial_pattern.perimeter_preference > self.STRONG_PATTERN_THRESHOLD:
            return PatternMatch(
                pattern_type="zone_preference",
                description=f"Perimeter shooter ({spatial_pattern.perimeter_preference:.1%} of shots)",
                strength=PatternStrength.MODERATE,
                confidence=0.75,
                evidence={
                    "perimeter_preference": spatial_pattern.perimeter_preference,
                    "primary_zone": spatial_pattern.primary_zone,
                },
                recommendations=[
                    "Best utilized from the point or wing",
                    "Effective on power play point",
                    "Consider traffic and screens for higher conversion",
                ],
            )

        if spatial_pattern.zone_diversity < self.DIVERSITY_LOW_THRESHOLD:
            return PatternMatch(
                pattern_type="predictable_location",
                description=f"Predictable shot locations (diversity: {spatial_pattern.zone_diversity:.2f})",
                strength=PatternStrength.MODERATE,
                confidence=0.7,
                evidence={
                    "zone_diversity": spatial_pattern.zone_diversity,
                    "primary_zone": spatial_pattern.primary_zone,
                },
                recommendations=[
                    "Opponents can anticipate shot locations",
                    "Work on diversifying attack angles",
                ],
            )

        return None

    def run_full_analysis(
        self,
        entity_id: int,
        entity_type: str,
        zone_shots: dict[str, int],
        early_stats: dict[str, float],
        mid_stats: dict[str, float],
        late_stats: dict[str, float],
        offensive_metrics: dict[str, float],
        defensive_metrics: dict[str, float],
    ) -> dict[str, Any]:
        """
        Run complete pattern analysis for an entity.

        Args:
            entity_id: Player or team ID
            entity_type: "player" or "team"
            zone_shots: Shot distribution by zone
            early_stats: Early game statistics
            mid_stats: Mid game statistics
            late_stats: Late game statistics
            offensive_metrics: Offensive metrics
            defensive_metrics: Defensive metrics

        Returns:
            Complete analysis results
        """
        # Analyze spatial patterns
        spatial = self.analyze_shot_distribution(entity_id, entity_type, zone_shots)

        # Analyze temporal patterns
        temporal = self.analyze_segment_performance(
            entity_id, entity_type, early_stats, mid_stats, late_stats
        )

        # Classify play style
        play_style = self.classify_play_style(
            entity_id, offensive_metrics, defensive_metrics, spatial
        )

        # Detect individual patterns
        patterns = []

        fatigue_pattern = self.detect_fatigue_pattern(entity_id, temporal)
        if fatigue_pattern:
            patterns.append(fatigue_pattern)

        clutch_pattern = self.detect_clutch_pattern(entity_id, temporal, late_stats)
        if clutch_pattern:
            patterns.append(clutch_pattern)

        zone_pattern = self.detect_zone_preference_pattern(entity_id, spatial)
        if zone_pattern:
            patterns.append(zone_pattern)

        self.detected_patterns[entity_id] = patterns

        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "play_style": play_style.value,
            "spatial_pattern": {
                "primary_zone": spatial.primary_zone,
                "secondary_zone": spatial.secondary_zone,
                "zone_diversity": spatial.zone_diversity,
                "slot_preference": spatial.slot_preference,
                "perimeter_preference": spatial.perimeter_preference,
                "left_side_bias": spatial.left_side_bias,
            },
            "temporal_pattern": {
                "early_game_strength": temporal.early_game_strength,
                "mid_game_strength": temporal.mid_game_strength,
                "late_game_strength": temporal.late_game_strength,
                "fatigue_indicator": temporal.fatigue_indicator,
                "clutch_rating": temporal.clutch_rating,
            },
            "detected_patterns": [
                {
                    "type": p.pattern_type,
                    "description": p.description,
                    "strength": p.strength.value,
                    "confidence": p.confidence,
                    "recommendations": p.recommendations,
                }
                for p in patterns
            ],
        }

    def get_patterns(self, entity_id: int) -> list[PatternMatch]:
        """Get detected patterns for an entity."""
        return self.detected_patterns.get(entity_id, [])

    def get_spatial_pattern(self, entity_id: int) -> SpatialPattern | None:
        """Get spatial pattern for an entity."""
        return self.spatial_patterns.get(entity_id)

    def get_temporal_pattern(self, entity_id: int) -> TemporalPattern | None:
        """Get temporal pattern for an entity."""
        return self.temporal_patterns.get(entity_id)

    def reset(self) -> None:
        """Reset all detected patterns."""
        self.detected_patterns.clear()
        self.spatial_patterns.clear()
        self.temporal_patterns.clear()
