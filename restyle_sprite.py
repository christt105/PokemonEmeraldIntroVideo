#!/usr/bin/env python3
"""Recolour a sprite's black ink into tinted outlines, Emerald style.

Sprites from other games tend to be drawn with a flat black outline. The
Emerald intro sprites never use black: the outline takes a darkened version of
whatever colour it wraps, pulled slightly towards the warm grey the whole
scene shares. Measured on Torchic, that dark tone is its body colour times
about 0.55; Manectric and Brendan follow the same rule.

  python3 restyle_sprite.py sprites/x1/external/mudkip_walk.png

Rewrites every scale under sprites/x*/ that holds the same file.
"""

import argparse
import os

import numpy as np
from PIL import Image

# The outline grey shared by Torchic, Manectric and the rider (index 1 of
# graphics/intro/scene_2/player.pal).
WARM_GREY = np.array([82, 74, 74], dtype=np.float64)


def find_ink(rgb, alpha, threshold):
    """Pixels dark enough to be outline ink."""
    return (alpha > 0) & (rgb.max(axis=2) <= threshold)


def nearest_body_colour(rgb, ink, alpha):
    """For every ink pixel, the most common non-ink colour around it.

    Grows the search ring until something is found, so interior ink lines
    (a mouth, the split between fins) get tinted by what they sit on rather
    than defaulting to grey.
    """
    h, w = ink.shape
    body = (alpha > 0) & ~ink
    out = np.zeros((h, w, 3), dtype=np.float64)
    found = np.zeros((h, w), dtype=bool)

    ys, xs = np.nonzero(ink)
    for y, x in zip(ys, xs):
        for r in range(1, 6):
            y0, y1 = max(0, y - r), min(h, y + r + 1)
            x0, x1 = max(0, x - r), min(w, x + r + 1)
            patch = rgb[y0:y1, x0:x1][body[y0:y1, x0:x1]]
            if len(patch):
                cols, counts = np.unique(patch, axis=0, return_counts=True)
                out[y, x] = cols[np.argmax(counts)]
                found[y, x] = True
                break
    return out, found


def darken(rgb, factor, sat):
    """Emerald's outline tone: drop the value, push the saturation.

    Fitted against the originals: Torchic's body drops V 93 -> 51 with its
    saturation untouched, which `sat=1.0` reproduces to within 6 per channel.
    Manectric's mane does climb S 63 -> 95, but pushing saturation to match it
    makes the fit worse overall, so the default leaves S alone and `--sat` is
    there for when a sprite wants it.
    """
    flat = rgb.reshape(-1, 3) / 255.0
    mx = flat.max(axis=1)
    mn = flat.min(axis=1)
    diff = mx - mn
    v = np.clip(mx * factor, 0, 1)
    s = np.where(mx > 0, diff / np.maximum(mx, 1e-9), 0)
    s = np.clip(s * sat, 0, 1)

    # hue survives untouched; rebuild from the original hue sector
    with np.errstate(invalid="ignore", divide="ignore"):
        hue = np.zeros(len(flat))
        r, g, b = flat[:, 0], flat[:, 1], flat[:, 2]
        nz = diff > 1e-9
        idx = np.argmax(flat, axis=1)
        hue = np.where(nz & (idx == 0), ((g - b) / np.where(diff == 0, 1, diff)) % 6, hue)
        hue = np.where(nz & (idx == 1), (b - r) / np.where(diff == 0, 1, diff) + 2, hue)
        hue = np.where(nz & (idx == 2), (r - g) / np.where(diff == 0, 1, diff) + 4, hue)
    h6 = hue
    c = v * s
    x = c * (1 - np.abs((h6 % 2) - 1))
    m = v - c
    sector = np.floor(h6).astype(int) % 6
    zero = np.zeros_like(c)
    table = np.array([[c, x, zero], [x, c, zero], [zero, c, x],
                      [zero, x, c], [x, zero, c], [c, zero, x]])
    out = table[sector, :, np.arange(len(flat))] + m[:, None]
    return np.clip(out * 255, 0, 255).reshape(rgb.shape)


def restyle(path, threshold, factor, sat, blend, out_path=None):
    im = Image.open(path).convert("RGBA")
    a = np.array(im)
    rgb, alpha = a[..., :3].astype(np.float64), a[..., 3]

    ink = find_ink(rgb, alpha, threshold)
    if not ink.any():
        return None

    body, found = nearest_body_colour(rgb, ink, alpha)
    tinted = darken(body, factor, sat)
    if blend:
        tinted = tinted * (1 - blend) + WARM_GREY * blend
    # ink with nothing around it falls back to the shared grey
    tinted[~found] = WARM_GREY

    a[..., :3] = np.where(ink[..., None], np.clip(tinted, 0, 255), rgb).astype(np.uint8)
    Image.fromarray(a, "RGBA").save(out_path or path)
    return int(ink.sum())


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", help="a strip under sprites/x1/")
    p.add_argument("--threshold", type=int, default=40,
                   help="a pixel is ink when its brightest channel is <= this")
    p.add_argument("--factor", type=float, default=0.55,
                   help="how far the outline's value drops (fitted on Torchic)")
    p.add_argument("--sat", type=float, default=1.0,
                   help="saturation multiplier; 1.0 fits the originals best")
    p.add_argument("--blend", type=float, default=0.0,
                   help="pull towards the scene's warm grey, 0..1")
    p.add_argument("--suffix", default="", help="write a copy instead, e.g. _v2")
    p.add_argument("--scales", type=int, nargs="+", default=[1, 4])
    args = p.parse_args()

    def named(path):
        if not args.suffix:
            return path
        stem, ext = os.path.splitext(path)
        return stem + args.suffix + ext

    rel = os.path.relpath(args.source, os.path.join("sprites", "x1"))
    base = os.path.join("sprites", "x1", rel)
    dst = named(base)
    n = restyle(base, args.threshold, args.factor, args.sat, args.blend, dst)
    if not n:
        print(f"{base}: no encontré tinta oscura")
        return
    print(f"{dst}: {n} píxeles de tinta recoloreados")

    # scale up from the recoloured x1 so every size stays identical
    src = Image.open(dst)
    for scale in args.scales:
        if scale == 1:
            continue
        out = named(os.path.join("sprites", f"x{scale}", rel))
        if not os.path.exists(os.path.join("sprites", f"x{scale}", rel)):
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        src.resize((src.width * scale, src.height * scale),
                   Image.NEAREST).save(out)
        print(f"{out}: reescalado x{scale}")


if __name__ == "__main__":
    main()
