"""The desktop (PySide6) presentation layer.

The systems under it -- ``core``, ``world``, ``game`` -- are the fork of the
terminal game and know nothing about a screen. Everything that does know is in
here: the CRT renderer, the pattern buffer, the input, and the screens.
"""

from __future__ import annotations

__all__: list[str] = []
