"""Cut the battle sprites out of the two alpha sheets.

The sheets in ``grafiken_kampfsystem/*_alpha.png`` are the exported animation
sets: one block per actor, a lattice of poses inside it, and a real alpha
channel -- so the background is *transparent* rather than near-black, and a pose
is exactly the pixels that have alpha. That is what this cuts.

A block's poses are found by their own lattice: the columns and rows of opaque
pixels, which are separated by gaps that are genuinely empty. The pose wanted is
picked off that lattice rather than counted off a division of the region, so a
block that is five frames wide and a block that is nine frames wide both work.

The arena draws one pose per actor: the monsters facing the viewer and the
heroes from behind. Everything else on the sheets -- the walk cycles, the attack
frames -- stays where it is until the attack animation wants it.

    python tools/cut_sprites.py ~/Vibecoding/grafiken_kampfsystem
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QImage

__all__ = ["SHEETS", "cut_all", "main"]

#: The game's own sprite folder, beside the fonts and the sounds: a sprite
#: travels with the game for the same reason the font does.
HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "src" / "neverdeads_revenge" / "desktop" / "sprites"

MONSTERS = "gamesprites_monsters_alpha.png"
HEROES = "gamesprites_neverdeads_revenge_alpha.png"

#: ``(sheet, x0, y0, x1, y1, column, row)``: the region is the actor's block of
#: poses -- generously, the lattice inside it is what decides where the frames
#: actually are -- and the column and row pick the pose out of that lattice.
#:
#: The monsters are cut from the front block (they face the hero, who stands
#: below them on screen) and the heroes from the back block (they face away, at
#: the monsters). Row 0 is the idle row on both sheets.
SHEETS: dict[str, tuple[str, int, int, int, int, int, int]] = {
    "ghoul": (MONSTERS, 20, 70, 512, 190, 0, 0),
    "skeleton": (MONSTERS, 800, 70, 1300, 190, 0, 0),
    "viper": (MONSTERS, 20, 400, 512, 520, 0, 0),
    "ooze": (MONSTERS, 800, 400, 1300, 520, 0, 0),
    "mound": (MONSTERS, 16, 736, 380, 856, 0, 0),
    "hunter": (MONSTERS, 556, 740, 936, 860, 0, 0),
    "wraith": (MONSTERS, 1056, 740, 1400, 860, 0, 0),
    # The heroes: the *back* block's idle row, which is where a hero is drawn
    # facing away from the player and at the monsters.
    "Noxx": (HEROES, 878, 66, 1170, 176, 0, 0),
    "Yeti": (HEROES, 878, 396, 1170, 506, 0, 0),
    "Walkyrion": (HEROES, 878, 736, 1170, 846, 0, 0),
}

#: The cell the sheets state for every block: one pose is 96 x 128 pixels,
#: whatever the art inside it happens to fill.
CELL_W = 96
CELL_H = 128
#: How far in from a block's edge to start looking: the sheets put a margin
#: around each block, and a margin is not a pose.
FRAME = 6
#: Pixels trimmed off the found box, so a sprite does not carry a hairline of
#: its neighbour's glow.
INSET = 1


def opaque(image: QImage, x: int, y: int) -> bool:
    return image.pixelColor(x, y).alpha() > 8


def occupied(image: QImage, x: int, y: int) -> bool:
    return opaque(image, x, y)


def find_box(image: QImage, x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
    """The opaque pixels inside a cell, as a tight box."""
    left, top, right, bottom = x1, y1, x0, y0
    for y in range(y0, y1):
        for x in range(x0, x1):
            if occupied(image, x, y):
                left, right = min(left, x), max(right, x)
                top, bottom = min(top, y), max(bottom, y)
    if left > right or top > bottom:
        raise ValueError(f"nothing to cut at {(x0, y0, x1, y1)}")
    return (left + INSET, top + INSET, right - INSET, bottom - INSET)


def first_pose(
    image: QImage, x0: int, y0: int, x1: int, y1: int
) -> tuple[int, int, int, int]:
    """The first pose of a block, on the sheet's own cell size.

    The poses *touch*: a row of glows is a row of pixels with no transparent
    column between two of them, so counting gaps gets one frame 279 pixels wide
    and two rows tall. The sheets state their cell size -- ``96 x 128`` on every
    block -- so the cell is taken from the block's first drawn pixel and the art
    is trimmed inside it, which needs no gaps at all.
    """
    left = top = None
    for y in range(y0, y1):
        for x in range(x0, x1):
            if occupied(image, x, y):
                left, top = x, y
                break
        if left is not None:
            break
    if left is None or top is None:
        raise ValueError(f"nothing at all in {(x0, y0, x1, y1)}")
    return find_box(
        image,
        left,
        top,
        min(x1, left + CELL_W),
        min(y1, top + CELL_H),
    )


def cut_one(image: QImage, region: tuple[int, int, int, int, int, int]) -> QImage:
    """One pose: the first cell of the block, trimmed to what is drawn."""
    x0, y0, x1, y1, _column, _row = region
    box = first_pose(image, x0, y0, x1, y1)
    return image.copy(
        box[0], box[1], box[2] - box[0] + 1, box[3] - box[1] + 1
    ).convertToFormat(QImage.Format.Format_ARGB32)


def cut_all(source: Path, out: Path = OUT) -> dict[str, QImage]:
    """Cut every actor's idle pose. Returns what was cut, for a report."""
    sheets = {MONSTERS: QImage(str(source / MONSTERS)), HEROES: QImage(str(source / HEROES))}
    out.mkdir(parents=True, exist_ok=True)
    cut: dict[str, QImage] = {}
    for name, region in SHEETS.items():
        sprite = cut_one(sheets[region[0]], region[1:])
        sprite.save(str(out / f"{name}.png"))
        cut[name] = sprite
    return cut


def contact_sheet(cut: dict[str, QImage]) -> QImage:
    """All of them in a row, so the cutting can be checked at a glance."""
    from PySide6.QtGui import QColor, QFont, QPainter

    height = max(sprite.height() for sprite in cut.values()) + 30
    width = sum(sprite.width() + 16 for sprite in cut.values()) + 16
    sheet = QImage(width, height, QImage.Format.Format_ARGB32)
    sheet.fill(QColor("#1e1e26"))  # a floor tone: a halo or a box would show
    painter = QPainter(sheet)
    font = QFont("DejaVu Sans Mono")
    font.setPixelSize(13)
    painter.setFont(font)
    painter.setPen(QColor("#c8c8c8"))
    x = 8
    for name, sprite in cut.items():
        painter.drawImage(x, height - 26 - sprite.height(), sprite)
        painter.drawText(x, height - 8, name)
        x += sprite.width() + 16
    painter.end()
    return sheet


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    source = Path(args[0] if args else "~/Vibecoding/grafiken_kampfsystem").expanduser()
    preview = Path(args[1]) if len(args) > 1 else Path("_preview.png")
    # A Qt *Gui* application, because painting text onto the preview needs one;
    # no window is opened (set QT_QPA_PLATFORM=offscreen without a display).
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    cut = cut_all(source)
    for name, sprite in cut.items():
        print(f"{name:12s} {sprite.width():3d} x {sprite.height():3d}")
    contact_sheet(cut).save(str(preview))
    print(f"preview: {preview}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
