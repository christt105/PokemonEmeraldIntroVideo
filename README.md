# Pokémon Emerald Bicycle Ride - Parallax Scene Project

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

## Credits

- Original Pokémon Emerald graphics, tilemaps, and palettes by **Nintendo / Game Freak** ([pret/pokeemerald](https://github.com/pret/pokeemerald)).
- Visual editor: [christt105/parallax-scene-editor](https://github.com/christt105/parallax-scene-editor).



