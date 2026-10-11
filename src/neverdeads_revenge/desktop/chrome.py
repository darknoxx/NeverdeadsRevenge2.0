"""The grim dark: frames, banners, and menus.

Every menu in this build is drawn from the same three pieces, so they cannot
drift into looking like three different games: a double-ruled box, a heading in
the accent, and a list with one line lit. The palette is the dungeon's own --
blood for the frame, bone for the words, ash for everything the player is not
looking at -- and the title keeps the purple it always had, because that is the
colour Noxx is.
"""

from __future__ import annotations

from .buffer import PatternBuffer
from .theme import Style, parse_style

__all__ = [
    "BLOOD",
    "BONE",
    "ASH",
    "PURPLE",
    "box",
    "centre_box",
    "menu",
    "banner",
    "rule",
]

#: The frame of every dialog and menu. Dark red -- the colour of a warning that
#: has already happened.
BLOOD = "#8b1a1a"
#: The words.
BONE = "#c8c8c8"
#: What the eye is not on yet.
ASH = "grey30"
#: Noxx's own colour, kept for his name and the title.
PURPLE = "#a855f7"
#: The inside of a panel, and the field a modal sits on. Two shades of the same
#: dark, so a menu reads as a layer rather than as a hole.
PANEL = "#15151f"
PANEL_DEEP = "#08080c"

_CORNER = {
    "tl": "╔", "tr": "╗", "bl": "╚", "br": "╝",
    "h": "═", "v": "║",
    "lt": "╠", "rt": "╣",
}


def box(
    buffer: PatternBuffer,
    x: int,
    y: int,
    width: int,
    height: int,
    title: str | None = None,
    border: str = BLOOD,
    fill: bool = False,
) -> None:
    """A double-ruled box, optionally titled and optionally opaque.

    Double-ruled rather than single, because a terminal that can draw a box is
    the one place a game gets to look like a piece of hardware, and the DOS era
    never used a thin line when a fat one would do. ``fill`` gives the inside a
    background, which is what keeps a menu from being a window onto the dungeon.
    """
    if width < 4 or height < 2:
        return
    style = parse_style(border)
    if fill:
        panel = Style(bg=parse_style(PANEL).fg)
        for j in range(y + 1, y + height - 1):
            for i in range(x + 1, x + width - 1):
                buffer.put(i, j, " ", panel)
    buffer.put(x, y, _CORNER["tl"], style)
    buffer.put(x + width - 1, y, _CORNER["tr"], style)
    buffer.put(x, y + height - 1, _CORNER["bl"], style)
    buffer.put(x + width - 1, y + height - 1, _CORNER["br"], style)
    for i in range(1, width - 1):
        buffer.put(x + i, y, _CORNER["h"], style)
        buffer.put(x + i, y + height - 1, _CORNER["h"], style)
    for j in range(1, height - 1):
        buffer.put(x, y + j, _CORNER["v"], style)
        buffer.put(x + width - 1, y + j, _CORNER["v"], style)

    if title:
        text = f" {title} "
        buffer.text(x + 2, y, text[: width - 4], parse_style(f"bold {BONE}"))


def centre_box(
    buffer: PatternBuffer,
    width: int,
    height: int,
    title: str | None = None,
    border: str = BLOOD,
) -> tuple[int, int]:
    """A box in the middle of the buffer. Returns its top-left corner."""
    x = max(0, (buffer.cols - width) // 2)
    y = max(0, (buffer.rows - height) // 2)
    box(buffer, x, y, width, height, title, border)
    return x, y


def banner(buffer: PatternBuffer, y: int, text: str, style: str = f"bold {BONE}") -> None:
    """One centred line."""
    x = max(0, (buffer.cols - len(text)) // 2)
    buffer.text(x, y, text, parse_style(style))


def rule(buffer: PatternBuffer, x: int, y: int, width: int, style: str = ASH) -> None:
    """A thin rule, for separating a body from its hint."""
    for i in range(width):
        buffer.put(x + i, y, "─", parse_style(style))


def menu(
    buffer: PatternBuffer,
    x: int,
    y: int,
    items: list[tuple[str, str]],
    index: int,
) -> None:
    """A list with one line lit: ``(key, label)`` per item.

    The chosen line is drawn in the accent with a blade in front of it; the rest
    are ash. That is the whole of the menu language, and it is the same in the
    title, the pause and the shop, so the player learns it once.
    """
    for row, (key, label) in enumerate(items):
        chosen = row == index
        marker = "►" if chosen else " "
        line = f"{marker} {key:<2} {label}"
        style = parse_style(f"bold {BONE}") if chosen else parse_style(ASH)
        buffer.text(x, y + row, line, style)
