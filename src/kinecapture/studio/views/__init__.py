"""Views: drawing and event routing only.

A view may read a viewmodel and call its methods. It may not talk to the
backend, hold application state, or decide anything a WinUI 3 rewrite would
have to decide again.
"""

from .shell import StudioWindow

__all__ = ["StudioWindow"]
