"""
Heat Map Visualization Module

Renders heat maps for shot distributions, zone performance, and matchup analysis.
Uses matplotlib for static images and can generate data for interactive visualizations.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

# Optional matplotlib import for systems without display
try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.colors import LinearSegmentedColormap
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("matplotlib not available, visualization functions will be limited")


@dataclass
class RinkDimensions:
    """NHL rink dimensions for visualization."""

    length: float = 200.0  # feet
    width: float = 85.0  # feet
    goal_line_x: float = 89.0  # Distance from center to goal line
    blue_line_x: float = 75.0  # Distance from center to offensive blue line
    center_x: float = 0.0
    faceoff_circle_radius: float = 15.0
    crease_width: float = 8.0
    crease_depth: float = 4.5


class HeatMapVisualizer:
    """
    Visualizer for hockey heat maps.

    Creates visual representations of:
    - Shot location heat maps
    - Zone-based performance maps
    - Offensive/defensive comparison maps
    - Mismatch visualization
    """

    # Color schemes
    SHOT_COLORMAP = "YlOrRd"  # Yellow-Orange-Red for shots
    GOAL_COLORMAP = "RdYlGn"  # Red-Yellow-Green for efficiency
    COMPARISON_COLORMAP = "RdBu"  # Red-Blue for comparisons

    def __init__(
        self,
        figsize: tuple[float, float] = (12, 8),
        dpi: int = 100,
        half_rink: bool = True,
    ):
        """
        Initialize the heat map visualizer.

        Args:
            figsize: Figure size in inches
            dpi: Dots per inch for output
            half_rink: Whether to show half rink (offensive zone only)
        """
        self.figsize = figsize
        self.dpi = dpi
        self.half_rink = half_rink
        self.rink = RinkDimensions()

        if not MATPLOTLIB_AVAILABLE:
            logger.warning("Visualization features require matplotlib")

    def _draw_half_rink(self, ax: Any) -> None:
        """Draw half-rink outline on axes."""
        if not MATPLOTLIB_AVAILABLE:
            return

        # Rink boundaries (half rink from center to end)
        rink_color = "#EEEEEE"
        line_color = "#333333"

        # Background
        ax.set_facecolor(rink_color)

        # Rink outline
        ax.plot([0, self.rink.goal_line_x + 11], [self.rink.width / 2, self.rink.width / 2],
                color=line_color, linewidth=2)
        ax.plot([0, self.rink.goal_line_x + 11], [-self.rink.width / 2, -self.rink.width / 2],
                color=line_color, linewidth=2)

        # Blue line
        ax.axvline(x=self.rink.blue_line_x, color="blue", linewidth=3, alpha=0.7)

        # Goal line
        ax.axvline(x=self.rink.goal_line_x, color="red", linewidth=2, alpha=0.7)

        # Center line (at x=0 for half rink)
        ax.axvline(x=0, color="red", linewidth=2, alpha=0.7)

        # Goal crease
        crease = patches.Rectangle(
            (self.rink.goal_line_x, -self.rink.crease_width / 2),
            self.rink.crease_depth,
            self.rink.crease_width,
            fill=True,
            facecolor="lightblue",
            edgecolor="blue",
            linewidth=2,
            alpha=0.5,
        )
        ax.add_patch(crease)

        # Faceoff circles
        for y_pos in [22, -22]:  # Left and right circles
            circle = patches.Circle(
                (69, y_pos),
                self.rink.faceoff_circle_radius,
                fill=False,
                edgecolor="red",
                linewidth=1.5,
            )
            ax.add_patch(circle)

        # Set limits
        ax.set_xlim(-5, 100)
        ax.set_ylim(-45, 45)
        ax.set_aspect("equal")
        ax.axis("off")

    def render_shot_heat_map(
        self,
        heat_map_data: np.ndarray,
        title: str = "Shot Heat Map",
        colormap: str | None = None,
        show_zones: bool = True,
        output_path: str | Path | None = None,
    ) -> Any | None:
        """
        Render a shot distribution heat map.

        Args:
            heat_map_data: 2D numpy array with heat map values
            title: Title for the visualization
            colormap: Matplotlib colormap name
            show_zones: Whether to overlay zone boundaries
            output_path: Path to save the figure (optional)

        Returns:
            matplotlib figure or None if matplotlib unavailable
        """
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("Cannot render heat map: matplotlib not available")
            return None

        fig, ax = plt.subplots(figsize=self.figsize, dpi=self.dpi)

        # Draw rink
        self._draw_half_rink(ax)

        # Create heat map overlay
        cmap = colormap or self.SHOT_COLORMAP

        # Transform data to rink coordinates
        extent = [0, 100, -42.5, 42.5]  # x_min, x_max, y_min, y_max

        im = ax.imshow(
            heat_map_data,
            extent=extent,
            origin="lower",
            cmap=cmap,
            alpha=0.6,
            aspect="auto",
            interpolation="gaussian",
        )

        # Add colorbar
        cbar = plt.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
        cbar.set_label("Shot Density", rotation=270, labelpad=15)

        # Add zone overlays if requested
        if show_zones:
            self._draw_zone_boundaries(ax)

        ax.set_title(title, fontsize=14, fontweight="bold", pad=10)

        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")
            logger.info(f"Saved heat map to {output_path}")

        return fig

    def render_shooting_efficiency_map(
        self,
        shooting_pct_data: np.ndarray,
        shot_count_data: np.ndarray,
        title: str = "Shooting Efficiency",
        min_shots: int = 5,
        output_path: str | Path | None = None,
    ) -> Any | None:
        """
        Render a shooting percentage heat map.

        Args:
            shooting_pct_data: 2D array with shooting percentages
            shot_count_data: 2D array with shot counts (for filtering)
            title: Title for the visualization
            min_shots: Minimum shots to show efficiency
            output_path: Path to save the figure

        Returns:
            matplotlib figure or None
        """
        if not MATPLOTLIB_AVAILABLE:
            return None

        fig, ax = plt.subplots(figsize=self.figsize, dpi=self.dpi)

        self._draw_half_rink(ax)

        # Mask low sample size areas
        masked_data = np.ma.masked_where(shot_count_data < min_shots, shooting_pct_data)

        extent = [0, 100, -42.5, 42.5]

        im = ax.imshow(
            masked_data,
            extent=extent,
            origin="lower",
            cmap=self.GOAL_COLORMAP,
            alpha=0.7,
            aspect="auto",
            interpolation="gaussian",
            vmin=0,
            vmax=0.3,  # Cap at 30% for visualization
        )

        cbar = plt.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
        cbar.set_label("Shooting %", rotation=270, labelpad=15)

        ax.set_title(title, fontsize=14, fontweight="bold", pad=10)

        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")

        return fig

    def render_comparison_map(
        self,
        heat_map_1: np.ndarray,
        heat_map_2: np.ndarray,
        label_1: str = "Player/Team 1",
        label_2: str = "Player/Team 2",
        title: str = "Shot Distribution Comparison",
        output_path: str | Path | None = None,
    ) -> Any | None:
        """
        Render a comparison between two heat maps.

        Args:
            heat_map_1: First heat map data
            heat_map_2: Second heat map data
            label_1: Label for first entity
            label_2: Label for second entity
            title: Title for the visualization
            output_path: Path to save the figure

        Returns:
            matplotlib figure or None
        """
        if not MATPLOTLIB_AVAILABLE:
            return None

        fig, axes = plt.subplots(1, 3, figsize=(16, 6), dpi=self.dpi)

        extent = [0, 100, -42.5, 42.5]

        # First heat map
        self._draw_half_rink(axes[0])
        im1 = axes[0].imshow(
            heat_map_1,
            extent=extent,
            origin="lower",
            cmap=self.SHOT_COLORMAP,
            alpha=0.6,
            aspect="auto",
            interpolation="gaussian",
        )
        axes[0].set_title(label_1, fontsize=12)
        plt.colorbar(im1, ax=axes[0], shrink=0.5)

        # Second heat map
        self._draw_half_rink(axes[1])
        im2 = axes[1].imshow(
            heat_map_2,
            extent=extent,
            origin="lower",
            cmap=self.SHOT_COLORMAP,
            alpha=0.6,
            aspect="auto",
            interpolation="gaussian",
        )
        axes[1].set_title(label_2, fontsize=12)
        plt.colorbar(im2, ax=axes[1], shrink=0.5)

        # Difference map
        diff = heat_map_1 - heat_map_2
        self._draw_half_rink(axes[2])
        im3 = axes[2].imshow(
            diff,
            extent=extent,
            origin="lower",
            cmap=self.COMPARISON_COLORMAP,
            alpha=0.6,
            aspect="auto",
            interpolation="gaussian",
            vmin=-np.abs(diff).max(),
            vmax=np.abs(diff).max(),
        )
        axes[2].set_title("Difference", fontsize=12)
        plt.colorbar(im3, ax=axes[2], shrink=0.5)

        fig.suptitle(title, fontsize=14, fontweight="bold")
        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")

        return fig

    def render_mismatch_map(
        self,
        offensive_map: np.ndarray,
        defensive_map: np.ndarray,
        offensive_label: str,
        defensive_label: str,
        title: str = "Matchup Mismatch Analysis",
        output_path: str | Path | None = None,
    ) -> Any | None:
        """
        Render a mismatch analysis map.

        Shows where offensive strength meets defensive weakness.

        Args:
            offensive_map: Offensive team/player heat map
            defensive_map: Defensive team/player heat map (shots allowed)
            offensive_label: Label for offensive entity
            defensive_label: Label for defensive entity
            title: Title for the visualization
            output_path: Path to save the figure

        Returns:
            matplotlib figure or None
        """
        if not MATPLOTLIB_AVAILABLE:
            return None

        fig, axes = plt.subplots(1, 3, figsize=(16, 6), dpi=self.dpi)

        extent = [0, 100, -42.5, 42.5]

        # Offensive heat map
        self._draw_half_rink(axes[0])
        im1 = axes[0].imshow(
            offensive_map,
            extent=extent,
            origin="lower",
            cmap="Oranges",
            alpha=0.6,
            aspect="auto",
            interpolation="gaussian",
        )
        axes[0].set_title(f"{offensive_label}\n(Offensive)", fontsize=11)
        plt.colorbar(im1, ax=axes[0], shrink=0.5)

        # Defensive weakness map
        self._draw_half_rink(axes[1])
        im2 = axes[1].imshow(
            defensive_map,
            extent=extent,
            origin="lower",
            cmap="Blues",
            alpha=0.6,
            aspect="auto",
            interpolation="gaussian",
        )
        axes[1].set_title(f"vs {defensive_label}\n(Shots Allowed)", fontsize=11)
        plt.colorbar(im2, ax=axes[1], shrink=0.5)

        # Mismatch opportunity map
        mismatch = offensive_map * defensive_map
        self._draw_half_rink(axes[2])
        im3 = axes[2].imshow(
            mismatch,
            extent=extent,
            origin="lower",
            cmap="RdYlGn",
            alpha=0.7,
            aspect="auto",
            interpolation="gaussian",
        )
        axes[2].set_title("Mismatch\nOpportunity", fontsize=11)
        plt.colorbar(im3, ax=axes[2], shrink=0.5)

        fig.suptitle(title, fontsize=14, fontweight="bold")
        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")

        return fig

    def _draw_zone_boundaries(self, ax: Any) -> None:
        """Draw zone boundary lines on the rink."""
        if not MATPLOTLIB_AVAILABLE:
            return

        zone_color = "#666666"
        alpha = 0.4
        linestyle = "--"

        # Slot boundaries
        ax.plot([69, 89], [22, 9], color=zone_color, alpha=alpha, linestyle=linestyle)
        ax.plot([69, 89], [-22, -9], color=zone_color, alpha=alpha, linestyle=linestyle)

        # High slot boundary
        ax.plot([25, 69], [15, 22], color=zone_color, alpha=alpha, linestyle=linestyle)
        ax.plot([25, 69], [-15, -22], color=zone_color, alpha=alpha, linestyle=linestyle)

    def export_for_web(
        self,
        heat_map_data: np.ndarray,
        entity_name: str,
    ) -> dict[str, Any]:
        """
        Export heat map data in a format suitable for web visualization.

        Args:
            heat_map_data: 2D numpy array
            entity_name: Name of the player/team

        Returns:
            Dictionary with data for web rendering
        """
        rows, cols = heat_map_data.shape

        # Convert to list of dictionaries for easy JSON serialization
        data_points = []
        for i in range(rows):
            for j in range(cols):
                if heat_map_data[i, j] > 0:
                    x = (j / cols) * 100  # Scale to rink coordinates
                    y = (i / rows) * 85 - 42.5
                    data_points.append({
                        "x": x,
                        "y": y,
                        "value": float(heat_map_data[i, j]),
                    })

        return {
            "entity_name": entity_name,
            "data_points": data_points,
            "rink_dimensions": {
                "length": self.rink.length,
                "width": self.rink.width,
                "goal_line_x": self.rink.goal_line_x,
                "blue_line_x": self.rink.blue_line_x,
            },
            "bounds": {
                "x_min": 0,
                "x_max": 100,
                "y_min": -42.5,
                "y_max": 42.5,
            },
        }

    def close_all(self) -> None:
        """Close all open figures."""
        if MATPLOTLIB_AVAILABLE:
            plt.close("all")
