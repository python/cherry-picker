"""Backport CPython changes from main to maintenance branches."""
import importlib.metadata

__version__ = importlib.metadata.version(__name__)
