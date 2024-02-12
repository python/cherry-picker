"""Backport CPython changes from main to maintenance branches."""

from __future__ import annotations

import importlib.metadata

__version__ = importlib.metadata.version(__name__)
