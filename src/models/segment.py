"""
Game Segment Model

Pydantic models for representing game time segments and segment-based analytics.
"""

from typing import Any

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    """Defines a time range within a game."""

    period: int
    start_minute: int
    end_minute: int

    @property
    def duration_minutes(self) -> int:
        """Calculate duration in minutes."""
        return self.end_minute - self.start_minute

    @property
    def start_game_seconds(self) -> int:
        """Calculate start time in total game seconds."""
        return (self.period - 1) * 1200 + self.start_minute * 60

    @property
    def end_game_seconds(self) -> int:
        """Calculate end time in total game seconds."""
        return (self.period - 1) * 1200 + self.end_minute * 60

    def contains_time(self, period: int, minute: int) -> bool:
        """Check if a given time falls within this range."""
        return (
            period == self.period
            and self.start_minute <= minute < self.end_minute
        )


class SegmentStats(BaseModel):
    """Statistics for a game segment."""

    goals: int = 0
    shots: int = 0
    shots_on_goal: int = 0
    hits: int = 0
    blocked_shots: int = 0
    takeaways: int = 0
    giveaways: int = 0
    faceoff_wins: int = 0
    faceoff_total: int = 0
    penalties: int = 0
    penalty_minutes: int = 0
    power_play_goals: int = 0
    power_play_opportunities: int = 0
    expected_goals: float = 0.0
    corsi_for: int = 0
    corsi_against: int = 0

    @property
    def shooting_percentage(self) -> float:
        """Calculate shooting percentage."""
        return self.goals / self.shots_on_goal if self.shots_on_goal > 0 else 0.0

    @property
    def faceoff_percentage(self) -> float:
        """Calculate faceoff win percentage."""
        return self.faceoff_wins / self.faceoff_total if self.faceoff_total > 0 else 0.5

    @property
    def corsi_percentage(self) -> float:
        """Calculate Corsi percentage."""
        total = self.corsi_for + self.corsi_against
        return self.corsi_for / total if total > 0 else 0.5


class SegmentPerformance(BaseModel):
    """Player or team performance within a segment."""

    entity_id: int  # Player ID or Team ID
    entity_type: str  # "player" or "team"
    segment_name: str
    games_played: int = 0

    # Counting stats
    goals: int = 0
    assists: int = 0
    points: int = 0
    shots: int = 0
    hits: int = 0
    blocked_shots: int = 0
    takeaways: int = 0
    plus_minus: int = 0

    # Rate stats (per 60 minutes)
    goals_per_60: float = 0.0
    points_per_60: float = 0.0
    shots_per_60: float = 0.0

    # Advanced stats
    expected_goals: float = 0.0
    expected_goals_against: float = 0.0
    corsi_percentage: float = 0.0

    # Clutch metrics (for late_game segment)
    game_tying_goals: int = 0
    game_winning_goals: int = 0
    clutch_rating: float = 0.0

    # Time on ice in this segment
    time_on_ice_seconds: int = 0

    @property
    def shooting_percentage(self) -> float:
        """Calculate shooting percentage."""
        return self.goals / self.shots if self.shots > 0 else 0.0

    @property
    def points_per_game(self) -> float:
        """Calculate points per game in this segment."""
        return self.points / self.games_played if self.games_played > 0 else 0.0


class Segment(BaseModel):
    """
    Game segment definition and associated data.

    Segments divide games into meaningful time periods:
    - Early game: Period 1 + first 10 min of Period 2
    - Mid game: Minutes 10-20 of Period 2 + first 10 min of Period 3
    - Late game: Final 10 minutes of regulation + overtime
    """

    name: str
    description: str = ""
    time_ranges: list[TimeRange] = Field(default_factory=list)
    characteristics: list[str] = Field(default_factory=list)

    # Aggregated league-wide stats for this segment
    league_stats: SegmentStats = Field(default_factory=SegmentStats)

    # Team performances in this segment
    team_performances: dict[int, SegmentPerformance] = Field(default_factory=dict)

    # Player performances in this segment
    player_performances: dict[int, SegmentPerformance] = Field(default_factory=dict)

    # Scoring patterns
    avg_goals_per_game: float = 0.0
    scoring_rate_per_minute: float = 0.0
    home_goal_percentage: float = 0.5  # Percentage of goals scored by home team

    # Fatigue and momentum factors
    avg_fatigue_factor: float = 1.0  # Performance degradation
    momentum_volatility: float = 0.0  # How often momentum shifts occur

    @property
    def total_duration_minutes(self) -> int:
        """Calculate total segment duration in minutes."""
        return sum(tr.duration_minutes for tr in self.time_ranges)

    @property
    def start_game_seconds(self) -> int:
        """Get the earliest start time in game seconds."""
        if not self.time_ranges:
            return 0
        return min(tr.start_game_seconds for tr in self.time_ranges)

    @property
    def end_game_seconds(self) -> int:
        """Get the latest end time in game seconds."""
        if not self.time_ranges:
            return 0
        return max(tr.end_game_seconds for tr in self.time_ranges)

    def contains_time(self, period: int, minute: int) -> bool:
        """Check if a given time falls within this segment."""
        return any(tr.contains_time(period, minute) for tr in self.time_ranges)

    def contains_game_seconds(self, game_seconds: int) -> bool:
        """Check if a given game second falls within this segment."""
        return any(
            tr.start_game_seconds <= game_seconds < tr.end_game_seconds
            for tr in self.time_ranges
        )

    def get_team_performance(self, team_id: int) -> SegmentPerformance | None:
        """Get team's performance in this segment."""
        return self.team_performances.get(team_id)

    def get_player_performance(self, player_id: int) -> SegmentPerformance | None:
        """Get player's performance in this segment."""
        return self.player_performances.get(player_id)

    def compare_players(
        self, player_id_1: int, player_id_2: int, metric: str = "points"
    ) -> tuple[float, float]:
        """
        Compare two players' performance in this segment.

        Args:
            player_id_1: First player ID
            player_id_2: Second player ID
            metric: Metric to compare

        Returns:
            Tuple of (player_1_value, player_2_value)
        """
        perf_1 = self.player_performances.get(player_id_1)
        perf_2 = self.player_performances.get(player_id_2)

        val_1 = getattr(perf_1, metric, 0.0) if perf_1 else 0.0
        val_2 = getattr(perf_2, metric, 0.0) if perf_2 else 0.0

        return (val_1, val_2)

    def get_top_performers(
        self, metric: str = "points", limit: int = 10
    ) -> list[tuple[int, float]]:
        """
        Get top performers in this segment.

        Args:
            metric: Metric to rank by
            limit: Maximum number of results

        Returns:
            List of (player_id, metric_value) tuples
        """
        performances = []
        for player_id, perf in self.player_performances.items():
            value = getattr(perf, metric, 0.0)
            performances.append((player_id, value))

        performances.sort(key=lambda x: x[1], reverse=True)
        return performances[:limit]


class SegmentAnalysis(BaseModel):
    """Analysis results for segment-based performance."""

    # Segment definitions
    early_game: Segment = Field(default_factory=lambda: Segment(name="early_game"))
    mid_game: Segment = Field(default_factory=lambda: Segment(name="mid_game"))
    late_game: Segment = Field(default_factory=lambda: Segment(name="late_game"))

    # Cross-segment comparisons
    fatigue_indicators: dict[int, float] = Field(default_factory=dict)  # player_id -> fatigue
    clutch_performers: dict[int, float] = Field(default_factory=dict)  # player_id -> clutch rating
    collapse_prone_teams: list[int] = Field(default_factory=list)  # team_ids
    resilient_teams: list[int] = Field(default_factory=list)  # team_ids

    def get_segment(self, name: str) -> Segment | None:
        """Get segment by name."""
        if name == "early_game":
            return self.early_game
        elif name == "mid_game":
            return self.mid_game
        elif name == "late_game":
            return self.late_game
        return None

    def calculate_fatigue_indicator(self, player_id: int) -> float:
        """
        Calculate fatigue indicator for a player.

        Compares early game to late game performance.

        Args:
            player_id: Player ID

        Returns:
            Fatigue indicator (< 1.0 indicates performance decline)
        """
        early_perf = self.early_game.get_player_performance(player_id)
        late_perf = self.late_game.get_player_performance(player_id)

        if not early_perf or not late_perf:
            return 1.0

        # Compare points per 60
        early_rate = early_perf.points_per_60 if early_perf.points_per_60 > 0 else 0.1
        late_rate = late_perf.points_per_60 if late_perf.points_per_60 > 0 else 0.1

        return late_rate / early_rate

    def calculate_clutch_rating(self, player_id: int) -> float:
        """
        Calculate clutch performance rating for a player.

        Based on late game performance, especially in close games.

        Args:
            player_id: Player ID

        Returns:
            Clutch rating (higher = better in clutch situations)
        """
        late_perf = self.late_game.get_player_performance(player_id)
        if not late_perf:
            return 0.0

        # Weight factors for clutch rating
        gwg_weight = 5.0
        gtg_weight = 3.0
        points_weight = 1.0

        rating = (
            late_perf.game_winning_goals * gwg_weight
            + late_perf.game_tying_goals * gtg_weight
            + late_perf.points * points_weight
        )

        # Normalize by games played
        if late_perf.games_played > 0:
            rating /= late_perf.games_played

        return rating

    def identify_collapse_prone_team(self, team_id: int) -> bool:
        """
        Check if a team is prone to late-game collapses.

        Args:
            team_id: Team ID

        Returns:
            True if team shows collapse patterns
        """
        early_perf = self.early_game.get_team_performance(team_id)
        late_perf = self.late_game.get_team_performance(team_id)

        if not early_perf or not late_perf:
            return False

        # Check if goal differential is significantly worse in late game
        early_diff = early_perf.goals - (early_perf.expected_goals_against or 0)
        late_diff = late_perf.goals - (late_perf.expected_goals_against or 0)

        return late_diff < early_diff - 0.5  # Threshold for collapse indicator
