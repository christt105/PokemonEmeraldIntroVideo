# Pokémon Emerald Bicycle Ride Parallax Scene

Assets, extracted sprites, scene specifications, and Python rendering scripts for generating seamless pixel-art parallax animated loops (GIF, MP4, WebM) of the Pokémon Emerald bicycle intro and credits sequence.

This scene project is fully compatible with the visual web tool **[Parallax Scene Editor](https://github.com/christt105/parallax-scene-editor)** ([Live Web App](https://christt105.github.io/parallax-scene-editor/)).


---

## Key Features

- **Extracted Sprite Library**: Clean RGBA sprites extracted from decompilation assets (`sprites/x1/`, `sprites/x4/`) covering characters, Pokémon, tileable scenery layers, and backgrounds (`day`, `sunset`, `night`, `ocean`, `ocean_sunset`).
- **Scene Compositor ([`compose.py`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/compose.py))**: Keyframe-driven scene rendering engine supporting camera zoom, multi-layer parallax scrolling, depth sorting, procedural motion (sine, cosine, wobble), and frame-rate adjustment.
- **Web Editor Integration ([`export_editor_scene.py`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/export_editor_scene.py))**: Export scene configurations into the portable JSON format compatible with the browser-based [Parallax Scene Editor](https://christt105.github.io/parallax-scene-editor/).
- **External Sprite Importer & Restyler**:
  - [`import_sprite.py`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/import_sprite.py): Automatically slices, auto-crops, and aligns irregular sprite sheets into uniform strips.
  - [`restyle_sprite.py`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/restyle_sprite.py): Converts flat black outlines of external sprites into tinted, warm-grey outlines matching Pokémon Emerald's intro art direction.
- **Pokémon Extractor ([`export_pokemon.py`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/export_pokemon.py))**: Extract any of the 386+ Gen 1–3 Pokémon battle/menu sprites (normal or shiny) directly from decompilation data.
- **Aseprite Generator ([`make_aseprite.lua`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/make_aseprite.lua))**: Generates pre-assembled `.aseprite` files with exact frame delays and multi-layer parallax scene templates.
- **GBA Engine Emulation ([`render_bike_loop.py`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/render_bike_loop.py) & [`gba.py`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/gba.py))**: Low-level Python renderer handling 4bpp tiles, screenblocks, and 1D OBJ mapping for bit-exact reference rendering.

---

## Web Parallax Scene Editor

Scenes can be edited visually in the browser using the **[Parallax Scene Editor](https://christt105.github.io/parallax-scene-editor/)** (Source: [christt105/parallax-scene-editor](https://github.com/christt105/parallax-scene-editor)).

### Workflow
1. Convert a native scene file to the portable web format:
   ```bash
   python3 export_editor_scene.py scenes/wide.json
   # Output: scenes/wide_web.json
   ```
2. Open [Parallax Scene Editor](https://christt105.github.io/parallax-scene-editor/) in a Chromium browser (Chrome, Edge, Brave) and select **Open Directory**, pointing to the root of this repository.
3. Edit parallax layers, actor keyframes, speeds, and loop timing visually.
4. Render the converted project using [`compose.py`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/compose.py):
   ```bash
   python3 compose.py scenes/wide_web.json --format gif mp4
   ```

---

## Directory Structure

```text
├── assets/             Decompiled GBA graphics, tilemaps, and palettes
├── decomp/             Subset of pret/pokeemerald graphics data
├── scenes/             JSON scene definitions (e.g. wide.json, wide_web.json)
├── sprites/
│   ├── x1/             Original scale (160px screen height)
│   └── x4/             4x scale (640px screen height)
│       ├── characters/ Rider and bicycle sprites
│       ├── pokemon/    Intro Pokémon (Manectric, Torchic, Volbeat, Flygon, etc.)
│       ├── pokemon_extra/ Extracted Pokémon battle/icon sprites
│       ├── external/   Imported external sprites (e.g., Mudkip)
│       ├── backgrounds/ Parallax background and ground strips
│       ├── aseprite/   Pre-assembled .aseprite files
│       └── sprites.json Sprite metadata, frame sizes, and speeds
├── compose.py          Main scene rendering and composition script
├── export_editor_scene.py Converts scenes to web editor JSON format
├── export_pokemon.py   Extracts any Pokémon sprite from decompilation data
├── export_sprites.py   Extracts GBA intro sprites into structured PNG sheets
├── import_sprite.py    Aligns and normalizes external sprite sheets
├── restyle_sprite.py   Adapts external sprite outlines to Emerald intro style
├── render_bike_loop.py Reference GBA loop renderer
├── gba.py              Low-level GBA tile, map, and palette renderer
└── make_aseprite.lua   Aseprite Lua script to build .aseprite files
```

---

## Main Tools & Usage

### 1. Rendering Scenes ([`compose.py`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/compose.py))

Renders a JSON scene specification to GIF, MP4, WebM, or PNG sequences.

```bash
# Render to GIF and MP4
python3 compose.py scenes/wide.json --format gif mp4

# Render a single specific frame
python3 compose.py scenes/wide.json --frame 0 --out out/

# Render PNG frame sequence with custom step
python3 compose.py scenes/wide.json --format png --step 2
```

### 2. Exporting Extra Pokémon ([`export_pokemon.py`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/export_pokemon.py))

Extracts front/back battle views and menu icons for any Pokémon:

```bash
# Export specific Pokémon at 4x scale
python3 export_pokemon.py pikachu swampert rayquaza --scale 4

# Include shiny variants
python3 export_pokemon.py charizard --shiny --scale 4

# List all available Pokémon names
python3 export_pokemon.py --list
```

### 3. Importing External Sprites ([`import_sprite.py`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/import_sprite.py))

Processes arbitrary sprite sheets into uniform, center-bottom aligned animation strips:

```bash
python3 import_sprite.py path/to/sheet.png --name mudkip_walk --anchor bottom-center --delay 6
```

### 4. Restyling Outlines to Match Intro Style ([`restyle_sprite.py`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/restyle_sprite.py))

Replaces flat black outlines on external sprites with contextual dark tones and warm grey highlights:

```bash
python3 restyle_sprite.py sprites/x1/external/mudkip_walk.png
```

### 5. Building Aseprite Files ([`make_aseprite.lua`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/make_aseprite.lua))

Generates pre-configured `.aseprite` animation files and scene layouts:

```bash
aseprite -b --script-param root=sprites/x4 --script-param scene=day --script make_aseprite.lua
```

---

## Scene Specification Format

Scenes are defined in JSON (e.g. [`scenes/wide.json`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/scenes/wide.json) or [`scenes/wide_web.json`](file:///home/christian/Projects/PokemonEmeraldIntroVideo/scenes/wide_web.json)). Below is an example actor definition:

```json
{
  "name": "mudkip",
  "sprite": "external/mudkip_walk.png",
  "frames": 3,
  "order": [0, 1, 2, 1],
  "delay": 8,
  "flip_x": true,
  "anchor": "bottom-center",
  "depth": 25,
  "keys": [
    { "f": 0,  "x": 300, "y": 150, "ease": "in-out" },
    { "f": 96, "x": 105, "y": 150, "ease": "in-out" }
  ],
  "motion": [
    { "type": "sine", "axis": "y", "amp": 1, "period": 32 }
  ]
}
```

### Key Parameters:
- **`zoom`**: Integer scaling factor (e.g., `4` maps 160px GBA height to 640px canvas).
- **`keys`**: Keyframe positions over frame numbers (`f`), supporting easing functions (`linear`, `in`, `out`, `in-out`).
- **`motion`**: Procedural secondary motion overlays (`sine`, `cosine`, or `wobble`).
- **`order`**: Custom frame sequencing (e.g., ping-ponging `[0,1,2,1]` to fit loop divisors).
- **`depth`**: Layering index for z-ordering actors and background elements.

---

## License & Credits

- Game graphics, tilemaps, and palettes originated from **Pokémon Emerald** ([pret/pokeemerald](https://github.com/pret/pokeemerald)).
- Parallax web editor integration: [parallax-scene-editor](https://github.com/christt105/parallax-scene-editor).

