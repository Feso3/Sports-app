"""Player collector for NHL data collection.

Collects all active NHL players from team rosters and stores in database.
"""

import sys
from typing import Any, Callable, Optional

from loguru import logger

from src.collectors.nhl_api import NHLApiClient
from src.database import get_database
from src.database.db import Database


# All 32 NHL team abbreviations
NHL_TEAMS = [
    "ANA", "ARI", "BOS", "BUF", "CGY", "CAR", "CHI", "COL",
    "CBJ", "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL",
    "NSH", "NJD", "NYI", "NYR", "OTT", "PHI", "PIT", "SJS",
    "SEA", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WSH", "WPG"
]


class PlayerCollector:
    """Collects all NHL players from team rosters."""

    def __init__(
        self,
        db: Optional[Database] = None,
        api_client: Optional[NHLApiClient] = None,
    ):
        """Initialize player collector.

        Args:
            db: Database instance (creates new if not provided)
            api_client: NHL API client (creates new if not provided)
        """
        self.db = db or get_database()
        self.api = api_client or NHLApiClient()
        self._stop_requested = False

    def stop(self) -> None:
        """Request graceful stop of collection."""
        self._stop_requested = True
        logger.info("Stop requested, will finish current operation...")

    def _parse_player_from_roster(
        self, player_data: dict[str, Any], team_abbrev: str
    ) -> dict[str, Any]:
        """Parse player data from roster response.

        Args:
            player_data: Raw player data from roster API
            team_abbrev: Team abbreviation

        Returns:
            Parsed player dict for database insertion
        """
        return {
            "player_id": player_data.get("id"),
            "full_name": f"{player_data.get('firstName', {}).get('default', '')} {player_data.get('lastName', {}).get('default', '')}".strip(),
            "first_name": player_data.get("firstName", {}).get("default"),
            "last_name": player_data.get("lastName", {}).get("default"),
            "position": player_data.get("positionCode"),
            "shoots_catches": player_data.get("shootsCatches"),
            "height_inches": player_data.get("heightInInches"),
            "weight_lbs": player_data.get("weightInPounds"),
            "birth_date": player_data.get("birthDate"),
            "birth_city": player_data.get("birthCity", {}).get("default"),
            "birth_country": player_data.get("birthCountry"),
            "current_team_id": None,  # Will be filled from detailed profile
            "current_team_abbrev": team_abbrev,
            "jersey_number": player_data.get("sweaterNumber"),
            "is_active": True,
        }

    def _parse_player_from_landing(
        self, player_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Parse player data from player landing page response.

        Args:
            player_data: Raw player data from landing API

        Returns:
            Parsed player dict for database insertion
        """
        return {
            "player_id": player_data.get("playerId"),
            "full_name": f"{player_data.get('firstName', {}).get('default', '')} {player_data.get('lastName', {}).get('default', '')}".strip(),
            "first_name": player_data.get("firstName", {}).get("default"),
            "last_name": player_data.get("lastName", {}).get("default"),
            "position": player_data.get("position"),
            "shoots_catches": player_data.get("shootsCatches"),
            "height_inches": player_data.get("heightInInches"),
            "weight_lbs": player_data.get("weightInPounds"),
            "birth_date": player_data.get("birthDate"),
            "birth_city": player_data.get("birthCity", {}).get("default"),
            "birth_country": player_data.get("birthCountry"),
            "current_team_id": player_data.get("currentTeamId"),
            "current_team_abbrev": player_data.get("currentTeamAbbrev"),
            "jersey_number": player_data.get("sweaterNumber"),
            "is_active": player_data.get("isActive", True),
        }

    def collect_team_roster(
        self,
        team_abbrev: str,
        fetch_details: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> list[dict[str, Any]]:
        """Collect all players from a team's roster.

        Args:
            team_abbrev: Team abbreviation (e.g., 'EDM')
            fetch_details: Whether to fetch detailed player profiles
            progress_callback: Optional callback(player_name, current, total)

        Returns:
            List of player dicts
        """
        logger.info(f"Collecting roster for {team_abbrev}")
        self.db.set_collection_progress("roster", team_abbrev, "in_progress")

        try:
            roster_data = self.api.get_team_roster(team_abbrev)
            players = []

            # Roster has forwards, defensemen, goalies
            all_players = []
            for position_group in ["forwards", "defensemen", "goalies"]:
                all_players.extend(roster_data.get(position_group, []))

            total = len(all_players)
            for idx, player_raw in enumerate(all_players):
                if self._stop_requested:
                    logger.info("Stop requested, halting roster collection")
                    break

                player_id = player_raw.get("id")

                if fetch_details:
                    try:
                        landing_data = self.api.get_player_landing(player_id)
                        player = self._parse_player_from_landing(landing_data)
                    except Exception as e:
                        logger.warning(
                            f"Could not fetch details for player {player_id}: {e}"
                        )
                        player = self._parse_player_from_roster(player_raw, team_abbrev)
                else:
                    player = self._parse_player_from_roster(player_raw, team_abbrev)

                # Ensure team abbrev is set
                player["current_team_abbrev"] = team_abbrev

                # Insert into database
                self.db.insert_player(player)
                players.append(player)

                if progress_callback:
                    progress_callback(player["full_name"], idx + 1, total)

            self.db.set_collection_progress("roster", team_abbrev, "complete")
            logger.info(f"Collected {len(players)} players from {team_abbrev}")
            return players

        except Exception as e:
            self.db.set_collection_progress(
                "roster", team_abbrev, "error", error=str(e)
            )
            logger.error(f"Error collecting roster for {team_abbrev}: {e}")
            raise

    def collect_all_players(
        self,
        teams: Optional[list[str]] = None,
        fetch_details: bool = True,
        resume: bool = True,
        progress_callback: Optional[Callable[[str, str, int, int, int, int], None]] = None,
    ) -> int:
        """Collect all players from all teams.

        Args:
            teams: List of team abbreviations (defaults to all 32 teams)
            fetch_details: Whether to fetch detailed player profiles
            resume: Skip teams already marked as complete
            progress_callback: Optional callback(team, player_name, team_idx, total_teams, player_idx, total_players)

        Returns:
            Total number of players collected
        """
        if teams is None:
            teams = NHL_TEAMS.copy()

        # Filter out completed teams if resuming
        if resume:
            completed = self.db.get_collection_progress("roster", status="complete")
            completed_teams = {p["entity_id"] for p in completed}
            teams = [t for t in teams if t not in completed_teams]
            if completed_teams:
                logger.info(f"Resuming: skipping {len(completed_teams)} completed teams")

        total_players = 0
        total_teams = len(teams)

        for team_idx, team_abbrev in enumerate(teams):
            if self._stop_requested:
                logger.info("Stop requested, halting collection")
                break

            def team_progress(name: str, p_idx: int, p_total: int) -> None:
                if progress_callback:
                    progress_callback(
                        team_abbrev, name, team_idx + 1, total_teams, p_idx, p_total
                    )

            try:
                players = self.collect_team_roster(
                    team_abbrev,
                    fetch_details=fetch_details,
                    progress_callback=team_progress,
                )
                total_players += len(players)
            except Exception as e:
                logger.error(f"Failed to collect {team_abbrev}: {e}")
                # Continue with next team

        return total_players

    def get_collection_status(self) -> dict[str, Any]:
        """Get current collection status.

        Returns:
            Status summary with counts and pending teams
        """
        progress = self.db.get_collection_progress("roster")

        complete = [p for p in progress if p["status"] == "complete"]
        in_progress = [p for p in progress if p["status"] == "in_progress"]
        errors = [p for p in progress if p["status"] == "error"]
        pending = [t for t in NHL_TEAMS if t not in {p["entity_id"] for p in progress}]

        return {
            "total_teams": len(NHL_TEAMS),
            "complete": len(complete),
            "in_progress": len(in_progress),
            "errors": len(errors),
            "pending": len(pending),
            "complete_teams": [p["entity_id"] for p in complete],
            "error_teams": [(p["entity_id"], p["last_error"]) for p in errors],
            "pending_teams": pending,
            "total_players": self.db.get_player_count(active_only=True),
        }


def print_progress_bar(
    current: int, total: int, prefix: str = "", suffix: str = "", length: int = 30
) -> None:
    """Print a progress bar to stdout."""
    if total == 0:
        return
    percent = current / total
    filled = int(length * percent)
    bar = "█" * filled + "░" * (length - filled)
    sys.stdout.write(f"\r{prefix} [{bar}] {current}/{total} {suffix}")
    sys.stdout.flush()


def collect_players_with_progress(
    db: Optional[Database] = None,
    resume: bool = True,
    fetch_details: bool = True,
) -> int:
    """Collect all players with console progress display.

    Args:
        db: Database instance
        resume: Whether to resume from previous collection
        fetch_details: Whether to fetch detailed player profiles

    Returns:
        Total players collected
    """
    collector = PlayerCollector(db=db)

    def progress(
        team: str,
        player: str,
        team_idx: int,
        total_teams: int,
        player_idx: int,
        total_players: int,
    ) -> None:
        print_progress_bar(
            team_idx,
            total_teams,
            prefix=f"Teams",
            suffix=f"| {team}: {player[:20]:<20}",
        )

    print("Collecting all NHL players...")
    print()

    total = collector.collect_all_players(
        fetch_details=fetch_details,
        resume=resume,
        progress_callback=progress,
    )

    print()  # New line after progress bar
    print()

    status = collector.get_collection_status()
    print(f"Collection complete!")
    print(f"  Teams: {status['complete']}/{status['total_teams']}")
    print(f"  Players: {status['total_players']}")

    if status["errors"]:
        print(f"  Errors: {len(status['errors'])}")
        for team, error in status["error_teams"]:
            print(f"    - {team}: {error[:50]}")

    return total
