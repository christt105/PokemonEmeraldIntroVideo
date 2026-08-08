#!/usr/bin/env python3
"""Render the Pokemon Emerald bike-ride scene as a seamless animated loop.

Rebuilds the scene from the pret/pokeemerald assets (graphics/intro/scene_2)
rather than capturing the emulator, so the loop can be made frame-exact and
rendered at any scale.

  python3 render_bike_loop.py --scene day --scale 4 --format gif mp4
"""

import argparse
import os
import subprocess

import numpy as np
from PIL import Image

from gba import (
    DISPLAY_H,
    DISPLAY_W,
    Canvas,
    build_bg_rgba,
    cut_obj,
    palette_bank,
    gba_cos,
    gba_sin,
    load_indexed,
    load_jasc_pal,
    load_screenblocks,
    split_frames,
)

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def a(name):
    return os.path.join(ASSETS, name)


# Backdrop layer set per scene: (tileset png, tilemap bin, far/near bg palette,
# ground palette, moving-scenery sheet, its palette, sprite layout key)
SCENES = {
    # Intro scene 2: daytime, forest
    "day": dict(bg="trees.png", map="trees_map.bin", bgpal=None,
                grasspal=None, scenery="trees_small.png", scenerypal=None,
                layout="trees"),
    # Credits: forest at sunset
    "sunset": dict(bg="trees.png", map="trees_map.bin", bgpal="trees_sunset.pal",
                   grasspal="grass_sunset.pal", scenery="trees_small.png",
                   scenerypal="trees_sunset.pal", layout="trees"),
    # Credits: town at night
    "night": dict(bg="houses.png", map="houses_map.bin", bgpal="houses.pal",
                  grasspal="grass_night.pal", scenery="house_silhouette.png",
                  scenerypal=None, layout="houses"),
    # Credits: ocean at morning
    "ocean": dict(bg="clouds_bg.png", map="clouds_bg_map.bin", bgpal="clouds_bg.pal",
                  grasspal=None, scenery="clouds.png", scenerypal=None,
                  layout="clouds"),
    "ocean_sunset": dict(bg="clouds_bg.png", map="clouds_bg_map.bin",
                         bgpal="clouds_bg_sunset.pal", grasspal="grass_sunset.pal",
                         scenery="clouds.png", scenerypal="clouds_sunset.pal",
                         layout="clouds"),
}

# Moving-scenery sprite layouts, straight from sSpriteMetadata_* in
# intro_credits_graphics.c: (anim frame, w, h, x, y, subpriority)
SCENERY_LAYOUTS = {
    "trees": [
        (0, 32, 32, 16, 88, 100), (0, 32, 32, 80, 88, 100),
         (0, 32, 32, 144, 88, 100), (0, 32, 32, 208, 88, 100),
         (16, 16, 32, 40, 88, 101), (16, 16, 32, 104, 88, 101),
         (16, 16, 32, 168, 88, 101), (16, 16, 32, 232, 88, 101),
         (24, 16, 16, 56, 96, 102), (24, 16, 16, 120, 96, 102),
         (24, 16, 16, 184, 96, 102), (24, 16, 16, 248, 96, 102)
    ],
    "houses": [
        (0, 32, 32, 24, 88, 100), (0, 32, 32, 64, 88, 100),
         (0, 32, 32, 104, 88, 100), (0, 32, 32, 144, 88, 100),
         (0, 32, 32, 184, 88, 100), (0, 32, 32, 224, 88, 100)
    ],
    "clouds": [
        (0, 32, 32, 72, 32, 100), (0, 32, 32, 158, 32, 100),
         (16, 16, 16, 192, 40, 101), (16, 16, 16, 56, 40, 101),
         (20, 16, 8, 100, 44, 102), (20, 16, 8, 152, 44, 102),
         (22, 16, 8, 8, 46, 103), (22, 16, 8, 56, 46, 103),
         (22, 16, 8, 240, 46, 103)
    ],
}

# Scroll speeds in px/frame. The game's own values (CreateBicycleBgAnimationTask
# with 0x4000/0x400/0x10, scenery xOff 0x2000/0x1000) never realign, so the loop
# preset rounds them to values whose period divides LOOP_FRAMES.
LOOP_FRAMES = 256
SPEEDS_LOOP = dict(grass=4.0, bg2=1.0, bg3=0.0, scenery_big=1.125, scenery_small=2.25)
SPEEDS_GAME = dict(grass=4.0, bg2=0.25, bg3=0.0625, scenery_big=0.125,
                   scenery_small=0.0625)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scene", default="day", choices=sorted(SCENES))
    p.add_argument("--gender", default="male", choices=["male", "female"])
    p.add_argument("--sheet", default="intro", choices=["intro", "credits"],
                   help="intro = 4-frame rider sheet, credits = 7-frame sheet")
    p.add_argument("--scale", type=int, default=4)
    p.add_argument("--frames", type=int, default=LOOP_FRAMES)
    p.add_argument("--fps", type=float, default=59.7275)
    p.add_argument("--step", type=int, default=1,
                   help="keep every Nth frame (2 halves GIF size; the loop stays "
                        "seamless as long as N divides --frames)")
    p.add_argument("--speeds", default="loop", choices=["loop", "game"])
    p.add_argument("--format", nargs="+", default=["gif", "mp4"],
                   choices=["gif", "mp4", "webm", "png"])
    p.add_argument("--out", default="out")
    p.add_argument("--pokemon", default="manectric,torchic,volbeat,flygon",
                   help="comma-separated subset of manectric,torchic,volbeat,"
                        "flygon,latios,latias")
    args = p.parse_args()

    scene = SCENES[args.scene]
    speeds = SPEEDS_LOOP if args.speeds == "loop" else SPEEDS_GAME
    os.makedirs(args.out, exist_ok=True)

    # --- backgrounds -------------------------------------------------------
    bg_sheet, bg_own_pal = load_indexed(a(scene["bg"]))
    bg_pal = load_jasc_pal(a(scene["bgpal"])) if scene["bgpal"] else bg_own_pal
    blocks = load_screenblocks(a(scene["map"]))

    grass_sheet, grass_own_pal = load_indexed(a("grass.png"))
    grass_pal = load_jasc_pal(a(scene["grasspal"])) if scene["grasspal"] else grass_own_pal

    # The BG palette file lands at slot 0 and spills into 1 and 2 when it holds
    # more than 16 colours; grass always loads at slot 15. Each tilemap entry
    # then picks which slot its tile uses.
    bank = palette_bank([(0, bg_pal), (15, grass_pal)])

    # trees_map/houses_map/clouds_bg_map hold two screenblocks: 6 -> BG3, 7 -> BG2
    bg3 = build_bg_rgba(bg_sheet, blocks[0], bank)
    bg2 = build_bg_rgba(bg_sheet, blocks[1], bank) if len(blocks) > 1 else None
    bg1 = build_bg_rgba(grass_sheet, load_screenblocks(a("grass_map.bin"))[0], bank)

    scenery_sheet, scenery_own_pal = load_indexed(a(scene["scenery"]))
    scenery_pal = (load_jasc_pal(a(scene["scenerypal"])) if scene["scenerypal"]
                   else scenery_own_pal)
    scenery_meta = SCENERY_LAYOUTS[scene["layout"]]

    backdrop = bank[0, 0]

    # --- rider + bike ------------------------------------------------------
    who = "brendan" if args.gender == "male" else "may"
    if args.sheet == "credits":
        rider_sheet, rider_pal = load_indexed(a(f"{who}_credits.png"))
    else:
        rider_sheet, _ = load_indexed(a(f"{who}.png"))
        rider_pal = load_jasc_pal(a("player.pal"))
    rider_frames = split_frames(rider_sheet, 64, 64)[:4]
    bike_sheet, _ = load_indexed(a("bicycle.png"))
    bike_frames = split_frames(bike_sheet, 64, 32)

    # --- accompanying pokemon ---------------------------------------------
    mons = [m.strip() for m in args.pokemon.split(",") if m.strip()]

    manectric_sheet, manectric_pal = load_indexed(a("manectric.png"))
    manectric_frames = split_frames(manectric_sheet, 64, 64)
    torchic_sheet, torchic_pal = load_indexed(a("torchic.png"))
    torchic_frames = split_frames(torchic_sheet, 32, 32)
    volbeat_sheet, volbeat_pal = load_indexed(a("volbeat.png"))
    volbeat_frames = split_frames(volbeat_sheet, 32, 32)

    flyer_name = next((m for m in mons if m in ("flygon", "latios", "latias")), None)
    flyer_frames = flyer_pal = None
    if flyer_name:
        flyer_sheet, flyer_pal = load_indexed(a(f"{flyer_name}.png"))
        flyer_frames = split_frames(flyer_sheet, 64, 64)

    # Rider wobble: the game picks it at random every 8th frame; a fixed
    # 4-step pattern keeps it seamless across the loop.
    wobble = [0, -1, 0, 1]

    frames = []
    for f in range(0, args.frames, args.step):
        c = Canvas(backdrop)

        # BG3 starts at hofs 8 (tBg3PosHi in CreateBicycleBgAnimationTask)
        c.blit_bg(bg3, 8 - speeds["bg3"] * f, 0)

        # Moving-scenery OBJs sit at OAM priority 3: over BG3, under BG2/BG1
        for meta in sorted(scenery_meta, key=lambda m: -m[5]):
            tile, w, h, x0, y0, _ = meta
            v = speeds["scenery_big"] if w >= 32 else speeds["scenery_small"]
            x = ((x0 + v * f + 32) % 288) - 32
            frame = cut_obj(scenery_sheet, tile, w, h)
            c.blit_sprite(frame, scenery_pal, x - w // 2, y0 - h // 2)

        if bg2 is not None:
            c.blit_bg(bg2, -speeds["bg2"] * f, 0)
        c.blit_bg(bg1, -speeds["grass"] * f, 0)

        # --- OBJ priority 1: flyer, volbeat, rider, torchic, manectric -----
        if flyer_frames is not None:
            fy = 46 + gba_sin(f * 4, 8)
            # left and right halves of one 128x64 pokemon
            c.blit_sprite(flyer_frames[0], flyer_pal, 168 - 32 - 32, fy - 32)
            c.blit_sprite(flyer_frames[1], flyer_pal, 168 + 32 - 32, fy - 32)

        if "volbeat" in mons:
            # Figure-8 from VOLBEAT_FIGURE_8 in intro.c, kept inside the frame
            vx = 56 + gba_sin(0xC0 + f * 2, 26)
            vy = 72 + gba_sin(0x80 + f * 4, 0x14)
            vf = volbeat_frames[(f // 2) % 2]
            c.blit_sprite(vf, volbeat_pal, vx - 16, vy - 16)

        ry = 100 + wobble[(f // 8) % 4]
        rf = (f // 4) % 4
        c.blit_sprite(bike_frames[rf], rider_pal, 120 - 32, ry + 8 - 16)
        c.blit_sprite(rider_frames[rf], rider_pal, 120 - 32, ry - 32)

        if "torchic" in mons:
            # Run cycle 0,16,32,16 (sAnim_Torchic_Run) at 4 ticks so it tiles
            tf = [0, 1, 2, 1][(f // 4) % 4]
            ty = 112 + (1 if (f // 4) % 2 else 0)
            c.blit_sprite(torchic_frames[tf], torchic_pal, 196 - 16, ty - 16)

        if "manectric" in mons:
            mf = (f // 4) % 4
            my = 126 + gba_cos(f * 4, 2)
            c.blit_sprite(manectric_frames[mf], manectric_pal, 64 - 32, my - 32)

        frames.append(c.rgb.copy())

    # --- encode ------------------------------------------------------------
    fps = args.fps / args.step
    base = f"bike_{args.scene}_{args.gender}"
    imgs = [Image.fromarray(fr) for fr in frames]
    if args.scale != 1:
        imgs = [im.resize((DISPLAY_W * args.scale, DISPLAY_H * args.scale),
                          Image.NEAREST) for im in imgs]

    written = []
    if "png" in args.format:
        d = os.path.join(args.out, base + "_frames")
        os.makedirs(d, exist_ok=True)
        for i, im in enumerate(imgs):
            im.save(os.path.join(d, f"{i:04d}.png"))
        written.append(d)

    if "gif" in args.format:
        path = os.path.join(args.out, base + ".gif")
        pal_im = imgs[0].quantize(colors=255, method=Image.MEDIANCUT)
        gif = [im.quantize(palette=pal_im, dither=Image.NONE) for im in imgs]
        gif[0].save(path, save_all=True, append_images=gif[1:], loop=0,
                    duration=round(1000 / fps), disposal=1, optimize=True)
        written.append(path)

    for fmt in ("mp4", "webm"):
        if fmt not in args.format:
            continue
        raw = os.path.join(args.out, base + ".raw")
        with open(raw, "wb") as fh:
            for im in imgs:
                fh.write(np.asarray(im.convert("RGB")).tobytes())
        path = os.path.join(args.out, f"{base}.{fmt}")
        codec = (["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16"]
                 if fmt == "mp4" else
                 ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-crf", "24", "-b:v", "0"])
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo",
             "-pixel_format", "rgb24", "-video_size", f"{imgs[0].width}x{imgs[0].height}",
             "-framerate", str(fps), "-i", raw, *codec, path],
            check=True)
        os.remove(raw)
        written.append(path)

    for w in written:
        print(w)


if __name__ == "__main__":
    main()
