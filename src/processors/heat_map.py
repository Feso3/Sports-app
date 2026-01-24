"""
Heat Map Processor

Generates spatial heat maps from shot and event data for visualization
and analysis of player and team performance patterns.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger


@dataclass
class HeatMapCell:
    """Represents a single cell in a heat map grid."""

    row: int
    col: int
    shots: int = 0
    goals: int = 0
    expected_goals: float = 0.0
    blocked_shots: int = 0
    missed_shots: int = 0

    @property
    def total_attempts(self) -> int:
        """Total shot attempts including blocks and misses."""
        return self.shots + self.blocked_shots + self.missed_shots

    @property
    def shooting_percentage(self) -> float:
        """Calculate shooting percentage."""
        return self.goals / self.shots if self.shots > 0 else 0.0

    @property
    def conversion_rate(self) -> float:
        """Calculate goal rate from all attempts."""
        return self.goals / self.total_attempts if self.total_attempts > 0 else 0.0


@dataclass
class HeatMapData:
    """Container for heat map data."""

    entity_id: int  # Player ID or Team ID
    entity_type: str  # "player" or "team"
    entity_name: str
    map_type: str  # "offensive", "defensive", "shooting_pct", "xg"
    grid_width: int
    grid_height: int
    cells: list[list[HeatMapCell]] = field(default_factory=list)

    # Metadata
    games_included: int = 0
    total_shots: int = 0
    total_goals: int = 0
    date_range_start: str | None = None
    date_range_end: str | None = None

    def __post_init__(self) -> None:
        """Initialize cells grid if empty."""
        if not self.cells:
            self.cells = [
                [HeatMapCell(row=r, col=c) for c in range(self.grid_width)]
                for r in range(self.grid_height)
            ]

    def to_numpy(self, metric: str = "shots") -> np.ndarray:
        """
        Convert heat map to numpy array.

        Args:
            metric: Which metric to extract ("shots", "goals", "xg", "shooting_pct")

        Returns:
            2D numpy array
        """
        grid = np.zeros((self.grid_height, self.grid_width))

        for row in range(self.grid_height):
            for col in range(self.grid_width):
                cell = self.cells[row][col]
                if metric == "shots":
                    grid[row, col] = cell.shots
                elif metric == "goals":
                    grid[row, col] = cell.goals
                elif metric == "xg":
                    grid[row, col] = cell.expected_goals
                elif metric == "shooting_pct":
                    grid[row, col] = cell.shooting_percentage
                elif metric == "attempts":
                    grid[row, col] = cell.total_attempts

        return grid

    def normalize(self) -> np.ndarray:
        """Return normalized shot distribution (0-1 scale)."""
        grid = self.to_numpy("shots")
        total = grid.sum()
        return grid / total if total > 0 else grid

    def get_hot_zones(self, threshold: float = 0.1) -> list[tuple[int, int, float]]:
        """
        Identify hot zones (high concentration areas).

        Args:
            threshold: Minimum normalized value to be considered hot

        Returns:
            List of (row, col, intensity) tuples
        """
        normalized = self.normalize()
        hot_zones = []

        for row in range(self.grid_height):
            for col in range(self.grid_width):
                if normalized[row, col] >= threshold:
                    hot_zones.append((row, col, normalized[row, col]))

        return sorted(hot_zones, key=lambda x: x[2], reverse=True)


class HeatMapProcessor:
    """
    Processor for generating heat maps from shot and event data.

    Creates spatial visualizations for:
    - Player shot distributions
    - Team offensive patterns
    - Defensive vulnerability maps
    - Expected goals surfaces
    """

    # NHL rink dimensions (feet)
    RINK_LENGTH = 200
    RINK_WIDTH = 85
    OFFENSIVE_ZONE_START = 75  # Offensive zone starts at 75 feet from center

    def __init__(
        self,
        grid_width: int = 50,
        grid_height: int = 42,
        smoothing_radius: int = 2,
    ):
        """
        Initialize the heat map processor.

        Args:
            grid_width: Number of columns in heat map grid
            grid_height: Number of rows in heat map grid
            smoothing_radius: Radius for Gaussian smoothing
        """
        self.grid_width = grid_width
        self.grid_height = grid_height
        self.smoothing_radius = smoothing_radius

        # Storage for heat maps
        self.player_offensive_maps: dict[int, HeatMapData] = {}
        self.player_defensive_maps: dict[int, HeatMapData] = {}
        self.team_offensive_maps: dict[int, HeatMapData] = {}
        self.team_defensive_maps: dict[int, HeatMapData] = {}

        # Expected goals model parameters (simplified)
        self._xg_base_rates = self._load_xg_rates()

    def _load_xg_rates(self) -> np.ndarray:
        """Load or generate base expected goals rates by location."""
        # Simplified xG model based on distance and angle
        xg_grid = np.zeros((self.grid_height, self.grid_width))

        goal_x = self.grid_width - 1  # Goal at right edge
        goal_y = self.grid_height // 2  # Goal at center

        for row in range(self.grid_height):
            for col in range(self.grid_width):
                # Calculate distance to goal
                dx = goal_x - col
                dy = goal_y - row
                distance = np.sqrt(dx**2 + dy**2)

                # Calculate angle to goal
                angle = np.arctan2(abs(dy), dx) if dx > 0 else np.pi / 2

                # Base xG decreases with distance and angle
                if distance < 5:  # Very close to goal
                    base_xg = 0.30
                elif distance < 10:  # Slot area
                    base_xg = 0.15
                elif distance < 20:  # Medium range
                    base_xg = 0.08
                else:  # Long range
                    base_xg = 0.03

                # Angle penalty
                angle_factor = max(0.3, 1 - angle / (np.pi / 2))
                xg_grid[row, col] = base_xg * angle_factor

        return xg_grid

    def coords_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """
        Convert rink coordinates to grid indices.

        NHL coordinates: x from -100 to 100, y from -42.5 to 42.5

        Args:
            x: X coordinate (center ice = 0)
            y: Y coordinate (center ice = 0)

        Returns:
            (row, col) grid indices
        """
        # Normalize to offensive zone (positive x direction)
        x = abs(x)

        # Map to grid
        col = int((x / 100) * self.grid_width)
        row = int(((y + 42.5) / 85) * self.grid_height)

        # Clamp to valid range
        col = max(0, min(col, self.grid_width - 1))
        row = max(0, min(row, self.grid_height - 1))

        return row, col

    def grid_to_coords(self, row: int, col: int) -> tuple[float, float]:
        """
        Convert grid indices back to rink coordinates.

        Args:
            row: Grid row index
            col: Grid column index

        Returns:
            (x, y) rink coordinates
        """
        x = (col / self.grid_width) * 100
        y = (row / self.grid_height) * 85 - 42.5
        return x, y

    def process_shot(
        self,
        x: float | None,
        y: float | None,
        is_goal: bool,
        is_blocked: bool = False,
        is_missed: bool = False,
        shooter_id: int | None = None,
        shooter_name: str = "",
        team_id: int | None = None,
        team_name: str = "",
        opponent_id: int | None = None,
        goalie_id: int | None = None,
    ) -> None:
        """
        Process a shot event and update heat maps.

        Args:
            x: X coordinate
            y: Y coordinate
            is_goal: Whether shot was a goal
            is_blocked: Whether shot was blocked
            is_missed: Whether shot missed the net
            shooter_id: Player ID of shooter
            shooter_name: Name of shooter
            team_id: Team ID of shooting team
            team_name: Name of shooting team
            opponent_id: Team ID of defending team
            goalie_id: Player ID of goalie
        """
        if x is None or y is None:
            return

        row, col = self.coords_to_grid(x, y)
        xg = self._xg_base_rates[row, col]

        # Update shooter's offensive heat map
        if shooter_id is not None:
            self._update_player_offensive(
                shooter_id, shooter_name, row, col, is_goal, is_blocked, is_missed, xg
            )

        # Update team offensive heat map
        if team_id is not None:
            self._update_team_offensive(
                team_id, team_name, row, col, is_goal, is_blocked, is_missed, xg
            )

        # Update opponent defensive heat map (shots allowed)
        if opponent_id is not None:
            self._update_team_defensive(
                opponent_id, row, col, is_goal, is_blocked, is_missed, xg
            )

        # Update goalie defensive heat map
        if goalie_id is not None:
            self._update_player_defensive(
                goalie_id, "", row, col, is_goal, is_blocked, is_missed, xg
            )

    def _ensure_player_offensive_map(
        self, player_id: int, player_name: str
    ) -> HeatMapData:
        """Ensure player offensive heat map exists."""
        if player_id not in self.player_offensive_maps:
            self.player_offensive_maps[player_id] = HeatMapData(
                entity_id=player_id,
                entity_type="player",
                entity_name=player_name,
                map_type="offensive",
                grid_width=self.grid_width,
                grid_height=self.grid_height,
            )
        return self.player_offensive_maps[player_id]

    def _ensure_player_defensive_map(
        self, player_id: int, player_name: str
    ) -> HeatMapData:
        """Ensure player defensive heat map exists (for goalies)."""
        if player_id not in self.player_defensive_maps:
            self.player_defensive_maps[player_id] = HeatMapData(
                entity_id=player_id,
                entity_type="player",
                entity_name=player_name,
                map_type="defensive",
                grid_width=self.grid_width,
                grid_height=self.grid_height,
            )
        return self.player_defensive_maps[player_id]

    def _ensure_team_offensive_map(
        self, team_id: int, team_name: str
    ) -> HeatMapData:
        """Ensure team offensive heat map exists."""
        if team_id not in self.team_offensive_maps:
            self.team_offensive_maps[team_id] = HeatMapData(
                entity_id=team_id,
                entity_type="team",
                entity_name=team_name,
                map_type="offensive",
                grid_width=self.grid_width,
                grid_height=self.grid_height,
            )
        return self.team_offensive_maps[team_id]

    def _ensure_team_defensive_map(self, team_id: int) -> HeatMapData:
        """Ensure team defensive heat map exists."""
        if team_id not in self.team_defensive_maps:
            self.team_defensive_maps[team_id] = HeatMapData(
                entity_id=team_id,
                entity_type="team",
                entity_name="",
                map_type="defensive",
                grid_width=self.grid_width,
                grid_height=self.grid_height,
            )
        return self.team_defensive_maps[team_id]

    def _update_player_offensive(
        self,
        player_id: int,
        player_name: str,
        row: int,
        col: int,
        is_goal: bool,
        is_blocked: bool,
        is_missed: bool,
        xg: float,
    ) -> None:
        """Update player offensive heat map."""
        heat_map = self._ensure_player_offensive_map(player_id, player_name)
        cell = heat_map.cells[row][col]

        if is_blocked:
            cell.blocked_shots += 1
        elif is_missed:
            cell.missed_shots += 1
        else:
            cell.shots += 1
            cell.expected_goals += xg
            heat_map.total_shots += 1
            if is_goal:
                cell.goals += 1
                heat_map.total_goals += 1

    def _update_player_defensive(
        self,
        player_id: int,
        player_name: str,
        row: int,
        col: int,
        is_goal: bool,
        is_blocked: bool,
        is_missed: bool,
        xg: float,
    ) -> None:
        """Update player defensive heat map (for goalies)."""
        heat_map = self._ensure_player_defensive_map(player_id, player_name)
        cell = heat_map.cells[row][col]

        if not is_blocked and not is_missed:
            cell.shots += 1
            cell.expected_goals += xg
            heat_map.total_shots += 1
            if is_goal:
                cell.goals += 1
                heat_map.total_goals += 1

    def _update_team_offensive(
        self,
        team_id: int,
        team_name: str,
        row: int,
        col: int,
        is_goal: bool,
        is_blocked: bool,
        is_missed: bool,
        xg: float,
    ) -> None:
        """Update team offensive heat map."""
        heat_map = self._ensure_team_offensive_map(team_id, team_name)
        cell = heat_map.cells[row][col]

        if is_blocked:
            cell.blocked_shots += 1
        elif is_missed:
            cell.missed_shots += 1
        else:
            cell.shots += 1
            cell.expected_goals += xg
            heat_map.total_shots += 1
            if is_goal:
                cell.goals += 1
                heat_map.total_goals += 1

    def _update_team_defensive(
        self,
        team_id: int,
        row: int,
        col: int,
        is_goal: bool,
        is_blocked: bool,
        is_missed: bool,
        xg: float,
    ) -> None:
        """Update team defensive heat map (shots against)."""
        heat_map = self._ensure_team_defensive_map(team_id)
        cell = heat_map.cells[row][col]

        if is_blocked:
            cell.blocked_shots += 1
        elif is_missed:
            cell.missed_shots += 1
        else:
            cell.shots += 1
            cell.expected_goals += xg
            heat_map.total_shots += 1
            if is_goal:
                cell.goals += 1
                heat_map.total_goals += 1

    def apply_gaussian_smoothing(
        self, data: np.ndarray, sigma: float | None = None
    ) -> np.ndarray:
        """
        Apply Gaussian smoothing to heat map data.

        Args:
            data: Input 2D array
            sigma: Standard deviation for Gaussian kernel

        Returns:
            Smoothed 2D array
        """
        if sigma is None:
            sigma = self.smoothing_radius

        from scipy.ndimage import gaussian_filter
        return gaussian_filter(data, sigma=sigma)

    def get_player_heat_map(
        self,
        player_id: int,
        map_type: str = "offensive",
        smoothed: bool = True,
    ) -> np.ndarray | None:
        """
        Get heat map for a player.

        Args:
            player_id: Player ID
            map_type: "offensive" or "defensive"
            smoothed: Whether to apply Gaussian smoothing

        Returns:
            2D numpy array or None if no data
        """
        if map_type == "offensive":
            heat_map = self.player_offensive_maps.get(player_id)
        else:
            heat_map = self.player_defensive_maps.get(player_id)

        if heat_map is None:
            return None

        data = heat_map.normalize()
        if smoothed:
            data = self.apply_gaussian_smoothing(data)

        return data

    def get_team_heat_map(
        self,
        team_id: int,
        map_type: str = "offensive",
        smoothed: bool = True,
    ) -> np.ndarray | None:
        """
        Get heat map for a team.

        Args:
            team_id: Team ID
            map_type: "offensive" or "defensive"
            smoothed: Whether to apply Gaussian smoothing

        Returns:
            2D numpy array or None if no data
        """
        if map_type == "offensive":
            heat_map = self.team_offensive_maps.get(team_id)
        else:
            heat_map = self.team_defensive_maps.get(team_id)

        if heat_map is None:
            return None

        data = heat_map.normalize()
        if smoothed:
            data = self.apply_gaussian_smoothing(data)

        return data

    def compare_heat_maps(
        self,
        heat_map_1: np.ndarray,
        heat_map_2: np.ndarray,
    ) -> dict[str, float]:
        """
        Compare two heat maps and calculate similarity metrics.

        Args:
            heat_map_1: First heat map
            heat_map_2: Second heat map

        Returns:
            Dictionary with comparison metrics
        """
        # Normalize both maps
        hm1 = heat_map_1 / heat_map_1.sum() if heat_map_1.sum() > 0 else heat_map_1
        hm2 = heat_map_2 / heat_map_2.sum() if heat_map_2.sum() > 0 else heat_map_2

        # Cosine similarity
        flat1, flat2 = hm1.flatten(), hm2.flatten()
        norm1, norm2 = np.linalg.norm(flat1), np.linalg.norm(flat2)
        cosine_sim = np.dot(flat1, flat2) / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0

        # Mean absolute difference
        mae = np.mean(np.abs(hm1 - hm2))

        # Overlap (where both have significant activity)
        threshold = 0.01
        overlap = np.sum((hm1 > threshold) & (hm2 > threshold)) / max(
            np.sum(hm1 > threshold), np.sum(hm2 > threshold), 1
        )

        return {
            "cosine_similarity": float(cosine_sim),
            "mean_absolute_error": float(mae),
            "overlap_coefficient": float(overlap),
        }

    def calculate_mismatch_map(
        self,
        offensive_team_id: int,
        defensive_team_id: int,
    ) -> np.ndarray | None:
        """
        Calculate offensive-defensive mismatch heat map.

        Identifies zones where offensive strength meets defensive weakness.

        Args:
            offensive_team_id: Attacking team ID
            defensive_team_id: Defending team ID

        Returns:
            Mismatch heat map (positive = advantage for offense)
        """
        off_map = self.get_team_heat_map(offensive_team_id, "offensive", smoothed=True)
        def_map = self.get_team_heat_map(defensive_team_id, "defensive", smoothed=True)

        if off_map is None or def_map is None:
            return None

        # Mismatch: offensive strength * defensive weakness
        # Higher defensive values = more shots allowed = weaker defense
        mismatch = off_map * def_map

        # Weight by xG rates (more dangerous zones matter more)
        mismatch = mismatch * self._xg_base_rates

        return mismatch

    def save_heat_maps(self, output_dir: str | Path) -> None:
        """Save all heat maps to files."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for player_id, heat_map in self.player_offensive_maps.items():
            data = {
                "entity_id": heat_map.entity_id,
                "entity_type": heat_map.entity_type,
                "entity_name": heat_map.entity_name,
                "map_type": heat_map.map_type,
                "total_shots": heat_map.total_shots,
                "total_goals": heat_map.total_goals,
                "grid": heat_map.to_numpy("shots").tolist(),
            }
            path = output_dir / f"player_{player_id}_offensive.json"
            with open(path, "w") as f:
                json.dump(data, f)

        for team_id, heat_map in self.team_offensive_maps.items():
            data = {
                "entity_id": heat_map.entity_id,
                "entity_type": heat_map.entity_type,
                "entity_name": heat_map.entity_name,
                "map_type": heat_map.map_type,
                "total_shots": heat_map.total_shots,
                "total_goals": heat_map.total_goals,
                "grid": heat_map.to_numpy("shots").tolist(),
            }
            path = output_dir / f"team_{team_id}_offensive.json"
            with open(path, "w") as f:
                json.dump(data, f)

        logger.info(f"Saved heat maps to {output_dir}")

    def reset(self) -> None:
        """Reset all heat maps."""
        self.player_offensive_maps.clear()
        self.player_defensive_maps.clear()
        self.team_offensive_maps.clear()
        self.team_defensive_maps.clear()
