#!/usr/bin/env python3
"""Turn a loose sprite sheet into an evenly spaced, registered strip.

Sheets ripped from elsewhere (Mystery Dungeon, spriters' resource, an Aseprite
export) tend to have frames at irregular gaps and each one sitting at its own
offset. Animating that makes the sprite jitter. This finds the frames, gives
them a common box, and lines them up on a chosen anchor.

  python3 import_sprite.py out/Walk-Anim-export.png --name mudkip_walk
"""

import argparse
import json
import os

import numpy as np
from PIL import Image


def find_frames(alpha, axis=1):
    """Split on fully transparent columns; return (start, end) spans."""
    occupied = alpha.any(axis=0) if axis == 1 else alpha.any(axis=1)
    spans, start = [], None
    for i, on in enumerate(occupied):
        if on and start is None:
            start = i
        elif not on and start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(occupied)))
    return spans


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source")
    p.add_argument("--name", help="output basename (default: source stem)")
    p.add_argument("--anchor", default="bottom-center",
                   choices=["bottom-center", "center", "top-left"],
                   help="how frames line up inside the common box")
    p.add_argument("--delay", type=int, default=6,
                   help="frame delay in GBA frames at 59.7275 Hz")
    p.add_argument("--pad", type=int, default=1, help="transparent margin, px")
    p.add_argument("--frames", type=int, help="force a fixed frame count "
                                              "(splits into equal columns)")
    p.add_argument("--scale", type=int, nargs="+", default=[1, 4])
    p.add_argument("--out", default="sprites")
    args = p.parse_args()

    name = args.name or os.path.splitext(os.path.basename(args.source))[0]
    src = np.array(Image.open(args.source).convert("RGBA"))
    alpha = src[..., 3] > 0

    if args.frames:
        w = src.shape[1] // args.frames
        spans = [(i * w, (i + 1) * w) for i in range(args.frames)]
    else:
        spans = find_frames(alpha)
    if not spans:
        raise SystemExit("no opaque pixels found")

    # Trim each frame to its own content, then find one box that fits them all
    cuts = []
    for x0, x1 in spans:
        sub = src[:, x0:x1]
        rows = np.nonzero(sub[..., 3].any(axis=1))[0]
        cuts.append(sub[rows[0] : rows[-1] + 1] if len(rows) else sub[:0])

    fw = max(c.shape[1] for c in cuts) + 2 * args.pad
    fh = max(c.shape[0] for c in cuts) + 2 * args.pad

    out = np.zeros((fh, fw * len(cuts), 4), dtype=np.uint8)
    for i, c in enumerate(cuts):
        h, w = c.shape[:2]
        if args.anchor == "top-left":
            ox, oy = args.pad, args.pad
        elif args.anchor == "center":
            ox, oy = (fw - w) // 2, (fh - h) // 2
        else:  # bottom-center: feet stay planted, which is what walk cycles need
            ox, oy = (fw - w) // 2, fh - args.pad - h
        out[oy : oy + h, i * fw + ox : i * fw + ox + w] = c

    meta = dict(file=f"{name}.png", frames=len(cuts),
                frame_delay_gba=args.delay,
                frame_ms=round(args.delay * 1000 / 59.7275, 1))

    for scale in args.scale:
        d = os.path.join(args.out, f"x{scale}", "external")
        os.makedirs(d, exist_ok=True)
        im = Image.fromarray(out, "RGBA")
        if scale != 1:
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        im.save(os.path.join(d, f"{name}.png"))

        index = os.path.join(d, "external.json")
        all_meta = json.load(open(index)) if os.path.exists(index) else {}
        all_meta[name] = dict(meta, frame_width=fw * scale, frame_height=fh * scale)
        with open(index, "w") as fh_:
            json.dump(all_meta, fh_, indent=2)

    print(f"{name}: {len(cuts)} frames of {fw}x{fh} (x1), anchored {args.anchor}")


if __name__ == "__main__":
    main()
