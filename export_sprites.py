#!/usr/bin/env python3
"""Export the Emerald bike-scene graphics as clean RGBA sheets for Aseprite.

Every sprite comes out as a horizontal strip of equally sized frames with a
real alpha channel, trimmed to the tightest box that still holds every frame
of that sprite (so the frames stay registered against each other). Background
layers come out as horizontally tileable strips.

  python3 export_sprites.py --scale 4
"""

import argparse
import json
import os

import numpy as np
from PIL import Image

from gba import (
    build_bg_rgba,
    cut_obj,
    palette_bank,
    load_indexed,
    load_jasc_pal,
    load_screenblocks,
    split_frames,
)

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Canvas the sprites are meant to be composed on. 160 px of GBA screen scaled
# 4x is exactly 640, and 1280 px is a 320 px-wide (wider than the GBA's 240)
# panoramic slice of the same scene.
CANVAS_W, CANVAS_H = 1280, 640
DEFAULT_SCALE = 4

# name -> (sheet file, frame w, frame h, palette override, [(anim, [frames], delay)])
# delay is in GBA frames at 59.7275 Hz, taken from the ANIMCMD tables.
CHARACTERS = {
    "brendan_intro":  ("brendan.png",         64, 64, "player.pal",
                       [("bike", [0, 1, 2, 3], 4)]),
    "may_intro":      ("may.png",             64, 64, "player.pal",
                       [("bike", [0, 1, 2, 3], 4)]),
    # The credits sheets carry three extra frames: the rider glancing back
    # over their shoulder (sAnim_PlayerBicycle_LookBack/LookForward).
    "brendan_credits": ("brendan_credits.png", 64, 64, None,
                        [("bike", [0, 1, 2, 3], 8), ("look_back", [4, 5, 6], 4),
                         ("look_forward", [6, 5, 4], 16)]),
    "may_credits":    ("may_credits.png",     64, 64, None,
                       [("bike", [0, 1, 2, 3], 8), ("look_back", [4, 5, 6], 4),
                        ("look_forward", [6, 5, 4], 16)]),
    "bicycle_brendan": ("bicycle.png",        64, 32, "player.pal",
                        [("bike", [0, 1, 2, 3], 4)]),
}

POKEMON = {
    "manectric": ("manectric.png", 64, 64, None, [("run", [0, 1, 2, 3], 4)]),
    "torchic":   ("torchic.png",   32, 32, None,
                  [("walk", [0, 1, 2, 1], 5), ("run", [0, 1, 2, 1], 3),
                   ("trip", [3, 4, 5], 4)]),
    "volbeat":   ("volbeat.png",   32, 32, None, [("fly", [0, 1], 2)]),
    "flygon":    ("flygon.png",    64, 64, None, [("fly", [0, 1], 16)]),
    "latios":    ("latios.png",    64, 64, None, [("fly", [0, 1], 16)]),
    "latias":    ("latias.png",    64, 64, None, [("fly", [0, 1], 16)]),
}
# Flygon/Latios/Latias are one 128x64 pokemon split across two OBJs
WIDE_MONS = {"flygon", "latios", "latias"}

# Background layer sets, from LoadIntroPart2Graphics / LoadCreditsSceneGraphics
SCENES = {
    "day":    dict(bg="trees.png", map="trees_map.bin", bgpal=None,
                   grasspal=None, scenery="trees_small.png", scenerypal=None,
                   layout="trees"),
    "sunset": dict(bg="trees.png", map="trees_map.bin", bgpal="trees_sunset.pal",
                   grasspal="grass_sunset.pal", scenery="trees_small.png",
                   scenerypal="trees_sunset.pal", layout="trees"),
    "night":  dict(bg="houses.png", map="houses_map.bin", bgpal="houses.pal",
                   grasspal="grass_night.pal", scenery="house_silhouette.png",
                   scenerypal=None, layout="houses"),
    "ocean":  dict(bg="clouds_bg.png", map="clouds_bg_map.bin",
                   bgpal="clouds_bg.pal", grasspal=None, scenery="clouds.png",
                   scenerypal=None, layout="clouds"),
    "ocean_sunset": dict(bg="clouds_bg.png", map="clouds_bg_map.bin",
                         bgpal="clouds_bg_sunset.pal", grasspal="grass_sunset.pal",
                         scenery="clouds.png", scenerypal="clouds_sunset.pal",
                         layout="clouds"),
}

# Layer scroll, px per GBA frame, rounded from CreateBicycleBgAnimationTask so
# every layer's period divides the 256-frame loop (see render_bike_loop.py).
SCROLL = {"far": 0.0, "near": 1.0, "ground": 4.0}
SCENERY_SCROLL = {32: 1.125, 16: 2.25}   # by piece width: bigger == further away

# Moving-scenery OBJ pieces per scene layout: name -> (first tile, w, h)
SCENERY_PIECES = {
    "trees":  {"tree_large": (0, 32, 32), "tree_tall": (16, 16, 32),
               "tree_small": (24, 16, 16)},
    "houses": {"house": (0, 32, 32)},
    "clouds": {"cloud_largest": (0, 32, 32), "cloud_large": (16, 16, 16),
               "cloud_small": (20, 16, 8), "cloud_smallest": (22, 16, 8)},
}


# Where each moving-scenery OBJ starts, from sSpriteMetadata_* (x and y are
# the OBJ centre, and they wrap over a 288 px span: x > 255 resets to -32).
SCENERY_PLACEMENT = {
    "trees": [("tree_large", 16, 88), ("tree_large", 80, 88),
              ("tree_large", 144, 88), ("tree_large", 208, 88),
              ("tree_tall", 40, 88), ("tree_tall", 104, 88),
              ("tree_tall", 168, 88), ("tree_tall", 232, 88),
              ("tree_small", 56, 96), ("tree_small", 120, 96),
              ("tree_small", 184, 96), ("tree_small", 248, 96)],
    "houses": [("house", 24, 88), ("house", 64, 88), ("house", 104, 88),
               ("house", 144, 88), ("house", 184, 88), ("house", 224, 88)],
    "clouds": [("cloud_largest", 72, 32), ("cloud_largest", 158, 32),
               ("cloud_large", 192, 40), ("cloud_large", 56, 40),
               ("cloud_small", 100, 44), ("cloud_small", 152, 44),
               ("cloud_smallest", 8, 46), ("cloud_smallest", 56, 46),
               ("cloud_smallest", 240, 46)],
}


SCENERY_WRAP = 288  # OBJs run from -32 to 255 before resetting, in GBA px


def a(name):
    return os.path.join(ASSETS, name)


def layer_period(layer):
    """Smallest horizontal repeat of a 256-px-wide BG layer.

    The tilemap wraps every 256 px, but most of these layers repeat sooner, and
    a shorter period means a narrower strip and a shorter loop.
    """
    for p in (8, 16, 32, 64, 128, 256):
        if np.array_equal(layer, np.roll(layer, p, axis=1)):
            return p
    return 256


def to_rgba(idx, pal):
    """Index array + palette -> RGBA, with palette index 0 fully transparent."""
    h, w = idx.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = pal[idx]
    out[..., 3] = np.where(idx == 0, 0, 255)
    return out


def common_bbox(frames):
    """Tightest box containing the opaque pixels of every frame."""
    box = None
    for fr in frames:
        ys, xs = np.nonzero(fr[..., 3])
        if not len(ys):
            continue
        b = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]),
                                     max(box[2], b[2]), max(box[3], b[3]))
    return box


def save_strip(frames, path, scale, trim=True):
    """Write frames side by side as one RGBA strip. Returns its metadata."""
    fh, fw = frames[0].shape[:2]
    ox, oy = 0, 0
    if trim:
        box = common_bbox(frames)
        if box:
            ox, oy = int(box[0]), int(box[1])
            frames = [fr[box[1]:box[3], box[0]:box[2]] for fr in frames]
    h, w = frames[0].shape[:2]
    strip = np.zeros((h, w * len(frames), 4), dtype=np.uint8)
    for i, fr in enumerate(frames):
        strip[:, i * w : (i + 1) * w] = fr
    im = Image.fromarray(strip, "RGBA")
    if scale != 1:
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)
    return dict(file=os.path.basename(path), frames=len(frames),
                frame_width=w * scale, frame_height=h * scale,
                oam_width=fw * scale, oam_height=fh * scale,
                trim_offset=[ox * scale, oy * scale])


# The bicycle's bottom two rows are a contact shadow painted olive green so it
# blends into the grass. On any other background it reads as a stray line.
BIKE_SHADOW_INDEX = 15


def export_obj(name, spec, outdir, scale, meta, wide=False, shadow="separate"):
    sheet_file, fw, fh, pal_file, anims = spec
    sheet, own_pal = load_indexed(a(sheet_file))
    pal = load_jasc_pal(a(pal_file)) if pal_file else own_pal
    raw = split_frames(sheet, fw, fh)

    if sheet_file == "bicycle.png" and shadow != "keep":
        if shadow == "separate":
            shade = [np.where(f == BIKE_SHADOW_INDEX, f, 0) for f in raw]
            save_strip([to_rgba(f, pal) for f in shade],
                       os.path.join(outdir, f"{name}_shadow.png"), scale)
        raw = [np.where(f == BIKE_SHADOW_INDEX, 0, f) for f in raw]

    if wide:
        # Stitch the left and right OBJ halves back into one 128x64 sprite
        raw = [np.concatenate([raw[0], raw[1]], axis=1)]
        anims = [("fly", [0], 16)]

    frames = [to_rgba(f, pal) for f in raw]
    entries = {}
    for anim, order, delay in anims:
        seq = [frames[i] for i in order]
        info = save_strip(seq, os.path.join(outdir, f"{name}_{anim}.png"), scale)
        info["frame_delay_gba"] = delay
        info["frame_ms"] = round(delay * 1000 / 59.7275, 1)
        info["source_frames"] = order
        entries[anim] = info
    meta[name] = entries


def export_composed_rider(who, sheet_key, outdir, scale, meta, shadow="separate"):
    """Rider and bicycle drawn together, the way CreateIntroBrendanSprite does.

    The bike OBJ tracks the rider at y + 8, so its 64x32 art sits 24 px below
    the rider's 64x64 top edge once both are anchored on their own centres.
    """
    rider_spec = CHARACTERS[f"{who}_{sheet_key}"]
    rider_sheet, rider_own = load_indexed(a(rider_spec[0]))
    rider_pal = load_jasc_pal(a(rider_spec[3])) if rider_spec[3] else rider_own
    rider = split_frames(rider_sheet, 64, 64)[:4]
    bike = split_frames(load_indexed(a("bicycle.png"))[0], 64, 32)
    if shadow != "keep":
        bike = [np.where(f == BIKE_SHADOW_INDEX, 0, f) for f in bike]

    frames = []
    for i in range(4):
        canvas = np.zeros((88, 64, 4), dtype=np.uint8)
        b = to_rgba(bike[i], rider_pal)
        canvas[24:56][b[..., 3] > 0] = b[b[..., 3] > 0]
        r = to_rgba(rider[i], rider_pal)
        top = canvas[0:64]
        top[r[..., 3] > 0] = r[r[..., 3] > 0]
        frames.append(canvas)

    delay = 4 if sheet_key == "intro" else 8
    info = save_strip(frames, os.path.join(outdir, f"{who}_on_bike.png"), scale)
    info["frame_delay_gba"] = delay
    info["frame_ms"] = round(delay * 1000 / 59.7275, 1)
    meta[f"{who}_on_bike"] = {"bike": info}


def export_backgrounds(scene_name, outdir, scale, meta):
    scene = SCENES[scene_name]
    bg_sheet, bg_own = load_indexed(a(scene["bg"]))
    bg_pal = load_jasc_pal(a(scene["bgpal"])) if scene["bgpal"] else bg_own
    blocks = load_screenblocks(a(scene["map"]))

    grass_sheet, grass_own = load_indexed(a("grass.png"))
    grass_pal = (load_jasc_pal(a(scene["grasspal"])) if scene["grasspal"]
                 else grass_own)

    # The scene's BG palette file goes to slot 0 and spills into 1 and 2 when it
    # holds more than 16 colours (clouds_bg.pal has 48, houses.pal 32); grass
    # always loads at slot 15. Each tilemap entry then picks its own slot.
    bank = palette_bank([(0, bg_pal), (15, grass_pal)])

    layers = {
        "far": build_bg_rgba(bg_sheet, blocks[0], bank),
        "near": build_bg_rgba(bg_sheet, blocks[1], bank),
        "ground": build_bg_rgba(grass_sheet,
                                load_screenblocks(a("grass_map.bin"))[0], bank),
    }

    entry = {"backdrop_rgb": [int(v) for v in bank[0, 0]], "layers": {}, "scenery": {}}
    d = os.path.join(outdir, scene_name)
    os.makedirs(d, exist_ok=True)

    for lname, layer in layers.items():
        # Drop transparent rows, then clip to what actually falls on the canvas
        rows = np.nonzero(layer[..., 3].any(axis=1))[0]
        if not len(rows):
            continue
        y0 = int(rows[0])
        y1 = min(int(rows[-1]) + 1, CANVAS_H // scale)
        art = layer[y0:y1]
        if art.size == 0:
            continue
        # Repeat past the canvas by one period, so sliding the layer left by up
        # to `period` px never exposes a gap on the right.
        period = layer_period(layer)
        strip_w = CANVAS_W // scale + period
        reps = -(-strip_w // period)
        tiled = np.tile(art, (1, reps, 1))[:, :strip_w]
        im = Image.fromarray(tiled, "RGBA")
        if scale != 1:
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        im.save(os.path.join(d, f"{lname}.png"))
        entry["layers"][lname] = dict(
            file=f"{lname}.png", y=y0 * scale, height=(y1 - y0) * scale,
            tile_period=period * scale, width=im.width,
            scroll_px_per_gba_frame=SCROLL[lname] * scale)

    scenery_sheet, scenery_own = load_indexed(a(scene["scenery"]))
    scenery_pal = (load_jasc_pal(a(scene["scenerypal"])) if scene["scenerypal"]
                   else scenery_own)
    pieces = {}
    for piece, (tile, w, h) in SCENERY_PIECES[scene["layout"]].items():
        frame = to_rgba(cut_obj(scenery_sheet, tile, w, h), scenery_pal)
        pieces[piece] = frame
        info = save_strip([frame], os.path.join(d, f"scenery_{piece}.png"), scale)
        info["scroll_px_per_gba_frame"] = SCENERY_SCROLL[w] * scale
        entry["scenery"][piece] = info

    # Pre-composed scenery strips, one per parallax speed, tileable over the
    # 288 px span the OBJs wrap across. Ready to slide as a single layer.
    entry["scenery_layers"] = {}
    by_speed = {}
    for piece, x, y in SCENERY_PLACEMENT[scene["layout"]]:
        w = SCENERY_PIECES[scene["layout"]][piece][1]
        by_speed.setdefault(SCENERY_SCROLL[w], []).append((piece, x, y))

    for rank, speed in enumerate(sorted(by_speed)):
        placed = by_speed[speed]
        tops = [y - pieces[p].shape[0] // 2 for p, _, y in placed]
        bots = [y - pieces[p].shape[0] // 2 + pieces[p].shape[0] for p, _, y in placed]
        y0, y1 = min(tops), max(bots)
        strip_w = CANVAS_W // scale + SCENERY_WRAP
        strip = np.zeros((y1 - y0, strip_w, 4), dtype=np.uint8)
        for piece, x, y in placed:
            art = pieces[piece]
            ph, pw = art.shape[:2]
            for n in range(-1, strip_w // SCENERY_WRAP + 2):
                px = x + n * SCENERY_WRAP - pw // 2
                py = y - ph // 2 - y0
                sx0, sx1 = max(0, -px), min(pw, strip_w - px)
                if sx0 >= sx1:
                    continue
                sub = art[:, sx0:sx1]
                dst = strip[py : py + ph, px + sx0 : px + sx1]
                m = sub[..., 3] > 0
                dst[m] = sub[m]

        name = f"scenery_layer_{rank}"
        im = Image.fromarray(strip, "RGBA")
        if scale != 1:
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        im.save(os.path.join(d, f"{name}.png"))
        entry["scenery_layers"][name] = dict(
            file=f"{name}.png", y=y0 * scale, height=(y1 - y0) * scale,
            width=im.width, tile_period=SCENERY_WRAP * scale,
            scroll_px_per_gba_frame=speed * scale)

    entry["scenery_placement"] = [
        {"piece": piece, "x": x * scale, "y": y * scale}
        for piece, x, y in SCENERY_PLACEMENT[scene["layout"]]]
    entry["scenery_wrap_px"] = 288 * scale
    meta[scene_name] = entry


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scale", type=int, nargs="+", default=[1, DEFAULT_SCALE],
                   help="export at these integer scales (4 fills 640 px height)")
    p.add_argument("--shadow", default="separate",
                   choices=["separate", "drop", "keep"],
                   help="what to do with the bicycle's olive contact shadow")
    p.add_argument("--out", default="sprites")
    args = p.parse_args()

    for scale in args.scale:
        root = os.path.join(args.out, f"x{scale}")
        meta = {"scale": scale, "canvas": [CANVAS_W, CANVAS_H],
                "gba_screen": [240 * scale, 160 * scale],
                "fps": 59.7275, "characters": {}, "pokemon": {}, "backgrounds": {}}

        cdir = os.path.join(root, "characters")
        for name, spec in CHARACTERS.items():
            export_obj(name, spec, cdir, scale, meta["characters"],
                       shadow=args.shadow)
        for who in ("brendan", "may"):
            export_composed_rider(who, "intro", cdir, scale, meta["characters"],
                                  shadow=args.shadow)

        pdir = os.path.join(root, "pokemon")
        for name, spec in POKEMON.items():
            export_obj(name, spec, pdir, scale, meta["pokemon"],
                       wide=name in WIDE_MONS)

        bdir = os.path.join(root, "backgrounds")
        for scene_name in SCENES:
            export_backgrounds(scene_name, bdir, scale, meta["backgrounds"])

        with open(os.path.join(root, "sprites.json"), "w") as fh:
            json.dump(meta, fh, indent=2)
        print(f"{root}  ({sum(len(v) for v in meta['characters'].values())} character "
              f"anims, {len(meta['pokemon'])} pokemon, {len(meta['backgrounds'])} scenes)")


if __name__ == "__main__":
    main()
