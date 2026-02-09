"""
Player Data Model

Pydantic models for representing player biographical and positional data.
"""

from enum import Enum

from pydantic import BaseModel


class PlayerPosition(str, Enum):
    """Player position enumeration."""

    CENTER = "C"
    LEFT_WING = "LW"
    RIGHT_WING = "RW"
    DEFENSEMAN = "D"
    GOALIE = "G"
    UNKNOWN = "U"


class Player(BaseModel):
    """Player biographical and roster data."""

    # Identification
    player_id: int
    full_name: str
    first_name: str = ""
    last_name: str = ""

    # Biographical
    birth_date: str | None = None
    birth_city: str | None = None
    birth_country: str | None = None
    height_inches: int | None = None
    weight_pounds: int | None = None

    # Position and handedness
    position: PlayerPosition = PlayerPosition.UNKNOWN
    shoots_catches: str | None = None  # "L" or "R"

    # Current team
    current_team_id: int | None = None
    current_team_abbrev: str | None = None
    jersey_number: int | None = None

    # Status
    is_active: bool = True

    class Config:
        """Pydantic configuration."""

        use_enum_values = True

    @property
    def is_goalie(self) -> bool:
        """Check if player is a goalie."""
        return self.position == PlayerPosition.GOALIE

    @property
    def is_forward(self) -> bool:
        """Check if player is a forward."""
        return self.position in {
            PlayerPosition.CENTER,
            PlayerPosition.LEFT_WING,
            PlayerPosition.RIGHT_WING,
        }

    @property
    def is_defenseman(self) -> bool:
        """Check if player is a defenseman."""
        return self.position == PlayerPosition.DEFENSEMAN
