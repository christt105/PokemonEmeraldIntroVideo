#!/usr/bin/env python3
"""Cut a normalised sprite strip out of a Spriters Resource rip.

The custom Pokémon sheets in `project/pokemon/` all come from the same place and
share three traits the editor does not: a flat `(199,225,209)` backdrop instead
of alpha, cels laid out by hand rather than on a grid, and several unrelated
animations packed onto one row next to dotted grouping boxes and a credit line.

    python3 tools/sheet_slice.py <sheet.png> --list
    python3 tools/sheet_slice.py <sheet.png> --row 4 --out pokemon/foo_fly.png
    python3 tools/sheet_slice.py <sheet.png> --row 1 --cels 0-2 --out pokemon/foo.png

`--list` prints the row and cel map without writing anything; run it first, then
name what you want. Output is a single horizontal strip of equal cels with a
transparent background, which is the only layout `parallax-scene/1` reads.

The part that is easy to get wrong is the layout slope. These sheets are pasted
by dragging, so a row often descends a couple of pixels per cel. Played back
that reads as the sprite sinking and then snapping home at the wrap. It cannot
be told apart from real motion by looking at one cel — but a row usually repeats
a pose (a held frame, or a flutter that cycles), and two copies of *the same
drawing* at different heights can only be layout. That is what `_fit_drift`
measures, and it is the only vertical offset removed; whatever is left is the
animator's own bob and stays in.
"""

import argparse
import json
import os
import sys
from collections import Counter, deque

import numpy as np
from PIL import Image

TOL = 12          # colour distance that still counts as backdrop
LINE_MIN = 40     # a 1px run this long is a grouping box, not artwork
MATCH = 20        # pixels two cels may differ by and still be the same drawing
PAD = 2           # transparent margin around the union of all cels


# --------------------------------------------------------------- reading --

def detect_bg(rgb):
    """The backdrop is whatever colour covers the most ground."""
    flat = rgb.reshape(-1, 3)[::7]
    return np.array(Counter(map(tuple, flat)).most_common(1)[0][0])


def strip_boxes(mask, rgb):
    """Erase the dotted rectangles that group animations on these sheets.

    They are the reason naive row detection fails: one box welds three rows into
    a single band. A box line is one pixel thick, greyish, and runs far, so all
    three tests together never catch a sprite — the thickness test alone spares
    anything with a body behind it.
    """
    grey = mask & (rgb.max(axis=2) - rgb.min(axis=2) < 24)
    out = mask.copy()
    H, W = mask.shape

    for axis in (0, 1):
        g = grey if axis == 0 else grey.T
        m = out if axis == 0 else out.T
        n, span = g.shape
        for i in range(n):
            thin = g[i] & ~(g[i - 1] if i else np.zeros(span, bool)) \
                        & ~(g[i + 1] if i + 1 < n else np.zeros(span, bool))
            idx = np.where(thin)[0]
            if len(idx) < LINE_MIN // 2:
                continue
            # dotted lines have gaps; walk the dashes and keep long chains
            start = prev = idx[0]
            for x in list(idx[1:]) + [None]:
                if x is not None and x - prev <= 3:
                    prev = x
                    continue
                if prev - start >= LINE_MIN:
                    m[i, start:prev + 1] &= ~thin[start:prev + 1]
                if x is None:
                    break
                start = prev = x
    return out


# ------------------------------------------------------------ segmenting --
#
# Rows cannot be found by projecting the mask onto the y axis: on most of these
# sheets a wing from one row reaches into the next, and the whole page collapses
# into one band. Blobs and their bounding boxes survive that, so everything below
# works from connected components instead.

def components(mask):
    """8-connected blobs, as (x0, y0, x1, y1, area). Run-length union-find."""
    H, W = mask.shape
    parent = []

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    boxes = {}
    prev = []
    for y in range(H):
        edges = np.flatnonzero(np.diff(np.concatenate(
            ([0], mask[y].view(np.int8), [0]))))
        cur = []
        for a, b in zip(edges[0::2], edges[1::2] - 1):
            lab = None
            for pa, pb, pl in prev:
                if pa <= b + 1 and a <= pb + 1:      # touching, diagonals included
                    if lab is None:
                        lab = pl
                    else:
                        union(lab, pl)
            if lab is None:
                lab = len(parent)
                parent.append(lab)
            cur.append((a, b, lab))
            box = boxes.get(lab)
            boxes[lab] = ((min(box[0], a), min(box[1], y), max(box[2], b), y,
                           box[4] + b - a + 1) if box else (a, y, b, y, b - a + 1))
        prev = cur

    merged = {}
    for lab, (x0, y0, x1, y1, n) in boxes.items():
        r = find(lab)
        m = merged.get(r)
        merged[r] = ((min(m[0], x0), min(m[1], y0), max(m[2], x1), max(m[3], y1),
                      m[4] + n) if m else (x0, y0, x1, y1, n))
    return list(merged.values())


def is_art(b, min_h=8, min_area=60):
    """Credit text and stray dots are small on both counts; artwork is not."""
    return (b[3] - b[1] + 1) >= min_h and b[4] >= min_area


def cluster(values, tol):
    """Split sorted `values` wherever the step to the next one exceeds `tol`.

    A row is not a tidy horizontal line on these sheets — bodies stagger by a
    dozen pixels across one animation, more than a whole row's pitch on the
    tighter sheets — so a fixed window measured from where the group opened cuts
    real rows in half. What does hold everywhere is that the step between two
    neighbours inside a row stays well under the step between rows.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    groups, cur = [], [order[0]]
    for i in order[1:]:
        if values[i] - values[cur[-1]] <= tol:
            cur.append(i)
        else:
            groups.append(cur)
            cur = [i]
    groups.append(cur)
    return groups


def find_rows(blobs, gap=0):
    """Bands of artwork as (y0, y1, blobs), keyed off each blob's middle.

    Only whole bodies vote on where the rows are. These sheets park loose limbs
    and spare heads in a box off to the right, at heights that belong to no row
    at all; let those vote and the page shatters into twice as many bands as a
    reader would count. They are picked back up afterwards, but only where they
    sit alongside a body — a detached wing rejoins its own cel, an orphan in the
    parts bin is left out of the row entirely.

    Membership is decided by a blob's centre, not its extent, so a wing that
    reaches down into the next band still belongs to the row it was drawn in.
    """
    art = [b for b in blobs if is_art(b)]
    if not art:
        return []
    cut = 0.5 * float(np.percentile([b[4] for b in art], 75))
    body = [b for b in art if b[4] >= cut] or art
    spare = [b for b in art if b[4] < cut]

    mid = [(b[1] + b[3]) / 2 for b in body]
    tol = max(6, float(np.median([b[3] - b[1] + 1 for b in body])) * 0.5)

    rows = []
    for g in cluster(mid, tol):
        here = [body[i] for i in g]
        y0, y1 = min(b[1] for b in here), max(b[3] for b in here)
        here += [s for s in spare
                 if y0 <= (s[1] + s[3]) / 2 <= y1
                 and any(s[0] <= b[2] + gap and b[0] <= s[2] + gap for b in here)]
        rows.append((min(b[1] for b in here), max(b[3] for b in here), here))
    return sorted(rows)


def find_cels(blobs, gap=0):
    """Cels of one band: blobs chained together wherever their x ranges meet.

    A sprite is often several blobs — a detached wing, an eye highlight sitting
    on its own. Those overlap the body horizontally, so chaining on x reunites
    them without also swallowing the neighbouring cel.
    """
    cels = []
    for b in sorted(blobs, key=lambda b: b[0]):
        if cels and b[0] <= cels[-1][2] + gap:
            p = cels[-1]
            cels[-1] = (p[0], min(p[1], b[1]), max(p[2], b[2]), max(p[3], b[3]))
        else:
            cels.append((b[0], b[1], b[2], b[3]))
    return cels


# -------------------------------------------------------------- aligning --

def same_drawing(a, b, reach=4):
    """Best pixel difference between two cels over a small offset search."""
    (ra, ma), (rb, mb) = a, b
    h = max(ma.shape[0], mb.shape[0]) + 2 * reach
    w = max(ma.shape[1], mb.shape[1]) + 2 * reach

    def fit(r, m):
        A = np.zeros((h, w, 3), int)
        M = np.zeros((h, w), bool)
        A[:m.shape[0], :m.shape[1]] = r * m[:, :, None]
        M[:m.shape[0], :m.shape[1]] = m
        return A, M

    Aa, Ma = fit(ra, ma)
    Ab, Mb = fit(rb, mb)
    best = None
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            r = np.roll(np.roll(Ab, dy, 0), dx, 1)
            m = np.roll(np.roll(Mb, dy, 0), dx, 1)
            d = ((np.abs(Aa - r).sum(axis=2) > 8) | (Ma != m)).sum()
            if best is None or d < best:
                best = d
    return best


def group_poses(cels):
    """Which cels are literally the same drawing pasted more than once."""
    pose = [-1] * len(cels)
    groups = []
    for i, c in enumerate(cels):
        if pose[i] >= 0:
            continue
        pose[i] = len(groups)
        g = [i]
        for j in range(i + 1, len(cels)):
            if pose[j] < 0 and same_drawing((c["rgb"], c["m"]),
                                            (cels[j]["rgb"], cels[j]["m"])) <= MATCH:
                pose[j] = len(groups)
                g.append(j)
        groups.append(g)
    return pose, groups


def _spread(vals):
    return max(vals) - min(vals)


def _disagreement(cels, groups, slope):
    """Worst gap between two copies of one drawing once `slope` is removed.

    Identical drawings have to end up in identical places; whatever slope leaves
    them furthest apart is the wrong slope.
    """
    worst = 0.0
    for g in groups:
        if len(g) < 2:
            continue
        r = [cels[i]["com"][1] - slope * i for i in g]
        worst = max(worst, _spread(r))
    return worst


def _fit_slope(cels, groups):
    """Pixels per cel of pure layout slope down the row, 0 if there is none.

    Least squares proposes; repeated drawings judge. Fitting straight off the
    repeats is tempting — for two copies of one pose the whole difference in
    position *is* layout — but it only works when the copies sit far apart. Two
    adjacent copies differ by a pixel or two of ordinary animation, and reading
    that as a slope and extending it down the row wrecks the alignment. Least
    squares over every cel cannot be led astray that way, and a periodic bounce,
    which is what an adjacent repeat usually belongs to, sums out of it.

    Measured on the centre of mass, not the top of the box: a box top tracks
    whichever wing happens to be highest, so on a flap it swings further than the
    bird does and buries the slope in noise.
    """
    n = len(cels)
    if n < 3:
        return 0.0
    y = np.array([c["com"][1] for c in cels], float)
    i = np.arange(n)
    ls = float(np.polyfit(i, y, 1)[0])

    votes = [(cels[b]["com"][1] - cels[a]["com"][1]) / (b - a)
             for g in groups for a, b in zip(g, g[1:]) if b - a >= 2]
    best = ls
    if votes:
        exact = float(np.median(votes))
        if _disagreement(cels, groups, exact) < _disagreement(cels, groups, ls):
            best = exact

    # a slope only earns its keep by pulling the row together
    if _spread(y - best * i) >= _spread(y) or abs(best) * (n - 1) < 3:
        return 0.0
    return best


def anchors(cels, groups):
    """Where each cel's ink sits once the layout slope is taken out.

    The axes are not treated alike, because they do not fail alike.

    Vertically these rows carry real animation — a run bounces, a glide rises
    and dips — so only the straight-line part comes out and the rest is kept.
    Horizontally there is nothing to keep: the gaps between cels are eyeballed,
    they vary by a dozen pixels on the same row, and none of that is motion. So
    x pins flat to the centre of mass and the sprite tracks dead straight. Any
    sway it wants is one `motion` entry in the editor.
    """
    slope = _fit_slope(cels, groups)
    base = cels[0]["com"][1]
    return {
        # Each entry is the source coordinate pinned to the same spot in every
        # cel. Pin the centre of mass and that axis goes flat; pin a line that
        # only follows the slope and everything the sprite does around that line
        # survives into the strip.
        "x0": [c["com"][0] for c in cels],
        "x0_mode": "centre of mass, pinned flat",
        "y0": [base + slope * i for i in range(len(cels))],
        "y0_mode": (f"layout slope {slope:+.2f} px/cel removed, the rest kept"
                    if slope else "kept as laid out (no slope to remove)"),
    }


# --------------------------------------------------------------- scaling --

def rescale(cels, k):
    """Resample every cel by `k`, back onto the colours the sheet already uses.

    These custom sheets are drawn at roughly twice the scale of the GBA overworld
    sprites the scene is built around, so a Ninjask ends up wider than the bike it
    is flying past. The editor's own `scale` clamps at 1, so the fix has to happen
    here, on the way out.

    Two details make the difference between this and a plain resize:

    *Each cel is resampled on its own ink box*, not on a grid shared by the sheet.
    There is no shared grid to use — the cels were pasted by hand, so the same
    drawing sits at a different sub-pixel phase in every one, and sampling them
    all off the sheet's origin would give one pose two different silhouettes
    depending on where it landed. Anchoring the grid to the ink instead makes a
    repeated drawing resample identically every time it appears.

    *Colour is snapped back to the source palette.* Box-averaging invents blends
    along every edge, which on a 12-colour sprite reads as a soft halo rather than
    as a smaller sprite. Averaging first and then snapping each pixel to the
    nearest colour the artist actually used keeps the edge decisions the average
    makes without keeping its colours. Alpha is thresholded at half for the same
    reason: partial coverage is not something the rest of this pipeline, or the
    editor, has any use for.
    """
    ink = np.concatenate([c["rgb"][c["m"]] for c in cels])
    pal = np.unique(ink, axis=0).astype(float)
    out = []
    for c in cels:
        h, w = c["m"].shape
        nw, nh = max(1, round(w * k)), max(1, round(h * k))

        # premultiplied, so the backdrop behind the silhouette cannot bleed in
        prem = np.zeros((h, w, 4), np.uint8)
        prem[:, :, :3] = c["rgb"] * c["m"][:, :, None]
        prem[:, :, 3] = c["m"] * 255
        sm = np.asarray(Image.fromarray(prem, "RGBA")
                        .resize((nw, nh), Image.BOX)).astype(float)

        m = sm[:, :, 3] >= 128
        if not m.any():
            raise SystemExit(f"scale {k} leaves a cel with no pixels")
        cov = np.maximum(sm[:, :, 3:4], 1e-6) / 255.0
        col = sm[:, :, :3] / cov
        idx = ((col[:, :, None, :] - pal[None, None, :, :]) ** 2).sum(-1).argmin(-1)

        rgb = pal[idx].astype(np.uint8)
        rgb[~m] = 0
        ys, xs = np.where(m)
        out.append(dict(x0=c["x0"] * k, y0=c["y0"] * k, m=m, rgb=rgb,
                        com=(c["x0"] * k + xs.mean(), c["y0"] * k + ys.mean())))
    return out


# ---------------------------------------------------------------- output --

def build(cels, anc, pad=PAD):
    """Lay the cels into one strip, every anchor landing on the same spot."""
    ox = [round(c["x0"] - anc["x0"][i]) for i, c in enumerate(cels)]
    oy = [round(c["y0"] - anc["y0"][i]) for i, c in enumerate(cels)]
    L = -min(ox)
    U = -min(oy)
    CW = max(ox[i] + c["m"].shape[1] for i, c in enumerate(cels)) + L + 2 * pad
    CH = max(oy[i] + c["m"].shape[0] for i, c in enumerate(cels)) + U + 2 * pad

    sheet = Image.new("RGBA", (CW * len(cels), CH), (0, 0, 0, 0))
    for i, c in enumerate(cels):
        h, w = c["m"].shape
        tile = np.zeros((h, w, 4), np.uint8)
        tile[:, :, :3] = c["rgb"]
        tile[:, :, 3] = c["m"] * 255
        sheet.paste(Image.fromarray(tile, "RGBA"),
                    (i * CW + L + ox[i] + pad, U + oy[i] + pad))
    return sheet, CW, CH, (L + pad, U + pad)


def loop_delays(n, loop):
    """Delays for which `n` cels divide the scene loop exactly."""
    return [d for d in range(1, 33) if loop % (n * d) == 0]


def suggest_order(n, loop):
    """A playback order that stretches `n` cels to a length the loop can hold.

    `loop_frames` is a power of two in this project, so only a power-of-two run
    of steps ever divides it and most rows — three cels, seven, ten — cannot
    close on their own however the delay is set. Padding the cycle out to the
    next length that does divide, holding cels evenly along the way, keeps every
    drawing and every delay and just runs one or two of them a beat longer.
    """
    m = next((k for k in range(n + 1, loop + 1) if loop % k == 0), None)
    if m is None:
        return None, []
    return [j * n // m for j in range(m)], loop_delays(m, loop)


# ------------------------------------------------------------------ main --

def load(path):
    rgb = np.array(Image.open(path).convert("RGB")).astype(int)
    bg = detect_bg(rgb)
    mask = np.abs(rgb - bg).sum(axis=2) > TOL
    return rgb, strip_boxes(mask, rgb), bg


def collect(rgb, mask, blobs, gap, min_w):
    cels = []
    for bx0, by0, bx1, by1 in find_cels(blobs, gap):
        if bx1 - bx0 + 1 < min_w:
            continue
        m = mask[by0:by1 + 1, bx0:bx1 + 1]
        ys, xs = np.where(m)
        cels.append(dict(x0=bx0, y0=by0, m=m,
                         rgb=rgb[by0:by1 + 1, bx0:bx1 + 1].astype(np.uint8),
                         com=(bx0 + xs.mean(), by0 + ys.mean())))
    return cels


def parse_cels(spec, n):
    if not spec:
        return list(range(n))
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sheet")
    ap.add_argument("--row", type=int, help="1-based row, as printed by --list")
    ap.add_argument("--band", help="y0:y1 instead of --row, when a row needs splitting")
    ap.add_argument("--cels", help="e.g. 0-2 or 0,1,4 (default: the whole row)")
    ap.add_argument("--out", help="path to write, relative to the project root")
    ap.add_argument("--gap", type=int, default=1,
                    help="columns of backdrop bridged inside one cel (default 1)")
    ap.add_argument("--min-width", type=int, default=8,
                    help="drop slivers narrower than this (default 8)")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="resample the cels by this factor, e.g. 0.5 to bring a "
                         "sheet down to overworld scale (default 1)")
    ap.add_argument("--loop", type=int, default=256, help="scene loop_frames")
    ap.add_argument("--list", action="store_true", help="print the map and stop")
    args = ap.parse_args(argv)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rgb, mask, bg = load(args.sheet)
    print(f"{os.path.basename(args.sheet)}  {rgb.shape[1]}x{rgb.shape[0]}  "
          f"backdrop rgb{tuple(bg)}")

    blobs = components(mask)
    rows = find_rows(blobs, args.gap)
    if args.list or not (args.row or args.band):
        for n, (y0, y1, bs) in enumerate(rows, 1):
            cs = collect(rgb, mask, bs, args.gap, args.min_width)
            print(f"  row {n}: y {y0}..{y1}  h={y1-y0+1}  {len(cs)} cels  x "
                  + ", ".join(f"{c['x0']}..{c['x0']+c['m'].shape[1]-1}" for c in cs))
        return 0

    if args.band:
        y0, y1 = (int(v) for v in args.band.split(":"))
        mids = [b for b in blobs if is_art(b) and y0 <= (b[1] + b[3]) / 2 <= y1]
    else:
        if not 1 <= args.row <= len(rows):
            print(f"row {args.row} out of range: the sheet has {len(rows)}", file=sys.stderr)
            return 1
        y0, y1, mids = rows[args.row - 1]

    cels = collect(rgb, mask, mids, args.gap, args.min_width)
    pick = parse_cels(args.cels, len(cels))
    if max(pick) >= len(cels):
        print(f"cel {max(pick)} out of range: the band has {len(cels)}", file=sys.stderr)
        return 1
    cels = [cels[i] for i in pick]
    print(f"band y {y0}..{y1}, {len(cels)} cels: "
          f"{', '.join(str(c['x0']) for c in cels)}")

    if args.scale != 1.0:
        before = cels[0]["m"].shape
        cels = rescale(cels, args.scale)
        after = cels[0]["m"].shape
        # scaled before grouping and anchoring, so both run on the grid the strip
        # is actually written on and the pin lands on a whole output pixel
        print(f"  scaled x{args.scale:g}: ink box {before[1]}x{before[0]} -> "
              f"{after[1]}x{after[0]}")

    pose, groups = group_poses(cels)
    if len(groups) < len(cels):
        print("  repeated drawings: " +
              "; ".join(f"{g}" for g in groups if len(g) > 1))
    anc = anchors(cels, groups)
    print(f"  x: {anc['x0_mode']}\n  y: {anc['y0_mode']}")

    sheet, CW, CH, (ax, ay) = build(cels, anc)
    if not args.out:
        print("  (no --out given, nothing written)")
        return 0
    out = args.out if os.path.isabs(args.out) else os.path.join(root, "project", args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)

    print(f"  wrote {os.path.relpath(out, root)}  {sheet.width}x{sheet.height}"
          f"  ({len(cels)} cels of {CW}x{CH}, anchor at {ax},{ay})")

    actor = {"name": os.path.basename(out)[:-4].split("_")[0],
             "sprite": os.path.relpath(out, os.path.join(root, "project"))
                         .replace(os.sep, "/"),
             "frames": len(cels)}
    ds = loop_delays(len(cels), args.loop)
    if ds:
        print(f"  closes a {args.loop} frame loop at delay {', '.join(map(str, ds))}")
    else:
        order, ds = suggest_order(len(cels), args.loop)
        print(f"  {len(cels)} cels never divide {args.loop} at any delay; "
              f"padded to {len(order)} steps it closes at delay "
              f"{', '.join(map(str, ds))}")
        actor["order"] = order
    actor["delay"] = ds[len(ds) // 2] if ds else 4
    print("  " + json.dumps(actor))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
