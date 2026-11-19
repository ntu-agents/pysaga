# The saga-map format, version 1

A Saga Online map is one JSON file, `game/maps/<name>.json`. It says what the
place looks like and how it plays: the terrain, the objects standing on it, and the
points the game uses. People and language models can read and write it; the game
reads it strictly and explains every fault it finds.

- `saga-map.schema.json` is the format as a JSON Schema (draft 2020-12), made from
  the element catalogue: an editor can check a map against it.
- `llm-prompt.md` is what a language model is told so it can write a map.
- `./run-local.sh map-check <file>` reads, compiles and validates a map. It prints
  every fault with its JSON path, an ASCII preview, and the hashes.

The game's reader is the judge. The schema describes a map's shape, while the reader
also checks what no schema can state: for example, that every walkable cell can be
reached.

## The grid

- A map is a grid of **cells** of 16 x 16 pixels; `size` is `[width, height]` in cells.
- A cell is `[x, y]`: x counts from 0 at the left, y from 0 at the top.
- A point stands at the centre of its cell.
- Characters step to the four neighbouring cells, never diagonally. Two cells that
  touch only at a corner are not connected.
- A map for the game is from 50 x 40 to 128 x 128 cells. A map used only for training
  may be any size up to 512 x 512.

## A map

```json
{
  "format": "saga-map",
  "version": 1,
  "name": "Millbrook",
  "description": "A village by a pond.",
  "size": [50, 40],
  "tileset": "outdoor",
  "rules": {"teams": [2, 2], "modes": ["dm", "tdm", "dom"]},
  "terrain": {"fill": "grass", "layers": [ ... ]},
  "objects": [ ... ],
  "points": [ ... ]
}
```

| key | | |
|---|---|---|
| `format`, `version` | required | `"saga-map"` and `1` |
| `name` | required | what players read, 1 to 64 characters |
| `description`, `author` | optional | free text |
| `size` | required | `[width, height]` in cells |
| `tileset` | optional | how the map is drawn; default `"outdoor"` |
| `rules` | optional | `teams`: `[fewest, most]` (2 to 4), or one number; `modes`: any of `dm`, `tdm`, `dom`, `ma` (Monster Attack: needs a monster home) and `ctf` (capture the flag: needs a flag for every team). Default `[2, 4]` and `dm`, `tdm`, `dom` |
| `terrain` | optional | `fill` (default: the catalogue's first kind) and `layers` |
| `objects` | optional | what stands on the terrain |
| `points` | required | where players spawn, capture, shop, bounce and teleport |
| `generator` | optional | where a generated map came from: `name`, `version`, `spec`, `seed`. Provenance only: the map is what the file says |
| `requires` | optional | features beyond version 1 the map needs |
| `meta`, `x_*` | optional | free data of the author's or a tool's; kept, never read |

## Terrain

`terrain.fill` covers the map, and the `layers` paint over it in order, later over
earlier. A layer is a terrain kind and exactly one shape, or a stamp.

| shape | | which cells |
|---|---|---|
| `"rect": [x, y, w, h]` | | x..x+w-1, y..y+h-1 |
| `"ellipse": [cx, cy, rx, ry]` | | the cells whose centre lies within rx + 1/2 and ry + 1/2 of the centre of cell (cx, cy); `[cx, cy, 0, 0]` is that cell |
| `"polygon": [[x, y], ...]` | | corners on the grid lines; the cells whose centre is inside, by the even-odd rule. `[[0,0],[3,0],[3,2],[0,2]]` covers exactly `rect [0, 0, 3, 2]` |
| `"path": [[x, y], ...], "width": w` | | the cells from each point to the next, stepping along x before y wherever both change, so the path is 4-connected; each cell is widened to the square -(w-1)/2 .. w/2 around it |

A **stamp** paints a small picture of several kinds:
`{"rows": ["~~~", "~.~"], "at": [x, y], "legend": {"~": "water"}}`. Every row is as
long as the first, and a character not in the legend leaves its cell as it was.

Shapes may reach past the map's edge; what lies outside is ignored. A shape lying
wholly outside is reported as a warning. The arithmetic is integer only, so every
machine paints the same cells.

## Objects

| written as | for |
|---|---|
| `{"type": "tree", "at": [x, y]}` | an object of fixed size; `[x, y]` is its top left |
| `{"type": "pine", "at": [x, y], "variant": "teal"}` | one of a kind with variants (the catalogue's `variants`: a tree's colours): how it looks, the kind's first when left out. Variants play alike, so a variant is in no simHash |
| `{"type": "house", "at": [x, y], "size": [w, h], "variant": "orange", "walls": "plaster", "door": "S", "sign": "inn", "roof": "hip", "window": "arched", "doorway": "iron", "chimney": "east"}` | a house of the given size; `variant` is its roof's colour and covering, and `walls` (`stone` or `plaster`, left out for the variant's own: stone under orange, plaster under teal) its walls' look; `roof` (`gable`, the default, a gable over the door; `hip`, both ends sloped; `hip-gable`, both) `window` (`plain`, the default; `arched`; `lattice`; `curtained`), `doorway` (`plank`, the default; `arched`; `iron`) and `chimney` (`west` or `east`, the end of the roof it stands at, left out for none) are its look alone; `sign`, left out for none, hangs on the wall beside its door (the catalogue's house names the signs) |
| `{"type": "fence", "path": [[x, y], [x, y], ...]}` | a wall or a fence along legs that run horizontally or vertically |
| `{"type": "plateau", "at": [x, y], "size": [w, h], "variant": "earth", "cut": [west, east], "north": [west, east], "ramps": [x, ...]}` | ground raised by a cliff: see below |
| `{"scatter": "tree", "area": {"rect": [x, y, w, h]}, "permille": 150, "seed": 1}` | many small objects: one on about permille of every 1000 cells of the area; a `variant` makes them all of it |

Every cell an object covers must lie inside the map, on walkable terrain, and clear of
other objects and of points -- with one exception, the **overhang**: a cell of a fixed
object's footprint that is walkable and drawn over characters (a tree's crown, a
statue's figure, a standing stone's top; the catalogue's `overhangs`) may lie on a cell
another object stands on -- a house's wall, a wall or a fence, a cliff's edge or face,
another tree's trunk -- and is drawn in front of it. The cell walks and sees as the object under
it (walking and sight both, over either), and the overhang is drawn as a piece apart,
among the characters by the row its own object stands on in that column, so a character
in front of the house and behind the tree is over the wall and under the crown. A cell
holds at most one object and one overhang of another; it is the same map whichever is
listed first. A house, a line or a plateau has no overhang. Which objects may share a
cell:

- **Objects placed one by one share with each other**: an overhang may lie on another such
  object, and one may stand under another's lone overhang.
- **Plants share with plants** (objects the catalogue marks `"plant": true`), however each
  was placed: a crown may lie on another plant's trunk, and a plant may stand under
  another's lone crown, so a wood stands tree before tree.
- **A scattered object shares otherwise only with a building** -- a house, a wall or fence,
  a plateau, or an object the catalogue names a building (`"building": true`: the
  cottage): its overhang may lie on one (not on a cottage's peak, itself an overhang), and
  one may stand under its lone overhang. Its other cells stand on free ground, so a wood
  grows up to a house, not over what stands in it, and a scatter's place in the file does
  not change the map.
- **Nothing shares a cell with an object of one cell** -- a bush, a rock, a stump, a
  campfire, rubble -- and an object of one cell shares none: no crown hides a small thing.

The map generator grows its trees by the same rules. The ASCII
preview shows the object under an overhang. A scatter skips a cell where its object
would break these rules, and every cell next to a point. Its draws come from SplitMix64, seeded with
`seed ^ (0x9E3779B97F4A7C15 * (index + 1))`, where index is its place in `objects`.
There is one draw per cell of the area, in row-major order, and a cell is taken when
`(draw >>> 1) % 1000 < permille`.

A plant (an object the catalogue marks `"plant": true`: trees, bushes, flowers) never stands with its foot on
ground that grows nothing (`"grows": false`: ice); a scatter of plants skips such cells, and a crown may hang over them.

A scatter never walls ground in. Once the objects are placed, the compiler asks which walkable
cells the first spawn cannot reach (the validator's own reach, through teleports). Where a way
into such an area crosses only cells scattered objects block, the cheapest way -- fewest blocked
cells -- is kept clear and the map compiled again, every scatter skipping an object that would
block a kept cell; until no walled-in area can be opened so. Each scatter that left objects out
says how many, as a warning. A map whose walkable cells are all reached compiles exactly as it
would without this; ground walled in by objects placed one by one, or by terrain, is the map's
own design, and the validator refuses it.

A **plateau** is high ground. The game has no heights, so a plateau plays as ground
fenced by its own edge, reached only by its ramps:
- its **edge** -- the north row and the west and east columns of its top -- cannot be
  stepped over;
- its **cliff face**, the bottom two rows (the catalogue's `face`), cannot be walked
  either, but at a **ramp**: `ramps` names columns of the face, inside the edge, where a
  ladder climbs it;
- `cut` (left out for none) **slants the face back** at its west and east ends by that
  many columns, a row higher a column further out: the slant is a row taller than the
  face, and below it lies the ground again, not the plateau's. Cuts adding up to the
  width meet on a straight stretch two columns wide; a ramp stands on the straight part only;
- `front` (in place of `cut`) makes the face **jagged**: one number for each column, west
  to east, how many rows the face stands back from the plateau's foot -- `[0, 0, 1, 2, 2,
  1, 0, 0]` is a notch two rows deep. Neighbouring columns differ by a row at most, and a
  change is drawn as a slant, as a cut's ends are; below a set-back face lies the ground
  again. No notch is one column wide, and a ramp stands where the face is straight. A
  cut is the same as a front that slants at its ends alone;
- `north` (left out for none) **slants the north edge down** at its west and east
  corners by that many columns, a row lower a column further out: above the diagonal
  lies the ground again, not the plateau's. A corner and a cut at one side together take
  at most the rows above the face, and a ramp cannot climb into a corner's edge;
- `open` (left out for none) names the sides -- `"west"`, `"east"`, `"north"` -- that **run
  off the map**: such a side lies on the map's edge (west at x 0, east at the map's last
  column, north at y 0) and has no edge of its own, its top going on to the map's edge. A
  cliff across the whole map is open to the west and east; another plateau may stand on
  its top as far as the map's edge, open there too. An open north has no north corners;
- its **top**, the rest, is walkable ground of its own. The plateau covers it with its
  picture and nothing else: objects and points stand on it, and another plateau may rise
  on it -- a summit on a terrace, its ramp climbed from the terrace. The terrain under
  the top must be walkable.

Edge and face block walking, not sight: one sees and shoots up and down a cliff. A
plateau with no ramp is refused, since nobody could reach its top. `variant` picks the
rock: `earth`, `lava` or `ice`.

`"fallback": "<type>"` places a known type in the place of one this game does not
know. A map written for a later game can then still be played here, with a warning.

## Elements: game/config/map/elements.json

The catalogue says what each terrain kind and object means for play, cell by cell:
- `walk`: the cell can be walked on;
- `sight`: a line of sight passes through it;
- `over`: it is drawn above characters, like a tree's crown or a roof's eave.

A cell's flags are its terrain's with an object's on top: it is walkable or
see-through only if both allow it, and drawn over if either is.

The catalogue holds no pictures: the tileset decides how each element looks, so a new
tileset never changes how a map plays. A new decorative element (another tree, a
rock, a well) is a catalogue entry and its pictures; no code is needed. Fixed objects
declare a footprint of cells. `builder: "house"` makes any size between `min` and
`max`, with the top row the eave. `builder: "line"` runs along a path.
`builder: "plateau"` makes any size between `min` and `max`, its face the bottom `face`
rows; `rim`, `cliff` and `ramp` give its edge's, its face's and a ramp's flags.

## Tilesets

A map names its tileset (`"tileset"`, default `outdoor`), which lives in
`game/images/tiles/<name>/tileset.json` and says how each element looks, and nothing
else. Its file names a sheet of 16 x 16 tiles beside it (`image`, `size`), and may name
further sheets (`"sheets": {"inner": {"image": "inner.png", "size": [30, 16]}}`), each
drawn clear at the same palette index. Every position is a tile `[column, row]` of the
main sheet, from 0 at the top left, unless a picture names another sheet: a terrain kind,
a fixed object or a plateau may say `"sheet": "<name>"`, and all its positions are then on
that sheet. The outdoor tileset's `cave` sheet holds volcanic and cave ground, the
plateaus' rock, crystals and spires.
`./run-local.sh map-tiles [tileset]` draws the sheet with every column and row numbered.

| element | written as | drawn |
|---|---|---|
| terrain | `{"fill": [c, r]}` | that tile in every cell |
| | `{"autotile": [c, r]}` | from a block of 3 x 4 tiles: an isolated patch, an unused tile, the inner corners, then a 3 x 3 frame |
| | `{"water": [c, r]}` | from a strip of five tiles: an isolated piece, the left and right edges, the top and bottom edges, the inner corners, open water; the strip is three tiles wide, its frames, shown in turn |
| terrain that flows | a fill or an autotile with `"frames": {"sheet", "at": [[c, r], [c, r]]}` | two further blocks of the kind's own shape, shown in turn with water's frames -- lava. The picture alone moves |
| terrain on other ground | an autotile with `"on": "<kind>"` | the kind its block lies on, which its rim shows: its rim is drawn against that kind even where both can be walked on -- ice lies on snow, and fades into it. Elsewhere two kinds one walks on meet edge to edge |
| water's shores | water with `"shores": {"<land kind>": {"sheet", "at": [c, r]}}` | a strip of the four rim rows, three frames wide, for water meeting that land: each rim quarter takes the strip of the land across it, open water the water's own -- a lake in snow rimmed with ice. Ground toward water that has its shore draws no rim of its own: the shore is the edge |
| fixed object | `{"at": [c, r]}` | the picture with its top left there, as large as the object's footprint |
| fixed object with variants | `{"sheet", "variants": {name: [c, r]}}` | each variant's picture, in place of `at`, every one on the object's sheet; such an object does not move |
| fixed object that moves | `{"at": [c, r], "frames": {"sheet", "at": [[c, r], ...], "ms"}}` | further pictures, shown in turn after `at` for `ms` each -- a campfire's flame. Only an object that stands (drawn among the figures) may move, and the picture alone moves: nothing of how the map plays |
| house | `{"window", "beam", "chimney", "doorways": {...}, "walls": {...}, "variants": {...}, "signs": {...}}` | each walls' `wall` and `base` tiles by column; each variant's `roof` tiles by row, its `roof-edge`, a 2 x 2 `gable` over the door, and the `walls` it has when a map names none; `beam` the first of three tiles along the wall's top (left end, middle, right end); each doorway `{"sheet", "at"}`, two tiles high; each sign `{"sheet", "at"}`, drawn on the wall beside the door |
| plateau | `{"sheet", "ramp": [top, middle, bottom], "variants": {name: {"top": [c, r], "face": [[c, r], ...], "slant": [c, r], "north": [west tile, east tile]}}}` | its top by quarters from the four corners of a 3 x 3 frame (a quarter on the edge from the corner on that side, one inside from the corner across, whose inner side is plain); a tile for each face row, repeated along it; a slanted end from the slant block (two tiles wide, a row taller than the face: the west slant's column, then the east's), of whose first and last tiles only the cliff's half is drawn, so a slant stands on any ground; a ramp's ladder over the top's last row and the face. A plateau lies on the ground, drawn before every other object |
| wall, fence | `{"frame": [c, r]}` or `{"pieces": {...}}` | by quarters from a 3 x 4 frame; or a rail each way (`h`, `v`) and a corner for each pair of directions it joins (`se`, `sw`, `ne`, `nw`) |

Terrain is drawn by quarters: each 8 x 8 quarter of a cell looks at the two cells on its
side and the one between them, and takes the block's matching quarter. That gives an
edge where the kind ends, a corner where it turns, and the middle inside. A cell with no
neighbour of its kind takes the isolated patch whole. Past the map's edge counts as the
same kind. The blocks draw their edges against grass; the cave sheet's lava and chasm draw
theirs as volcanic rock and cave floor, so they belong on `lava-rock` and on `cave`.

A cell the catalogue marks `over` (a tree's crown, a house's eave) goes into an overlay.
The game draws it after every character whose feet stand above the foot of the object,
and before every character in front of it.

A tileset is read against the catalogue: every terrain kind and object needs a picture of
the right kind, every variant (a house's, a fixed object's) and sign one of its own, and every tile must lie on its
sheet.
`./run-local.sh map-render <map.json> <out.png>` draws a map as the game does.

## Points

Each point stands on a walkable cell of its own, with no object on it. An `id` is
optional; messages use it.

| | | |
|---|---|---|
| `{"type": "spawn", "at": [x, y], "team": 1}` | spawn | where players start and come back. With a team (1-4) it is that team's; without one it is no team's, and only deathmatch and Monster Attack -- where every player may use every point, the capture points too -- use it |
| `{"type": "capture", "at": [x, y]}` | capture | taken by standing on it alone for five seconds; scores in domination. A `team` owns it at the start |
| `{"type": "shop", "at": [x, y], "stock": "skill"}` | shop | `all`, `skill`, `equipment`, `small`, `medium`, `large`, or `{"items": [numbers]}`; default `all` |
| `{"type": "bounce", "at": [x, y], "dir": "NE", "power": 300}` | bounce | throws whoever steps on it `power` pixels towards `dir`: a compass direction, or `[dx, dy]` |
| `{"type": "teleport", "at": [x, y], "to": [x, y]}` | teleport | moves whoever steps on it to the centre of `to` |
| `{"type": "monster", "kind": "slime", "at": [x, y], "leash": 6}` | monster | a monster's home: where one stands, chases from and returns to, if the round fills it -- a server fills none unless told. `leash`, in cells, is how far it follows; the kind's own when absent |
| `{"type": "flag", "at": [x, y], "team": 1}` | flag | a team's flag at its base, for capture the flag (`ctf`): another team's player takes it by walking into it, and scores by carrying it to its own team's flag while that stands at home. Ground like a home: it fires nothing, and plays no part outside `ctf`. A `team` is required; one flag a team |
| `{"type": "ambient", "kind": "sheep", "count": 3, "area": {"rect": [x, y, w, h]}}` | ambient | `count` (1-16) animals or people of a kind that wander inside `area` -- a rect, ellipse or polygon -- on its walkable cells and never leave it. Decoration: drawn by each client, nothing the game plays, so it does not count in the `simHash`. It stands on no one cell, so it needs no `at` |

A kind is one of the game's NPC table (`game/config/sim/npcs.tsv`), and of the right
role: a monster's home names a monster, an ambient group an ambient kind. The game's
reader refuses any other; a reader of the format alone, with no table, does not check.

## What the game checks

- **Reading:**
  - The text is JSON, strictly: no trailing comma, no key given twice, no leading
    zero, and no control character in a string.
  - Every key is one the format knows, apart from `meta` and `x_*`.
  - Every value has the right type and range: a whole number where one belongs, never
    `4.0`.
  - Every element is one the catalogue knows.
- **Placing:** objects and points as above.
- **Validating:**
  - **Size**, for the game client.
  - **Counts:** at most 16 captures, since the game keeps capture state for 16, and at
    most 127 points of each kind, since their numbers travel as bytes.
  - **Spawns:** a spawn that is not a capture, and, where the map lists a team mode, a
    spawn of its own for every team the map allows.
  - **Flags:** no team with two; and a map listing `ctf` has one for every team it
    allows.
  - **Teleports:** a destination inside the map and walkable, and neither a bounce nor
    a teleport.
  - **Reach:** every walkable cell can be reached from every spawn, stepping to the four
    neighbours and through teleports. A bounce cell counts as ground for this.

Every fault names the JSON path of the part it is about, such as `$.points[3].at`,
and the cells concerned. A warning does not stop a map; an error does.

## Growth

- **`version`:** a map of a later major version is refused, with the version it needs.
- **`requires`:** names features beyond version 1; a game without one refuses the map,
  saying so.
- **Unknown keys:** an error, not ignored. A misspelt key that loaded silently would be a
  setting that silently never applied.
- **New elements:** new decorative elements are catalogue entries, and older maps keep
  their meaning.

## What the game makes of a map

The compiler writes one 4-bit code per cell, the code the simulation's navigation grid
reads:
- bit 0: sight passes;
- bit 1: drawn over;
- bit 2: walkable;
- bit 3: a point. The codes are 8 shop, 12 spawn, 13 capture, 14 bounce and
  15 teleport.

Points are numbered in a fixed order:
- captures first, then the other spawns, each in the file's order;
- shops, bounces and teleports in the file's order.

Captures come first because only the first 16 spawn points can be captured.

There are two fingerprints:
- **simHash:** SHA-256 of what the simulation reads (the codes and the points). Two
  files with the same simHash play the same game. A server sends it with its round's
  map, and a client that compiles the map to another hash does not join.
- **fileHash:** SHA-256 of the canonical text the game writes for a map. Whitespace and
  key order don't change it; names and meta do.

## Generated maps

The game makes maps itself too: `./run-local.sh map-gen <spec> [--seed N] [--out map.json]`.
A spec is one line, the template first and then `key=value` pairs joined by `:`:

    village:size=61x51:symmetry=rot2:houses=6:trees=40

The same spec and seed give the same file, to the byte, on every machine. The file
records both under `generator`, and from then on it is an ordinary map: a later
generator never changes a map already made.

| key | for | default | |
|---|---|---|---|
| `size` | every template | `61x51` | from 20 x 20 to 512 x 512; a client plays 50 x 40 to 128 x 128 |
| `symmetry` | every template | `mirror` (arena), `rot2` (the rest) | `none`, `mirror`, `rot2`, or `rot4` (square, four teams) |
| `teams` | every template | `2` | 2, or 4 with `rot4` |
| `spawns`, `captures` | every template | `1`, `1` | spawns per team; captures on the map |
| `shops` | every template | `1` | per team, each selling everything (its window switches between items and equipment): 0 to 2 |
| `teleports`, `bounces` | every template | `0`, `0` | per side |
| `name` | every template | the template and the seed | |
| `gap`, `cover`, `rocks` | arena | `12`, `6`, `8` | cells between the sides' spawns; walls and rocks per thousand cells |
| `fields`, `trees`, `hedges`, `orchards`, `streams`, `ditches`, `fences` | field | `2`, `15`, `6`, `2`, `1`, `2`, `3` | fenced fields per side; trees per thousand cells; hedgerow lines with gaps, parting the map into paddocks; orchards of oaks, in rows or loose, per side, at most -- each map draws from one up; a bridged stream a side on no map (0), one map in two (1) or every map (2); ditches, water a cell wide, and fences along the roads, at most -- each map draws from none up |
| `trees`, `oaks`, `paths`, `cottages` | forest | `90`, `12`, `2`, `1` | per thousand cells; the path's width; cottages standing alone among the trees, per side, at most -- each map draws from none up |
| `houses`, `trees`, `fields`, `ponds` | village | `5`, `12`, `2`, `2` | houses per side; trees per thousand cells; small fenced fields and ponds per side, at most -- each map draws from none up to this many |
| `rivers` | village | `1` | a river through the village or beside it, in place of the ponds, bridged where its roads cross it: 0 on no map, 1 on one map in three, 2 on every map |

A key the template does not have, or a value out of range, is refused by name.

On a symmetric map every side has the same ground and its points in the same places.
The generator refuses a map on which one team walks further to a capture or to its own
shops than another, and one on which a spawn cannot reach every walkable cell.

## Maps written by a language model

`./run-local.sh map-llm "<description>" [--out map.json]` -- or *Describe* on the Create
Game Server screen -- asks a language model for a map:

1. The model gets the prompt the game publishes (`docs/maps/llm-prompt.md`, the
   description in place of `{{request}}`) and, where it can take one, a JSON schema for
   its answer: this format's schema relaxed for models, with no alternatives, references
   or bounds.
2. The game reads the answer as it reads any map file. A map it cannot play goes back to
   the model with its faults, each at its JSON path, and the picture of what it compiled
   to, three rounds in all.
3. What comes back is a map only once the game's reader says so.

The model and its key come from `~/.saga-online/llm.properties`:

    provider=anthropic        # or openai: any server speaking OpenAI's chat completions
    model=claude-opus-5-5
    key=...
    url=https://api.anthropic.com
    max_tokens=32000          # the most it may write, its hidden thinking included

Or from the environment, which wins: `ANTHROPIC_API_KEY` (`OPENAI_API_KEY`),
`SAGA_LLM_PROVIDER`, `SAGA_LLM_MODEL`, `SAGA_LLM_URL`, `SAGA_LLM_KEY`. The key is never
written to a log or an error.
