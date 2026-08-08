#!/usr/bin/env python3
"""Render a bike-scene loop from a scene description file.

The scene lives in JSON: camera, which background, and a list of actors with
positions, keyframes and procedural motion. Nothing is hand-placed per frame,
so changing "how far away" or "which Pokemon" is an edit to one file.

  python3 compose.py scenes/wide.json --format gif mp4

Coordinates are GBA pixels in the original 160-px-tall frame, with the ground
pinned to the bottom of the canvas: pull the camera back and you see more sky,
while everything standing on the grass stays put.
"""

import argparse
import json
import math
import os
import subprocess

import numpy as np
from PIL import Image

from gba import (
    build_bg_rgba,
    cut_obj,
    load_indexed,
    load_jasc_pal,
    load_screenblocks,
    palette_bank,
)
import export_sprites as ex

WORLD_H = 160  # the scene was authored for a 160 px tall screen

# Layer scroll in GBA px per GBA frame. Rounded from the game's own values so
# each layer's period divides the loop; see README.
DEFAULT_SPEEDS = {"far": 0.0, "near": 1.0, "ground": 4.0}


def load_background(name):
    """Build the three BG layers plus the moving-scenery pieces for a scene."""
    scene = ex.SCENES[name]
    bg_sheet, bg_own = load_indexed(ex.a(scene["bg"]))
    bg_pal = load_jasc_pal(ex.a(scene["bgpal"])) if scene["bgpal"] else bg_own
    grass_sheet, grass_own = load_indexed(ex.a("grass.png"))
    grass_pal = (load_jasc_pal(ex.a(scene["grasspal"])) if scene["grasspal"]
                 else grass_own)
    bank = palette_bank([(0, bg_pal), (15, grass_pal)])

    blocks = load_screenblocks(ex.a(scene["map"]))
    layers = {
        "far": build_bg_rgba(bg_sheet, blocks[0], bank),
        "near": build_bg_rgba(bg_sheet, blocks[1], bank),
        "ground": build_bg_rgba(grass_sheet,
                                load_screenblocks(ex.a("grass_map.bin"))[0], bank),
    }

    sc_sheet, sc_own = load_indexed(ex.a(scene["scenery"]))
    sc_pal = (load_jasc_pal(ex.a(scene["scenerypal"])) if scene["scenerypal"]
              else sc_own)
    pieces = {}
    for piece, (tile, w, h) in ex.SCENERY_PIECES[scene["layout"]].items():
        pieces[piece] = ex.to_rgba(cut_obj(sc_sheet, tile, w, h), sc_pal)

    placement = []
    for piece, x, y in ex.SCENERY_PLACEMENT[scene["layout"]]:
        w = ex.SCENERY_PIECES[scene["layout"]][piece][1]
        placement.append((piece, x, y, ex.SCENERY_SCROLL[w]))

    return layers, pieces, placement, bank[0, 0]


def load_actor_sheet(path, frames):
    """A horizontal strip -> list of RGBA frames."""
    im = np.array(Image.open(path).convert("RGBA"))
    fw = im.shape[1] // frames
    return [im[:, i * fw : (i + 1) * fw] for i in range(frames)]


def ease(t, kind):
    if kind == "in-out":
        return t * t * (3 - 2 * t)
    if kind == "in":
        return t * t
    if kind == "out":
        return t * (2 - t)
    return t


def sample_keys(keys, f, loop):
    """Interpolate x/y from keyframes, wrapping the last key back to the first."""
    f = f % loop
    ks = sorted(keys, key=lambda k: k["f"])
    if len(ks) == 1:
        return ks[0].get("x", 0), ks[0].get("y", 0)
    # close the ring so the loop has no seam
    ring = ks + [dict(ks[0], f=ks[0]["f"] + loop)]
    for a, b in zip(ring, ring[1:]):
        if a["f"] <= f < b["f"]:
            span = b["f"] - a["f"]
            t = ease((f - a["f"]) / span, a.get("ease", "linear")) if span else 0
            return (a.get("x", 0) + (b.get("x", 0) - a.get("x", 0)) * t,
                    a.get("y", 0) + (b.get("y", 0) - a.get("y", 0)) * t)
    return ks[-1].get("x", 0), ks[-1].get("y", 0)


def apply_motion(motion, f, loop):
    """Procedural offsets layered on top of the base position."""
    dx = dy = 0.0
    for m in motion:
        kind = m.get("type", "sine")
        amp = m.get("amp", 0)
        period = m.get("period", loop) or loop
        phase = m.get("phase", 0)
        theta = 2 * math.pi * (f / period) + math.radians(phase)
        v = amp * (math.sin(theta) if kind == "sine" else math.cos(theta))
        if kind == "wobble":
            # the game's random 1 px jitter, made periodic
            v = amp * [0, -1, 0, 1][int(f / max(1, m.get("hold", 8))) % 4]
        if m.get("axis", "y") == "x":
            dx += v
        else:
            dy += v
    return dx, dy


class View:
    """RGBA canvas in GBA pixels, with the world pinned to the bottom."""

    def __init__(self, w, h, backdrop):
        self.w, self.h = w, h
        self.dy = h - WORLD_H
        self.rgb = np.zeros((h, w, 3), dtype=np.uint8)
        self.rgb[:, :] = backdrop

    def tile_layer(self, layer, offset, y, extend_up=False):
        """Draw a 256-px-periodic layer scrolled right by `offset`.

        `extend_up` repeats the layer's top row into the space above it. The
        GBA never shows that space (the far BG fills the screen), so its
        backdrop colour is unset — usually black. Pulling the camera back
        reveals it, and the top row is sky, which is what belongs there.
        """
        lh = layer.shape[0]
        y0 = y + self.dy
        xs = (np.arange(self.w) - int(round(offset))) % 256

        if extend_up and y0 > 0:
            top = layer[0][xs]
            m = top[..., 3] != 0
            self.rgb[:y0][:, m] = top[..., :3][m]

        src_y0, src_y1 = max(0, -y0), min(lh, self.h - y0)
        if src_y0 >= src_y1:
            return
        px = layer[src_y0:src_y1][:, xs]
        band = self.rgb[y0 + src_y0 : y0 + src_y1]
        m = px[..., 3] != 0
        band[m] = px[..., :3][m]

    def sprite(self, frame, x, y, flip_x=False):
        """Blit an RGBA frame with its top-left at (x, y) in world space."""
        if flip_x:
            frame = frame[:, ::-1]
        h, w = frame.shape[:2]
        x, y = int(round(x)), int(round(y)) + self.dy
        sx0, sy0 = max(0, -x), max(0, -y)
        sx1, sy1 = min(w, self.w - x), min(h, self.h - y)
        if sx0 >= sx1 or sy0 >= sy1:
            return
        sub = frame[sy0:sy1, sx0:sx1]
        m = sub[..., 3] != 0
        dst = self.rgb[y + sy0 : y + sy1, x + sx0 : x + sx1]
        dst[m] = sub[..., :3][m]


def resolve_anchor(anchor, w, h):
    """Offset from the anchor point to the frame's top-left corner."""
    if anchor == "center":
        return -w / 2, -h / 2
    if anchor == "top-left":
        return 0, 0
    return -w / 2, -h  # bottom-center


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scene", help="path to a scene .json")
    p.add_argument("--format", nargs="+", default=["gif"],
                   choices=["gif", "mp4", "webm", "png"])
    p.add_argument("--step", type=int, default=1, help="keep every Nth frame")
    p.add_argument("--out", default="out")
    p.add_argument("--frame", type=int, help="render a single frame and stop")
    args = p.parse_args()

    cfg = json.load(open(args.scene))
    canvas_w, canvas_h = cfg.get("canvas", [1280, 640])
    zoom = cfg.get("zoom", 4)
    loop = cfg.get("loop_frames", 256)
    fps = cfg.get("fps", 59.7275)
    view_w = -(-canvas_w // zoom)
    view_h = -(-canvas_h // zoom)

    layers, pieces, placement, backdrop = load_background(cfg["background"])
    speeds = dict(DEFAULT_SPEEDS, **cfg.get("layer_speeds", {}))

    root = cfg.get("sprite_root", "sprites/x1")
    actors = []
    for spec in cfg["actors"]:
        frames = load_actor_sheet(os.path.join(root, spec["sprite"]),
                                  spec.get("frames", 1))
        actors.append((spec, frames))

        # An actor whose cycle doesn't divide the loop jumps when it wraps.
        # Fix it with `order` (a ping-pong like [0,1,2,1] is often enough) or
        # by nudging `delay`.
        cycle = len(spec.get("order") or frames) * max(1, spec.get("delay", 4))
        if loop % cycle:
            print(f"warning: {spec.get('name', spec['sprite'])} cycles every "
                  f"{cycle} frames, which does not divide the {loop}-frame loop "
                  f"— it will jump when the loop wraps")

    indices = range(0, loop, args.step) if args.frame is None else [args.frame]
    out_frames = []
    for f in indices:
        v = View(view_w, view_h, backdrop)

        v.tile_layer(layers["far"], speeds["far"] * f, 0, extend_up=True)

        # Scenery OBJs wrap over a 288 px span; slower pieces sit further back
        for piece, x0, y0, speed in sorted(placement, key=lambda p: p[3]):
            art = pieces[piece]
            ph, pw = art.shape[:2]
            base = (x0 + speed * f + 32) % 288 - 32
            for n in range(-1, view_w // 288 + 2):
                v.sprite(art, base + n * 288 - pw / 2, y0 - ph / 2)

        v.tile_layer(layers["near"], speeds["near"] * f, 0)
        v.tile_layer(layers["ground"], speeds["ground"] * f, 0)

        for spec, frames in sorted(actors, key=lambda a: a[0].get("depth", 0)):
            order = spec.get("order") or list(range(len(frames)))
            delay = max(1, spec.get("delay", 4))
            frame = frames[order[int(f / delay) % len(order)]]
            if spec.get("keys"):
                x, y = sample_keys(spec["keys"], f, loop)
            else:
                x, y = spec.get("x", 0), spec.get("y", 0)
            mx, my = apply_motion(spec.get("motion", []), f, loop)
            fh, fw = frame.shape[:2]
            ax, ay = resolve_anchor(spec.get("anchor", "bottom-center"), fw, fh)
            v.sprite(frame, x + mx + ax, y + my + ay, spec.get("flip_x", False))

        im = Image.fromarray(v.rgb)
        if zoom != 1:
            im = im.resize((im.width * zoom, im.height * zoom), Image.NEAREST)
        out_frames.append(im.crop((0, 0, canvas_w, canvas_h)))

    os.makedirs(args.out, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.scene))[0]
    written = []

    if args.frame is not None:
        path = os.path.join(args.out, f"{base}_f{args.frame}.png")
        out_frames[0].save(path)
        print(path)
        return

    if "png" in args.format:
        d = os.path.join(args.out, base + "_frames")
        os.makedirs(d, exist_ok=True)
        for i, im in enumerate(out_frames):
            im.save(os.path.join(d, f"{i:04d}.png"))
        written.append(d)

    eff_fps = fps / args.step
    if "gif" in args.format:
        path = os.path.join(args.out, base + ".gif")
        pal = out_frames[0].quantize(colors=255, method=Image.MEDIANCUT)
        gif = [im.quantize(palette=pal, dither=Image.NONE) for im in out_frames]
        gif[0].save(path, save_all=True, append_images=gif[1:], loop=0,
                    duration=round(1000 / eff_fps), disposal=1, optimize=True)
        written.append(path)

    for fmt in ("mp4", "webm"):
        if fmt not in args.format:
            continue
        raw = os.path.join(args.out, base + ".raw")
        with open(raw, "wb") as fh:
            for im in out_frames:
                fh.write(np.asarray(im.convert("RGB")).tobytes())
        path = os.path.join(args.out, f"{base}.{fmt}")
        codec = (["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16"]
                 if fmt == "mp4" else
                 ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-crf", "24", "-b:v", "0"])
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo",
             "-pixel_format", "rgb24",
             "-video_size", f"{out_frames[0].width}x{out_frames[0].height}",
             "-framerate", str(eff_fps), "-i", raw, *codec, path], check=True)
        os.remove(raw)
        written.append(path)

    for w in written:
        print(w)


if __name__ == "__main__":
    main()
