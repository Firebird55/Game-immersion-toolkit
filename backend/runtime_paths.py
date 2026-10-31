"""Narrow bridge for services that still accept a legacy project-root argument.

Source callers keep their existing per-installation layout. Frozen callers use
the explicit host roots; an application slot is never a mutable project root.
"""
from pathlib import Path

from .runtime_bundle import discover_layout


def data_root(project_root: Path) -> Path:
    layout = discover_layout()
    return layout.data_root if layout.mode == 'bundle' else Path(project_root) / 'data'


def voice_work_root(project_root: Path) -> Path:
    layout = discover_layout()
    return layout.work_root if layout.mode == 'bundle' else Path(project_root) / 'work/voice-assets'


def default_export_root(project_root: Path) -> Path:
    layout = discover_layout()
    return layout.default_export_root if layout.mode == 'bundle' else Path(project_root) / 'output/mobile-libraries'
