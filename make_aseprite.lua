-- Turn the exported RGBA strips into .aseprite files, plus a layered scene
-- template on a 1280x640 canvas.
--
--   aseprite -b --script-param root=sprites/x4 --script-param scene=day \
--            --script make_aseprite.lua
--
-- Every animated sprite becomes its own .aseprite with one frame per animation
-- frame and the game's own frame durations. The scene template stacks the
-- background layers and drops the rider and Pokemon in at their in-game
-- positions, ready to animate.

local root  = app.params["root"]  or "sprites/x4"
local scene = app.params["scene"] or "day"
local frames = tonumber(app.params["frames"] or "64")

local function readJson(path)
  local fh = io.open(path, "r")
  if not fh then error("cannot read " .. path) end
  local text = fh:read("a")
  fh:close()
  return json.decode(text)
end

local meta = readJson(root .. "/sprites.json")
local scale = meta.scale
local canvasW, canvasH = meta.canvas[1], meta.canvas[2]

-- The GBA screen is 240 px wide; the canvas holds 320, so centre the action.
local marginX = (canvasW / scale - 240) / 2

local outDir = root .. "/aseprite"
os.execute("mkdir -p '" .. outDir .. "'")

-- Load a strip PNG and return its frames as separate Images.
local function stripFrames(path, frameW, frameH, count)
  local src = app.open(path)
  if not src then error("cannot open " .. path) end
  local flat = Image(src.spec)
  flat:drawSprite(src, 1)
  local out = {}
  for i = 1, count do
    out[i] = Image(flat, Rectangle((i - 1) * frameW, 0, frameW, frameH))
  end
  src:close()
  return out
end

-- Write one .aseprite per animation.
local function buildSprite(name, info, dir)
  local imgs = stripFrames(dir .. "/" .. info.file,
                           info.frame_width, info.frame_height, info.frames)
  local spr = Sprite(info.frame_width, info.frame_height, ColorMode.RGB)
  spr.filename = outDir .. "/" .. name .. ".aseprite"
  local layer = spr.layers[1]
  layer.name = name
  local ms = (info.frame_ms or 66.7) / 1000
  for i = 1, info.frames do
    if i > 1 then spr:newEmptyFrame(i) end
    spr:newCel(layer, i, imgs[i], Point(0, 0))
    spr.frames[i].duration = ms
  end
  spr:saveAs(spr.filename)
  spr:close()
  return info
end

local made = 0
for group, dir in pairs({characters = root .. "/characters",
                         pokemon    = root .. "/pokemon"}) do
  for name, anims in pairs(meta[group]) do
    for anim, info in pairs(anims) do
      buildSprite(name .. "_" .. anim, info, dir)
      made = made + 1
    end
  end
end

-- ---------------------------------------------------------------- scene ----
local bg = meta.backgrounds[scene]
if not bg then error("unknown scene: " .. scene) end
local bgDir = root .. "/backgrounds/" .. scene

local spr = Sprite(canvasW, canvasH, ColorMode.RGB)
spr.filename = outDir .. "/scene_" .. scene .. ".aseprite"
for i = 2, frames do spr:newEmptyFrame(i) end

local function newLayer(name)
  local l = spr:newLayer()
  l.name = name
  return l
end

-- Flat backdrop: the GBA's colour 0, visible wherever every BG is transparent.
local backdrop = spr.layers[1]
backdrop.name = "backdrop"
local fill = Image(canvasW, canvasH, ColorMode.RGB)
local c = bg.backdrop_rgb
fill:clear(Color{ r = c[1], g = c[2], b = c[3], a = 255 })
for i = 1, frames do spr:newCel(backdrop, i, fill, Point(0, 0)) end

-- Each document frame covers this many GBA frames, matching the 4-frame
-- cadence of the pedalling animation (about 67 ms per document frame).
local GBA_PER_DOC = 4

-- Round a layer's real speed to one that completes a whole number of tile
-- periods over the loop, so frame `frames + 1` lands exactly back on frame 1.
local function loopSpeed(pxPerGbaFrame, period)
  if pxPerGbaFrame == 0 or period == 0 then return 0 end
  local ideal = pxPerGbaFrame * GBA_PER_DOC
  local cycles = math.floor(ideal * frames / period + 0.5)
  if cycles < 1 then cycles = 1 end
  return cycles * period / frames
end

-- A layer that scrolls right starts one period to the left of the canvas and
-- slides back to 0, at which point the next period has taken its place.
local function addScrollingLayer(name, dir, info)
  local src = app.open(dir .. "/" .. info.file)
  local img = Image(src.spec)
  img:drawSprite(src, 1)
  src:close()

  local period = info.tile_period or 0
  local speed = loopSpeed(info.scroll_px_per_gba_frame or 0, period)
  local layer = newLayer(name)
  layer.data = string.format("period=%d px_per_frame=%.2f", period, speed)
  for i = 1, frames do
    local x = 0
    if speed > 0 then
      x = -period + ((i - 1) * speed) % period
    end
    spr:newCel(layer, i, img, Point(x, info.y))
  end
end

-- Back to front: distant scenery first, then the layers that move fastest.
for _, name in ipairs({ "far", "near" }) do
  if bg.layers[name] then addScrollingLayer("bg_" .. name, bgDir, bg.layers[name]) end
end

local sceneryNames = {}
for name, _ in pairs(bg.scenery_layers) do sceneryNames[#sceneryNames + 1] = name end
table.sort(sceneryNames)
for _, name in ipairs(sceneryNames) do
  addScrollingLayer(name, bgDir, bg.scenery_layers[name])
end

if bg.layers.ground then
  addScrollingLayer("bg_ground", bgDir, bg.layers.ground)
end

-- Characters, at the positions render_bike_loop.py uses (OBJ centres, GBA px).
local cast = {
  { layer = "flygon",    group = "pokemon",    anim = "flygon_fly",       x = 168, y = 46 },
  { layer = "volbeat",   group = "pokemon",    anim = "volbeat_fly",      x = 56,  y = 72 },
  { layer = "rider",     group = "characters", anim = "brendan_on_bike_bike", x = 120, y = 108 },
  { layer = "torchic",   group = "pokemon",    anim = "torchic_run",      x = 196, y = 112 },
  { layer = "manectric", group = "pokemon",    anim = "manectric_run",    x = 64,  y = 126 },
}

for _, entry in ipairs(cast) do
  local name, anim = entry.anim:match("^(.*)_([^_]+)$")
  local info = meta[entry.group][name] and meta[entry.group][name][anim]
  if info then
    local dir = root .. "/" .. (entry.group == "pokemon" and "pokemon" or "characters")
    local imgs = stripFrames(dir .. "/" .. info.file,
                             info.frame_width, info.frame_height, info.frames)
    local layer = newLayer(entry.layer)
    local x = (entry.x + marginX) * scale - info.oam_width / 2 + info.trim_offset[1]
    local y = entry.y * scale - info.oam_height / 2 + info.trim_offset[2]
    local step = math.floor(GBA_PER_DOC / (info.frame_delay_gba or GBA_PER_DOC))
    if step < 1 then step = 1 end
    if info.frames > 1 and step % info.frames == 0 then step = 1 end
    for i = 1, frames do
      local idx = ((i - 1) * step) % info.frames + 1
      spr:newCel(layer, i, imgs[idx], Point(x, y))
      spr.frames[i].duration = GBA_PER_DOC / 59.7275
    end
  end
end

spr:saveAs(spr.filename)
spr:close()

print(string.format("%d sprite files + scene_%s.aseprite in %s", made, scene, outDir))
