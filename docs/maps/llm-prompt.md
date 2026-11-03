# Writing a map for Saga Online

You design a map for Saga Online, a top-down 2D action game in which two to four teams, or everyone
against everyone, fight over a small world of grass, roads, water, houses and trees. Write the map as
one JSON document in the saga-map format, version 1, described below. Reply with the JSON
document only: no explanation before or after it, no comments inside it.

The map to make: {{request}}

## The grid

- The map is a grid of cells, each 16 pixels square. `size` is `[width, height]` in cells.
- A cell is `[x, y]`: x counts from 0 at the left, y from 0 at the top.
- A map is at least 50 x 40 and at most 128 x 128 cells. A player sees about 50 x 37 cells at a time;
  60 x 50 is a good size for four to eight players.
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
and free of other objects and of points.

| object | placed as | what it is |
|---|---|---|
| `tree` | `{"type": "tree", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a tree: its trunk blocks walking, its crown above the trunk is drawn over characters behind it |
| `oak` | `{"type": "oak", "at": [x, y]}`, 2 wide and 2 high, [x, y] its top left | a broad tree two cells wide: its trunk row blocks walking, its crown above is drawn over characters behind it |
| `stump` | `{"type": "stump", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a tree stump |
| `rock` | `{"type": "rock", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a boulder |
| `bush` | `{"type": "bush", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a bush: blocks walking, not sight |
| `flowers` | `{"type": "flowers", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | flowers: decoration that can be walked through |
| `sign` | `{"type": "sign", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a signpost |
| `barrel` | `{"type": "barrel", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a barrel |
| `campfire` | `{"type": "campfire", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a campfire |
| `well` | `{"type": "well", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a stone well |
| `statue` | `{"type": "statue", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a statue on a plinth: the plinth blocks walking, the figure above it is drawn over characters |
| `tent` | `{"type": "tent", "at": [x, y]}`, 3 wide and 3 high, [x, y] its top left | a tent, three cells wide and three high: its top row is drawn over characters behind it |
| `house` | `{"type": "house", "at": [x, y], "size": [w, h], "variant": "orange|teal", "door": "S", "sign": "inn|pub"}`, from 3x3 to 12x10; a `sign`, left out for none, hangs over the door | a house of the given size: its top row is roof eave, drawn over characters and walkable behind the house; every other row is solid |
| `wall` | `{"type": "wall", "path": [[x, y], [x, y], ...]}`, every leg horizontal or vertical | a stone wall along a path of horizontal and vertical segments: blocks walking and sight |
| `fence` | `{"type": "fence", "path": [[x, y], [x, y], ...]}`, every leg horizontal or vertical | a wooden fence along a path of horizontal and vertical segments: blocks walking, not sight |
| `plateau` | `{"type": "plateau", "at": [x, y], "size": [w, h], "variant": "earth|lava|ice|grass", "cut": [west, east], "ramps": [x, ...]}`, from 3x4 to 40x40; its north row and its west and east columns are its edge, which blocks walking; the bottom 2 rows are its cliff face, which blocks walking but where a ramp stands (`ramps`: columns x of the face, inside the west and east edges and the slants); `cut` slants the face back at its west and east ends, by that many columns, a row higher a column further out -- a cliff with angled corners, or with cuts adding up to its width a point; everything else is its top, walkable ground where objects and points may stand, and another plateau too. Without a ramp nobody can climb it | ground raised by a cliff, of the given size: its north row and its west and east columns are its edge and block walking; its bottom two rows are its cliff face, which blocks walking but not sight, but at a ramp; the face may slant back at either end, a row higher a column further out; the rest is its top, walkable ground other things stand on |
| `crystal` | `{"type": "crystal", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a tall blue crystal: its foot blocks walking, not sight; its top is drawn over characters behind it |
| `crystals` | `{"type": "crystals", "at": [x, y]}`, 2 wide and 2 high, [x, y] its top left | a cluster of blue crystals two cells wide: its foot row blocks walking, not sight; its top row is drawn over characters behind it |
| `stalagmite` | `{"type": "stalagmite", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a grey spire of rock: its foot blocks walking, not sight; its tip is drawn over characters behind it |
| `ice-spire` | `{"type": "ice-spire", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a spire of ice: its foot blocks walking, not sight; its tip is drawn over characters behind it |
| `boulder` | `{"type": "boulder", "at": [x, y]}`, 2 wide and 2 high, [x, y] its top left | a great boulder two cells wide: its lower row blocks walking and sight; its upper row is drawn over characters behind it |
| `torch` | `{"type": "torch", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a fire burning on a stand: its stand blocks walking, not sight; its flame is drawn over characters behind it |
| `gargoyle` | `{"type": "gargoyle", "at": [x, y]}`, 1 wide and 2 high, [x, y] its top left | a stone gargoyle on a plinth: the plinth blocks walking, not sight; the figure above it is drawn over characters behind it |
| `skulls` | `{"type": "skulls", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a heap of skulls and bones |
| `tombstone` | `{"type": "tombstone", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a gravestone |
| `embers` | `{"type": "embers", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | glowing embers on the ground: decoration that can be walked through |
| `rubble` | `{"type": "rubble", "at": [x, y]}`, 1 wide and 1 high, [x, y] its top left | a few loose stones: decoration that can be walked through |
| `pine` | `{"type": "pine", "at": [x, y], "variant": "green|dark|teal|blue"}`, 1 wide and 2 high, [x, y] its top left; the variant, `green` when left out, is how it looks and plays alike | a pine a cell wide: its trunk blocks walking, its crown above is drawn over characters behind it |
| `pine-large` | `{"type": "pine-large", "at": [x, y], "variant": "green|dark|teal|blue"}`, 2 wide and 3 high, [x, y] its top left; the variant, `green` when left out, is how it looks and plays alike | a tall pine two cells wide and three high: its foot row blocks walking, its crown above is drawn over characters behind it |
| `maple` | `{"type": "maple", "at": [x, y], "variant": "green|yellow|red|orange"}`, 1 wide and 2 high, [x, y] its top left; the variant, `green` when left out, is how it looks and plays alike | a young broadleaf a cell wide, green or in autumn colours: its trunk blocks walking, its crown above is drawn over characters behind it |
| `maple-large` | `{"type": "maple-large", "at": [x, y], "variant": "green|yellow|red|orange"}`, 2 wide and 4 high, [x, y] its top left; the variant, `green` when left out, is how it looks and plays alike | a tall broadleaf two cells wide and four high, green or in autumn colours: its foot row blocks walking, its crown above is drawn over characters behind it |
| `dead-tree` | `{"type": "dead-tree", "at": [x, y], "variant": "bare|frost"}`, 1 wide and 2 high, [x, y] its top left; the variant, `bare` when left out, is how it looks and plays alike | a dead tree a cell wide, bare or in frost: its trunk blocks walking, its branches above are drawn over characters behind it |
| `dead-tree-large` | `{"type": "dead-tree-large", "at": [x, y], "variant": "bare|frost"}`, 2 wide and 3 high, [x, y] its top left; the variant, `bare` when left out, is how it looks and plays alike | a tall dead tree two cells wide and three high, bare or in frost: its foot row blocks walking, its branches above are drawn over characters behind it |

Many small objects at once: `{"scatter": "tree", "area": {"rect": [x, y, w, h]}, "permille": 150, "seed": 1}`
places one on about 150 of every 1000 cells of the area (an ellipse or a polygon works too), skipping any
cell where it would not fit and every cell next to a point; a `variant` makes them all of that variant.

## Points

`points` are where the game happens. Each stands on a walkable cell of its own, with nothing on it.
An `id` is optional and helps you refer to a point.

- `{"type": "spawn", "at": [x, y], "team": 1}` -- where players start and come back after dying.
  With a team (1-4) it is that team's; without one every team shares it. Every team the map
  allows needs a spawn of its own or a shared one, and the map needs at least one spawn that is not a capture.
- `{"type": "capture", "at": [x, y]}` -- a point teams take by standing on it alone for five seconds; in
  the domination mode held points score. At most 16. A `team` makes it that team's at the start.
- `{"type": "shop", "at": [x, y], "stock": "skill"}` -- players buy here, from within 6 cells and in sight.
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
- `{"type": "ambient", "kind": "sheep", "count": 3, "area": {"rect": [x, y, w, h]}}` -- animals or people
  that wander inside `area` and never leave it: sheep in a fenced field, villagers on a square. Decoration:
  nobody can touch them. Kinds: `chicken`, `dog`, `sheep`, `cow`, `horse`, `villager`.

## Rules the game checks

- Every walkable cell can be reached from every spawn, walking to the four neighbouring cells and through
  teleports. A walkable cell walled in by water, walls or objects is an error: open a way or fill it.
- `rules.teams` is `[fewest, most]` teams the map is for (2 to 4); `rules.modes` lists the modes it
  suits: `dm` (everyone against everyone), `tdm` (team deathmatch), `dom` (domination: needs captures),
  `ma` (Monster Attack: all players on one team against monsters from the homes; needs a monster home).
- Unknown keys are errors: write only the keys described here.

## Making a good map

- Fair: in team modes give each team spawns of the same kind and distance from the middle; a mirrored or
  rotated layout is fair by construction.
- Varied: open ground for fighting, cover (trees, houses, walls) to break lines of sight, a few chokepoints.
- Readable: roads lead between the spawns, the shops and the captures; water and walls shape the space.

## Example

A valid map of 50 x 40 cells, for two teams:

```json
{
  "format": "saga-map",
  "version": 1,
  "name": "Millbrook",
  "description": "A village by a pond: houses along a dirt road, a fenced field in the north east, woods along the east edge, and a stone square in the middle with the capture point.",
  "size": [50, 40],
  "tileset": "outdoor",
  "rules": {"teams": [2, 2], "modes": ["dm", "tdm", "dom"]},
  "terrain": {
    "fill": "grass",
    "layers": [
      {"kind": "dirt", "path": [[0, 20], [49, 20]], "width": 2},
      {"kind": "dirt", "path": [[25, 21], [25, 39]], "width": 2},
      {"kind": "stone", "rect": [22, 17, 7, 7]},
      {"kind": "water", "ellipse": [12, 30, 5, 3]},
      {"kind": "field", "rect": [30, 4, 12, 7]}
    ]
  },
  "objects": [
    {"type": "house", "at": [8, 12], "size": [5, 4], "variant": "orange", "door": "S"},
    {"type": "house", "at": [16, 11], "size": [4, 5], "variant": "teal", "door": "S"},
    {"type": "house", "at": [31, 23], "size": [6, 4], "variant": "orange", "door": "S"},
    {"type": "fence", "path": [[29, 6], [29, 3], [42, 3], [42, 11], [29, 11], [29, 9]]},
    {"type": "tree", "at": [4, 4]},
    {"type": "tree", "at": [6, 6]},
    {"type": "tree", "at": [20, 28]},
    {"type": "bush", "at": [21, 9]},
    {"type": "flowers", "at": [14, 17]},
    {"type": "sign", "at": [21, 22]},
    {"scatter": "tree", "area": {"rect": [44, 0, 6, 18]}, "permille": 120, "seed": 7},
    {"scatter": "tree", "area": {"rect": [44, 23, 6, 17]}, "permille": 120, "seed": 8}
  ],
  "points": [
    {"type": "spawn", "id": "west", "at": [2, 21], "team": 1},
    {"type": "spawn", "id": "east", "at": [47, 21], "team": 2},
    {"type": "spawn", "id": "south", "at": [25, 37]},
    {"type": "capture", "id": "square", "at": [25, 20]},
    {"type": "shop", "id": "store", "at": [10, 17], "stock": "skill"},
    {"type": "shop", "id": "smith", "at": [33, 28], "stock": "equipment"},
    {"type": "teleport", "id": "pond", "at": [5, 30], "to": [40, 34]},
    {"type": "bounce", "id": "ramp", "at": [20, 34], "dir": "E", "power": 300}
  ]
}
```
