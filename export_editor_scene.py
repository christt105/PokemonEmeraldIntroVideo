#!/usr/bin/env python3
"""Convert a scene to the portable format the web editor speaks.

The old format names a background (`"background": "day"`) and lets `compose.py`
rebuild it from the ROM data. That is convenient here and meaningless anywhere
else, so the editor wants every layer spelled out as a PNG with its own speed:

    python3 export_editor_scene.py scenes/wide.json

writes `scenes/wide_web.json`, which both the editor at
https://christt105.github.io/parallax-scene-editor/ and `compose.py` can read.

The exported PNGs it points at are the ones `export_sprites.py` already writes,
so there is nothing new to generate — open the project folder in the editor and
the paths resolve.

One thing does flip: the editor takes a positive `speed` to scroll artwork
leftwards, the way a runner moving right sees the world go by. The game scrolls
the other way, so the speeds come out negated.
"""

import argparse
import json
import os


def build_layers(meta, scene_name, speeds):
    """far, scenery, near, ground — in the order the game draws them."""
    bg = meta["backgrounds"][scene_name]
    root = f"backgrounds/{scene_name}"
    out = []
    depth = -160

    def add(name, info, speed, **extra):
        nonlocal depth
        out.append({
            "name": name,
            "sprite": f"{root}/{info['file']}",
            "y": info.get("y", 0),
            "depth": depth,
            "speed": -speed,
            "tile_period": info.get("tile_period", 0),
            "repeat": "x",
            **extra,
        })
        depth += 5

    layers = bg["layers"]
    if "far" in layers:
        add("far", layers["far"], speeds.get("far", 0), extend_up=True)

    # slower scenery sits further back, which is also the order it is drawn in
    for name, info in sorted(bg.get("scenery_layers", {}).items(),
                             key=lambda kv: kv[1]["scroll_px_per_gba_frame"]):
        add(name, info, info["scroll_px_per_gba_frame"])

    for name in ("near", "ground"):
        if name in layers:
            add(name, layers[name], speeds.get(name, layers[name].get(
                "scroll_px_per_gba_frame", 0)))
    return out


def convert(cfg, meta):
    if cfg.get("layers"):
        raise SystemExit("that scene is already in the portable format")
    speeds = dict({"far": 0.0, "near": 1.0, "ground": 4.0},
                  **cfg.get("layer_speeds", {}))
    bg = meta["backgrounds"][cfg["background"]]
    return {
        "format": "parallax-scene/1",
        "name": cfg.get("name", "scene"),
        "canvas": cfg.get("canvas", [1280, 640]),
        "zoom": cfg.get("zoom", 4),
        "world_height": 160,
        "align": "bottom",
        "loop_frames": cfg.get("loop_frames", 256),
        "fps": cfg.get("fps", 59.7275),
        "backdrop": "#%02x%02x%02x" % tuple(bg["backdrop_rgb"]),
        "sprite_root": cfg.get("sprite_root", "sprites/x1"),
        "layers": build_layers(meta, cfg["background"], speeds),
        "actors": [{k: v for k, v in a.items() if not k.startswith("_")}
                   for a in cfg["actors"]],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("scene", help="path to a scene .json in the old format")
    p.add_argument("-o", "--out", help="default: <name>_web.json next to it")
    args = p.parse_args()

    cfg = json.load(open(args.scene))
    root = cfg.get("sprite_root", "sprites/x1")
    meta = json.load(open(os.path.join(root, "sprites.json")))

    out = args.out or f"{os.path.splitext(args.scene)[0]}_web.json"
    name = os.path.basename(os.path.splitext(out)[0])
    scene = convert(cfg, meta)
    scene["name"] = name
    with open(out, "w") as fh:
        json.dump(scene, fh, indent=2, ensure_ascii=False)
    print(out)
    print(f"{len(scene['layers'])} capas, {len(scene['actors'])} actores")


if __name__ == "__main__":
    main()
