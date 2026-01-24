"""
Charts Visualization Module

Creates statistical visualizations including:
- Player comparison charts
- Team statistics charts
- Zone performance charts
- Segment performance timelines
- Matchup analysis charts
"""

from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("matplotlib not available, chart functions will be limited")


class ChartVisualizer:
    """
    Visualizer for statistical charts.

    Creates various chart types for hockey analytics including
    player comparisons, zone breakdowns, and performance trends.
    """

    # Color palettes
    TEAM_COLORS = {
        "TOR": "#00205B",
        "MTL": "#AF1E2D",
        "BOS": "#FFB81C",
        "NYR": "#0038A8",
        "EDM": "#FF4C00",
        "COL": "#6F263D",
        "TBL": "#002868",
        "FLA": "#C8102E",
        "default": "#333333",
    }

    ZONE_COLORS = {
        "slot": "#FF4136",
        "inner_slot": "#FF0000",
        "crease": "#DC143C",
        "left_circle": "#FF851B",
        "right_circle": "#FF851B",
        "high_slot": "#FFDC00",
        "left_point": "#2ECC40",
        "right_point": "#2ECC40",
        "left_wing": "#0074D9",
        "right_wing": "#0074D9",
        "behind_net": "#B10DC9",
    }

    SEGMENT_COLORS = {
        "early_game": "#2ECC40",
        "mid_game": "#FFDC00",
        "late_game": "#FF4136",
    }

    def __init__(
        self,
        figsize: tuple[float, float] = (10, 6),
        dpi: int = 100,
        style: str = "seaborn-v0_8-whitegrid",
    ):
        """
        Initialize the chart visualizer.

        Args:
            figsize: Default figure size in inches
            dpi: Dots per inch for output
            style: Matplotlib style to use
        """
        self.figsize = figsize
        self.dpi = dpi

        if MATPLOTLIB_AVAILABLE:
            try:
                plt.style.use(style)
            except OSError:
                plt.style.use("ggplot")

    def _get_team_color(self, team_abbrev: str) -> str:
        """Get color for a team."""
        return self.TEAM_COLORS.get(team_abbrev, self.TEAM_COLORS["default"])

    def render_player_comparison(
        self,
        player_1_stats: dict[str, float],
        player_2_stats: dict[str, float],
        player_1_name: str,
        player_2_name: str,
        metrics: list[str] | None = None,
        title: str = "Player Comparison",
        output_path: str | Path | None = None,
    ) -> Any | None:
        """
        Render a radar chart comparing two players.

        Args:
            player_1_stats: Stats dictionary for player 1
            player_2_stats: Stats dictionary for player 2
            player_1_name: Name of player 1
            player_2_name: Name of player 2
            metrics: List of metrics to compare (keys in stats dicts)
            title: Chart title
            output_path: Path to save the figure

        Returns:
            matplotlib figure or None
        """
        if not MATPLOTLIB_AVAILABLE:
            return None

        if metrics is None:
            metrics = ["goals", "assists", "shots", "hits", "blocks", "takeaways"]

        # Get values for each player
        p1_values = [player_1_stats.get(m, 0) for m in metrics]
        p2_values = [player_2_stats.get(m, 0) for m in metrics]

        # Normalize values (0-1 scale)
        max_vals = [max(p1_values[i], p2_values[i], 1) for i in range(len(metrics))]
        p1_normalized = [p1_values[i] / max_vals[i] for i in range(len(metrics))]
        p2_normalized = [p2_values[i] / max_vals[i] for i in range(len(metrics))]

        # Create radar chart
        angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()
        angles += angles[:1]  # Complete the circle

        p1_normalized += p1_normalized[:1]
        p2_normalized += p2_normalized[:1]

        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True), dpi=self.dpi)

        ax.plot(angles, p1_normalized, "o-", linewidth=2, label=player_1_name, color="#0074D9")
        ax.fill(angles, p1_normalized, alpha=0.25, color="#0074D9")

        ax.plot(angles, p2_normalized, "o-", linewidth=2, label=player_2_name, color="#FF4136")
        ax.fill(angles, p2_normalized, alpha=0.25, color="#FF4136")

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels([m.replace("_", " ").title() for m in metrics])

        ax.set_title(title, size=14, fontweight="bold", pad=20)
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))

        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")

        return fig

    def render_zone_breakdown(
        self,
        zone_stats: dict[str, dict[str, float]],
        entity_name: str,
        metric: str = "shots",
        title: str | None = None,
        output_path: str | Path | None = None,
    ) -> Any | None:
        """
        Render a bar chart showing performance by zone.

        Args:
            zone_stats: Dict mapping zone names to stat dicts
            entity_name: Name of player/team
            metric: Metric to display
            title: Chart title
            output_path: Path to save the figure

        Returns:
            matplotlib figure or None
        """
        if not MATPLOTLIB_AVAILABLE:
            return None

        zones = list(zone_stats.keys())
        values = [zone_stats[z].get(metric, 0) for z in zones]
        colors = [self.ZONE_COLORS.get(z, "#666666") for z in zones]

        fig, ax = plt.subplots(figsize=self.figsize, dpi=self.dpi)

        bars = ax.barh(zones, values, color=colors, edgecolor="white", linewidth=0.5)

        # Add value labels
        for bar, val in zip(bars, values):
            width = bar.get_width()
            ax.text(
                width + max(values) * 0.02,
                bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}" if isinstance(val, float) else str(val),
                va="center",
                fontsize=10,
            )

        ax.set_xlabel(metric.replace("_", " ").title())
        ax.set_title(title or f"{entity_name} - {metric.title()} by Zone", fontweight="bold")

        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")

        return fig

    def render_segment_performance(
        self,
        segment_stats: dict[str, dict[str, float]],
        entity_name: str,
        metrics: list[str] | None = None,
        title: str | None = None,
        output_path: str | Path | None = None,
    ) -> Any | None:
        """
        Render a grouped bar chart showing performance by game segment.

        Args:
            segment_stats: Dict mapping segment names to stat dicts
            entity_name: Name of player/team
            metrics: List of metrics to display
            title: Chart title
            output_path: Path to save the figure

        Returns:
            matplotlib figure or None
        """
        if not MATPLOTLIB_AVAILABLE:
            return None

        if metrics is None:
            metrics = ["goals", "shots", "xg"]

        segments = ["early_game", "mid_game", "late_game"]
        x = np.arange(len(metrics))
        width = 0.25

        fig, ax = plt.subplots(figsize=self.figsize, dpi=self.dpi)

        for i, segment in enumerate(segments):
            stats = segment_stats.get(segment, {})
            values = [stats.get(m, 0) for m in metrics]
            offset = (i - 1) * width
            bars = ax.bar(
                x + offset,
                values,
                width,
                label=segment.replace("_", " ").title(),
                color=self.SEGMENT_COLORS.get(segment, "#666666"),
                edgecolor="white",
                linewidth=0.5,
            )

        ax.set_ylabel("Value")
        ax.set_title(title or f"{entity_name} - Performance by Game Segment", fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels([m.replace("_", " ").title() for m in metrics])
        ax.legend()

        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")

        return fig

    def render_corsi_chart(
        self,
        corsi_for: list[float],
        corsi_against: list[float],
        labels: list[str],
        title: str = "Corsi Comparison",
        output_path: str | Path | None = None,
    ) -> Any | None:
        """
        Render a Corsi comparison chart.

        Args:
            corsi_for: List of CF values
            corsi_against: List of CA values
            labels: Labels for each entry
            title: Chart title
            output_path: Path to save the figure

        Returns:
            matplotlib figure or None
        """
        if not MATPLOTLIB_AVAILABLE:
            return None

        x = np.arange(len(labels))
        width = 0.35

        fig, ax = plt.subplots(figsize=self.figsize, dpi=self.dpi)

        bars1 = ax.bar(x - width / 2, corsi_for, width, label="CF", color="#2ECC40")
        bars2 = ax.bar(x + width / 2, corsi_against, width, label="CA", color="#FF4136")

        # Add CF% line
        cf_pct = [cf / (cf + ca) * 100 if (cf + ca) > 0 else 50 for cf, ca in zip(corsi_for, corsi_against)]

        ax2 = ax.twinx()
        ax2.plot(x, cf_pct, "ko-", linewidth=2, markersize=8, label="CF%")
        ax2.axhline(y=50, color="gray", linestyle="--", alpha=0.5)
        ax2.set_ylabel("CF%")
        ax2.set_ylim(30, 70)

        ax.set_ylabel("Shot Attempts")
        ax.set_title(title, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right")

        # Combined legend
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc="upper right")

        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")

        return fig

    def render_xg_chart(
        self,
        xg_for: list[float],
        xg_against: list[float],
        goals_for: list[int],
        goals_against: list[int],
        labels: list[str],
        title: str = "Expected Goals Analysis",
        output_path: str | Path | None = None,
    ) -> Any | None:
        """
        Render an expected goals analysis chart.

        Args:
            xg_for: List of xGF values
            xg_against: List of xGA values
            goals_for: List of actual goals for
            goals_against: List of actual goals against
            labels: Labels for each entry
            title: Chart title
            output_path: Path to save the figure

        Returns:
            matplotlib figure or None
        """
        if not MATPLOTLIB_AVAILABLE:
            return None

        fig, axes = plt.subplots(1, 2, figsize=(14, 6), dpi=self.dpi)

        # Left: xG vs Actual Goals scatter
        ax1 = axes[0]
        ax1.scatter(xg_for, goals_for, c="#2ECC40", s=100, alpha=0.7, label="Goals For")
        ax1.scatter(xg_against, goals_against, c="#FF4136", s=100, alpha=0.7, label="Goals Against")

        # Add diagonal line (perfect prediction)
        max_val = max(max(xg_for + xg_against), max(goals_for + goals_against))
        ax1.plot([0, max_val], [0, max_val], "k--", alpha=0.5, label="Perfect Prediction")

        ax1.set_xlabel("Expected Goals")
        ax1.set_ylabel("Actual Goals")
        ax1.set_title("xG vs Actual Goals", fontweight="bold")
        ax1.legend()

        # Right: Goals Above Expected bar chart
        ax2 = axes[1]
        gae_for = [g - x for g, x in zip(goals_for, xg_for)]
        gae_against = [x - g for g, x in zip(goals_against, xg_against)]  # Positive = good defense

        x = np.arange(len(labels))
        width = 0.35

        ax2.bar(x - width / 2, gae_for, width, label="Goals Above Expected (Offense)",
                color=["#2ECC40" if v >= 0 else "#FF4136" for v in gae_for])
        ax2.bar(x + width / 2, gae_against, width, label="Goals Saved Above Expected",
                color=["#0074D9" if v >= 0 else "#FF851B" for v in gae_against])

        ax2.axhline(y=0, color="black", linewidth=0.5)
        ax2.set_ylabel("Goals Above/Below Expected")
        ax2.set_title("Performance vs Expected", fontweight="bold")
        ax2.set_xticks(x)
        ax2.set_xticklabels(labels, rotation=45, ha="right")
        ax2.legend()

        fig.suptitle(title, fontsize=14, fontweight="bold")
        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")

        return fig

    def render_matchup_history(
        self,
        team_1_wins: int,
        team_2_wins: int,
        overtime_losses: int,
        team_1_name: str,
        team_2_name: str,
        goals_for: int,
        goals_against: int,
        title: str | None = None,
        output_path: str | Path | None = None,
    ) -> Any | None:
        """
        Render a matchup history summary chart.

        Args:
            team_1_wins: Wins for team 1
            team_2_wins: Wins for team 2
            overtime_losses: OT losses
            team_1_name: Name of team 1
            team_2_name: Name of team 2
            goals_for: Total goals for team 1
            goals_against: Total goals against team 1
            title: Chart title
            output_path: Path to save the figure

        Returns:
            matplotlib figure or None
        """
        if not MATPLOTLIB_AVAILABLE:
            return None

        fig, axes = plt.subplots(1, 2, figsize=(12, 5), dpi=self.dpi)

        # Left: Win/Loss pie chart
        ax1 = axes[0]
        sizes = [team_1_wins, team_2_wins, overtime_losses]
        labels_pie = [f"{team_1_name} Wins", f"{team_2_name} Wins", "OT Losses"]
        colors = ["#2ECC40", "#FF4136", "#FFDC00"]
        explode = (0.05, 0.05, 0)

        ax1.pie(
            sizes,
            explode=explode,
            labels=labels_pie,
            colors=colors,
            autopct="%1.1f%%",
            shadow=True,
            startangle=90,
        )
        ax1.set_title("Win Distribution", fontweight="bold")

        # Right: Goals comparison
        ax2 = axes[1]
        categories = ["Goals For", "Goals Against"]
        values = [goals_for, goals_against]
        colors = ["#2ECC40", "#FF4136"]

        bars = ax2.bar(categories, values, color=colors, edgecolor="white", linewidth=2)

        for bar, val in zip(bars, values):
            ax2.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(values) * 0.02,
                str(val),
                ha="center",
                va="bottom",
                fontsize=12,
                fontweight="bold",
            )

        ax2.set_ylabel("Goals")
        ax2.set_title("Goals Summary", fontweight="bold")

        fig.suptitle(
            title or f"{team_1_name} vs {team_2_name} - Historical Matchup",
            fontsize=14,
            fontweight="bold",
        )
        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")

        return fig

    def render_shooting_percentage_trend(
        self,
        games: list[str],
        shooting_pcts: list[float],
        league_avg: float = 0.10,
        entity_name: str = "",
        title: str | None = None,
        output_path: str | Path | None = None,
    ) -> Any | None:
        """
        Render a shooting percentage trend line chart.

        Args:
            games: List of game identifiers/dates
            shooting_pcts: List of shooting percentages
            league_avg: League average for comparison
            entity_name: Name of player/team
            title: Chart title
            output_path: Path to save the figure

        Returns:
            matplotlib figure or None
        """
        if not MATPLOTLIB_AVAILABLE:
            return None

        fig, ax = plt.subplots(figsize=self.figsize, dpi=self.dpi)

        x = range(len(games))

        ax.plot(x, shooting_pcts, "o-", linewidth=2, markersize=6, color="#0074D9", label=entity_name)
        ax.axhline(y=league_avg, color="red", linestyle="--", alpha=0.7, label=f"League Avg ({league_avg:.1%})")

        # Add rolling average
        if len(shooting_pcts) >= 5:
            rolling_avg = np.convolve(shooting_pcts, np.ones(5) / 5, mode="valid")
            ax.plot(
                range(2, len(shooting_pcts) - 2),
                rolling_avg,
                linewidth=2,
                color="#2ECC40",
                alpha=0.7,
                label="5-Game Rolling Avg",
            )

        ax.set_xlabel("Games")
        ax.set_ylabel("Shooting %")
        ax.set_title(title or f"{entity_name} - Shooting Percentage Trend", fontweight="bold")
        ax.legend()

        # Format y-axis as percentage
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))

        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=self.dpi, bbox_inches="tight")

        return fig

    def export_chart_data(
        self,
        chart_type: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Export chart data in a format suitable for web visualization.

        Args:
            chart_type: Type of chart
            data: Chart data

        Returns:
            Dictionary with data for web rendering
        """
        return {
            "chart_type": chart_type,
            "data": data,
            "colors": {
                "zones": self.ZONE_COLORS,
                "segments": self.SEGMENT_COLORS,
            },
        }

    def close_all(self) -> None:
        """Close all open figures."""
        if MATPLOTLIB_AVAILABLE:
            plt.close("all")
