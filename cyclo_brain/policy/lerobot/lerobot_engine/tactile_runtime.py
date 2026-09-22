#!/usr/bin/env python3
"""Checkpoint-scoped tactile preprocessing contracts for inference."""

from __future__ import annotations

from typing import Any


TACTILE_RUNTIME_MODE_FIELD = "_cyclo_tactile_runtime_mode"
TACTILE_STATE_MODE_FIELD = "cyclo_tactile_mode"
TACTILE_STATE_MODE_OFF = "off"
TACTILE_STATE_MODE_STATE_MEAN = "state_mean"
TACTILE_MODE_LEFT_ZERO_RIGHT_BASELINE = "left_zero_right_baseline"
TACTILE_MODE_BOTH_EPISODE_BASELINE = "both_episode_baseline"
VALID_TACTILE_RUNTIME_MODES = frozenset(
    {
        TACTILE_MODE_LEFT_ZERO_RIGHT_BASELINE,
        TACTILE_MODE_BOTH_EPISODE_BASELINE,
    }
)
VALID_TACTILE_STATE_MODES = frozenset(
    {
        TACTILE_STATE_MODE_OFF,
        TACTILE_STATE_MODE_STATE_MEAN,
    }
)


def tactile_runtime_mode(policy_or_config: Any) -> str:
    """Return a validated mode, preserving the older deployment default."""
    config = getattr(policy_or_config, "config", policy_or_config)
    mode = str(
        getattr(
            config,
            TACTILE_RUNTIME_MODE_FIELD,
            TACTILE_MODE_LEFT_ZERO_RIGHT_BASELINE,
        )
    ).strip()
    if mode not in VALID_TACTILE_RUNTIME_MODES:
        raise RuntimeError(f"Unsupported tactile runtime mode: {mode!r}")
    return mode


def tactile_state_mode(policy_or_config: Any) -> str:
    """Return whether legacy tactile means are part of observation.state."""
    config = getattr(policy_or_config, "config", policy_or_config)
    mode = str(
        getattr(config, TACTILE_STATE_MODE_FIELD, TACTILE_STATE_MODE_OFF)
    ).strip() or TACTILE_STATE_MODE_OFF
    if mode not in VALID_TACTILE_STATE_MODES:
        raise RuntimeError(f"Unsupported tactile state mode: {mode!r}")
    return mode


def set_tactile_runtime_mode(config: Any, mode: str) -> None:
    normalized = str(mode).strip()
    if normalized not in VALID_TACTILE_RUNTIME_MODES:
        raise ValueError(f"Unsupported tactile runtime mode: {normalized!r}")
    setattr(config, TACTILE_RUNTIME_MODE_FIELD, normalized)
