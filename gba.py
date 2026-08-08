"""Mini GBA-style renderer (BG layers + OAM sprites) for the Pokemon Emerald
bike scene, driven by the assets in graphics/intro/scene_2 of pret/pokeemerald.

Only the pieces the scene needs: 4bpp tile graphics, text BGs with a 32x32
screenblock, and non-affine OBJs with a center-anchored position.
"""

import numpy as np
from PIL import Image

DISPLAY_W, DISPLAY_H = 240, 160
TILE = 8
SCREENBLOCK_TILES = 32  # 32x32 tiles == 256x256 px


def load_indexed(path):
    """PNG (indexed) -> (index array HxW uint8, palette as Nx3 uint8)."""
    im = Image.open(path)
    assert im.mode == "P", f"{path} is {im.mode}, expected indexed"
    pal = np.array(im.getpalette()[: 16 * 3], dtype=np.uint8).reshape(-1, 3)
    return np.array(im, dtype=np.uint8), pal


def load_jasc_pal(path):
    """JASC-PAL file -> Nx3 uint8."""
    lines = open(path).read().split()
    n = int(lines[2])
    vals = list(map(int, lines[3 : 3 + n * 3]))
    return np.array(vals, dtype=np.uint8).reshape(n, 3)


def load_screenblocks(path):
    """Tilemap .bin -> list of (32,32) uint16 screenblocks."""
    raw = np.fromfile(path, dtype="<u2")
    n = raw.size // (SCREENBLOCK_TILES * SCREENBLOCK_TILES)
    return [
        raw[i * 1024 : (i + 1) * 1024].reshape(SCREENBLOCK_TILES, SCREENBLOCK_TILES)
        for i in range(n)
    ]


def tile_from_sheet(sheet, n):
    """8x8 index tile `n` out of a linear 4bpp charblock stored as a PNG."""
    per_row = sheet.shape[1] // TILE
    ty, tx = divmod(n, per_row)
    return sheet[ty * TILE : ty * TILE + TILE, tx * TILE : tx * TILE + TILE]


def build_bg(tileset, screenblock):
    """Render a screenblock into a 256x256 array of palette indices."""
    out = np.zeros((256, 256), dtype=np.uint8)
    for ty in range(SCREENBLOCK_TILES):
        for tx in range(SCREENBLOCK_TILES):
            entry = int(screenblock[ty, tx])
            t = tile_from_sheet(tileset, entry & 0x3FF)
            if entry & 0x400:
                t = t[:, ::-1]
            if entry & 0x800:
                t = t[::-1, :]
            out[ty * TILE : ty * TILE + TILE, tx * TILE : tx * TILE + TILE] = t
    return out


def build_bg_palnums(screenblock):
    """Per-pixel BG palette slot, from bits 12-15 of each tilemap entry."""
    nums = (screenblock >> 12).astype(np.uint8)
    return np.repeat(np.repeat(nums, TILE, axis=0), TILE, axis=1)


def palette_bank(entries):
    """Build the 16x16 BG palette bank from (slot, colours) pairs.

    A .pal holding more than 16 colours fills consecutive slots, which is what
    LoadPalette does when handed the whole file: clouds_bg.pal is 48 colours,
    so it occupies BG palettes 0, 1 and 2, and the tilemap picks between them.
    """
    bank = np.zeros((16, 16, 3), dtype=np.uint8)
    for slot, colours in entries:
        colours = np.asarray(colours, dtype=np.uint8)
        for i in range(0, len(colours), 16):
            s = slot + i // 16
            if s > 15:
                break
            chunk = colours[i : i + 16]
            bank[s, : len(chunk)] = chunk
    return bank


def build_bg_rgba(tileset, screenblock, bank):
    """Render a screenblock to RGBA, honouring each tile's palette slot.

    Colour 0 of every palette is transparent on a BG layer.
    """
    idx = build_bg(tileset, screenblock)
    pal = build_bg_palnums(screenblock)
    out = np.zeros(idx.shape + (4,), dtype=np.uint8)
    out[..., :3] = bank[pal, idx]
    out[..., 3] = np.where(idx == 0, 0, 255)
    return out


def cut_obj(sheet, first_tile, w, h):
    """Assemble a w*h OBJ starting at tile `first_tile` using 1D tile mapping.

    Under DISPCNT_OBJ_1D_MAP a sprite's tiles are consecutive and laid out row
    by row across the sprite, which only coincides with a rectangular crop of
    the sheet when the sheet is exactly as wide as the sprite.
    """
    tw, th = w // TILE, h // TILE
    out = np.zeros((h, w), dtype=np.uint8)
    for ty in range(th):
        for tx in range(tw):
            out[ty * TILE : ty * TILE + TILE, tx * TILE : tx * TILE + TILE] = (
                tile_from_sheet(sheet, first_tile + ty * tw + tx))
    return out


def split_frames(sheet, w, h):
    """Sprite sheet PNG -> list of (h,w) index frames, in tile order."""
    per_frame = (w // TILE) * (h // TILE)
    total = (sheet.shape[0] // TILE) * (sheet.shape[1] // TILE)
    return [cut_obj(sheet, i * per_frame, w, h) for i in range(total // per_frame)]


class Canvas:
    """RGB framebuffer drawn back-to-front."""

    def __init__(self, backdrop):
        self.rgb = np.zeros((DISPLAY_H, DISPLAY_W, 3), dtype=np.uint8)
        self.rgb[:, :] = backdrop

    def blit_bg(self, layer, hofs, vofs):
        """Draw a 256x256 RGBA layer (from build_bg_rgba) with wrapping scroll."""
        ys = (np.arange(DISPLAY_H) + int(vofs)) % 256
        xs = (np.arange(DISPLAY_W) + int(hofs)) % 256
        px = layer[np.ix_(ys, xs)]
        mask = px[..., 3] != 0
        self.rgb[mask] = px[..., :3][mask]

    def blit_sprite(self, frame, pal, x, y, hflip=False):
        """Draw an index frame with its top-left at (x, y); index 0 is clear."""
        if hflip:
            frame = frame[:, ::-1]
        h, w = frame.shape
        x, y = int(x), int(y)
        sx0, sy0 = max(0, -x), max(0, -y)
        sx1, sy1 = min(w, DISPLAY_W - x), min(h, DISPLAY_H - y)
        if sx0 >= sx1 or sy0 >= sy1:
            return
        sub = frame[sy0:sy1, sx0:sx1]
        mask = sub != 0
        dst = self.rgb[y + sy0 : y + sy1, x + sx0 : x + sx1]
        dst[mask] = pal[sub[mask]]


def gba_sin(idx, amp):
    """pokeemerald Sin(): amplitude-scaled sine over a 256-step period."""
    return int(round(amp * np.sin(2 * np.pi * (idx % 256) / 256)))


def gba_cos(idx, amp):
    return int(round(amp * np.cos(2 * np.pi * (idx % 256) / 256)))
