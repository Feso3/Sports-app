"""
Line Matchup Logic

Handles line vs line matchup calculations, integrating synergy scores
from Phase 3 analytics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from simulation.models import LineMatchup, MatchupAnalysis

if TYPE_CHECKING:
    from src.analytics.synergy import SynergyAnalyzer
    from src.models.player import Player
    from src.models.team import Team, LineConfiguration


@dataclass
class MatchupStrength:
    """Strength comparison for a matchup."""

    home_strength: float = 0.5
    away_strength: float = 0.5
    home_advantage: float = 0.0

    @property
    def dominant_side(self) -> str:
        """Which side has the advantage."""
        if self.home_advantage > 0.05:
            return "home"
        elif self.home_advantage < -0.05:
            return "away"
        return "even"


class MatchupAnalyzer:
    """
    Analyzer for line-on-line matchups.

    Integrates synergy scores and individual player metrics to determine
    matchup advantages.
    """

    # Ice time distribution by line (approximate)
    LINE_ICE_TIME_SHARES = {
        1: 0.30,  # First line
        2: 0.27,  # Second line
        3: 0.23,  # Third line
        4: 0.20,  # Fourth line
    }

    DEFENSE_ICE_TIME_SHARES = {
        1: 0.40,  # Top pair
        2: 0.35,  # Second pair
        3: 0.25,  # Third pair
    }

    def __init__(
        self,
        synergy_analyzer: SynergyAnalyzer | None = None,
        home_ice_advantage: float = 0.03,
    ) -> None:
        """
        Initialize the matchup analyzer.

        Args:
            synergy_analyzer: Optional synergy analyzer from Phase 3
            home_ice_advantage: Home ice advantage factor
        """
        self.synergy_analyzer = synergy_analyzer
        self.home_ice_advantage = home_ice_advantage

    def analyze_full_matchup(
        self,
        home_team: Team,
        away_team: Team,
        players: dict[int, Player] | None = None,
    ) -> MatchupAnalysis:
        """
        Perform complete matchup analysis between two teams.

        Args:
            home_team: Home team
            away_team: Away team
            players: Optional player data dictionary

        Returns:
            Complete MatchupAnalysis
        """
        analysis = MatchupAnalysis(
            home_team_id=home_team.team_id,
            away_team_id=away_team.team_id,
        )

        # Analyze zone-by-zone advantages
        zones = ["slot", "high_slot", "left_circle", "right_circle", "point"]
        for zone in zones:
            home_off = home_team.get_zone_strength(zone, offensive=True)
            away_def = away_team.get_zone_strength(zone, offensive=False)
            away_off = away_team.get_zone_strength(zone, offensive=True)
            home_def = home_team.get_zone_strength(zone, offensive=False)

            # Positive = home advantage
            analysis.zone_advantages[zone] = (home_off - away_def) - (away_off - home_def)

        # Analyze forward line matchups
        for home_line in home_team.forward_lines:
            best_matchup = self._find_best_matchup(
                home_line, away_team.forward_lines, players
            )
            analysis.forward_line_advantages.append(best_matchup.home_advantage)

        # Analyze defense pair matchups
        for home_pair in home_team.defense_pairs:
            best_matchup = self._find_best_matchup(
                home_pair, away_team.defense_pairs, players
            )
            analysis.defense_pair_advantages.append(best_matchup.home_advantage)

        # Segment advantages
        analysis.early_game_advantage = self._calculate_segment_advantage(
            home_team, away_team, "early_game"
        )
        analysis.mid_game_advantage = self._calculate_segment_advantage(
            home_team, away_team, "mid_game"
        )
        analysis.late_game_advantage = self._calculate_segment_advantage(
            home_team, away_team, "late_game"
        )

        # Special teams
        analysis.power_play_advantage = self._calculate_pp_advantage(home_team, away_team)
        analysis.penalty_kill_advantage = self._calculate_pk_advantage(home_team, away_team)

        # Goalie comparison
        analysis.goalie_advantage = self._calculate_goalie_advantage(
            home_team, away_team, players
        )

        # Identify key mismatches
        analysis.key_mismatches = self._identify_key_mismatches(
            home_team, away_team, analysis, players
        )

        return analysis

    def calculate_line_matchup(
        self,
        home_line: LineConfiguration,
        away_line: LineConfiguration,
        players: dict[int, Player] | None = None,
    ) -> LineMatchup:
        """
        Calculate detailed metrics for a specific line matchup.

        Args:
            home_line: Home team line
            away_line: Away team line
            players: Optional player data

        Returns:
            LineMatchup with calculated values
        """
        matchup = LineMatchup(
            home_line_number=home_line.line_number,
            away_line_number=away_line.line_number,
            line_type=home_line.line_type,
        )

        # Calculate offensive strengths
        matchup.home_offensive_strength = self._calculate_line_offense(
            home_line, players
        )
        matchup.away_offensive_strength = self._calculate_line_offense(
            away_line, players
        )

        # Calculate defensive strengths
        matchup.home_defensive_strength = self._calculate_line_defense(
            home_line, players
        )
        matchup.away_defensive_strength = self._calculate_line_defense(
            away_line, players
        )

        # Get chemistry scores
        matchup.home_chemistry = self._get_line_chemistry(home_line, players)
        matchup.away_chemistry = self._get_line_chemistry(away_line, players)

        # Calculate expected goals for matchup
        # Home team attacking
        home_attack_modifier = matchup.home_offensive_strength / max(
            matchup.away_defensive_strength, 0.1
        )
        home_attack_modifier *= 1 + (matchup.home_chemistry * 0.1)

        # Away team attacking
        away_attack_modifier = matchup.away_offensive_strength / max(
            matchup.home_defensive_strength, 0.1
        )
        away_attack_modifier *= 1 + (matchup.away_chemistry * 0.1)

        # Base xG per period for a line (approximately)
        base_xg_per_period = 0.5

        matchup.home_xg = base_xg_per_period * home_attack_modifier * (1 + self.home_ice_advantage)
        matchup.away_xg = base_xg_per_period * away_attack_modifier

        return matchup

    def get_optimal_matchups(
        self,
        home_team: Team,
        away_team: Team,
        players: dict[int, Player] | None = None,
    ) -> list[LineMatchup]:
        """
        Determine optimal line matchups for the home team.

        Args:
            home_team: Home team
            away_team: Away team
            players: Optional player data

        Returns:
            List of optimal LineMatchup configurations
        """
        optimal = []

        # Match forward lines
        for home_line in home_team.forward_lines:
            best_matchup = None
            best_advantage = float("-inf")

            for away_line in away_team.forward_lines:
                matchup = self.calculate_line_matchup(home_line, away_line, players)
                advantage = matchup.home_xg - matchup.away_xg

                if advantage > best_advantage:
                    best_advantage = advantage
                    best_matchup = matchup

            if best_matchup:
                optimal.append(best_matchup)

        # Match defense pairs
        for home_pair in home_team.defense_pairs:
            best_matchup = None
            best_advantage = float("-inf")

            for away_pair in away_team.defense_pairs:
                matchup = self.calculate_line_matchup(home_pair, away_pair, players)
                advantage = matchup.home_xg - matchup.away_xg

                if advantage > best_advantage:
                    best_advantage = advantage
                    best_matchup = matchup

            if best_matchup:
                optimal.append(best_matchup)

        return optimal

    def _calculate_line_offense(
        self,
        line: LineConfiguration,
        players: dict[int, Player] | None,
    ) -> float:
        """Calculate offensive strength for a line."""
        # Base from line stats
        base = (line.expected_goals_percentage or 0.5) + (line.corsi_percentage or 0.5)
        base /= 2

        # Goals scored contribution
        if line.goals_for > 0:
            toi_hours = line.time_on_ice_seconds / 3600 if line.time_on_ice_seconds > 0 else 1
            goals_per_60 = (line.goals_for / toi_hours) if toi_hours > 0 else 0
            base += min(goals_per_60 / 10, 0.3)  # Cap contribution

        # Player xG contribution
        if players:
            for player_id in line.player_ids:
                player = players.get(player_id)
                if player:
                    xg_for = player.career_stats.expected_goals_for
                    games = max(player.career_stats.games_played, 1)
                    base += (xg_for / games) * 0.1

        # Synergy boost
        if self.synergy_analyzer:
            synergy = self.synergy_analyzer.line_synergy(line.player_ids)
            base *= 1 + (synergy * 0.05)

        return max(0.3, min(1.5, base))

    def _calculate_line_defense(
        self,
        line: LineConfiguration,
        players: dict[int, Player] | None,
    ) -> float:
        """Calculate defensive strength for a line."""
        # Base from line stats
        base = (line.expected_goals_percentage or 0.5) + (line.corsi_percentage or 0.5)
        base /= 2

        # Goals against penalty
        if line.goals_against > 0:
            toi_hours = line.time_on_ice_seconds / 3600 if line.time_on_ice_seconds > 0 else 1
            ga_per_60 = (line.goals_against / toi_hours) if toi_hours > 0 else 0
            # Lower goals against = better defense
            base += max(-ga_per_60 / 10, -0.3)

        # Player xG against contribution
        if players:
            for player_id in line.player_ids:
                player = players.get(player_id)
                if player:
                    xg_against = player.career_stats.expected_goals_against
                    games = max(player.career_stats.games_played, 1)
                    # Lower xG against = better
                    base -= (xg_against / games) * 0.05

        # Defense pairs get defensive bonus
        if line.line_type == "defense":
            base *= 1.1

        return max(0.3, min(1.5, base))

    def _get_line_chemistry(
        self,
        line: LineConfiguration,
        players: dict[int, Player] | None,
    ) -> float:
        """Get chemistry score for a line."""
        # Use stored chemistry if available
        if line.chemistry_score > 0:
            return line.chemistry_score

        # Calculate from synergy analyzer
        if self.synergy_analyzer and line.player_ids:
            return self.synergy_analyzer.line_synergy(line.player_ids)

        # Calculate from player synergy data
        if players and len(line.player_ids) >= 2:
            total_synergy = 0.0
            pairs = 0
            for i, pid1 in enumerate(line.player_ids):
                player1 = players.get(pid1)
                if not player1:
                    continue
                for pid2 in line.player_ids[i + 1:]:
                    synergy = player1.synergies.get(pid2, 0.5)
                    total_synergy += synergy
                    pairs += 1
            return total_synergy / pairs if pairs > 0 else 0.5

        return 0.5

    def _find_best_matchup(
        self,
        home_line: LineConfiguration,
        away_lines: list[LineConfiguration],
        players: dict[int, Player] | None,
    ) -> MatchupStrength:
        """Find best matchup strength for a home line."""
        best = MatchupStrength()
        best_advantage = float("-inf")

        for away_line in away_lines:
            matchup = self.calculate_line_matchup(home_line, away_line, players)
            advantage = matchup.home_xg - matchup.away_xg

            if advantage > best_advantage:
                best_advantage = advantage
                best = MatchupStrength(
                    home_strength=matchup.home_offensive_strength,
                    away_strength=matchup.away_offensive_strength,
                    home_advantage=advantage,
                )

        return best

    def _calculate_segment_advantage(
        self,
        home_team: Team,
        away_team: Team,
        segment: str,
    ) -> float:
        """Calculate home team advantage for a game segment."""
        home_diff = home_team.get_segment_goal_differential(segment)
        away_diff = away_team.get_segment_goal_differential(segment)

        # Normalize by games played
        home_games = max(home_team.current_season_stats.games_played, 1)
        away_games = max(away_team.current_season_stats.games_played, 1)

        home_normalized = home_diff / home_games
        away_normalized = away_diff / away_games

        return home_normalized - away_normalized

    def _calculate_pp_advantage(self, home_team: Team, away_team: Team) -> float:
        """Calculate power play advantage."""
        home_pp = home_team.current_season_stats.power_play_percentage or 20
        away_pk = away_team.current_season_stats.penalty_kill_percentage or 80

        # Home PP vs Away PK
        home_advantage = home_pp - (100 - away_pk)
        return home_advantage / 100  # Normalize

    def _calculate_pk_advantage(self, home_team: Team, away_team: Team) -> float:
        """Calculate penalty kill advantage."""
        home_pk = home_team.current_season_stats.penalty_kill_percentage or 80
        away_pp = away_team.current_season_stats.power_play_percentage or 20

        # Home PK vs Away PP
        home_advantage = home_pk - (100 - away_pp)
        return home_advantage / 100  # Normalize

    def _calculate_goalie_advantage(
        self,
        home_team: Team,
        away_team: Team,
        players: dict[int, Player] | None,
    ) -> float:
        """Calculate goaltending advantage."""
        home_save_pct = 0.910  # Default
        away_save_pct = 0.910

        if players:
            # Get starting goalie stats
            if home_team.starting_goalie_id:
                goalie = players.get(home_team.starting_goalie_id)
                if goalie and goalie.goalie_stats:
                    home_save_pct = goalie.goalie_stats.save_percentage or 0.910

            if away_team.starting_goalie_id:
                goalie = players.get(away_team.starting_goalie_id)
                if goalie and goalie.goalie_stats:
                    away_save_pct = goalie.goalie_stats.save_percentage or 0.910

        # Difference in save percentage (scaled)
        return (home_save_pct - away_save_pct) * 10

    def _identify_key_mismatches(
        self,
        home_team: Team,
        away_team: Team,
        analysis: MatchupAnalysis,
        players: dict[int, Player] | None,
    ) -> dict[str, float]:
        """Identify key mismatches in the matchup."""
        mismatches = {}

        # Zone mismatches
        for zone, advantage in analysis.zone_advantages.items():
            if abs(advantage) > 0.1:
                direction = "home" if advantage > 0 else "away"
                mismatches[f"{direction}_dominates_{zone}"] = abs(advantage)

        # Line mismatches
        for i, advantage in enumerate(analysis.forward_line_advantages):
            if abs(advantage) > 0.15:
                direction = "home" if advantage > 0 else "away"
                mismatches[f"{direction}_line{i+1}_advantage"] = abs(advantage)

        # Special teams mismatch
        if abs(analysis.power_play_advantage) > 0.05:
            direction = "home" if analysis.power_play_advantage > 0 else "away"
            mismatches[f"{direction}_pp_advantage"] = abs(analysis.power_play_advantage)

        # Goalie mismatch
        if abs(analysis.goalie_advantage) > 0.03:
            direction = "home" if analysis.goalie_advantage > 0 else "away"
            mismatches[f"{direction}_goalie_advantage"] = abs(analysis.goalie_advantage)

        # Late game mismatch (important for close games)
        if abs(analysis.late_game_advantage) > 0.1:
            direction = "home" if analysis.late_game_advantage > 0 else "away"
            mismatches[f"{direction}_late_game_edge"] = abs(analysis.late_game_advantage)

        return mismatches
