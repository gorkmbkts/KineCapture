"""KineCapture Studio interface, built on the offline processing architecture.

Three layers, and the boundary between them is the whole point:

``services/``    the only way in to the backend   - no Qt
``viewmodels/``  state, commands, formatting      - no Qt
``views/``       PySide6 widgets                  - drawing and events only

If this product later moves to C# + WinUI 3, only ``views/`` is rewritten.
``tests/test_studio_layers.py`` imports the two lower layers in a subprocess
where PySide6 cannot be imported, so the boundary cannot rot quietly.

The previous interface in :mod:`kinecapture.gui` is left intact and still
launchable with ``--legacy-gui``: it is the only thing that can open
recordings made before the raw-first capture policy, and those recordings are
kept.
"""

STUDIO_VERSION = "0.1.0"

__all__ = ["STUDIO_VERSION"]
