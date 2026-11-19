# Writing a map

You design a map for a top-down 2D action game in which two to four teams, or everyone
against everyone, fight over a small world: green land with villages and woods, snow and ice, caves,
or lava. Write the map as one JSON document in the saga-map format, version 1, described
below. The map to make is described at the end, and how to answer after it.

## The document

- Required: `format` (`"saga-map"`), `version` (1), `name`, `size` and `points`.
- Optional: `description` (what the place is, in a sentence or two), `author`, `tileset` (`outdoor` when left
  out), `rules`, `terrain`, `objects` and `meta` (anything of your own).
- Without `rules` a map is for 2 to four teams and needs a spawn for each; give `rules.teams` to match the teams your
  spawns are for.
- Unknown keys are errors: write only the keys described here.

## The grid

- The map is a grid of cells, each 16 pixels square. `size` is `[width, height]` in cells.
- A cell is `[x, y]`: x counts from 0 at the left, y from 0 at the top.
- A map is at least 50 x 40 and at most 128 x 128 cells. A player sees about 50 x 37 cells at a time.
- Size words in a description mean: small 50 x 40, medium 61 x 51, large 80 x 64, huge 100 x 80 cells; medium suits four to eight players.
  For three or four teams, square: as tall as that width (large is 80 x 80).
- Characters walk from a cell to one of its four neighbours, never diagonally: two walkable cells
  that touch only at a corner are not connected.

## Terrain

`terrain.fill` covers the whole map; `terrain.layers` paint over it, in order, later over earlier.

| kind | walk | see through | what it is |
|---|---|---|---|
| `grass` | yes | yes | open grass |
| `dirt` | yes | yes | bare earth, for paths and yards |
| `sand` | yes | yes | sand |
| `road` | yes | yes | a cobbled road |
| `stone` | yes | yes | a paved stone floor, for squares and courtyards |
| `field` | yes | yes | a ploughed field with crops |
| `snow` | yes | yes | snow |
| `water` | no | yes | water: blocks walking, not sight |
| `pit` | no | yes | a hole in the ground: blocks walking, not sight |
| `lava-rock` | yes | yes | dark red volcanic rock, the ground lava lies in |
| `lava` | no | yes | molten lava, rimmed with volcanic rock: blocks walking, not sight; draw it on lava-rock |
| `cave` | yes | yes | the grey rock floor of a cave |
| `chasm` | no | yes | a black chasm, rimmed with cave floor: blocks walking, not sight; draw it on cave |
| `earth` | yes | yes | packed brown earth with a pale rim |
| `slate` | yes | yes | a floor of grey slate slabs |
| `ice` | yes | yes | frozen water, its cracked ice walkable |
| `bridge-ew` | yes | yes | a plank bridge crossed east to west, its boards running north to south: over lava, a chasm or water |
| `bridge-ns` | yes | yes | a plank bridge crossed north to south, its boards running east to west: over lava, a chasm or water |
| `footbridge-ew` | yes | yes | a wooden footbridge over water, crossed east to west, its planks across the way and posts every three cells: paint it two cells high, from shore to shore, or from a shore out into the water as a dock |
| `footbridge-ns` | yes | yes | a wooden footbridge over water, crossed north to south, its boards across the way and posts every three cells: paint it two cells wide, from shore to shore, or from a shore out into the water as a dock |
| `cobbles` | yes | yes | grey cobblestones laid as a path or a yard over rock: on volcanic rock (lava-rock) or a cave floor |

Nothing grows on `ice`, `cobbles`: a plant (`tree`, `oak`, `shrub`, `bush`, `flowers`, `pine`, `pine-large`, `maple`, `maple-large`, `dead-tree`, `dead-tree-large`) never stands on it, and a scatter of plants skips it; a crown may hang over it.

A layer is a kind and exactly one shape:

- `{"kind": "water", "rect": [x, y, width, height]}` -- the cells x..x+width-1, y..y+height-1
- `{"kind": "water", "ellipse": [cx, cy, rx, ry]}` -- the cells within rx columns and ry rows of the centre
- `{"kind": "stone", "polygon": [[x, y], ...]}` -- corners on the grid lines; the cells whose centre is inside.
  `[[0,0],[3,0],[3,2],[0,2]]` is the same as `"rect": [0, 0, 3, 2]`
- `{"kind": "road", "path": [[x, y], ...], "width": 2}` -- a road through the cells given; each leg steps
  along x first, then y, so a path one cell wide can always be walked end to end
- a stamp: `{"rows": ["~~~", "~.~"], "at": [x, y], "legend": {"~": "water"}}` -- small pictures, every row
  as long as the first; a character not in the legend leaves its cell as it was

Shapes may reach past the edge of the map; what lies outside is ignored. Prefer shapes to large stamps.

## Objects

`objects` stand on the terrain. Every cell an object covers must be inside the map, on walkable terrain,
and free of other objects and of points -- with one exception: the top of an object of fixed size, the part drawn
over characters (a tree's crown, a statue's figure, a standing stone's top), may lie on a cell another object
stands on, such as a house's wall, a fence, a cliff's edge or face, and is drawn in front of it. Two such tops
never share a cell. A scattered object's top may lie on a house, a wall, a fence, a cliff or a cottage (so a wood grows up to a house),
but its other cells need free ground and it never shares a cell with an object of fixed size. The ASCII picture of a map
shows the object under such a top.

| object | placed as | what it is |
|---|---|---|
| `tree` | `{"type": "tree", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a tree: its trunk blocks walking, its crown above the trunk is drawn over characters behind it |
| `oak` | `{"type": "oak", "at": [x, y]}`, 2 wide and 2 high, [x, y] its top left | a broad tree two cells wide: its trunk row blocks walking, its crown above is drawn over characters behind it |
| `stump` | `{"type": "stump", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a tree stump |
| `rock` | `{"type": "rock", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a boulder |
| `shrub` | `{"type": "shrub", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a leafy bush: blocks walking, not sight |
| `bush` | `{"type": "bush", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a bush: blocks walking, not sight |
| `flowers` | `{"type": "flowers", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a flowering bush: blocks walking, not sight |
| `sign` | `{"type": "sign", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a signpost |
| `barrel` | `{"type": "barrel", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a barrel |
| `campfire` | `{"type": "campfire", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a campfire |
| `well` | `{"type": "well", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a stone well |
| `statue` | `{"type": "statue", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a statue on a plinth: the plinth blocks walking, the figure above it is drawn over characters |
| `tent` | `{"type": "tent", "at": [x, y]}`, 3 wide and 3 high, [x, y] its top left | a tent, three cells wide and three high: its top row is drawn over characters behind it |
| `house` | `{"type": "house", "at": [x, y], "size": [w, h], "variant": "orange|teal|orange-ribbed|teal-ribbed|orange-woven|teal-woven", "walls": "stone|plaster", "door": "S", "sign": "inn|pub|weapons|armour|potions|chapel", "roof": "gable|hip|hip-gable", "window": "plain|arched|lattice|curtained", "doorway": "plank|arched|iron", "chimney": "west|east", "beam": true}`, from 3x4 to 12x10; a `sign`, left out for none, hangs beside the door; a `roof` is its look alone: `gable` a gable over the door, `hip` both ends sloped, `hip-gable` both; `window` is its windows' look alone; `doorway` is its door's look alone; the `variant` is its roof's colour and covering, and `walls` its walls' look, left out for the variant's own; a `chimney`, left out for none, stands on that sloped end of a hipped roof, a picture alone; `beam`, a wooden beam under the roof, a picture too | a house of the given size, at least 4 rows high so its roof has two rows: its top row is roof eave, drawn over characters and walkable behind the house; every other row is solid |
| `wall` | `{"type": "wall", "path": [[x, y], [x, y], ...]}`, every leg horizontal or vertical | a stone wall along a path of horizontal and vertical segments: blocks walking and sight |
| `fence` | `{"type": "fence", "path": [[x, y], [x, y], ...]}`, every leg horizontal or vertical | a wooden fence along a path of horizontal and vertical segments: blocks walking, not sight |
| `plateau` | `{"type": "plateau", "at": [x, y], "size": [w, h], "ramps": [x, ...]}`: see Plateaus below | ground raised by a cliff, of the given size: its north row and its west and east columns are its edge and block walking; its bottom two rows are its cliff face, which blocks walking but not sight, but at a ramp; the face may slant back at either end, a row higher a column further out, or be jagged, standing back as many rows as a front gives column by column, and the north edge down at either corner, a row lower a column further out; a side on the map's edge may run off the map, with no edge of its own; the rest is its top, walkable ground other things stand on |
| `crystal` | `{"type": "crystal", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a tall blue crystal: its foot blocks walking, not sight; its top is drawn over characters behind it |
| `crystals` | `{"type": "crystals", "at": [x, y]}`, 2 wide and 2 high, [x, y] its top left | a cluster of blue crystals two cells wide: its foot row blocks walking, not sight; its top row is drawn over characters behind it |
| `stalagmite` | `{"type": "stalagmite", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a grey spire of rock: its foot blocks walking, not sight; its tip is drawn over characters behind it |
| `ice-spire` | `{"type": "ice-spire", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a spire of ice: its foot blocks walking, not sight; its tip is drawn over characters behind it |
| `ice-boulder` | `{"type": "ice-boulder", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a dome of ice and snow, its foot drifted with snow: blocks walking, not sight |
| `snowman` | `{"type": "snowman", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a snowman: blocks walking, not sight |
| `boulder` | `{"type": "boulder", "at": [x, y]}`, 2 wide and 2 high, [x, y] its top left | a great boulder two cells wide: its lower row blocks walking and sight; its upper row is drawn over characters behind it |
| `torch` | `{"type": "torch", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a fire burning on a stand: its stand blocks walking, not sight; its flame is drawn over characters behind it |
| `gargoyle` | `{"type": "gargoyle", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a stone gargoyle on a plinth: the plinth blocks walking, not sight; the figure above it is drawn over characters behind it |
| `skulls` | `{"type": "skulls", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a heap of skulls and bones |
| `tombstone` | `{"type": "tombstone", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a gravestone |
| `embers` | `{"type": "embers", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | glowing embers in volcanic rock, for lava-rock ground: decoration that can be walked through |
| `rubble` | `{"type": "rubble", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a few loose stones: decoration that can be walked through |
| `menhir` | `{"type": "menhir", "at": [x, y], "variant": "slab|leaning|short"}`, 1 wide and 2 high, [x, y] its top left; the variant, `slab` when left out, is how it looks and plays alike | a standing stone a cell wide: its foot blocks walking and sight, its top is drawn over characters behind it; a tall slab, a stone leaning east, or a short one |
| `pine` | `{"type": "pine", "at": [x, y], "variant": "green|dark|teal|blue"}`, 1 wide and 2 high, [x, y] its top left; the variant, `green` when left out, is how it looks and plays alike | a pine a cell wide: its trunk blocks walking, its crown above is drawn over characters behind it |
| `pine-large` | `{"type": "pine-large", "at": [x, y], "variant": "green|dark|teal|blue"}`, 2 wide and 3 high, [x, y] its top left; the variant, `green` when left out, is how it looks and plays alike | a tall pine two cells wide and three high: its foot row blocks walking, its crown above is drawn over characters behind it |
| `maple` | `{"type": "maple", "at": [x, y], "variant": "green|yellow|red|orange"}`, 1 wide and 2 high, [x, y] its top left; the variant, `green` when left out, is how it looks and plays alike | a young broadleaf a cell wide, green or in autumn colours: its trunk blocks walking, its crown above is drawn over characters behind it |
| `maple-large` | `{"type": "maple-large", "at": [x, y], "variant": "green|yellow|red|orange"}`, 2 wide and 4 high, [x, y] its top left; the variant, `green` when left out, is how it looks and plays alike | a tall broadleaf two cells wide and four high, green or in autumn colours: its foot row blocks walking, its crown above is drawn over characters behind it |
| `dead-tree` | `{"type": "dead-tree", "at": [x, y], "variant": "bare|frost"}`, 1 wide and 2 high, [x, y] its top left; the variant, `bare` when left out, is how it looks and plays alike | a dead tree a cell wide, bare or in frost: its trunk blocks walking, its branches above are drawn over characters behind it |
| `dead-tree-large` | `{"type": "dead-tree-large", "at": [x, y], "variant": "bare|frost"}`, 2 wide and 3 high, [x, y] its top left; the variant, `bare` when left out, is how it looks and plays alike | a tall dead tree two cells wide and three high, bare or in frost: its foot row blocks walking, its branches above are drawn over characters behind it |
| `cottage` | `{"type": "cottage", "at": [x, y]}`, 5 wide and 7 high, [x, y] its top left | a timber cottage five cells wide and seven high, its door to the south: its two top rows, the roof's peak, are drawn over characters behind it and walkable; the rest of the roof and the walls block walking and sight |

Many small objects at once: `{"scatter": "tree", "area": {"rect": [x, y, w, h]}, "permille": 150, "seed": 1}`
places one on about 150 of every 1000 cells of the area (an ellipse or a polygon works too), skipping any
cell where it would not fit and every cell next to a point; a `variant` makes them all of that variant. A
scatter never walls ground in: an object of it that would leave walkable cells no spawn can reach is left
out, as few as open them, so a dense wood is safe.

### Plateaus (cliffs)

`{"type": "plateau", "at": [x, y], "size": [w, h], "variant": "earth|lava|ice|grass", "ramps": [x, ...]}` is all a cliff needs; [x, y] is its top left, w x h the whole of it, from 3 x 4 to 128 x 128.

- Its north row and its west and east columns are its edge: they block walking.
- Its bottom 2 rows are its cliff face: they block walking, not sight.
- The rest is its top: walkable ground where objects, points and a smaller plateau may stand.
- `ramps` are map columns of the face, inside the edge columns and the slants, where a ladder climbs it.
  The top is reached by its ramps, or by a teleport that lands on it, and no other way; a top nothing
  reaches gets the map refused, and a top reached only by a teleport needs a ramp or a teleport to leave by.

Its look, all optional:

- `cut`: `[west, east]` slants the face back at its west and east ends, by that many columns, a row
  higher a column further out: a cliff with angled corners. Cuts adding up to its width meet on a straight
  stretch two columns wide.
- `north`: `[west, east]` slants its north edge down at its west and east corners the same way, the ground
  beyond the diagonal being the map's.
- `front`, in place of `cut`: one number for each column, west to east, how many rows the face stands back
  from the plateau's foot, changing by at most a row a column, a change drawn as a slant, and no notch one
  column wide (a ramp stands where the face is straight).
- `open`: any of `["west", "east", "north"]` lets a side that lies on the map's edge run off the map,
  with no edge of its own: a cliff across the whole map.

Use `cut` and `north` by default, `front` for one large cliff.

## Points

`points` are where the game happens. Each stands on a walkable cell of its own, with nothing on it.
An `id` is optional and helps you refer to a point.

- `{"type": "spawn", "at": [x, y], "team": 1}` -- where players start and come back after dying.
  With a team (1-4) it is that team's; without one it is no team's, and only the modes where
  every player may use every point (dm, ma) use it -- there the capture points are spawns too. Where the map lists
  a team mode, every team it allows needs a spawn of its own; the map needs at least one spawn that is not a capture.
- `{"type": "capture", "at": [x, y]}` -- a point teams take by standing on it alone for five seconds; in
  the domination mode held points score. At most 16. A `team` makes it that team's at the start.
- `{"type": "shop", "at": [x, y], "stock": "skill"}` -- players buy here, from within about 3 cells (50 pixels) and in sight.
  `stock` is one of `all`, `skill`, `equipment`, `small`, `medium`, `large`, or `{"items": [item numbers]}`.
- `{"type": "bounce", "at": [x, y], "dir": "NE", "power": 300}` -- throws whoever steps on it `power`
  pixels (16 per cell) towards `dir`: one of `N`, `NE`, `E`, `SE`, `S`, `SW`, `W`, `NW`, or `[dx, dy]`.
- `{"type": "teleport", "at": [x, y], "to": [x, y]}` -- moves whoever steps on it to `to`, which must be
  walkable and neither a bounce nor a teleport.
- `{"type": "monster", "kind": "slime", "at": [x, y], "leash": 6}` -- a monster's home: where one stands,
  chases players from and returns to, if the server fills it (by default it fills none). `leash` is how far it
  follows, in cells. Keep homes well away from the spawns. In Monster Attack (`ma`) every monster comes out of
  a home drawn among them and hunts the players wherever they are, so the homes are the directions an attack
  comes from: place them where the attacks should come from. Kinds: `slime`, `skeleton`, `pig`, `golem`, `blue-slime`, `red-slime`, `bull`.
- `{"type": "flag", "at": [x, y], "team": 1}` -- a team's flag at its base, for capture the flag (`ctf`):
  a player takes another team's flag by walking into it and scores by carrying it to their own flag. One
  flag a team, near (not on) its spawns, on open ground that is neither a bounce nor a teleport.
- `{"type": "ambient", "kind": "sheep", "count": 3, "area": {"rect": [x, y, w, h]}}` -- animals or people
  that wander inside `area` and never leave it: sheep in a fenced field, villagers on a square. Decoration:
  nobody can touch them. Kinds: `chicken`, `dog`, `sheep`, `cow`, `horse`, `villager`.

## Rules the game checks

- Every walkable cell can be reached from every spawn, walking to the four neighbouring cells and through
  teleports. A walkable cell walled in by water, walls or objects is an error: open a way or fill it.
- `rules.teams` is `[fewest, most]` teams the map is for (2 to 4); `rules.modes` lists the modes it
  suits: `dm` (everyone against everyone), `tdm` (team deathmatch), `dom` (domination: needs captures),
  `ma` (Monster Attack: all players on one team against monsters from the homes; needs a monster home),
  `ctf` (capture the flag: needs a flag for every team). List every mode the map has the points for.

## What the format cannot do

- No heights but plateaus. A plateau's top is reached by its ramps (or a teleport landing on it): no
  bridge or road leads onto a top, nor from one top to another. Join cliffs by ways on the ground between
  the feet of their ramps, over lava, water or a chasm by a bridge there.
- A cliff's face and a house's door face south. Where cliffs or houses decide play, mirror the
  layout left to right, not top to bottom.
- A bridge runs east to west or north to south: paint it as a `rect` from bank to bank, both ends on
  walkable ground; a bridge may turn where one kind meets the other.
- Two to four teams. With three teams no layout is exactly fair: give each team near-equal walks to
  the captures and shops, and where the description itself places a team nearer, keep what it asks.
- Nothing moves or opens: doors and gates are pictures. Monsters stay near their homes, within their
  leash, except in Monster Attack or when a player hits one.

## Making a good map

How it plays:

- Fair: in team modes give each team spawns of the same kind and distance from the middle; a mirrored or
  rotated layout is fair by construction (for three teams, see above).
- Varied: open ground for fighting, cover (trees, houses, walls) to break lines of sight, a few chokepoints.
- Readable: roads lead between the spawns, the shops and the captures; water and walls shape the space.

How it looks -- a map should look like a place, not a diagram:

- Natural shapes. Draw grass, snow, sand, dirt, water, woods and rough ground as `polygon`, `ellipse` and
  `path` layers with uneven edges; a `rect` only for what people build: fields, squares, yards. Scatter
  woods over a polygon or an ellipse, not a rectangle.
- Roads. In a village or a town, cobbled streets (`road`) run straight, 2 or 3 wide, as people build them,
  lanes branch off to houses, fields and points, and the village grows along its street rather than on a grid.
  Outside a settlement a road or a track follows the land, bending round hills, water and woods, a `path`
  of a few points, and leads from one place to another: never a ring or a frame round nothing. A track's
  ground suits its region: dirt in green land, cobbles on volcanic rock or a cave floor; on snow or ice, none (they are
  walked on as they are). A path steps along x, then y, so a slanting leg comes out as a staircase: keep
  legs level or upright, and bend at a few points.
- Cliffs and mountains. Give a plateau slanted ends (`cut`) and corners (`north`), or, for one large
  cliff, a jagged face (`front`), and a ramp to climb it: each ramp column is a ladder of its own, so one column is a way up,
  and two ways up stand apart. A mountain range is several plateaus of different sizes, smaller ones
  standing on larger ones as terraces, with pines, rocks and boulders on top.
- Gradual borders. Where two regions meet (grass and snow, wood and field) make the border uneven, with
  patches of each on the other's side and things that belong to both near it (frosted dead trees and blue
  pines by the snow). A river between regions winds and changes width, with fords or bridges where roads
  cross it.
- Narrow rims. Ground drawn round water, lava or a chasm as its shore or rim (sand, lava-rock, cave floor)
  is one or two cells wide; beyond it lies the region's own ground.
- Dense woods. A wood is two or three scatters of different kinds over one polygon, 150 to 300 permille
  each (pine-large, maple-large, oak, pine, maple, shrub), with a sparser scatter round its edge and a
  clearing or a path through it. Trees may stand against houses and cliffs, their crowns over them. Not
  single trees dotted over grass.
- Each region keeps its look. Snow, ice, ice spires and frosted trees belong to an icy region, tombstones to
  a graveyard, lava to volcanic rock: nothing of one region dropped in the middle of another.
- Lived-in villages. Houses of different sizes and looks in loose clusters, not a grid; gardens, fences and
  paths to the doors; a well, a market or a square; animals in pens and people about (`ambient`).
- A landmark in each area: a shrine with a statue, a ruined tower, a graveyard, a pond with a dock, a camp
  round a fire, with things about it that tell what it is.
- Fair layout, varied detail. Mirror or turn what decides play (spawns, captures, shops, cover, the ways
  between them); small decoration away from the ways (flowers, rocks, shrubs, rubble) may differ between
  the halves, so they do not look the same.
- What the description names, plainly. Every feature the description asks for (a mountain range, a river,
  a castle) is large and clear enough to recognise at a glance.

The example below is small and plain: it shows the format, not the look to aim for.

## Example

A valid map of 50 x 40 cells, for two teams:

```json
{
  "format": "saga-map",
  "version": 1,
  "name": "Millbrook",
  "description": "A village on a straight cobbled street between two fenced fields, a stone square with the capture point in the middle, a grassy hill with a shrine to the north, two ponds with docks, mixed woods in the corners, and a camp round a fire to the south.",
  "size": [50, 40],
  "tileset": "outdoor",
  "rules": {"teams": [2, 2], "modes": ["dm", "tdm", "dom"]},
  "terrain": {
    "fill": "grass",
    "layers": [
      {"kind": "road", "path": [[0, 20], [49, 20]], "width": 2},
      {"kind": "stone", "rect": [21, 16, 8, 9]},
      {"kind": "dirt", "path": [[24, 12], [24, 15]], "width": 2},
      {"kind": "dirt", "path": [[23, 10], [23, 12], [26, 12], [26, 10]], "width": 1},
      {"kind": "dirt", "path": [[24, 25], [24, 32]], "width": 2},
      {"kind": "dirt", "polygon": [[20, 32], [30, 32], [31, 35], [27, 38], [23, 38], [19, 35]]},
      {"kind": "sand", "ellipse": [9, 31, 7, 5]},
      {"kind": "sand", "ellipse": [40, 31, 7, 5]},
      {"kind": "water", "ellipse": [9, 31, 5, 3]},
      {"kind": "water", "ellipse": [40, 31, 5, 3]},
      {"kind": "dirt", "path": [[11, 22], [11, 24], [9, 26]], "width": 2},
      {"kind": "dirt", "path": [[37, 22], [37, 24], [39, 26]], "width": 2},
      {"kind": "footbridge-ns", "rect": [9, 26, 2, 5]},
      {"kind": "footbridge-ns", "rect": [39, 26, 2, 5]},
      {"kind": "field", "rect": [3, 4, 8, 5]},
      {"kind": "field", "rect": [39, 4, 8, 5]}
    ]
  },
  "objects": [
    {"type": "plateau", "at": [17, 1], "size": [16, 9], "variant": "grass", "front": [0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0], "north": [2, 2], "ramps": [23, 26]},
    {"type": "house", "at": [9, 12], "size": [5, 4], "variant": "orange", "walls": "plaster", "door": "S", "roof": "hip", "chimney": "west", "window": "curtained"},
    {"type": "house", "at": [36, 12], "size": [5, 4], "variant": "teal", "walls": "stone", "door": "S", "roof": "gable", "chimney": "east", "window": "arched"},
    {"type": "house", "at": [12, 23], "size": [6, 4], "variant": "teal-ribbed", "walls": "stone", "door": "S", "sign": "inn", "roof": "hip-gable", "window": "lattice", "beam": true},
    {"type": "house", "at": [32, 23], "size": [6, 4], "variant": "orange-woven", "walls": "plaster", "door": "S", "sign": "pub", "roof": "hip", "window": "plain", "beam": true},
    {"type": "fence", "path": [[6, 9], [2, 9], [2, 3], [11, 3], [11, 9], [8, 9]]},
    {"type": "fence", "path": [[43, 9], [47, 9], [47, 3], [38, 3], [38, 9], [41, 9]]},
    {"type": "well", "at": [22, 17]},
    {"type": "well", "at": [27, 17]},
    {"type": "torch", "at": [21, 22]},
    {"type": "torch", "at": [28, 22]},
    {"type": "pine-large", "at": [19, 3], "variant": "dark"},
    {"type": "pine-large", "at": [29, 3], "variant": "dark"},
    {"type": "menhir", "at": [22, 5]},
    {"type": "menhir", "at": [27, 5]},
    {"type": "tent", "at": [20, 33]},
    {"type": "tent", "at": [27, 33]},
    {"type": "barrel", "at": [19, 26]},
    {"type": "barrel", "at": [30, 26]},
    {"type": "maple-large", "at": [19, 21], "variant": "orange"},
    {"type": "maple-large", "at": [29, 21], "variant": "orange"},
    {"type": "flowers", "at": [15, 16]},
    {"type": "flowers", "at": [34, 16]},
    {"type": "shrub", "at": [8, 16]},
    {"type": "shrub", "at": [41, 16]},
    {"type": "campfire", "at": [25, 34]},
    {"type": "statue", "at": [24, 3]},
    {"scatter": "pine-large", "area": {"polygon": [[0, 10], [7, 10], [8, 14], [6, 18], [0, 18]]}, "permille": 300, "seed": 7, "variant": "dark"},
    {"scatter": "pine-large", "area": {"polygon": [[50, 10], [43, 10], [42, 14], [44, 18], [50, 18]]}, "permille": 300, "seed": 8, "variant": "dark"},
    {"scatter": "oak", "area": {"polygon": [[0, 10], [7, 10], [8, 14], [6, 18], [0, 18]]}, "permille": 250, "seed": 9},
    {"scatter": "oak", "area": {"polygon": [[50, 10], [43, 10], [42, 14], [44, 18], [50, 18]]}, "permille": 250, "seed": 10},
    {"scatter": "shrub", "area": {"polygon": [[0, 10], [7, 10], [8, 14], [6, 18], [0, 18]]}, "permille": 200, "seed": 11},
    {"scatter": "shrub", "area": {"polygon": [[50, 10], [43, 10], [42, 14], [44, 18], [50, 18]]}, "permille": 200, "seed": 12},
    {"scatter": "maple-large", "area": {"polygon": [[0, 36], [3, 34], [9, 37], [15, 37], [17, 40], [0, 40]]}, "permille": 300, "seed": 13, "variant": "green"},
    {"scatter": "maple-large", "area": {"polygon": [[50, 36], [47, 34], [41, 37], [35, 37], [33, 40], [50, 40]]}, "permille": 300, "seed": 14, "variant": "green"},
    {"scatter": "pine-large", "area": {"polygon": [[0, 36], [3, 34], [9, 37], [15, 37], [17, 40], [0, 40]]}, "permille": 250, "seed": 15, "variant": "teal"},
    {"scatter": "pine-large", "area": {"polygon": [[50, 36], [47, 34], [41, 37], [35, 37], [33, 40], [50, 40]]}, "permille": 250, "seed": 16, "variant": "teal"},
    {"scatter": "shrub", "area": {"polygon": [[0, 36], [3, 34], [9, 37], [15, 37], [17, 40], [0, 40]]}, "permille": 200, "seed": 17},
    {"scatter": "shrub", "area": {"polygon": [[50, 36], [47, 34], [41, 37], [35, 37], [33, 40], [50, 40]]}, "permille": 200, "seed": 18}
  ],
  "points": [
    {"type": "spawn", "id": "west", "at": [2, 21], "team": 1},
    {"type": "spawn", "id": "east", "at": [47, 21], "team": 2},
    {"type": "spawn", "id": "south", "at": [25, 37]},
    {"type": "capture", "id": "square", "at": [25, 20]},
    {"type": "shop", "id": "west-store", "at": [14, 18], "stock": "all"},
    {"type": "shop", "id": "east-store", "at": [35, 18], "stock": "all"},
    {"type": "teleport", "id": "west-pond", "at": [3, 31], "to": [46, 26]},
    {"type": "teleport", "id": "east-pond", "at": [46, 31], "to": [3, 26]},
    {"type": "bounce", "id": "west-ramp", "at": [19, 30], "dir": "E", "power": 300},
    {"type": "bounce", "id": "east-ramp", "at": [30, 30], "dir": "W", "power": 300},
    {"type": "ambient", "kind": "sheep", "count": 2, "area": {"rect": [3, 4, 8, 5]}},
    {"type": "ambient", "kind": "sheep", "count": 2, "area": {"rect": [39, 4, 8, 5]}}
  ]
}
```

## The map to make

{{request}}

## How to answer

Reply with the map's JSON document only: no explanation before or after it, no comments inside it.
