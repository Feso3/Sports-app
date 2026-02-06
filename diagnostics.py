"""
NHL Simulator Diagnostics Module

Provides structured observability for the simulation pipeline without
changing model behavior. Emits checkpoint events at fixed pipeline
boundaries: INGEST, FEATURE, SIM, OUTPUT.

Usage:
    from diagnostics import diag, DiagConfig

    # Enable diagnostics
    diag.configure(DiagConfig(enabled=True, level="lite"))

    # Emit a checkpoint
    with diag.timer("INGEST"):
        data = load_data()
    diag.event("INGEST", {"teams": 2, "players": 45})

    # At end of run
    diag.print_checklist()
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VALID_LEVELS = ("lite", "normal", "verbose")
STAGE_ORDER = ("INGEST", "FEATURE", "SIM", "OUTPUT")


@dataclass
class DiagConfig:
    """Central diagnostics configuration."""

    enabled: bool = False
    level: str = "lite"  # lite | normal | verbose
    strict: bool = False  # raise on sanity failures instead of warn
    jsonl_path: str | None = None  # optional .jsonl log file

    def __post_init__(self) -> None:
        if self.level not in VALID_LEVELS:
            self.level = "lite"


# ---------------------------------------------------------------------------
# Logger setup  (uses stdlib logging, separate from loguru used by app)
# ---------------------------------------------------------------------------

_diag_logger = logging.getLogger("nhl.diagnostics")
_diag_logger.propagate = False

_console_handler: logging.StreamHandler | None = None


def _ensure_handler() -> None:
    """Lazily attach a console handler so we don't duplicate."""
    global _console_handler
    if _console_handler is None:
        _console_handler = logging.StreamHandler()
        _console_handler.setFormatter(
            logging.Formatter("[DIAG][%(levelname)s] %(message)s")
        )
        _diag_logger.addHandler(_console_handler)
        _diag_logger.setLevel(logging.DEBUG)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def summarize_list(
    items: list[Any],
    name: str,
    key_fields: list[str] | None = None,
    n: int = 3,
) -> dict[str, Any]:
    """Summarize a list of objects/dicts into a compact diagnostic dict.

    Args:
        items: The list to summarize.
        name: Human label for the collection.
        key_fields: Which fields to extract for samples.
        n: Number of sample items to include.

    Returns:
        A dict with count + sample entries.
    """
    summary: dict[str, Any] = {"name": name, "count": len(items)}
    samples = []
    for item in items[:n]:
        if key_fields:
            if isinstance(item, dict):
                samples.append({k: item.get(k) for k in key_fields})
            else:
                samples.append({k: getattr(item, k, None) for k in key_fields})
        else:
            samples.append(str(item)[:120])
    summary["samples"] = samples
    return summary


def summarize_df(
    df: Any,
    name: str,
    sample_cols: list[str] | None = None,
    n: int = 3,
) -> dict[str, Any]:
    """Summarize a pandas DataFrame (if pandas is available).

    Falls back gracefully if the object is not a DataFrame.
    """
    summary: dict[str, Any] = {"name": name}
    try:
        summary["rows"] = len(df)
        summary["columns"] = list(df.columns)
        cols = sample_cols or list(df.columns)[:5]
        summary["sample"] = df[cols].head(n).to_dict(orient="records")
        # Numeric stats for key columns
        numeric = df[cols].select_dtypes(include="number")
        if not numeric.empty:
            summary["stats"] = {
                col: {
                    "min": float(numeric[col].min()),
                    "max": float(numeric[col].max()),
                    "mean": round(float(numeric[col].mean()), 4),
                }
                for col in numeric.columns
            }
    except Exception:
        summary["raw_type"] = type(df).__name__
    return summary


def numeric_stats(values: list[float | int], name: str) -> dict[str, Any]:
    """Compute min/max/mean for a list of numbers."""
    if not values:
        return {"name": name, "count": 0}
    return {
        "name": name,
        "count": len(values),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "mean": round(sum(values) / len(values), 4),
    }


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------


class SanityWarning:
    """A recorded sanity-check warning."""

    def __init__(self, name: str, message: str) -> None:
        self.name = name
        self.message = message
        self.timestamp = time.time()

    def __repr__(self) -> str:
        return f"SanityWarning({self.name}: {self.message})"


# ---------------------------------------------------------------------------
# Core Diagnostics Engine
# ---------------------------------------------------------------------------


@dataclass
class _StageRecord:
    """Internal record for a single pipeline stage."""

    stage: str
    start_time: float = 0.0
    end_time: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration(self) -> float:
        if self.end_time > 0 and self.start_time > 0:
            return self.end_time - self.start_time
        return 0.0


class DiagnosticsEngine:
    """Singleton-style diagnostics engine.

    Typical usage::

        diag.configure(DiagConfig(enabled=True, level="normal"))

        with diag.timer("INGEST"):
            ...
        diag.event("INGEST", {"teams": 2, "players": 45})

        diag.print_checklist()
    """

    def __init__(self) -> None:
        self._config = DiagConfig()
        self._pipeline_start: float = 0.0
        self._stages: dict[str, _StageRecord] = {}
        self._warnings: list[SanityWarning] = []
        self._jsonl_fh: Any = None
        self._output_locations: list[str] = []

    # -- configuration -------------------------------------------------------

    def configure(self, config: DiagConfig) -> None:
        """Apply a new diagnostics configuration."""
        self._config = config
        if config.enabled:
            _ensure_handler()
            self.reset()
            if config.jsonl_path:
                try:
                    self._jsonl_fh = open(config.jsonl_path, "w")
                except OSError:
                    pass

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def level(self) -> str:
        return self._config.level

    @property
    def strict(self) -> bool:
        return self._config.strict

    def reset(self) -> None:
        """Reset all state for a fresh run."""
        self._pipeline_start = time.time()
        self._stages = {}
        self._warnings = []
        self._output_locations = []

    # -- timing --------------------------------------------------------------

    @contextmanager
    def timer(self, stage: str) -> Generator[None, None, None]:
        """Context manager that records wall-clock duration for *stage*."""
        if not self.enabled:
            yield
            return

        rec = self._stages.setdefault(stage, _StageRecord(stage=stage))
        rec.start_time = time.time()
        _diag_logger.info(f"[{stage}] started")
        try:
            yield
        finally:
            rec.end_time = time.time()
            _diag_logger.info(f"[{stage}] completed in {rec.duration:.3f}s")

    # -- events --------------------------------------------------------------

    def event(
        self,
        stage: str,
        summary: dict[str, Any],
        level: str = "lite",
    ) -> None:
        """Emit a structured diagnostic event.

        Args:
            stage: Pipeline stage name (INGEST, FEATURE, SIM, OUTPUT).
            summary: Key-value summary dict.
            level: Minimum diag level required to emit ("lite", "normal", "verbose").
        """
        if not self.enabled:
            return
        if VALID_LEVELS.index(level) > VALID_LEVELS.index(self._config.level):
            return

        rec = self._stages.setdefault(stage, _StageRecord(stage=stage))
        entry = {
            "stage": stage,
            "level": level,
            "ts": time.time(),
            "elapsed": time.time() - self._pipeline_start,
            **summary,
        }
        rec.events.append(entry)

        # Human-readable log
        _diag_logger.info(f"[{stage}] {_format_summary(summary)}")

        # JSONL
        if self._jsonl_fh:
            try:
                self._jsonl_fh.write(json.dumps(entry, default=str) + "\n")
                self._jsonl_fh.flush()
            except OSError:
                pass

    # -- sanity checks -------------------------------------------------------

    def assert_sanity(
        self,
        name: str,
        value: Any,
        expected_range: tuple[float, float] | None = None,
        non_null: bool = True,
    ) -> None:
        """Check a value and warn (or raise in strict mode) on failure.

        Args:
            name: Human label for the check.
            value: The value to check.
            expected_range: Optional (min, max) tuple.
            non_null: If True, warn when value is None/empty/0.
        """
        if not self.enabled:
            return

        msg = None
        if non_null and (value is None or value == 0 or value == ""):
            msg = f"Expected non-null, got {value!r}"
        if expected_range is not None and value is not None:
            lo, hi = expected_range
            try:
                if float(value) < lo or float(value) > hi:
                    msg = f"Value {value} outside expected range [{lo}, {hi}]"
            except (TypeError, ValueError):
                msg = f"Cannot compare {value!r} to range [{lo}, {hi}]"

        if msg:
            warning = SanityWarning(name, msg)
            self._warnings.append(warning)
            _diag_logger.warning(f"SANITY [{name}]: {msg}")
            if self._config.strict:
                raise ValueError(f"Strict sanity failure [{name}]: {msg}")

    # -- output tracking -----------------------------------------------------

    def record_output(self, location: str) -> None:
        """Track an output file/location produced by the pipeline."""
        self._output_locations.append(location)

    # -- checklist -----------------------------------------------------------

    def print_checklist(self) -> None:
        """Print the end-of-run diagnostics checklist."""
        if not self.enabled:
            return

        total_elapsed = time.time() - self._pipeline_start

        lines = [
            "",
            "=" * 62,
            "  DIAGNOSTICS CHECKLIST",
            "=" * 62,
            "",
            f"  Total runtime:  {total_elapsed:.3f}s",
            "",
            "  Stage timings:",
        ]

        for stage_name in STAGE_ORDER:
            rec = self._stages.get(stage_name)
            if rec:
                dur = rec.duration
                lines.append(f"    [{stage_name:>8}]  {dur:.3f}s")
            else:
                lines.append(f"    [{stage_name:>8}]  (not recorded)")

        # Key counts from events
        lines.append("")
        lines.append("  Key counts:")
        for stage_name in STAGE_ORDER:
            rec = self._stages.get(stage_name)
            if rec:
                for ev in rec.events:
                    for k, v in ev.items():
                        if k in ("stage", "level", "ts", "elapsed"):
                            continue
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            lines.append(f"    {k}: {v}")

        # Output locations
        if self._output_locations:
            lines.append("")
            lines.append("  Output locations:")
            for loc in self._output_locations:
                lines.append(f"    - {loc}")

        # Warnings
        lines.append("")
        if self._warnings:
            lines.append(f"  Sanity warnings: {len(self._warnings)}")
            for w in self._warnings:
                lines.append(f"    ! [{w.name}] {w.message}")
        else:
            lines.append("  Sanity warnings: 0 (all clear)")

        lines.append("")
        lines.append("=" * 62)

        output = "\n".join(lines)
        _diag_logger.info(output)
        # Also print directly for visibility
        print(output)

    # -- teardown ------------------------------------------------------------

    def close(self) -> None:
        """Close any open file handles."""
        if self._jsonl_fh:
            try:
                self._jsonl_fh.close()
            except OSError:
                pass
            self._jsonl_fh = None


# ---------------------------------------------------------------------------
# Formatting helper
# ---------------------------------------------------------------------------


def _format_summary(summary: dict[str, Any], max_width: int = 200) -> str:
    """Format a summary dict into a compact, human-readable string."""
    parts = []
    for k, v in summary.items():
        if isinstance(v, dict):
            inner = ", ".join(f"{ik}={iv}" for ik, iv in list(v.items())[:4])
            parts.append(f"{k}={{{inner}}}")
        elif isinstance(v, list):
            parts.append(f"{k}=[{len(v)} items]")
        elif isinstance(v, float):
            parts.append(f"{k}={v:.4f}")
        else:
            parts.append(f"{k}={v}")
    line = " | ".join(parts)
    if len(line) > max_width:
        line = line[:max_width] + "..."
    return line


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

diag = DiagnosticsEngine()
