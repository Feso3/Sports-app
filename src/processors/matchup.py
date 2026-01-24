"""
Matchup Processor

Tracks and analyzes historical matchup data between:
- Player vs Player
- Player vs Team
- Team vs Team
- Line combinations vs opposing lines
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class MatchupEvent:
    """A single event in a matchup history."""

    game_id: str
    date: str
    event_type: str  # "goal", "shot", "assist", "hit", "block", etc.
    period: int
    game_seconds: int
    for_player_id: int | None = None
    against_player_id: int | None = None
    for_team_id: int | None = None
    against_team_id: int | None = None
    x_coord: float | None = None
    y_coord: float | None = None
    zone: str | None = None


@dataclass
class MatchupStats:
    """Statistics for a matchup relationship."""

    games: int = 0
    goals_for: int = 0
    goals_against: int = 0
    assists_for: int = 0
    shots_for: int = 0
    shots_against: int = 0
    hits_for: int = 0
    hits_against: int = 0
    blocks_for: int = 0
    blocks_against: int = 0
    takeaways: int = 0
    giveaways: int = 0
    faceoff_wins: int = 0
    faceoff_losses: int = 0
    xg_for: float = 0.0
    xg_against: float = 0.0
    toi_seconds: int = 0  # Time on ice together/against

    # Zone-specific stats
    slot_shots_for: int = 0
    slot_shots_against: int = 0
    slot_goals_for: int = 0
    slot_goals_against: int = 0

    @property
    def goal_differential(self) -> int:
        """Calculate goal differential."""
        return self.goals_for - self.goals_against

    @property
    def shot_differential(self) -> int:
        """Calculate shot differential."""
        return self.shots_for - self.shots_against

    @property
    def xg_differential(self) -> float:
        """Calculate expected goals differential."""
        return self.xg_for - self.xg_against

    @property
    def goals_for_percentage(self) -> float:
        """Calculate goals for percentage."""
        total = self.goals_for + self.goals_against
        return self.goals_for / total if total > 0 else 0.5

    @property
    def shots_for_percentage(self) -> float:
        """Calculate shots for percentage."""
        total = self.shots_for + self.shots_against
        return self.shots_for / total if total > 0 else 0.5

    @property
    def xg_percentage(self) -> float:
        """Calculate xG percentage."""
        total = self.xg_for + self.xg_against
        return self.xg_for / total if total > 0 else 0.5

    @property
    def faceoff_percentage(self) -> float:
        """Calculate faceoff win percentage."""
        total = self.faceoff_wins + self.faceoff_losses
        return self.faceoff_wins / total if total > 0 else 0.5

    def merge(self, other: "MatchupStats") -> "MatchupStats":
        """Merge another matchup stats into this one."""
        return MatchupStats(
            games=self.games + other.games,
            goals_for=self.goals_for + other.goals_for,
            goals_against=self.goals_against + other.goals_against,
            assists_for=self.assists_for + other.assists_for,
            shots_for=self.shots_for + other.shots_for,
            shots_against=self.shots_against + other.shots_against,
            hits_for=self.hits_for + other.hits_for,
            hits_against=self.hits_against + other.hits_against,
            blocks_for=self.blocks_for + other.blocks_for,
            blocks_against=self.blocks_against + other.blocks_against,
            takeaways=self.takeaways + other.takeaways,
            giveaways=self.giveaways + other.giveaways,
            faceoff_wins=self.faceoff_wins + other.faceoff_wins,
            faceoff_losses=self.faceoff_losses + other.faceoff_losses,
            xg_for=self.xg_for + other.xg_for,
            xg_against=self.xg_against + other.xg_against,
            toi_seconds=self.toi_seconds + other.toi_seconds,
            slot_shots_for=self.slot_shots_for + other.slot_shots_for,
            slot_shots_against=self.slot_shots_against + other.slot_shots_against,
            slot_goals_for=self.slot_goals_for + other.slot_goals_for,
            slot_goals_against=self.slot_goals_against + other.slot_goals_against,
        )


@dataclass
class PlayerMatchup:
    """Matchup record between two players."""

    player_id: int
    player_name: str
    opponent_id: int
    opponent_name: str
    stats: MatchupStats = field(default_factory=MatchupStats)
    events: list[MatchupEvent] = field(default_factory=list)
    first_game_date: str | None = None
    last_game_date: str | None = None

    @property
    def dominance_score(self) -> float:
        """
        Calculate overall dominance score.

        Positive = player dominates opponent
        Negative = opponent dominates player
        """
        if self.stats.games == 0:
            return 0.0

        # Weight different metrics
        gf_weight = 3.0
        sf_weight = 1.0
        xg_weight = 2.0

        gf_contribution = (self.stats.goals_for_percentage - 0.5) * gf_weight
        sf_contribution = (self.stats.shots_for_percentage - 0.5) * sf_weight
        xg_contribution = (self.stats.xg_percentage - 0.5) * xg_weight

        return gf_contribution + sf_contribution + xg_contribution


@dataclass
class TeamMatchup:
    """Matchup record between two teams."""

    team_id: int
    team_abbrev: str
    opponent_id: int
    opponent_abbrev: str
    stats: MatchupStats = field(default_factory=MatchupStats)
    events: list[MatchupEvent] = field(default_factory=list)
    wins: int = 0
    losses: int = 0
    overtime_losses: int = 0
    first_game_date: str | None = None
    last_game_date: str | None = None

    @property
    def win_percentage(self) -> float:
        """Calculate win percentage."""
        total = self.wins + self.losses + self.overtime_losses
        return self.wins / total if total > 0 else 0.5

    @property
    def points_percentage(self) -> float:
        """Calculate points percentage (wins = 2pts, OTL = 1pt)."""
        total_games = self.wins + self.losses + self.overtime_losses
        if total_games == 0:
            return 0.5
        points = self.wins * 2 + self.overtime_losses
        max_points = total_games * 2
        return points / max_points


@dataclass
class PlayerVsTeamMatchup:
    """Matchup record for a player vs a team."""

    player_id: int
    player_name: str
    team_id: int
    team_abbrev: str
    stats: MatchupStats = field(default_factory=MatchupStats)
    events: list[MatchupEvent] = field(default_factory=list)
    first_game_date: str | None = None
    last_game_date: str | None = None


class MatchupProcessor:
    """
    Processor for tracking and analyzing matchup history.

    Tracks:
    - Player vs Player matchups
    - Player vs Team matchups
    - Team vs Team matchups
    """

    def __init__(self) -> None:
        """Initialize the matchup processor."""
        # Player vs Player: {(player_id, opponent_id): PlayerMatchup}
        self.player_matchups: dict[tuple[int, int], PlayerMatchup] = {}

        # Player vs Team: {(player_id, team_id): PlayerVsTeamMatchup}
        self.player_vs_team: dict[tuple[int, int], PlayerVsTeamMatchup] = {}

        # Team vs Team: {(team_id, opponent_id): TeamMatchup}
        self.team_matchups: dict[tuple[int, int], TeamMatchup] = {}

        # Track processed games
        self.processed_games: set[str] = set()

        # Player/team name cache
        self.player_names: dict[int, str] = {}
        self.team_abbrevs: dict[int, str] = {}

    def register_player(self, player_id: int, name: str) -> None:
        """Register a player name for later reference."""
        self.player_names[player_id] = name

    def register_team(self, team_id: int, abbrev: str) -> None:
        """Register a team abbreviation for later reference."""
        self.team_abbrevs[team_id] = abbrev

    def _get_player_name(self, player_id: int) -> str:
        """Get player name from cache."""
        return self.player_names.get(player_id, f"Player {player_id}")

    def _get_team_abbrev(self, team_id: int) -> str:
        """Get team abbreviation from cache."""
        return self.team_abbrevs.get(team_id, f"Team {team_id}")

    def _ensure_player_matchup(
        self, player_id: int, opponent_id: int
    ) -> PlayerMatchup:
        """Ensure player matchup exists."""
        key = (player_id, opponent_id)
        if key not in self.player_matchups:
            self.player_matchups[key] = PlayerMatchup(
                player_id=player_id,
                player_name=self._get_player_name(player_id),
                opponent_id=opponent_id,
                opponent_name=self._get_player_name(opponent_id),
            )
        return self.player_matchups[key]

    def _ensure_player_vs_team(
        self, player_id: int, team_id: int
    ) -> PlayerVsTeamMatchup:
        """Ensure player vs team matchup exists."""
        key = (player_id, team_id)
        if key not in self.player_vs_team:
            self.player_vs_team[key] = PlayerVsTeamMatchup(
                player_id=player_id,
                player_name=self._get_player_name(player_id),
                team_id=team_id,
                team_abbrev=self._get_team_abbrev(team_id),
            )
        return self.player_vs_team[key]

    def _ensure_team_matchup(self, team_id: int, opponent_id: int) -> TeamMatchup:
        """Ensure team matchup exists."""
        key = (team_id, opponent_id)
        if key not in self.team_matchups:
            self.team_matchups[key] = TeamMatchup(
                team_id=team_id,
                team_abbrev=self._get_team_abbrev(team_id),
                opponent_id=opponent_id,
                opponent_abbrev=self._get_team_abbrev(opponent_id),
            )
        return self.team_matchups[key]

    def process_event(
        self,
        game_id: str,
        date: str,
        event_type: str,
        period: int,
        game_seconds: int,
        for_team_id: int,
        against_team_id: int,
        for_player_id: int | None = None,
        against_player_id: int | None = None,
        x_coord: float | None = None,
        y_coord: float | None = None,
        zone: str | None = None,
        xg: float = 0.0,
    ) -> None:
        """
        Process a game event and update matchup records.

        Args:
            game_id: Game identifier
            date: Game date (YYYY-MM-DD)
            event_type: Type of event
            period: Period number
            game_seconds: Time in seconds
            for_team_id: Team that produced the event
            against_team_id: Opposing team
            for_player_id: Player who produced the event
            against_player_id: Opposing player (if applicable)
            x_coord: X coordinate
            y_coord: Y coordinate
            zone: Ice zone
            xg: Expected goals value
        """
        # Create event record
        event = MatchupEvent(
            game_id=game_id,
            date=date,
            event_type=event_type,
            period=period,
            game_seconds=game_seconds,
            for_player_id=for_player_id,
            against_player_id=against_player_id,
            for_team_id=for_team_id,
            against_team_id=against_team_id,
            x_coord=x_coord,
            y_coord=y_coord,
            zone=zone,
        )

        is_slot = zone in ["slot", "inner_slot", "crease"]

        # Update team vs team matchup
        team_matchup = self._ensure_team_matchup(for_team_id, against_team_id)
        self._update_matchup_stats(
            team_matchup.stats, event_type, True, xg, is_slot
        )
        team_matchup.events.append(event)
        self._update_date_range(team_matchup, date)

        # Also update reverse matchup
        opp_matchup = self._ensure_team_matchup(against_team_id, for_team_id)
        self._update_matchup_stats(
            opp_matchup.stats, event_type, False, xg, is_slot
        )

        # Update player vs team matchup
        if for_player_id is not None:
            pvt_matchup = self._ensure_player_vs_team(for_player_id, against_team_id)
            self._update_matchup_stats(
                pvt_matchup.stats, event_type, True, xg, is_slot
            )
            pvt_matchup.events.append(event)
            self._update_date_range(pvt_matchup, date)

        # Update player vs player matchup
        if for_player_id is not None and against_player_id is not None:
            player_matchup = self._ensure_player_matchup(
                for_player_id, against_player_id
            )
            self._update_matchup_stats(
                player_matchup.stats, event_type, True, xg, is_slot
            )
            player_matchup.events.append(event)
            self._update_date_range(player_matchup, date)

            # Also update reverse matchup
            opp_player_matchup = self._ensure_player_matchup(
                against_player_id, for_player_id
            )
            self._update_matchup_stats(
                opp_player_matchup.stats, event_type, False, xg, is_slot
            )

    def _update_matchup_stats(
        self,
        stats: MatchupStats,
        event_type: str,
        is_for: bool,
        xg: float,
        is_slot: bool,
    ) -> None:
        """Update matchup stats based on event type."""
        event_type = event_type.lower()

        if is_for:
            if event_type == "goal":
                stats.goals_for += 1
                stats.shots_for += 1
                stats.xg_for += xg
                if is_slot:
                    stats.slot_goals_for += 1
                    stats.slot_shots_for += 1
            elif event_type in ["shot", "shot-on-goal"]:
                stats.shots_for += 1
                stats.xg_for += xg
                if is_slot:
                    stats.slot_shots_for += 1
            elif event_type == "assist":
                stats.assists_for += 1
            elif event_type == "hit":
                stats.hits_for += 1
            elif event_type in ["block", "blocked-shot"]:
                stats.blocks_for += 1
            elif event_type == "takeaway":
                stats.takeaways += 1
            elif event_type == "giveaway":
                stats.giveaways += 1
            elif event_type == "faceoff-win":
                stats.faceoff_wins += 1
        else:
            if event_type == "goal":
                stats.goals_against += 1
                stats.shots_against += 1
                stats.xg_against += xg
                if is_slot:
                    stats.slot_goals_against += 1
                    stats.slot_shots_against += 1
            elif event_type in ["shot", "shot-on-goal"]:
                stats.shots_against += 1
                stats.xg_against += xg
                if is_slot:
                    stats.slot_shots_against += 1
            elif event_type == "hit":
                stats.hits_against += 1
            elif event_type in ["block", "blocked-shot"]:
                stats.blocks_against += 1
            elif event_type == "faceoff-win":
                stats.faceoff_losses += 1

    def _update_date_range(
        self,
        matchup: PlayerMatchup | TeamMatchup | PlayerVsTeamMatchup,
        date: str,
    ) -> None:
        """Update first/last game dates for a matchup."""
        if matchup.first_game_date is None or date < matchup.first_game_date:
            matchup.first_game_date = date
        if matchup.last_game_date is None or date > matchup.last_game_date:
            matchup.last_game_date = date

    def record_game_result(
        self,
        game_id: str,
        home_team_id: int,
        away_team_id: int,
        home_score: int,
        away_score: int,
        is_overtime: bool = False,
    ) -> None:
        """
        Record a game result for team matchups.

        Args:
            game_id: Game identifier
            home_team_id: Home team ID
            away_team_id: Away team ID
            home_score: Home team final score
            away_score: Away team final score
            is_overtime: Whether game went to overtime
        """
        if game_id in self.processed_games:
            return

        home_matchup = self._ensure_team_matchup(home_team_id, away_team_id)
        away_matchup = self._ensure_team_matchup(away_team_id, home_team_id)

        home_matchup.stats.games += 1
        away_matchup.stats.games += 1

        if home_score > away_score:
            home_matchup.wins += 1
            if is_overtime:
                away_matchup.overtime_losses += 1
            else:
                away_matchup.losses += 1
        else:
            away_matchup.wins += 1
            if is_overtime:
                home_matchup.overtime_losses += 1
            else:
                home_matchup.losses += 1

        self.processed_games.add(game_id)

    def get_player_matchup(
        self, player_id: int, opponent_id: int
    ) -> PlayerMatchup | None:
        """Get matchup record between two players."""
        return self.player_matchups.get((player_id, opponent_id))

    def get_player_vs_team(
        self, player_id: int, team_id: int
    ) -> PlayerVsTeamMatchup | None:
        """Get matchup record for player vs team."""
        return self.player_vs_team.get((player_id, team_id))

    def get_team_matchup(self, team_id: int, opponent_id: int) -> TeamMatchup | None:
        """Get matchup record between two teams."""
        return self.team_matchups.get((team_id, opponent_id))

    def get_player_best_matchups(
        self, player_id: int, min_games: int = 5, limit: int = 10
    ) -> list[PlayerMatchup]:
        """
        Get player's best matchups (opponents they dominate).

        Args:
            player_id: Player ID
            min_games: Minimum games for consideration
            limit: Maximum results

        Returns:
            List of matchups sorted by dominance score
        """
        matchups = [
            m for (pid, _), m in self.player_matchups.items()
            if pid == player_id and m.stats.games >= min_games
        ]
        return sorted(matchups, key=lambda m: m.dominance_score, reverse=True)[:limit]

    def get_player_worst_matchups(
        self, player_id: int, min_games: int = 5, limit: int = 10
    ) -> list[PlayerMatchup]:
        """
        Get player's worst matchups (opponents who dominate them).

        Args:
            player_id: Player ID
            min_games: Minimum games for consideration
            limit: Maximum results

        Returns:
            List of matchups sorted by dominance score (ascending)
        """
        matchups = [
            m for (pid, _), m in self.player_matchups.items()
            if pid == player_id and m.stats.games >= min_games
        ]
        return sorted(matchups, key=lambda m: m.dominance_score)[:limit]

    def get_team_historical_record(
        self, team_id: int, opponent_id: int, seasons: int | None = None
    ) -> dict[str, Any]:
        """
        Get comprehensive historical record between teams.

        Args:
            team_id: Team ID
            opponent_id: Opponent team ID
            seasons: Number of recent seasons to consider (None = all)

        Returns:
            Dictionary with historical matchup data
        """
        matchup = self.get_team_matchup(team_id, opponent_id)
        if not matchup:
            return {"error": "No matchup data found"}

        return {
            "team": self._get_team_abbrev(team_id),
            "opponent": self._get_team_abbrev(opponent_id),
            "games": matchup.stats.games,
            "wins": matchup.wins,
            "losses": matchup.losses,
            "overtime_losses": matchup.overtime_losses,
            "win_percentage": matchup.win_percentage,
            "goals_for": matchup.stats.goals_for,
            "goals_against": matchup.stats.goals_against,
            "goal_differential": matchup.stats.goal_differential,
            "xg_for": matchup.stats.xg_for,
            "xg_against": matchup.stats.xg_against,
            "xg_differential": matchup.stats.xg_differential,
            "first_game": matchup.first_game_date,
            "last_game": matchup.last_game_date,
        }

    def calculate_matchup_advantage(
        self,
        team_1_id: int,
        team_2_id: int,
    ) -> dict[str, float]:
        """
        Calculate overall matchup advantage between teams.

        Args:
            team_1_id: First team ID
            team_2_id: Second team ID

        Returns:
            Dictionary with advantage metrics
        """
        t1_matchup = self.get_team_matchup(team_1_id, team_2_id)
        t2_matchup = self.get_team_matchup(team_2_id, team_1_id)

        if not t1_matchup or not t2_matchup:
            return {"advantage": 0.0, "confidence": 0.0}

        # Weight different factors
        win_pct_weight = 0.4
        gf_pct_weight = 0.3
        xg_pct_weight = 0.3

        t1_score = (
            t1_matchup.win_percentage * win_pct_weight
            + t1_matchup.stats.goals_for_percentage * gf_pct_weight
            + t1_matchup.stats.xg_percentage * xg_pct_weight
        )

        t2_score = (
            t2_matchup.win_percentage * win_pct_weight
            + t2_matchup.stats.goals_for_percentage * gf_pct_weight
            + t2_matchup.stats.xg_percentage * xg_pct_weight
        )

        advantage = t1_score - t2_score

        # Confidence based on sample size
        games = t1_matchup.stats.games
        confidence = min(1.0, games / 20)  # Max confidence at 20+ games

        return {
            "advantage": advantage,
            "team_1_score": t1_score,
            "team_2_score": t2_score,
            "confidence": confidence,
            "games": games,
        }

    def save_matchups(self, output_dir: str | Path) -> None:
        """Save matchup data to files."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save team matchups
        team_data = {}
        for (team_id, opp_id), matchup in self.team_matchups.items():
            key = f"{team_id}_vs_{opp_id}"
            team_data[key] = {
                "team_id": matchup.team_id,
                "team_abbrev": matchup.team_abbrev,
                "opponent_id": matchup.opponent_id,
                "opponent_abbrev": matchup.opponent_abbrev,
                "wins": matchup.wins,
                "losses": matchup.losses,
                "overtime_losses": matchup.overtime_losses,
                "stats": {
                    "games": matchup.stats.games,
                    "goals_for": matchup.stats.goals_for,
                    "goals_against": matchup.stats.goals_against,
                    "shots_for": matchup.stats.shots_for,
                    "shots_against": matchup.stats.shots_against,
                    "xg_for": matchup.stats.xg_for,
                    "xg_against": matchup.stats.xg_against,
                },
            }

        with open(output_dir / "team_matchups.json", "w") as f:
            json.dump(team_data, f, indent=2)

        logger.info(f"Saved matchup data to {output_dir}")

    def load_matchups(self, input_dir: str | Path) -> None:
        """Load matchup data from files."""
        input_dir = Path(input_dir)

        team_file = input_dir / "team_matchups.json"
        if team_file.exists():
            with open(team_file) as f:
                team_data = json.load(f)

            for _, matchup_dict in team_data.items():
                key = (matchup_dict["team_id"], matchup_dict["opponent_id"])
                stats = matchup_dict.get("stats", {})

                self.team_matchups[key] = TeamMatchup(
                    team_id=matchup_dict["team_id"],
                    team_abbrev=matchup_dict["team_abbrev"],
                    opponent_id=matchup_dict["opponent_id"],
                    opponent_abbrev=matchup_dict["opponent_abbrev"],
                    wins=matchup_dict.get("wins", 0),
                    losses=matchup_dict.get("losses", 0),
                    overtime_losses=matchup_dict.get("overtime_losses", 0),
                    stats=MatchupStats(
                        games=stats.get("games", 0),
                        goals_for=stats.get("goals_for", 0),
                        goals_against=stats.get("goals_against", 0),
                        shots_for=stats.get("shots_for", 0),
                        shots_against=stats.get("shots_against", 0),
                        xg_for=stats.get("xg_for", 0.0),
                        xg_against=stats.get("xg_against", 0.0),
                    ),
                )

            logger.info(f"Loaded {len(self.team_matchups)} team matchups")

    def reset(self) -> None:
        """Reset all matchup data."""
        self.player_matchups.clear()
        self.player_vs_team.clear()
        self.team_matchups.clear()
        self.processed_games.clear()
