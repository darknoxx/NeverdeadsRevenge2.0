#!/usr/bin/env python3
"""Turn a painted sprite into pixel art, at the size it already has.

The sheets are paintings: five thousand colours in an eighty-four-pixel-wide
picture, every edge soft, and a haze of half-transparent pixels around the
whole figure. Which is a fine thing to look at and not a thing that reads as
*pixels* -- so this is the conversion, in five passes, and each of them is one
sentence about what pixel art is:

* **the haze goes.** Alpha is cut to on or off at a threshold. What is left is
  the figure and the strands of its aura, and the soft ring between them -- the
  anti-aliasing an artist never draws -- is gone.
* **the palette shrinks.** Median cut over what survived, to a couple of dozen
  colours, and every pixel snapped to its nearest. This is the part that makes
  the shading *flat*: a painted cheek becomes one colour with a hard edge
  against the next, which is how a pixel face is drawn.
* **the noise goes too.** This is the pass the first two of them miss: a
  painted pixel and its neighbour are *almost* the same colour, so snapping each
  one on its own gives a mosaic of near-misses -- salt and pepper, and a figure
  that has dissolved into it. So the palette indices are smoothed: every pixel
  takes the colour most of its neighbours have, twice. That is what turns a
  hundred thousand half-differences into flat regions with edges, which is what
  the eye reads as pixel *drawing* rather than as a photograph of a small thing.
* **the edge gets a line.** Every transparent pixel beside the figure takes the
  neighbour's own colour, darkened. Painted figures are cut out with no outline;
  pixel figures are drawn with one, and a one-pixel dark edge is also what hides
  the staircase that quantizing leaves on a diagonal.
* **and it can be chunked.** `--block 2` takes every two-by-two square down to
  one colour and back up, which is a much stronger pixel look at the same output
  size -- half the detail, four times the pixels that look deliberate.

    python tools/pixelate.py ~/Vibecoding/grafiken_kampfsystem/noxx_front.png \\
        --out ~/Vibecoding/grafiken_kampfsystem/pixeltest

One file at a time, or a whole folder with `--all`. The output keeps the input's
size unless `--block` says otherwise, and nothing here ever touches the sheets
the game ships: this writes where it is told to write.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

__all__ = ["median_cut", "pixelate"]


def _pixels(image: QImage, alpha: int) -> list[tuple[int, int, int]]:
    """Every colour in the picture that the threshold keeps."""
    out: list[tuple[int, int, int]] = []
    for y in range(image.height()):
        for x in range(image.width()):
            ink = image.pixelColor(x, y)
            if ink.alpha() >= alpha:
                out.append((ink.red(), ink.green(), ink.blue()))
    return out


def median_cut(colours: list[tuple[int, int, int]], count: int) -> list[tuple[int, int, int]]:
    """``count`` colours that stand in for ``colours``, by cutting the worst box.

    Median cut and not a fixed palette: the art decides its own colours, which
    is the whole reason a painted sheet can be quantized without turning into
    somebody else's picture. The box with the widest channel is the one that is
    carrying the most variety, so it is the one worth splitting in two.
    """
    boxes = [colours]
    while len(boxes) < count:
        widest, widest_range = None, 0
        for index, box in enumerate(boxes):
            if len(box) < 2:
                continue
            spread = max(
                max(box, key=lambda c: c[channel])[channel]
                - min(box, key=lambda c: c[channel])[channel]
                for channel in range(3)
            )
            if spread > widest_range:
                widest, widest_range = index, spread
        if widest is None:
            break
        box = boxes.pop(widest)
        channel = max(
            range(3),
            key=lambda i: max(box, key=lambda c: c[i])[i] - min(box, key=lambda c: c[i])[i],
        )
        box.sort(key=lambda c: c[channel])
        middle = len(box) // 2
        boxes += [box[:middle], box[middle:]]
    return [
        (
            round(sum(c[0] for c in box) / len(box)),
            round(sum(c[1] for c in box) / len(box)),
            round(sum(c[2] for c in box) / len(box)),
        )
        for box in boxes
        if box
    ]


def _nearest(palette, ink) -> tuple[int, int, int]:
    return min(
        palette,
        key=lambda c: (c[0] - ink[0]) ** 2 + (c[1] - ink[1]) ** 2 + (c[2] - ink[2]) ** 2,
    )


def _smoothed(flat: QImage, palette, passes: int) -> QImage:
    """Every pixel takes the colour most of its neighbours have.

    Twice, because once is a median filter and twice is a *decision*: one pass
    takes the single stray pixels out, and the second takes out the two-pixel
    strays those were hiding behind. More than three and the palette starts
    eating its own edges.
    """
    look = {(r, g, b): i for i, (r, g, b) in enumerate(palette)}
    width, height = flat.width(), flat.height()
    index = [
        [
            look.get(
                (
                    flat.pixelColor(x, y).red(),
                    flat.pixelColor(x, y).green(),
                    flat.pixelColor(x, y).blue(),
                ),
                -1,
            )
            if flat.pixelColor(x, y).alpha() >= 128
            else -1
            for x in range(width)
        ]
        for y in range(height)
    ]
    for _ in range(passes):
        following = [row[:] for row in index]
        for y in range(height):
            for x in range(width):
                if index[y][x] < 0:
                    continue
                votes: Counter[int] = Counter()
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < height and 0 <= nx < width and index[ny][nx] >= 0:
                            votes[index[ny][nx]] += 1
                best, count = max(votes.items(), key=lambda pair: (pair[1], -abs(pair[0] - index[y][x])))
                if count >= 4:
                    following[y][x] = best
        index = following

    out = QImage(width, height, QImage.Format.Format_ARGB32)
    out.fill(QColor(0, 0, 0, 0))
    for y in range(height):
        for x in range(width):
            if index[y][x] >= 0:
                r, g, b = palette[index[y][x]]
                out.setPixelColor(x, y, QColor(r, g, b, 255))
    return out


def pixelate(
    image: QImage,
    *,
    colours: int = 24,
    alpha: int = 110,
    outline: bool = True,
    block: int = 1,
    smooth: int = 2,
) -> QImage:
    """The painted picture again, as pixels."""
    width, height = image.width(), image.height()
    if block > 1:
        # Every square down to its average and the picture taken back up: the
        # chunking is a *sampling* and not a blur, so the block edges stay hard.
        small = image.scaled(
            width // block,
            height // block,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
    else:
        small = image
    assert small.width() > 0 and small.height() > 0

    kept = Counter(_pixels(small, alpha))
    palette = median_cut([c for c in kept for _ in range(min(kept[c], 64))], colours)

    flat = QImage(small.width(), small.height(), QImage.Format.Format_ARGB32)
    flat.fill(QColor(0, 0, 0, 0))
    for y in range(small.height()):
        for x in range(small.width()):
            ink = small.pixelColor(x, y)
            if ink.alpha() < alpha:
                continue
            r, g, b = _nearest(palette, (ink.red(), ink.green(), ink.blue()))
            flat.setPixelColor(x, y, QColor(r, g, b, 255))

    if smooth:
        flat = _smoothed(flat, palette, smooth)

    if outline:
        flat = _outlined(flat)

    if block > 1:
        # Back up with the *nearest* filter, so a block stays a square block
        # instead of a soft patch: this is the whole point of the flag.
        flat = flat.scaled(
            width,
            height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
    return flat


def _outlined(image: QImage) -> QImage:
    """A one-pixel dark edge around whatever is there.

    The neighbour's own colour and not black: an aura outlined in black is a
    sticker, and a strand of petrol outlined in dark petrol is a *drawn*
    strand of petrol. This is the pass that makes the rest read as pixel art,
    because it is the pass an artist would have done first.
    """
    out = QImage(image.width(), image.height(), QImage.Format.Format_ARGB32)
    out.fill(QColor(0, 0, 0, 0))
    for y in range(image.height()):
        for x in range(image.width()):
            ink = image.pixelColor(x, y)
            if ink.alpha() >= 128:
                out.setPixelColor(x, y, ink)
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbour = image.pixelColor(x + dx, y + dy) if 0 <= x + dx < image.width() and 0 <= y + dy < image.height() else None
                if neighbour is None or neighbour.alpha() < 128:
                    continue
                out.setPixelColor(
                    x, y, neighbour.darker(230)
                )
                break
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Painted sprite in, pixel art out.")
    parser.add_argument("source", nargs="?", help="one PNG, or a folder with --all")
    parser.add_argument("--out", default=None, help="where to write (default: pixeltest beside the source)")
    parser.add_argument("--all", action="store_true", help="every PNG in the folder")
    parser.add_argument("--colours", type=int, default=24, help="how many the palette holds")
    parser.add_argument("--alpha", type=int, default=110, help="below this a pixel is not there")
    parser.add_argument("--block", type=int, default=1, help="chunk size: 2 is half the grid")
    parser.add_argument("--no-outline", action="store_true")
    parser.add_argument(
        "--smooth",
        type=int,
        default=2,
        help="majority passes over the palette indices: the noise filter",
    )
    args = parser.parse_args(argv)

    source = Path(args.source or "~/Vibecoding/grafiken_kampfsystem").expanduser()
    out = Path(args.out).expanduser() if args.out else source.parent / "pixeltest"
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(source.glob("*.png")) if args.all or source.is_dir() else [source]
    if not files:
        print(f"nothing to do in {source}")
        return 1
    for path in files:
        image = QImage(str(path))
        if image.isNull():
            print(f"not a picture: {path}")
            return 1
        made = pixelate(
            image,
            colours=args.colours,
            alpha=args.alpha,
            outline=not args.no_outline,
            block=args.block,
            smooth=args.smooth,
        )
        target = out / f"{path.stem}"
        target = target.with_name(f"{target.name}{'_block' + str(args.block) if args.block > 1 else ''}.png")
        made.save(str(target))
        print(f"{path.name:24s} -> {target}  {made.width()}x{made.height()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
