"""Render the lld-seed demo: HTML frames to PNG to GIF to MP4.

The design lives in ``docs/assets/frame.html`` rather than in drawing coordinates, so it can
be restyled by editing CSS. Each scene is injected into that page, screenshotted with
headless Chrome, assembled by Pillow, and transcoded by ffmpeg when it is available.

The scenes show the gate's actual decisions, transcribed from real runs: the deny text is
the message ``require_contract.py`` emits, not a dramatisation of it.

Usage:
    python make_demo.py [--theme dark|light] [--out docs/assets]
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from logsetup import configure

log = logging.getLogger("lld.demo")

WIDTH: Final = 1280
HEIGHT: Final = 720
FPS: Final = 25

#: Where Chrome usually lives on Windows. CHROME overrides it.
CHROME_CANDIDATES: Final = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)


@dataclass(frozen=True, slots=True)
class Scene:
    """One frame, held on screen for ``hold`` seconds."""

    step: str
    title: str
    sub: str
    lines: list[str]
    hold: float
    foot_left: str = ""
    foot_right: str = ""
    layout: str = "default"

    def payload(self, theme: str) -> dict[str, Any]:
        return {
            "theme": theme,
            "layout": self.layout,
            "step": self.step,
            "title": self.title,
            "sub": self.sub,
            "lines": self.lines,
            "footLeft": self.foot_left,
            "footRight": self.foot_right,
        }


@dataclass(frozen=True, slots=True)
class Storyboard:
    """The whole demo. Separate from rendering so the script is editable without reading it."""

    scenes: list[Scene] = field(default_factory=list)


def _s(style: str, text: str) -> str:
    """One styled run of text. The styles are defined in frame.html, not here."""
    return f'<span class="{style}">{text}</span>'


def _row(label: str, note: str) -> str:
    """A contract section and its one-line gloss, aligned in the panel."""
    return _s("fg", f"  {label:<15}") + _s("dim", note)


def _check(label: str) -> str:
    """One passing check in the allowed-write panel."""
    return _s("dim", f"  {label:<28}") + _s("allow", "ok")


def _prompt(command: str) -> str:
    """A shell line in the title card."""
    return _s("dim", "$") + " " + _s("fg", command)


def storyboard() -> Storyboard:
    """The demo, in the order a user meets the system."""
    return Storyboard(
        [
            Scene(
                step="the problem",
                title="Your agent writes code that exists.",
                sub="No design, no seams, no tests. It runs, so it looks finished.",
                lines=[
                    _s("dim", '$ claude "add a balance calculator"'),
                    "",
                    _s("fg", "def running_balance(entries):"),
                    _s("fg", "    total = 0"),
                    _s("fg", "    for e in entries:"),
                    _s("fg", "        total += e['amount']"),
                    _s("fg", "    return total"),
                    "",
                    _s("dim", "no types · no tests · no currency check · ships anyway"),
                ],
                hold=4.0,
                foot_left="60 lines later: which currency was that?",
            ),
            Scene(
                step="the gate",
                title="So the write is refused.",
                sub="A PreToolUse hook sees the call before the file exists.",
                lines=[
                    _s("dim", "Write  src/ledger/balance.py"),
                    "",
                    _s("deny", "  DENIED  No contract for src/ledger/balance.py."),
                    "",
                    _s("fg", "  This is a new module, so the design step has not"),
                    _s("fg", "  happened yet. Write docs/contracts/ledger.balance.md"),
                    _s("fg", "  following the new-module skill, then repeat this write."),
                ],
                hold=4.5,
                foot_left="verbatim from require_contract.py",
                foot_right="LLD_GATE=off to disable",
            ),
            Scene(
                step="design first",
                title="Design becomes a file, not a feeling.",
                sub="Eight sections. The gate validates structure; you supply the thinking.",
                lines=[
                    _s("accent", "docs/contracts/ledger.balance.md"),
                    "",
                    _row("Responsibility", "one sentence, and if it needs 'and', split it"),
                    _row("Interface", "invariants, ordering, units, error modes"),
                    _row("Seam", "what varies, and what you rejected"),
                    _row("Dependencies", "what it may import, and who imports it"),
                    _row("Errors", "type, condition, caller response"),
                    _row("Observability", "what is logged, at which level"),
                    _row("Tests", "behaviours through the interface"),
                    _row("Deletion test", "what reappears in callers without it"),
                ],
                hold=5.0,
                foot_right="versioned, so the diff says why an interface changed",
            ),
            Scene(
                step="then code",
                title="Now the write lands.",
                sub="And 26 anti-patterns are checked on the way in.",
                lines=[
                    _s("dim", "Write  src/ledger/balance.py"),
                    "",
                    _s("allow", "  ALLOWED  0 findings, all cleared (1 ms)"),
                    "",
                    _check("frozen value types"),
                    _check("no module-level state"),
                    _check("no import-time work"),
                    _check("errors named per condition"),
                    _check("every log call lazy"),
                ],
                hold=4.0,
                foot_left=".lld/gate.log records every decision",
            ),
            Scene(
                step="honestly",
                title="It raises the floor, not the ceiling.",
                sub="A module that passes every gate still had six defects on review.",
                lines=[
                    _s("allow", "  ruff, mypy --strict, pytest, 26 anti-patterns: all green"),
                    "",
                    _s("deny", "  still wrong:"),
                    _s("fg", "  - running_balance is a noun, not a verb phrase"),
                    _s("fg", "  - currency: str leaves illegal states representable"),
                    _s("fg", "  - Money and Entry are the same type twice"),
                    "",
                    _s("dim", "  Structure is mechanical. Meaning still needs a reader."),
                ],
                hold=5.0,
                foot_right="docs/phase-4-review.md",
            ),
            Scene(
                step="",
                title="Design before code. Enforced.",
                sub="A Claude Code plugin for Python repositories.",
                lines=[
                    _prompt("claude plugin marketplace add dt1729/claude_lld"),
                    _prompt("claude plugin install lld-seed@dt1729"),
                ],
                hold=5.0,
                layout="title",
            ),
        ]
    )


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
    chrome: str, template: str, scene: Scene, theme: str, work: Path, index: int
) -> Image.Image:
    """Render one scene to an image via headless Chrome."""
    tag = f"<script>window.SCENE={json.dumps(scene.payload(theme))};</script>"
    marker = "<!--SCENE_DATA-->"
    if marker not in template:
        raise RuntimeError("frame.html is missing the SCENE_DATA marker")

    page = work / f"scene{index:02d}.html"
    png = work / f"scene{index:02d}.png"
    page.write_text(template.replace(marker, tag, 1), encoding="utf-8")

    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--window-size={WIDTH},{HEIGHT}",
            "--virtual-time-budget=1200",
            f"--screenshot={png}",
            page.as_uri(),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with Image.open(png) as shot:
        return shot.convert("RGB").copy()


def write_gif(frames: list[Image.Image], durations: list[int], target: Path) -> None:
    """Palette-quantise and save. GIF is the fallback when ffmpeg is absent."""
    palettes = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for f in frames]
    palettes[0].save(
        target,
        save_all=True,
        append_images=palettes[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )


def _to_wsl_path(path: Path) -> str:
    """Translate C:/x/y into /mnt/c/x/y so a WSL binary can read a Windows path."""
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix()[len(resolved.drive) :]
    return f"/mnt/{drive}{rest}" if drive else resolved.as_posix()


def _ffmpeg_runner() -> tuple[list[str], bool] | None:
    """The command prefix for ffmpeg, and whether paths must be translated for WSL.

    ffmpeg is frequently absent from PATH on Windows while present inside WSL. Reaching for
    it there beats failing, and beats asking every user to install a second copy.
    """
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


def write_mp4(frames: list[Image.Image], holds: list[float], target: Path, work: Path) -> bool:
    """Transcode to MP4 by repeating each frame for its hold. Returns whether it ran."""
    runner = _ffmpeg_runner()
    if runner is None:
        log.warning("ffmpeg not found on PATH or in WSL; skipping %s", target.name)
        return False
    prefix, translate = runner

    sequence = work / "seq"
    sequence.mkdir(exist_ok=True)
    counter = 0
    for frame, hold in zip(frames, holds, strict=True):
        for _ in range(max(1, round(hold * FPS))):
            frame.save(sequence / f"{counter:05d}.png")
            counter += 1

    pattern = sequence / "%05d.png"
    in_path = _to_wsl_path(pattern) if translate else str(pattern)
    out_path = _to_wsl_path(target) if translate else str(target)
    subprocess.run(
        [
            *prefix,
            "-y",
            "-v",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            in_path,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            out_path,
        ],
        check=True,
    )
    log.info("wrote %s (%d frames, %.1fs)", target.name, counter, counter / FPS)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", default="dark", choices=["dark", "light"])
    parser.add_argument("--out", type=Path, default=Path("docs/assets"))
    parser.add_argument("--log-level", default=None)
    args = parser.parse_args(argv)

    configure(level=args.log_level, log_file=None)

    template = (args.out / "frame.html").read_text(encoding="utf-8")
    chrome = find_chrome()
    board = storyboard()
    args.out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        frames = [
            shoot(chrome, template, scene, args.theme, work, i)
            for i, scene in enumerate(board.scenes)
        ]
        log.info("rendered %d scenes at %dx%d", len(frames), WIDTH, HEIGHT)

        suffix = "" if args.theme == "dark" else "-light"
        holds = [s.hold for s in board.scenes]
        write_gif(frames, [int(h * 1000) for h in holds], args.out / f"demo{suffix}.gif")
        log.info("wrote demo%s.gif", suffix)
        write_mp4(frames, holds, args.out / f"demo{suffix}.mp4", work)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
