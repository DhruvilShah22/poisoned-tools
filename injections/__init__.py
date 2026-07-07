"""Injection template library + deterministic ASR detectors (design §5, §7)."""

from injections import detect, tokens
from injections.inject import Injector, poison_result
from injections.templates import (
    ASKS, FRAMINGS, GOALS, PLACEMENTS, POSITIONS, InjectionSpec,
    enumerate_specs, render, screen_specs, template_id,
)

__all__ = [
    "tokens", "detect", "render", "template_id", "InjectionSpec",
    "enumerate_specs", "screen_specs", "GOALS", "FRAMINGS", "POSITIONS",
    "PLACEMENTS", "ASKS", "Injector", "poison_result",
]
