#!/usr/bin/env python3
"""Export any Pokemon's Emerald sprites as RGBA sheets for Aseprite.

The bike scene only ships six hand-drawn side-view Pokemon. For anything else,
this pulls the regular battle and menu sprites out of pret/pokeemerald, which
is exactly what the credits do (CreateCreditsMonSprite uses the normal front
sprites).

  python3 export_pokemon.py pikachu swampert rayquaza --scale 4

Note these are front/back views, not side-view runners, so they read as
"posing alongside" rather than "running with" the bike.
"""

import argparse
import json
import os

import numpy as np
from PIL import Image

from gba import load_indexed, load_jasc_pal, split_frames
from export_sprites import save_strip, to_rgba

MONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "decomp", "monsrc", "graphics", "pokemon")

# file -> (frame w, frame h, palette file or None for the PNG's own, frame delay)
VIEWS = {
    "anim_front": (64, 64, "pal", 20),
    "back":       (64, 64, "pal", 20),
    "icon":       (32, 32, None, 20),
}


def list_mons():
    return sorted(d for d in os.listdir(MONS_DIR)
                  if os.path.isdir(os.path.join(MONS_DIR, d)))


def export_mon(name, outdir, scale, shiny, meta):
    src = os.path.join(MONS_DIR, name)
    if not os.path.isdir(src):
        raise SystemExit(f"unknown pokemon: {name!r} (see --list)")

    pal_file = os.path.join(src, "shiny.pal" if shiny else "normal.pal")
    pal = load_jasc_pal(pal_file) if os.path.exists(pal_file) else None
    suffix = "_shiny" if shiny else ""
    entry = {}

    for view, (fw, fh, pal_kind, delay) in VIEWS.items():
        path = os.path.join(src, f"{view}.png")
        if not os.path.exists(path):
            continue
        sheet, own_pal = load_indexed(path)
        use = pal if (pal_kind == "pal" and pal is not None) else own_pal
        frames = [to_rgba(f, use) for f in split_frames(sheet, fw, fh)]
        out = os.path.join(outdir, f"{name}_{view}{suffix}.png")
        info = save_strip(frames, out, scale)
        info["frame_delay_gba"] = delay
        info["frame_ms"] = round(delay * 1000 / 59.7275, 1)
        entry[view] = info

    meta[name + suffix] = entry
    return entry


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mons", nargs="*", help="pokemon names, e.g. pikachu swampert")
    p.add_argument("--list", action="store_true", help="print every available name")
    p.add_argument("--shiny", action="store_true")
    p.add_argument("--scale", type=int, nargs="+", default=[1, 4])
    p.add_argument("--out", default="sprites")
    args = p.parse_args()

    if not os.path.isdir(MONS_DIR):
        raise SystemExit(
            f"{MONS_DIR} missing. Fetch it with:\n"
            "  git clone --filter=blob:none --sparse --depth 1 "
            "https://github.com/pret/pokeemerald.git decomp/monsrc\n"
            "  git -C decomp/monsrc sparse-checkout set graphics/pokemon")

    if args.list:
        names = list_mons()
        print(f"{len(names)} pokemon:")
        for i in range(0, len(names), 6):
            print("  " + "  ".join(f"{n:<14}" for n in names[i : i + 6]))
        return

    if not args.mons:
        raise SystemExit("give at least one pokemon name, or --list")

    for scale in args.scale:
        outdir = os.path.join(args.out, f"x{scale}", "pokemon_extra")
        os.makedirs(outdir, exist_ok=True)
        index_path = os.path.join(outdir, "pokemon_extra.json")
        meta = json.load(open(index_path)) if os.path.exists(index_path) else {}
        for name in args.mons:
            export_mon(name.lower(), outdir, scale, args.shiny, meta)
        with open(index_path, "w") as fh:
            json.dump(meta, fh, indent=2)
        print(f"{outdir}  ({len(args.mons)} pokemon)")


if __name__ == "__main__":
    main()
