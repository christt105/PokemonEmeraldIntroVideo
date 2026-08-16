# Pokémon Emerald Bicycle Ride - Parallax Scene Project

![Result](./out/project.gif)

A pre-configured parallax animation scene project for the **[Parallax Scene Editor](https://github.com/christt105/parallax-scene-editor)** ([Live Web App](https://christt105.github.io/parallax-scene-editor/)), recreating the iconic Pokémon Emerald bicycle ride intro and credits sequence.

---

## Overview

This repository contains a standalone scene project (`project/`) designed to be loaded directly into the web-based **[Parallax Scene Editor](https://christt105.github.io/parallax-scene-editor/)** to preview, edit, and export seamless GIF and video loops.

---

## How to Use

1. Open the **[Parallax Scene Editor](https://christt105.github.io/parallax-scene-editor/)** in a Chromium-based web browser (Chrome, Edge, Brave).
2. Click **Open Folder...** and select the `project/` folder from this repository.
3. The editor will load `project/project.json` along with all sprite sheets and parallax background layers.
4. Preview the animation loop, adjust keyframes or layer speeds, and export your animated GIF directly from the browser.

---

## Project Structure

```text
project/
├── project.json       Main scene configuration file for Parallax Scene Editor
├── backgrounds/        Parallax background layers & tileable scenery strips
│   ├── day/            Daytime forest background & scenery layers
│   ├── night/          Nighttime background & scenery
│   ├── ocean/          Ocean & cloud background layers
│   ├── ocean_sunset/   Ocean sunset background layers
│   └── sunset/         Sunset forest background layers
├── characters/         Rider & bicycle sprite sheets (Brendan, May, bicycle)
└── pokemon/            Running Pokémon sprites (Manectric, Torchic, etc.)
                        plus the raw Spriters Resource sheets they were cut from

tools/
└── sheet_slice.py     Cuts one animation out of a raw sheet into a strip
```

---

## Scene Configuration (`project/project.json`)

The scene is defined in `project/project.json` using the `parallax-scene/1` specification:

- **Canvas**: `1280x640` (at `zoom: 3`, based on 160px GBA world height)
- **Loop Timing**: `256` frames at `59.7275` FPS (~4.28 seconds)
- **Background Layers**:
  - `far`: Far sky/mountains (speed `0`, tile period `128`)
  - `scenery_layer_0`: Distant scenery (speed `-1.125`, tile period `288`)
  - `scenery_layer_1`: Near scenery (speed `-2.25`, tile period `288`)
  - `near`: Trees/vegetation (speed `-1`, tile period `128`)
  - `ground`: Grass ground strip (speed `-4`, tile period `128`)
- **Actors**:
  - `manectric`: Running Pokémon with vertical cosine bounce
  - `rider`: Brendan on bike with vertical wobble
  - `mudkip`: Custom walking sprite overlay

---

## Ripping a sprite out of a Spriters Resource sheet

The `Custom _ Edited - …` sheets in `project/pokemon/` are reference rips, not
assets. The editor cannot read them directly and no amount of `frames`/`grid`
will make it: they have a flat `(199,225,209)` backdrop instead of alpha, the
cels are placed by hand rather than on a grid, and one sheet holds a dozen
unrelated animations plus a credit line and dotted grouping boxes.

`tools/sheet_slice.py` cuts one animation out of a sheet and writes the strip of
equal, transparent, aligned cels that `parallax-scene/1` expects. It needs
`pillow` and `numpy`.

**1. Read the sheet.** Rows are numbered top to bottom, counting the row the
credit text sits on. Cels are numbered left to right within a row; the loose
parts these sheets park on the right are dropped automatically, but a shiny
recolour standing next to the animation is not, so check the x ranges.

```bash
python tools/sheet_slice.py "project/pokemon/<sheet>.png" --list
```

**2. Cut it.** `--row` alone takes the whole row; add `--cels 0-2` (or `0,1,4`)
for part of one. If a row needs splitting differently, `--band y0:y1` takes
pixel coordinates instead.

```bash
python tools/sheet_slice.py "project/pokemon/<sheet>.png" --row 3 --out pokemon/foo_run.png
```

It prints an actor block to paste into `project.json`, and the exact commands
that produced everything currently in `project/pokemon/` are at the bottom of
this section.

### What it fixes, and what is left to you

**The layout slope.** This is the one that bites. These rows are pasted by
dragging, so a row often descends or climbs a couple of pixels per cel — 2 px on
Tropius' flight row, 2.7 px on Wingull's. Played back that reads as the sprite
sinking through the cycle and snapping home at the wrap. It cannot be spotted in
a single cel, and it is not always there: Breloom's run row looks identical on
the numbers but the up-and-down is a real bounce with no trend under it. The
tool fits the straight-line part, checks it against any drawing the row repeats
(two copies of one pose can only differ by layout), removes just that, and keeps
everything else. Read the `y:` line it prints — it says which of the two it
found.

**Horizontal placement is never kept.** The gaps between cels are eyeballed and
vary by a dozen pixels on one row; none of it is animation. Every cel is pinned
to its centre of mass, so the sprite tracks dead straight. If you want sway,
that is a `motion` entry in the editor, not a property of the sheet.

**Loop closing is on you.** `loop_frames` is 256, a power of two, so a cycle only
divides it if its length is a power of two — three cels, seven, ten cannot close
at any delay. The tool prints an `order` array padded to the next length that
does, holding a couple of cels a beat longer. The alternative is changing
`loop_frames`, which the editor's inspector will offer, but that moves every
layer speed too.

**Direction.** Every one of these sheets draws the Pokémon facing left and the
rider travels right, so the actor wants `"flip_x": true`.

**Scale.** These sheets are drawn at roughly twice the scale of the GBA
overworld sprites the scene is built around — Volbeat, a bug of the same size,
is 24×27 next to Ninjask's 61×50, and Zigzagoon stands twice as tall as Mudkip
though they are the same height in the games. The editor's `scale` clamps at 1,
so `--scale 0.5` does it here instead: each cel is box-averaged on its own ink
box and snapped back to the colours the sheet already uses, which keeps the
silhouette off the edge blends without keeping their in-between colours. It runs
before the pose grouping and the anchoring, so the centre-of-mass pin lands on a
whole pixel of the output grid rather than on half of one.

Halving costs the 1px details — Ninjask's eye comes out as a single pixel, and
Zigzagoon's stripes compact — so check the result rather than assuming it. Note
that shrinking a cel moves its top-left corner, so the actor's `x`/`y` in
`project.json` need the difference added back to keep the sprite where it was.

### What is in `project/pokemon/` and how it got there

```bash
S="project/pokemon/Custom _ Edited - Pokemon Customs - Third Generation -"
python tools/sheet_slice.py "$S #0276 Taillow.png"   --row 1 --cels 0-2 --out pokemon/taillow_fly.png
python tools/sheet_slice.py "$S #0263 Zigzagoon.png" --row 4            --out pokemon/zigzagoon_run.png
python tools/sheet_slice.py "$S #0286 Breloom.png"   --row 3            --out pokemon/breloom_run.png
python tools/sheet_slice.py "$S #0278 Wingull.png"   --row 1 --cels 0-5 --out pokemon/wingull_fly.png
python tools/sheet_slice.py "$S #0291 Ninjask.png"   --row 1 --cels 0-1 --scale 0.5 --out pokemon/ninjask_fly.png
```

| sprite | cels | cel size | cycle |
| --- | --- | --- | --- |
| `taillow_fly` | 3 | 37×31 | `order` of 4 |
| `zigzagoon_run` | 7 | 68×47 | `order` of 8 |
| `breloom_run` | 10 | 60×74 | `order` of 16 |
| `wingull_fly` | 6 | 58×46 | `order` of 8 |
| `ninjask_fly` | 2 | 34×29 | closes at any delay |
| `tropius_fly` | 12 | 190×70 | `order` of 16 |
| `tropius_glide` | 2 | 190×70 | closes at any delay |
| `tropius_flap` | 5 | 164×97 | `order` of 8 |

The three Tropius strips came out of row 4 of its sheet before this tool
existed, cut by hand and pinned to the trunk rather than to the whole
silhouette, which is why their cel boxes are a pixel or two off what
`sheet_slice.py` would produce today (`--row 4` with `--cels 0-11`, `4-5` and
`12-16` respectively — the tool independently finds the same +2.00 and −5.50
px/cel slopes). `tropius_fly` is the whole flight cycle, `tropius_glide` is the
two-cel flutter cut out of its middle and left on the same cel box so the two
are interchangeable, and `tropius_flap` is the separate wing-beat at the end of
the row, on a taller cel — swapping to it from the other two needs `y` +40 and,
with `flip_x`, `x` +10.

---

## Credits

- Original Pokémon Emerald graphics, tilemaps, and palettes by **Nintendo / Game Freak** ([pret/pokeemerald](https://github.com/pret/pokeemerald)).
- Visual editor: [christt105/parallax-scene-editor](https://github.com/christt105/parallax-scene-editor).



