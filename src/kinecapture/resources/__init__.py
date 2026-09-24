"""Data files the application reads at runtime, shipped inside the package.

Located through :mod:`importlib.resources`, never through a path walked up
from ``__file__``: an installed application has no repository to walk up to.
"""
