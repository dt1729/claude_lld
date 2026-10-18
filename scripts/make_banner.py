"""Render the README banner in light and dark variants.

The banner states what the plugin does by showing it: the wordmark, one line of positioning,
and a terminal line of the gate actually refusing a write. A picture of the behaviour beats
an adjective about it.

Usage:
    python make_banner.py [--out docs/assets]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFont

WIDTH: Final = 2400
HEIGHT: Final = 700
PAD: Final = 140

FONT_DIR: Final = Path("C:/Windows/Fonts")
BOLD: Final = FONT_DIR / "segoeuib.ttf"
REGULAR: Final = FONT_DIR / "segoeui.ttf"
MONO: Final = FONT_DIR / "consola.ttf"


@dataclass(frozen=True, slots=True)
class Theme:
    """One colour scheme. GitHub swaps between these by prefers-color-scheme."""

    name: str
    background: str
    wordmark: str
    tagline: str
    rule: str
    panel: str
    deny: str
    muted: str


DARK: Final = Theme(
    name="dark",
    background="#0d1117",
    wordmark="#e6edf3",
    tagline="#8b949e",
    rule="#30363d",
    panel="#161b22",
    deny="#f85149",
    muted="#6e7681",
)

LIGHT: Final = Theme(
    name="light",
    background="#ffffff",
    wordmark="#1f2328",
    tagline="#59636e",
    rule="#d1d9e0",
    panel="#f6f8fa",
    deny="#cf222e",
    muted="#818b98",
)


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def _draw_cross(draw: ImageDraw.ImageDraw, *, x: int, y: int, size: int, colour: str) -> None:
    """A refusal mark, drawn from two strokes so no font has to supply the glyph."""
    half = size // 2
    draw.line([(x - half, y - half), (x + half, y + half)], fill=colour, width=7)
    draw.line([(x - half, y + half), (x + half, y - half)], fill=colour, width=7)


def render(theme: Theme) -> Image.Image:
    """Draw one variant. Sizes are absolute so both variants line up exactly."""
    image = Image.new("RGB", (WIDTH, HEIGHT), theme.background)
    draw = ImageDraw.Draw(image)

    wordmark = _font(BOLD, 124)
    tagline = _font(REGULAR, 54)
    mono = _font(MONO, 44)
    mono_small = _font(MONO, 36)

    y = PAD
    draw.text((PAD, y), "lld-seed", font=wordmark, fill=theme.wordmark)
    y += 168

    draw.text(
        (PAD, y),
        "Your coding agent designs before it writes, or it does not write.",
        font=tagline,
        fill=theme.tagline,
    )
    y += 96

    draw.line([(PAD, y), (WIDTH - PAD, y)], fill=theme.rule, width=3)
    y += 56

    # The gate refusing a write: the product's actual behaviour, not a claim about it.
    panel_top, panel_bottom = y, y + 190
    draw.rounded_rectangle(
        [(PAD, panel_top), (WIDTH - PAD, panel_bottom)], radius=18, fill=theme.panel
    )

    text_x = PAD + 48
    # Drawn rather than typed: Consolas has no U+2717, and a missing glyph renders as tofu.
    _draw_cross(draw, x=text_x + 4, y=panel_top + 52, size=34, colour=theme.deny)
    draw.text(
        (text_x + 60, panel_top + 36),
        "Write  src/ledger/balance.py",
        font=mono,
        fill=theme.wordmark,
    )
    draw.text(
        (text_x + 60, panel_top + 104),
        "no contract — write docs/contracts/ledger.balance.md first",
        font=mono_small,
        fill=theme.muted,
    )

    return image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("docs/assets"))
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    for theme in (DARK, LIGHT):
        target = args.out / f"banner-{theme.name}.png"
        render(theme).save(target, optimize=True)
        print(f"wrote {target.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
