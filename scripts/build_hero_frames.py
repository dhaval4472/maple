#!/usr/bin/env python3
"""Rebuild the scroll-scrubbed hero film as a small WebP frame sequence.

The site never serves the source video. It paints frames onto a canvas while
the visitor scrolls, so the frame count and resolution are a direct trade-off
between smoothness, bandwidth and decoded-image memory.

This script keeps the source video out of the deployed static folder and
writes compact desktop/mobile sequences that are cheap to host.

Usage:
    python scripts/build_hero_frames.py
    python scripts/build_hero_frames.py --frames 60 --quality 74
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "source-assets" / "video" / "hero-scrub.mp4"

# width, height, output folder
TARGETS = (
    (1280, 720, ROOT / "static" / "hero-frames" / "desktop"),
    (960, 540, ROOT / "static" / "hero-frames" / "mobile"),
)


def build(source: Path, frame_count: int, quality: int) -> None:
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise SystemExit(f"Could not open {source}")

    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < frame_count:
        capture.release()
        raise SystemExit(f"Source has {total} frames; need at least {frame_count}")

    wanted = []
    for index in range(frame_count):
        position = round(index * (total - 1) / max(1, frame_count - 1))
        wanted.append(position)
    wanted_set = set(wanted)
    next_position = 0

    for _width, _height, folder in TARGETS:
        folder.mkdir(parents=True, exist_ok=True)
        for stale in folder.glob("frame-*.webp"):
            stale.unlink()

    written = 0
    for position in range(total):
        ok, frame = capture.read()
        if not ok:
            break
        if position not in wanted_set:
            continue

        for width, height, folder in TARGETS:
            resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            output = folder / f"frame-{next_position + 1:03d}.webp"
            Image.fromarray(rgb).save(output, "WEBP", quality=quality, method=6)
        next_position += 1
        written += 1

    capture.release()
    if written != frame_count:
        raise SystemExit(f"Wrote {written} of {frame_count} frames")

    for _width, _height, folder in TARGETS:
        size = sum(path.stat().st_size for path in folder.glob("frame-*.webp"))
        print(f"{folder.relative_to(ROOT)}: {written} frames, {size / 1024 / 1024:.2f} MB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--quality", type=int, default=74)
    args = parser.parse_args()
    build(args.source, args.frames, args.quality)


if __name__ == "__main__":
    main()
