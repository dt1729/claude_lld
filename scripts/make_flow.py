"""Render the flow diagram as a GIF: one state of the pipeline per scene.

The figure in ``docs/assets/flow.html`` is one drawing. Every scene lights different nodes
and edges of it, so the reader follows a single mechanism changing state rather than a
sequence of unrelated pictures - the thing that made the first demo unreadable.

The claim the figure makes: nothing reaches disk until the design, the tests and the checks
agree, and every refusal arcs back to the author.

Usage:
    python make_flow.py [--theme dark|light] [--still N]
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from logsetup import configure
from make_demo import FPS, HEIGHT, WIDTH, encode, find_chrome, shoot

log = logging.getLogger("lld.flow")

#: Node states: idle (greyed), active (accent), pass (green), block (red).
#: Edge states: off (greyed), on (accent), good (green), bad (red, dashed).
#: A name absent from a scene defaults to idle/off, so each scene lists only what it lights.


@dataclass(frozen=True, slots=True)
class Scene:
    """One state of the figure, held for a number of seconds."""

    step: str
    caption: str
    nodes: dict[str, str] = field(default_factory=dict)
    edges: dict[str, str] = field(default_factory=dict)
    seconds: float = 2.6

    def payload(self, theme: str) -> dict[str, Any]:
        return {
            "theme": theme,
            "step": self.step,
            "caption": self.caption,
            "nodes": self.nodes,
            "edges": self.edges,
        }


def storyboard() -> list[Scene]:
    """The pipeline, one state at a time, including both feedback loops."""
    return [
        Scene(
            step="1 / 7",
            caption="An agent writes a module. <b>The gate sees the call first.</b>",
            nodes={"agent": "active", "gate": "active"},
            edges={"write": "on"},
            seconds=2.8,
        ),
        Scene(
            step="2 / 7",
            caption="No contract covers it, so the write is <b>refused</b>. Nothing reaches disk.",
            nodes={"agent": "active", "gate": "block", "contract": "block"},
            edges={"write": "on", "c2g": "bad", "deny1": "bad"},
            seconds=3.4,
        ),
        Scene(
            step="3 / 7",
            caption="The design is written first. The AST then says which tests the module owes.",
            nodes={"agent": "active", "gate": "active", "contract": "pass", "ast": "active"},
            edges={"write": "on", "c2g": "good", "a2g": "on"},
            seconds=3.2,
        ),
        Scene(
            step="4 / 7",
            caption="37 rules read the pending write. "
            "<b>An anti-pattern, or a contract that no longer fits, refuses it again.</b>",
            nodes={
                "agent": "active",
                "gate": "block",
                "contract": "pass",
                "ast": "pass",
                "rules": "block",
            },
            edges={"write": "on", "c2g": "good", "a2g": "good", "r2g": "bad", "deny2": "bad"},
            seconds=3.6,
        ),
        Scene(
            step="5 / 7",
            caption="Once all three agree, the write lands.",
            nodes={
                "agent": "pass",
                "gate": "pass",
                "disk": "active",
                "contract": "pass",
                "ast": "pass",
                "rules": "pass",
            },
            edges={"write": "good", "allow": "good", "c2g": "good", "a2g": "good", "r2g": "good"},
            seconds=2.8,
        ),
        Scene(
            step="6 / 7",
            caption="Then the checks run. A failure arcs back the same way.",
            nodes={
                "agent": "idle",
                "gate": "pass",
                "disk": "pass",
                "checks": "active",
                "commit": "idle",
                "contract": "pass",
                "ast": "pass",
                "rules": "pass",
            },
            edges={
                "allow": "good",
                "run": "on",
                "deny3": "bad",
                "c2g": "good",
                "a2g": "good",
                "r2g": "good",
            },
            seconds=3.2,
        ),
        Scene(
            step="7 / 7",
            caption="Green commits. And every judgment becomes a recorded incident "
            "that <b>edits the rules</b>.",
            nodes={
                "gate": "pass",
                "disk": "pass",
                "checks": "pass",
                "commit": "pass",
                "contract": "pass",
                "ast": "pass",
                "rules": "active",
                "ledger": "active",
            },
            edges={
                "allow": "good",
                "run": "good",
                "green": "good",
                "c2g": "good",
                "a2g": "good",
                "r2g": "good",
                "j2l": "on",
                "l2r": "on",
            },
            seconds=4.2,
        ),
    ]


def render(theme: str, out: Path, stem: str) -> None:
    """Render every scene and write the GIF and MP4."""
    template = (out / "flow.html").read_text(encoding="utf-8")
    chrome = find_chrome()
    scenes = storyboard()

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        sequence = work / "seq"
        sequence.mkdir()

        images: list[Image.Image] = []
        durations: list[int] = []
        counter = 0
        for index, scene in enumerate(scenes):
            image = shoot(chrome, template, scene.payload(theme), work, index)
            images.append(image)
            durations.append(int(scene.seconds * 1000))
            for _ in range(max(1, round(scene.seconds * FPS))):
                image.save(sequence / f"{counter:05d}.png")
                counter += 1
        log.info("%d scenes at %dx%d, %.1fs", len(scenes), WIDTH, HEIGHT, counter / FPS)

        palettes = [i.quantize(colors=64, method=Image.Quantize.MEDIANCUT) for i in images]
        gif = out / f"{stem}.gif"
        palettes[0].save(
            gif,
            save_all=True,
            append_images=palettes[1:],
            duration=durations,
            loop=0,
            optimize=True,
        )
        log.info("wrote %s (%.0f KB)", gif.name, gif.stat().st_size / 1e3)
        if encode(sequence, out / f"{stem}.mp4"):
            log.info("wrote %s.mp4", stem)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", default="dark", choices=["dark", "light"])
    parser.add_argument("--out", type=Path, default=Path("docs/assets"))
    parser.add_argument("--still", type=int, default=None, help="render only scene N")
    parser.add_argument("--log-level", default=None)
    args = parser.parse_args(argv)
    configure(level=args.log_level, log_file=None)

    if args.still is not None:
        template = (args.out / "flow.html").read_text(encoding="utf-8")
        scene = storyboard()[args.still]
        with tempfile.TemporaryDirectory() as tmp:
            image = shoot(find_chrome(), template, scene.payload(args.theme), Path(tmp), 0)
        target = args.out / "_flow_still.png"
        image.save(target)
        log.info("wrote %s (scene %d)", target.name, args.still)
        return 0

    render(args.theme, args.out, "flow" if args.theme == "dark" else "flow-light")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
