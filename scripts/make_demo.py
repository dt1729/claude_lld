"""Render the lld-seed demo: an editor window where the plugin rewrites the code.

Frames are HTML, screenshotted by headless Chrome, assembled by Pillow and transcoded by
ffmpeg. The design lives in ``docs/assets/editor.html`` as CSS, so restyling is an edit there
rather than a hunt through drawing coordinates. Pipeline adapted from Parth1811/JevFlow.

The story runs inside one editor that never resets: an agent types an undesigned square
module, the gate refuses the write, a contract is written, and the module is rewritten into
the designed version. The panel text is what ``require_contract.py`` actually emits.

Usage:
    python make_demo.py [--theme dark|light] [--still N] [--clip FROM TO]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from logsetup import configure

log = logging.getLogger("lld.demo")

WIDTH: Final = 1280
HEIGHT: Final = 720
FPS: Final = 15
CHARS_PER_FRAME: Final = 7

CHROME_CANDIDATES: Final = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)

Token = tuple[str, str]

PROJECT: Final = "shapes/"
TABS_CODE: Final = ["square.py"]
TABS_BOTH: Final = ["square.py", "shapes.square.md"]

KEYWORDS: Final = frozenset(
    {
        "def",
        "class",
        "return",
        "from",
        "import",
        "if",
        "raise",
        "None",
        "True",
        "False",
        "self",
        "float",
        "int",
        "str",
        "property",
        "dataclass",
    }
)


TRIPLE_QUOTES: Final = ('"""', "'''")


def _scan_comment(source: str, index: int) -> tuple[Token, int] | None:
    """A # comment, running to the end of its line."""
    if source[index] != "#":
        return None
    end = source.find("\n", index)
    end = len(source) if end == -1 else end
    return ("com", source[index:end]), end


def _scan_string(source: str, index: int) -> tuple[Token, int] | None:
    """A quoted run, triple-quoted when it opens that way."""
    if source[index] not in "\"'":
        return None
    triple = source[index : index + 3]
    quote = triple if triple in TRIPLE_QUOTES else source[index]
    end = source.find(quote, index + len(quote))
    end = len(source) if end == -1 else end + len(quote)
    return ("str", source[index:end]), end


def _scan_word(source: str, index: int, previous: str) -> tuple[Token, int] | None:
    """An identifier, keyword or number. ``previous`` is what decides a definition name."""
    if not (source[index].isalnum() or source[index] == "_"):
        return None
    end = index
    while end < len(source) and (source[end].isalnum() or source[end] == "_"):
        end += 1
    word = source[index:end]
    if word in KEYWORDS:
        style = "kw"
    elif word[0].isdigit():
        style = "num"
    elif previous in ("def", "class"):
        style = "def"
    else:
        style = "pl"
    return (style, word), end


def _tok(source: str) -> list[Token]:
    """Tokenise Python crudely, for colour only.

    A real lexer is not needed: the demo renders fixed snippets, and a wrong colour on an
    unusual construct costs nothing. Keeping this small beats adding a dependency.

    Split into one scanner per construct because the single-function version tripped this
    repo's own complexity limit, which is the rule working as intended.
    """
    out: list[Token] = []
    buffer = ""
    index = 0
    while index < len(source):
        previous = out[-1][1].strip() if out else ""
        scanned = (
            _scan_comment(source, index)
            or _scan_string(source, index)
            or _scan_word(source, index, previous)
        )
        if scanned is None:
            buffer += source[index]
            index += 1
            continue
        if buffer:
            out.append(("pl", buffer))
            buffer = ""
        token, index = scanned
        out.append(token)
    if buffer:
        out.append(("pl", buffer))
    return out


NAIVE: Final = """def area(s):
    return s * s


def perimeter(s):
    return 4 * s
"""

DESIGNED: Final = '''"""A square, whose side length cannot be zero or negative."""

from dataclasses import dataclass


class InvalidSideError(ValueError):
    """A side length that is not strictly positive."""


@dataclass(frozen=True, slots=True)
class Square:
    """A square. side_m is metres, and is always > 0."""

    side_m: float

    def __post_init__(self) -> None:
        if self.side_m <= 0:
            raise InvalidSideError(f"side must be > 0, got {self.side_m}")

    @property
    def area_m2(self) -> float:
        return self.side_m ** 2

    @property
    def perimeter_m(self) -> float:
        return 4 * self.side_m
'''

CONTRACT: Final = """# Contract: shapes.square

**Status:** accepted

## Responsibility

Represent a square with a validated side length.

## Interface

```python
Square(side_m: float)
  .area_m2      -> float
  .perimeter_m  -> float
```

side_m is metres and always > 0, so no caller revalidates it.

## Seam

None. A value type over one number; nothing varies.

## Dependencies

- **May import:** stdlib only

## Errors

| Type | Raised when |
| --- | --- |
| InvalidSideError | side_m <= 0 |

## Observability

No logging. Pure computation, no I/O.

## Tests

- area of a unit square is 1
- perimeter of a unit square is 4
- a zero side raises InvalidSideError
- a negative side raises InvalidSideError

## Deletion test

Without it every caller revalidates the side, and one of them forgets.
"""


@dataclass(frozen=True, slots=True)
class Frame:
    """One rendered frame, repeated ``hold`` times in the output."""

    payload: dict[str, Any]
    hold: int = 1


def _base(**over: Any) -> dict[str, Any]:
    scene: dict[str, Any] = {
        "project": PROJECT,
        "tabs": TABS_CODE,
        "activeTab": 0,
        "tokens": [],
        "panelTitle": "lld-seed",
        "panel": [],
        "status": [("ruff", "pending"), ("mypy", "pending"), ("pytest", "pending")],
        "verdict": ("", "pending"),
        "minLines": 22,
        "caption": "",
    }
    scene.update(over)
    return scene


def _p(style: str, text: str) -> str:
    return f'<span class="{style}">{text}</span>'


def typing_frames(source: str, *, every: int = CHARS_PER_FRAME, **scene: Any) -> list[Frame]:
    """Frames revealing ``source`` progressively, with a blinking caret."""
    tokens = _tok(source)
    frames: list[Frame] = []
    shown = 0
    step = 0
    while shown < len(source):
        shown = min(len(source), shown + every)
        frames.append(
            Frame(
                _base(
                    tokens=tokens, reveal=shown, caret=True, caretOff=(step // 4) % 2 == 1, **scene
                )
            )
        )
        step += 1
    return frames


def hold_frames(seconds: float, **scene: Any) -> list[Frame]:
    """A still scene, held for a number of seconds."""
    return [Frame(_base(**scene), hold=max(1, round(seconds * FPS)))]


def storyboard(theme: str) -> list[Frame]:
    """The whole demo, as frames."""
    naive = _tok(NAIVE)
    designed = _tok(DESIGNED)
    contract = _tok(CONTRACT)
    t: dict[str, Any] = {"theme": theme}
    frames: list[Frame] = []

    watching = [_p("dim", "watching Write and Edit"), "", _p("dim", "no contract on file")]
    caption_one = "An agent writes what runs."

    frames += hold_frames(0.8, **t, panel=watching, caret=True, caption=caption_one)
    frames += typing_frames(NAIVE, **t, panel=watching, caption=caption_one)
    frames += hold_frames(1.1, **t, tokens=naive, panel=watching, caret=True, caption=caption_one)

    deny = [
        _p("deny", "DENIED"),
        "",
        _p("fg", "No contract for"),
        _p("accent", "src/shapes/square.py"),
        "",
        _p("dim", "This is a new module, so the"),
        _p("dim", "design step has not happened"),
        _p("dim", "yet. Write the contract first."),
    ]
    frames += hold_frames(
        3.4,
        **t,
        tokens=naive,
        panel=deny,
        verdict=("write refused", "bad"),
        caption="The gate refuses the write. <b>Nothing reaches disk.</b>",
    )

    drafting = [
        _p("amber", "waiting for a contract"),
        "",
        _p("dim", "8 sections, structure checked"),
    ]
    frames += typing_frames(
        CONTRACT,
        every=30,
        **t,
        tabs=TABS_BOTH,
        activeTab=1,
        panel=drafting,
        verdict=("drafting", "run"),
        caption="So the design is written first.",
    )
    frames += hold_frames(
        1.5,
        **t,
        tabs=TABS_BOTH,
        activeTab=1,
        tokens=contract,
        panel=[
            _p("allow", "contract accepted"),
            "",
            _p("dim", "responsibility, interface, seam,"),
            _p("dim", "errors, tests, deletion test"),
        ],
        verdict=("contract accepted", "ok"),
        caption="So the design is written first.",
    )

    rewriting = "Now the module is rewritten."
    frames += hold_frames(
        0.9,
        **t,
        tabs=TABS_BOTH,
        tokens=naive,
        faded=True,
        panel=[_p("dim", "rewriting square.py")],
        verdict=("rewriting", "run"),
        caption=rewriting,
    )
    frames += typing_frames(
        DESIGNED,
        **t,
        tabs=TABS_BOTH,
        panel=[
            _p("dim", "rewriting square.py"),
            "",
            _p("dim", "frozen value type"),
            _p("dim", "validated side length"),
            _p("dim", "error named for its condition"),
        ],
        verdict=("rewriting", "run"),
        caption=rewriting,
    )

    allowed = [_p("allow", "ALLOWED"), "", _p("dim", "0 findings, all cleared (1 ms)")]
    green = [("ruff", "ok"), ("mypy", "ok"), ("pytest", "4 passed")]
    for stage in (
        [("ruff", "run"), ("mypy", "pending"), ("pytest", "pending")],
        [("ruff", "ok"), ("mypy", "run"), ("pytest", "pending")],
        [("ruff", "ok"), ("mypy", "ok"), ("pytest", "run")],
        green,
    ):
        frames += hold_frames(
            0.5,
            **t,
            tabs=TABS_BOTH,
            tokens=designed,
            panel=allowed,
            status=stage,
            verdict=("write allowed", "ok"),
            caption=rewriting,
        )

    frames += hold_frames(
        2.4,
        **t,
        tabs=TABS_BOTH,
        tokens=designed,
        panel=allowed,
        status=green,
        verdict=("write allowed", "ok"),
        caption="A negative side is now <b>unrepresentable</b>.",
    )
    frames += hold_frames(
        3.0,
        **t,
        tabs=TABS_BOTH,
        tokens=designed,
        status=green,
        panel=[
            _p("allow", "every gate green"),
            "",
            _p("deny", "and still worth reading:"),
            _p("dim", "naming, whether two types are"),
            _p("dim", "really one, whether the contract"),
            _p("dim", "still matches the code"),
        ],
        verdict=("write allowed", "ok"),
        caption="Structure is mechanical. <b>Meaning still needs a reader.</b>",
    )

    frames.append(
        Frame(
            {
                "theme": theme,
                "layout": "title",
                "title": "Design before code. Enforced.",
                "sub": "A Claude Code plugin for Python repositories.",
                "commands": [
                    "$ claude plugin marketplace add dt1729/claude_lld",
                    "$ claude plugin install lld-seed@dt1729",
                ],
            },
            hold=round(4.0 * FPS),
        )
    )
    return frames


def find_chrome() -> str:
    """The browser used to screenshot frames, from CHROME or the usual locations."""
    override = os.environ.get("CHROME")
    if override:
        return override
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("no Chrome found; set CHROME to its path")


def shoot(
    chrome: str, template: str, payload: dict[str, Any], work: Path, index: int
) -> Image.Image:
    """Render one frame via headless Chrome."""
    marker = "<!--DATA-->"
    if marker not in template:
        raise RuntimeError("editor.html is missing the data marker")
    page = work / f"f{index:05d}.html"
    png = work / f"f{index:05d}.png"
    tag = f"<script>window.SCENE={json.dumps(payload)};</script>"
    page.write_text(template.replace(marker, tag, 1), encoding="utf-8")
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--window-size={WIDTH},{HEIGHT}",
            "--virtual-time-budget=700",
            f"--screenshot={png}",
            page.as_uri(),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with Image.open(png) as shot_image:
        return shot_image.convert("RGB").copy()


def _to_wsl_path(path: Path) -> str:
    """Translate C:/x/y into /mnt/c/x/y so a WSL binary can read a Windows path."""
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix()[len(resolved.drive) :]
    return f"/mnt/{drive}{rest}" if drive else resolved.as_posix()


def _ffmpeg_runner() -> tuple[list[str], bool] | None:
    """The ffmpeg command prefix, and whether paths need WSL translation."""
    direct = shutil.which("ffmpeg")
    if direct:
        return [direct], False
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if wsl is None:
        return None
    probe = subprocess.run(
        [wsl, "--", "which", "ffmpeg"], capture_output=True, text=True, check=False
    )
    if probe.returncode == 0 and probe.stdout.strip():
        return [wsl, "--", "ffmpeg"], True
    return None


def encode(sequence: Path, target: Path) -> bool:
    """Transcode a numbered PNG sequence to MP4. Returns whether ffmpeg ran."""
    runner = _ffmpeg_runner()
    if runner is None:
        log.warning("ffmpeg not found on PATH or in WSL; skipping %s", target.name)
        return False
    prefix, translate = runner
    pattern = sequence / "%05d.png"
    subprocess.run(
        [
            *prefix,
            "-y",
            "-v",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            _to_wsl_path(pattern) if translate else str(pattern),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            _to_wsl_path(target) if translate else str(target),
        ],
        check=True,
    )
    return True


def render(frames: list[Frame], out: Path, stem: str) -> None:
    """Render frames to GIF and MP4 under ``out``."""
    template = (out / "editor.html").read_text(encoding="utf-8")
    chrome = find_chrome()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        sequence = work / "seq"
        sequence.mkdir()

        images: list[Image.Image] = []
        durations: list[int] = []
        counter = 0
        for index, frame in enumerate(frames):
            image = shoot(chrome, template, frame.payload, work, index)
            images.append(image)
            durations.append(int(1000 / FPS) * frame.hold)
            for _ in range(frame.hold):
                image.save(sequence / f"{counter:05d}.png")
                counter += 1
        log.info("%d scenes rendered as %d frames (%.1fs)", len(frames), counter, counter / FPS)

        palettes = [i.quantize(colors=96, method=Image.Quantize.MEDIANCUT) for i in images]
        gif = out / f"{stem}.gif"
        palettes[0].save(
            gif,
            save_all=True,
            append_images=palettes[1:],
            duration=durations,
            loop=0,
            optimize=True,
        )
        log.info("wrote %s (%.1f MB)", gif.name, gif.stat().st_size / 1e6)
        if encode(sequence, out / f"{stem}.mp4"):
            log.info("wrote %s.mp4", stem)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", default="dark", choices=["dark", "light"])
    parser.add_argument("--out", type=Path, default=Path("docs/assets"))
    parser.add_argument("--still", type=int, default=None, help="render only frame N")
    parser.add_argument(
        "--clip",
        type=int,
        nargs=2,
        metavar=("FROM", "TO"),
        help="render only frames FROM..TO, for review",
    )
    parser.add_argument("--log-level", default=None)
    args = parser.parse_args(argv)
    configure(level=args.log_level, log_file=None)

    frames = storyboard(args.theme)
    log.info("storyboard: %d scenes, %.1fs", len(frames), sum(f.hold for f in frames) / FPS)

    if args.still is not None:
        template = (args.out / "editor.html").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            image = shoot(find_chrome(), template, frames[args.still].payload, Path(tmp), 0)
        target = args.out / "_still.png"
        image.save(target)
        log.info("wrote %s (frame %d of %d)", target.name, args.still, len(frames))
        return 0

    if args.clip:
        start, end = args.clip
        render(frames[start:end], args.out, "_clip")
        return 0

    render(frames, args.out, "demo" if args.theme == "dark" else "demo-light")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
