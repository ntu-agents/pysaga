# Abilities and weapons in Saga Online

Every ability and weapon in Saga Online, with every property the game gives it. This page is
generated from the game's content tables (`game/config/sim/`) by
`tools/public/abilities_doc.py`, so it always matches the release
it comes with. For how abilities fit into the RL environment's action space, see the
[RL reference](rl-reference.md).

1. [How the numbers work](#how-the-numbers-work)
2. [The properties](#the-properties)
3. [Shared abilities](#shared-abilities)
4. [Warrior abilities](#warrior-abilities)
5. [Magician abilities](#magician-abilities)
6. [Weapons](#weapons)

## How the numbers work

- **Power and Focus** are the game's two stats. The state, the observation and the tables
  call them `strength` and `intelligence`.
- **Damage** is a factor times one of the attacker's stats. A weapon strike reads Power,
  and so does a shield's counter-damage. Every other damaging ability reads Focus. That
  holds for both types. A character starts with 10 of each, and its starting weapon adds
  2 to Power for a warrior and to Focus for a magician. So at the start of a round a
  factor of 2.5 deals 25 for a warrior's ability and 30 for a magician's.
- **Elements.** Earth beats fire, fire beats ice, ice beats wind and wind beats earth. A
  hit deals 20% more to a character of the element it beats, and 20% less to one of the
  element that beats it. An ability of no element (neutral), and the basic strike with a
  weapon of no element, count as the caster's own element.
- **Resistance** takes its share off every hit, so 20% resistance turns 30 damage into
  24. The sources add up -- a shield, an aura, a weapon -- to 75% at most.
- **A lowered maximum** -- a buff ending, a channel wearing off, a weapon taken off --
  takes the current value down with it, but never a living character's health below 1.
- **A knockback** throws the character hit as many pixels as the damage dealt. A throw
  into a wall hurts again.
- **Stunned** characters can neither move nor use abilities. A new stun replaces a shorter
  one rather than adding to it.
- **One at a time.** A buff, a pull or a push cannot be used again while the caster's
  last one from the same row still runs. One from another row runs beside it.
- **Units.** Distances are pixels (a map cell is 16 px), times are seconds. A walking
  character covers 66 px/s.

An ability works by one of eight **templates**:

| template | how it works |
| --- | --- |
| strike | the basic strike, from the weapon in hand |
| area | an effect around the caster, at once or repeated over a duration |
| buff | a timed boost of the caster's own figures |
| channel | a boost the caster builds up step by step, walking or standing, which then wears off step by step |
| point | an effect at a target, at once or after a delay |
| projectile | a shot flying toward a target |
| teleport | the caster moves to a target |
| sweep | a box swept forward from the caster |

## The properties

Each ability table has a column for every property below. A property belongs to some templates only; a cell of another template reads "–".

| property | applies to | what it is |
| --- | --- | --- |
| Tree | every ability | Where it stands in its type's ability tree, as row / tier. A tree has 20 rows, four for each element in the order neutral, earth, fire, ice, wind (the RL environment's learn actions number them the same); along a row the tiers 1 to 4 are learned in order. |
| Template | every ability | How it works, one of the eight templates (see [How the numbers work](#how-the-numbers-work)). |
| Element | every ability | The element its hits count as. A neutral ability counts as its caster's element. |
| Targets | every ability | Who it can be aimed at and who it affects. *enemy* (another side's character, or a monster), *ally* (a team mate, or the caster), *any*. |
| Cost | every ability | The ability points it costs to learn. |
| Requires | every ability | The Power and Focus it needs to be learned: each stat's maximum, less what a running Surge, aura or potion lends it. Checked only when learning. The first ability of a row asks nothing. A type's own abilities ask mostly its own stat, Power for a warrior and Focus for a magician, and from the third of a row on the other stat too; an ability both types share asks both alike. |
| Cooldown | every ability | From the moment it is used. It blocks every ability of the character, the basic strike included. |
| Caster held | every ability | How long the caster stands still after using it, unable to move or use another ability. A strike's is its swing. |
| Range | point, projectile, teleport | The furthest its target may be when it is used, in px. |
| Radius | area | How far around the caster an area reaches, in px, wherever the caster stands at each pulse. 0 means the caster alone. |
| Hit box | strike, point, projectile, sweep | The box that hits, width x length in px. It stands in front of the attacker for a strike and a sweep, around where a point lands, around a projectile as it flies. A point with no box affects its target alone. |
| Steps | strike, sweep | A sweep's box moves forward in this many steps, one every interval, each a share of its length; each step hits whoever is in it once. A strike has one step, and its box stays live for the swing. |
| Duration | area, buff, teleport | How long an area, a buff or a teleport lasts. An area of 0 pulses once; a teleport's caster is invisible until it arrives, from the end of its delay. |
| Interval | area | The time between an area's pulses. |
| Delay | area, point, teleport | A point lands this long after it is used; an area's first pulse waits this long (Explosion 3 charges before it bursts); a teleport's caster vanishes this long after it is used (Passage's vine grows first). |
| Speed | projectile | A projectile's flight, in px/s. |
| Max flight | projectile | The longest a projectile flies before it ends; a wall ends it sooner. |
| Passes through | projectile | *yes*: a projectile passes through the characters it meets, affecting each, and flies on to its target; *no*: it ends on the first character it hits. |
| Ends on target | projectile | *yes*: a projectile passing through others ends once it has hit its target. |
| Follows target | projectile | *yes*: it steers after the target as it moves; *no*: it flies at where the target stood when it was used, so a step aside dodges it. |
| Channel | channel | A channel, built up walking or standing, as its longest time / a step every / a step taken back every once it ends. It ends when its time runs out, or early when the caster dies. |
| Buff shares | buff | A buff's shares of the caster's maxima and its resistance, given at the start and taken back at the end. |
| Bonus damage | strike | Added to the weapon's damage factor. |
| Fixed | area | *yes*: the caster is held for the whole duration, and the area ends at once if the caster's health changes after its first pulse; *no*: the caster may move, and the area moves with it. |
| Line of sight | area | *yes*: only characters the caster can see are reached, a wall shields; *no*: walls do not shield. |
| Multi-hit | area | *yes*: a character in range is affected once every pulse, and one who walks in between two pulses on arrival; *no*: each character at most once for the whole duration, at a pulse. |
| Effects | every ability | What it does, and when. At the start, on each character it hits (or each step of a channel), at the end; and for an enchant, what its caster's basic strike does while it runs. |

## Shared abilities

The abilities both types have, in the same place in both trees. The Strikes are the weapon's own, so their damage reads Power.

| Ability | Tree | Template | Element | Targets | Cost | Requires | Cooldown | Caster held | Range | Radius | Hit box | Steps | Duration | Interval | Delay | Speed | Max flight | Passes through | Ends on target | Follows target | Channel | Buff shares | Bonus damage | Fixed | Line of sight | Multi-hit | Effects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Strike&nbsp;1**&nbsp;(0) | 0 / 1 | strike | neutral | enemy | 1 | none | none | 0.25 s | – | – | 20 x 18 | 1 | – | – | – | – | – | – | – | – | – | – | 0 | – | – | – | each enemy hit: (the weapon's damage factor + the bonus) x the attacker's Power, and the weapon's own hit ([Weapons](#weapons)) |
| **Strike&nbsp;2**&nbsp;(1) | 0 / 2 | strike | neutral | enemy | 1 | 12 Power, 12 Focus | none | 0.25 s | – | – | 20 x 18 | 1 | – | – | – | – | – | – | – | – | – | – | 0.25 | – | – | – | each enemy hit: (the weapon's damage factor + the bonus) x the attacker's Power, and the weapon's own hit ([Weapons](#weapons)) |
| **Strike&nbsp;3**&nbsp;(2) | 0 / 3 | strike | neutral | enemy | 1 | 14 Power, 14 Focus | none | 0.25 s | – | – | 20 x 18 | 1 | – | – | – | – | – | – | – | – | – | – | 0.5 | – | – | – | each enemy hit: (the weapon's damage factor + the bonus) x the attacker's Power, and the weapon's own hit ([Weapons](#weapons)) |
| **Life&nbsp;Surge&nbsp;1**&nbsp;(3) | 1 / 1 | channel | neutral | ally | 1 | none | 5 s | none | – | – | – | – | – | – | – | – | – | – | – | – | 5 s / 1 s / 1 s | – | – | – | – | – | each step, on the caster: +10 maximum health; each step taken back: -10 maximum health |
| **Life&nbsp;Surge&nbsp;2**&nbsp;(4) | 1 / 2 | channel | neutral | ally | 1 | 12 Power, 12 Focus | 10 s | none | – | – | – | – | – | – | – | – | – | – | – | – | 10 s / 1 s / 1 s | – | – | – | – | – | each step, on the caster: +10 maximum health; each step taken back: -10 maximum health |
| **Power&nbsp;Surge&nbsp;1**&nbsp;(9) | 2 / 1 | channel | neutral | ally | 1 | none | 5 s | none | – | – | – | – | – | – | – | – | – | – | – | – | 5 s / 1 s / 1 s | – | – | – | – | – | each step, on the caster: +1 maximum Power; each step taken back: -1 maximum Power |
| **Power&nbsp;Surge&nbsp;2**&nbsp;(10) | 2 / 2 | channel | neutral | ally | 1 | 12 Power, 12 Focus | 10 s | none | – | – | – | – | – | – | – | – | – | – | – | – | 10 s / 1 s / 1 s | – | – | – | – | – | each step, on the caster: +1 maximum Power; each step taken back: -1 maximum Power |
| **Focus&nbsp;Surge&nbsp;1**&nbsp;(15) | 3 / 1 | channel | neutral | ally | 1 | none | 5 s | none | – | – | – | – | – | – | – | – | – | – | – | – | 5 s / 1 s / 1 s | – | – | – | – | – | each step, on the caster: +1 maximum Focus; each step taken back: -1 maximum Focus |
| **Focus&nbsp;Surge&nbsp;2**&nbsp;(16) | 3 / 2 | channel | neutral | ally | 1 | 12 Power, 12 Focus | 10 s | none | – | – | – | – | – | – | – | – | – | – | – | – | 10 s / 1 s / 1 s | – | – | – | – | – | each step, on the caster: +1 maximum Focus; each step taken back: -1 maximum Focus |
| **Earth&nbsp;Aura&nbsp;1**&nbsp;(25) | 4 / 1 | buff | earth | any | 1 | none | 2 s | none | – | – | – | – | 6 s | – | – | – | – | – | – | – | – | +10% health, +20% resistance | – | – | – | – | at the start, on the caster: its basic strike counts as earth; at the end, on the caster: its basic strike counts as its weapon's element again |
| **Earth&nbsp;Aura&nbsp;2**&nbsp;(26) | 4 / 2 | buff | earth | any | 1 | 12 Power, 12 Focus | 2 s | none | – | – | – | – | 8 s | – | – | – | – | – | – | – | – | +20% health, +40% resistance | – | – | – | – | at the start, on the caster: its basic strike counts as earth; at the end, on the caster: its basic strike counts as its weapon's element again |
| **Earth&nbsp;Aura&nbsp;3**&nbsp;(27) | 4 / 3 | buff | earth | any | 1 | 14 Power, 14 Focus | 2 s | none | – | – | – | – | 10 s | – | – | – | – | – | – | – | – | +30% health, +60% resistance | – | – | – | – | at the start, on the caster: its basic strike counts as earth; at the end, on the caster: its basic strike counts as its weapon's element again |
| **Fire&nbsp;Aura&nbsp;1**&nbsp;(50) | 8 / 1 | buff | fire | any | 1 | none | 2 s | none | – | – | – | – | 6 s | – | – | – | – | – | – | – | – | +20% Power | – | – | – | – | at the start, on the caster: its basic strike counts as fire, its basic strike's hits are drawn enchanted; at the end, on the caster: its basic strike counts as its weapon's element again, its basic strike's hits are drawn as its weapon's again |
| **Fire&nbsp;Aura&nbsp;2**&nbsp;(51) | 8 / 2 | buff | fire | any | 1 | 12 Power, 12 Focus | 2 s | none | – | – | – | – | 8 s | – | – | – | – | – | – | – | – | +30% Power | – | – | – | – | at the start, on the caster: its basic strike counts as fire, its basic strike's hits are drawn enchanted; at the end, on the caster: its basic strike counts as its weapon's element again, its basic strike's hits are drawn as its weapon's again |
| **Fire&nbsp;Aura&nbsp;3**&nbsp;(52) | 8 / 3 | buff | fire | any | 1 | 14 Power, 14 Focus | 2 s | none | – | – | – | – | 10 s | – | – | – | – | – | – | – | – | +40% Power | – | – | – | – | at the start, on the caster: its basic strike counts as fire, its basic strike's hits are drawn enchanted; at the end, on the caster: its basic strike counts as its weapon's element again, its basic strike's hits are drawn as its weapon's again |
| **Ice&nbsp;Aura&nbsp;1**&nbsp;(75) | 12 / 1 | buff | ice | any | 1 | none | 2 s | none | – | – | – | – | 6 s | – | – | – | – | – | – | – | – | +5% Power | – | – | – | – | at the start, on the caster: its basic strike counts as ice, its basic strike's hits are drawn enchanted; while it runs, each enemy the caster's basic strike hits is stunned for 1 s, at most once every 2 s per attacker; at the end, on the caster: its basic strike counts as its weapon's element again, its basic strike's hits are drawn as its weapon's again |
| **Ice&nbsp;Aura&nbsp;2**&nbsp;(76) | 12 / 2 | buff | ice | any | 1 | 12 Power, 12 Focus | 2 s | none | – | – | – | – | 8 s | – | – | – | – | – | – | – | – | +10% Power | – | – | – | – | at the start, on the caster: its basic strike counts as ice, its basic strike's hits are drawn enchanted; while it runs, each enemy the caster's basic strike hits is stunned for 1 s, at most once every 2 s per attacker; at the end, on the caster: its basic strike counts as its weapon's element again, its basic strike's hits are drawn as its weapon's again |
| **Ice&nbsp;Aura&nbsp;3**&nbsp;(77) | 12 / 3 | buff | ice | any | 1 | 14 Power, 14 Focus | 2 s | none | – | – | – | – | 10 s | – | – | – | – | – | – | – | – | +15% Power | – | – | – | – | at the start, on the caster: its basic strike counts as ice, its basic strike's hits are drawn enchanted; while it runs, each enemy the caster's basic strike hits is stunned for 1 s, at most once every 2 s per attacker; at the end, on the caster: its basic strike counts as its weapon's element again, its basic strike's hits are drawn as its weapon's again |
| **Wind&nbsp;Aura&nbsp;1**&nbsp;(100) | 16 / 1 | buff | wind | any | 1 | none | 2 s | none | – | – | – | – | 6 s | – | – | – | – | – | – | – | – | none | – | – | – | – | at the start, on the caster: +33 px/s walking speed, its basic strike counts as wind; at the end, on the caster: -33 px/s walking speed, its basic strike counts as its weapon's element again |
| **Wind&nbsp;Aura&nbsp;2**&nbsp;(101) | 16 / 2 | buff | wind | any | 1 | 12 Power, 12 Focus | 2 s | none | – | – | – | – | 8 s | – | – | – | – | – | – | – | – | none | – | – | – | – | at the start, on the caster: +33 px/s walking speed, its basic strike counts as wind; at the end, on the caster: -33 px/s walking speed, its basic strike counts as its weapon's element again |
| **Wind&nbsp;Aura&nbsp;3**&nbsp;(102) | 16 / 3 | buff | wind | any | 1 | 14 Power, 14 Focus | 2 s | none | – | – | – | – | 10 s | – | – | – | – | – | – | – | – | none | – | – | – | – | at the start, on the caster: +33 px/s walking speed, its basic strike counts as wind; at the end, on the caster: -33 px/s walking speed, its basic strike counts as its weapon's element again |

## Warrior abilities

The warrior's own abilities; its tree also holds the shared ones above.

| Ability | Tree | Template | Element | Targets | Cost | Requires | Cooldown | Caster held | Range | Radius | Hit box | Steps | Duration | Interval | Delay | Speed | Max flight | Passes through | Ends on target | Follows target | Channel | Buff shares | Bonus damage | Fixed | Line of sight | Multi-hit | Effects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Life&nbsp;Spring&nbsp;1**&nbsp;(5) | 1 / 3 | area | neutral | ally | 1 | 16 Power, 12 Focus | 3.25 s | none | – | 75 | – | – | 5 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | yes | each ally hit: +10 health |
| **Life&nbsp;Spring&nbsp;2**&nbsp;(6) | 1 / 4 | area | neutral | ally | 1 | 18 Power, 14 Focus | 5.75 s | none | – | 75 | – | – | 10 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | yes | each ally hit: +10 health |
| **Power&nbsp;Spring&nbsp;1**&nbsp;(11) | 2 / 3 | area | neutral | ally | 1 | 16 Power, 12 Focus | 5 s | none | – | 75 | – | – | 5 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | yes | each ally hit: +1 Power, up to its maximum |
| **Power&nbsp;Spring&nbsp;2**&nbsp;(12) | 2 / 4 | area | neutral | ally | 1 | 18 Power, 14 Focus | 5 s | none | – | 75 | – | – | 10 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | yes | each ally hit: +1 Power, up to its maximum |
| **Focus&nbsp;Spring&nbsp;1**&nbsp;(17) | 3 / 3 | area | neutral | ally | 1 | 16 Power, 12 Focus | 5 s | none | – | 75 | – | – | 5 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | yes | each ally hit: +1 Focus, up to its maximum |
| **Focus&nbsp;Spring&nbsp;2**&nbsp;(18) | 3 / 4 | area | neutral | ally | 1 | 18 Power, 14 Focus | 5 s | none | – | 75 | – | – | 10 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | yes | each ally hit: +1 Focus, up to its maximum |
| **Earthquake&nbsp;1**&nbsp;(28) | 5 / 1 | area | earth | enemy | 1 | none | 3.75 s | none | – | 100 | – | – | 6 s | 2 s | none | – | – | – | – | – | – | – | – | yes | no | yes | each enemy hit: 1.5 x Focus damage, stunned for 0.5 s |
| **Earthquake&nbsp;2**&nbsp;(29) | 5 / 2 | area | earth | enemy | 1 | 14 Power | 4.25 s | none | – | 150 | – | – | 6 s | 2 s | none | – | – | – | – | – | – | – | – | yes | no | yes | each enemy hit: 2 x Focus damage, stunned for 0.5 s |
| **Earthquake&nbsp;3**&nbsp;(30) | 5 / 3 | area | earth | enemy | 1 | 16 Power, 12 Focus | 4.75 s | none | – | 200 | – | – | 6 s | 2 s | none | – | – | – | – | – | – | – | – | yes | no | yes | each enemy hit: 2.5 x Focus damage, stunned for 0.5 s |
| **Healing&nbsp;Spring&nbsp;1**&nbsp;(31) | 6 / 1 | area | earth | ally | 1 | none | 2 s | none | – | 50 | – | – | 0 s | 0 s | none | – | – | – | – | – | – | – | – | no | no | no | each ally hit: +25 health |
| **Healing&nbsp;Spring&nbsp;2**&nbsp;(32) | 6 / 2 | area | earth | ally | 1 | 14 Power | 3.5 s | none | – | 75 | – | – | 0 s | 0 s | none | – | – | – | – | – | – | – | – | no | no | no | each ally hit: +50 health |
| **Healing&nbsp;Spring&nbsp;3**&nbsp;(33) | 6 / 3 | area | earth | ally | 1 | 16 Power, 12 Focus | 6 s | none | – | 100 | – | – | 0 s | 0 s | none | – | – | – | – | – | – | – | – | no | no | no | each ally hit: +94 health |
| **Passage&nbsp;1**&nbsp;(34) | 7 / 1 | teleport | earth | ally | 1 | none | 2 s | none | 400 | – | – | – | 1 s | – | 0.6 s | – | – | – | – | – | – | – | – | – | – | – | at the start, on the caster: invisible: no ability can target or hit the character; at the end, on the caster: the caster moves to where the target stands, visible again |
| **Passage&nbsp;2**&nbsp;(35) | 7 / 2 | teleport | earth | enemy | 1 | 14 Power | 2 s | none | 400 | – | – | – | 1 s | – | 0.6 s | – | – | – | – | – | – | – | – | – | – | – | at the start, on the caster: invisible: no ability can target or hit the character; at the end, on the caster: the caster moves to where the target stands, visible again |
| **Passage&nbsp;3**&nbsp;(36) | 7 / 3 | teleport | earth | any | 1 | 16 Power, 12 Focus | 2 s | none | 500 | – | – | – | 1 s | – | 0.6 s | – | – | – | – | – | – | – | – | – | – | – | at the start, on the caster: invisible: no ability can target or hit the character; at the end, on the caster: the caster moves to where the target stands, visible again |
| **Fire&nbsp;Run&nbsp;1**&nbsp;(53) | 9 / 1 | area | fire | enemy | 1 | none | 6 s | none | – | 20 | – | – | 5 s | 0.5 s | none | – | – | – | – | – | – | – | – | no | no | yes | at the start, on the caster: +33 px/s walking speed; each enemy hit: 0.7 x Focus damage, and a knockback as far as the damage; at the end, on the caster: -33 px/s walking speed |
| **Fire&nbsp;Run&nbsp;2**&nbsp;(54) | 9 / 2 | area | fire | enemy | 1 | 14 Power | 6 s | none | – | 20 | – | – | 10 s | 0.5 s | none | – | – | – | – | – | – | – | – | no | no | yes | at the start, on the caster: +33 px/s walking speed; each enemy hit: 0.4 x Focus damage, and a knockback as far as the damage; at the end, on the caster: -33 px/s walking speed |
| **Explosion&nbsp;1**&nbsp;(56) | 10 / 1 | area | fire | enemy | 1 | none | 1.25 s | none | – | 50 | – | – | 2 s | 2 s | none | – | – | – | – | – | – | – | – | yes | no | no | each enemy hit: 1.5 x Focus damage, and a knockback as far as the damage |
| **Explosion&nbsp;2**&nbsp;(57) | 10 / 2 | area | fire | enemy | 1 | 14 Power | 1.75 s | none | – | 80 | – | – | 2 s | 2 s | none | – | – | – | – | – | – | – | – | yes | no | no | each enemy hit: 2.5 x Focus damage, and a knockback as far as the damage |
| **Explosion&nbsp;3**&nbsp;(58) | 10 / 3 | area | fire | enemy | 1 | 16 Power, 12 Focus | 2.25 s | none | – | 100 | – | – | 2 s | 2 s | 0.5 s | – | – | – | – | – | – | – | – | yes | no | no | each enemy hit: 3.5 x Focus damage, and a knockback as far as the damage |
| **Fire&nbsp;Shield&nbsp;1**&nbsp;(59) | 11 / 1 | buff | fire | any | 1 | none | 3 s | none | – | – | – | – | 5 s | – | – | – | – | – | – | – | – | +15% resistance | – | – | – | – | at the start, on the caster: a basic strike that hits it costs the attacker 0.25 x the caster's Power in damage, with a knockback as far as the damage; at the end, on the caster: no more counter-hits |
| **Fire&nbsp;Shield&nbsp;2**&nbsp;(60) | 11 / 2 | buff | fire | any | 1 | 14 Power | 3 s | none | – | – | – | – | 7.5 s | – | – | – | – | – | – | – | – | +25% resistance | – | – | – | – | at the start, on the caster: a basic strike that hits it costs the attacker 0.25 x the caster's Power in damage, with a knockback as far as the damage; at the end, on the caster: no more counter-hits |
| **Fire&nbsp;Shield&nbsp;3**&nbsp;(61) | 11 / 3 | buff | fire | any | 1 | 16 Power, 12 Focus | 3 s | none | – | – | – | – | 10 s | – | – | – | – | – | – | – | – | +35% resistance | – | – | – | – | at the start, on the caster: a basic strike that hits it costs the attacker 0.25 x the caster's Power in damage, with a knockback as far as the damage; at the end, on the caster: no more counter-hits |
| **Ice&nbsp;Shield&nbsp;1**&nbsp;(78) | 13 / 1 | buff | ice | any | 1 | none | 2 s | none | – | – | – | – | 5 s | – | – | – | – | – | – | – | – | +20% resistance | – | – | – | – | at the start, on the caster: a basic strike that hits it stuns the attacker for 1 s; at the end, on the caster: no more counter-hits |
| **Ice&nbsp;Shield&nbsp;2**&nbsp;(79) | 13 / 2 | buff | ice | any | 1 | 14 Power | 2 s | none | – | – | – | – | 7.5 s | – | – | – | – | – | – | – | – | +30% resistance | – | – | – | – | at the start, on the caster: a basic strike that hits it stuns the attacker for 1.5 s; at the end, on the caster: no more counter-hits |
| **Ice&nbsp;Shield&nbsp;3**&nbsp;(80) | 13 / 3 | buff | ice | any | 1 | 16 Power, 12 Focus | 2 s | none | – | – | – | – | 10 s | – | – | – | – | – | – | – | – | +40% resistance | – | – | – | – | at the start, on the caster: a basic strike that hits it stuns the attacker for 2 s; at the end, on the caster: no more counter-hits |
| **Ice&nbsp;Spike&nbsp;1**&nbsp;(81) | 14 / 1 | point | ice | enemy | 1 | none | 3.25 s | none | 200 | – | 20 x 15 | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 1.5 x Focus damage, stunned for 0.5 s |
| **Ice&nbsp;Spike&nbsp;2**&nbsp;(82) | 14 / 2 | point | ice | enemy | 1 | 14 Power | 4.25 s | none | 250 | – | 29 x 20 | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 2 x Focus damage, stunned for 0.5 s |
| **Ice&nbsp;Spike&nbsp;3**&nbsp;(83) | 14 / 3 | point | ice | enemy | 1 | 16 Power, 12 Focus | 6 s | none | 300 | – | 32 x 20 | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 3 x Focus damage, stunned for 0.5 s |
| **Frost&nbsp;Nova&nbsp;1**&nbsp;(84) | 15 / 1 | area | ice | enemy | 1 | none | 4 s | none | – | 50 | – | – | 2 s | 0.5 s | none | – | – | – | – | – | – | – | – | yes | yes | no | each enemy hit: stunned for 2 s |
| **Frost&nbsp;Nova&nbsp;2**&nbsp;(85) | 15 / 2 | area | ice | enemy | 1 | 14 Power | 6 s | none | – | 75 | – | – | 3 s | 0.5 s | none | – | – | – | – | – | – | – | – | yes | yes | no | each enemy hit: stunned for 3 s |
| **Frost&nbsp;Nova&nbsp;3**&nbsp;(86) | 15 / 3 | area | ice | enemy | 1 | 16 Power, 12 Focus | 8 s | none | – | 100 | – | – | 4 s | 0.5 s | none | – | – | – | – | – | – | – | – | yes | yes | no | each enemy hit: stunned for 4 s |
| **Wind&nbsp;Run&nbsp;1**&nbsp;(103) | 17 / 1 | area | wind | any | 1 | none | 6 s | none | – | 0 | – | – | 6 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | no | at the start, on the caster: +66 px/s walking speed; at the end, on the caster: -66 px/s walking speed |
| **Wind&nbsp;Run&nbsp;2**&nbsp;(104) | 17 / 2 | area | wind | any | 1 | 14 Power | 6 s | none | – | 0 | – | – | 10 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | no | at the start, on the caster: +99 px/s walking speed; at the end, on the caster: -99 px/s walking speed |
| **Shockwave&nbsp;1**&nbsp;(106) | 18 / 1 | area | wind | enemy | 1 | none | 3 s | none | – | 100 | – | – | 2 s | 2 s | none | – | – | – | – | – | – | – | – | yes | yes | no | each enemy hit: thrown away from the caster: 200 px, 2 px less for every pixel of distance from it |
| **Shockwave&nbsp;2**&nbsp;(107) | 18 / 2 | area | wind | enemy | 1 | 14 Power | 3 s | none | – | 200 | – | – | 2 s | 2 s | none | – | – | – | – | – | – | – | – | yes | yes | no | each enemy hit: thrown away from the caster: 300 px, 2 px less for every pixel of distance from it |
| **Shockwave&nbsp;3**&nbsp;(108) | 18 / 3 | area | wind | enemy | 1 | 16 Power, 12 Focus | 3 s | none | – | 300 | – | – | 2 s | 2 s | none | – | – | – | – | – | – | – | – | yes | yes | no | each enemy hit: thrown away from the caster: 400 px, 2 px less for every pixel of distance from it |
| **Wind&nbsp;Draft&nbsp;1**&nbsp;(109) | 19 / 1 | area | wind | enemy | 1 | none | none | none | – | 150 | – | – | 4 s | 0.03 s | none | – | – | – | – | – | – | – | – | no | yes | yes | each enemy hit: pulled 1 px toward the caster |
| **Wind&nbsp;Draft&nbsp;2**&nbsp;(110) | 19 / 2 | area | wind | enemy | 1 | 14 Power | none | none | – | 200 | – | – | 6 s | 0.03 s | none | – | – | – | – | – | – | – | – | no | yes | yes | each enemy hit: pulled 2 px toward the caster |

## Magician abilities

The magician's own abilities; its tree also holds the shared ones above.

| Ability | Tree | Template | Element | Targets | Cost | Requires | Cooldown | Caster held | Range | Radius | Hit box | Steps | Duration | Interval | Delay | Speed | Max flight | Passes through | Ends on target | Follows target | Channel | Buff shares | Bonus damage | Fixed | Line of sight | Multi-hit | Effects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Life&nbsp;Drain&nbsp;1**&nbsp;(7) | 1 / 3 | area | neutral | enemy | 1 | 12 Power, 16 Focus | 3.25 s | none | – | 60 | – | – | 5 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | yes | each enemy hit: loses 10 health, never below 1 |
| **Life&nbsp;Drain&nbsp;2**&nbsp;(8) | 1 / 4 | area | neutral | enemy | 1 | 14 Power, 18 Focus | 5.75 s | none | – | 60 | – | – | 10 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | yes | each enemy hit: loses 10 health, never below 1 |
| **Power&nbsp;Drain&nbsp;1**&nbsp;(13) | 2 / 3 | area | neutral | enemy | 1 | 12 Power, 16 Focus | 5 s | none | – | 60 | – | – | 5 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | yes | each enemy hit: loses 1 Power |
| **Power&nbsp;Drain&nbsp;2**&nbsp;(14) | 2 / 4 | area | neutral | enemy | 1 | 14 Power, 18 Focus | 5 s | none | – | 60 | – | – | 10 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | yes | each enemy hit: loses 1 Power |
| **Focus&nbsp;Drain&nbsp;1**&nbsp;(19) | 3 / 3 | area | neutral | enemy | 1 | 12 Power, 16 Focus | 5 s | none | – | 60 | – | – | 5 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | yes | each enemy hit: loses 1 Focus |
| **Focus&nbsp;Drain&nbsp;2**&nbsp;(20) | 3 / 4 | area | neutral | enemy | 1 | 14 Power, 18 Focus | 5 s | none | – | 60 | – | – | 10 s | 1 s | none | – | – | – | – | – | – | – | – | no | no | yes | each enemy hit: loses 1 Focus |
| **Earth&nbsp;Thrust&nbsp;1**&nbsp;(39) | 5 / 1 | point | earth | enemy | 1 | none | 2.75 s | none | 150 | – | 18 x 10 | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 1.5 x Focus damage, stunned for 0.5 s |
| **Earth&nbsp;Thrust&nbsp;2**&nbsp;(40) | 5 / 2 | point | earth | enemy | 1 | 14 Focus | 3.75 s | none | 200 | – | 25 x 15 | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 2 x Focus damage, stunned for 0.5 s |
| **Earth&nbsp;Thrust&nbsp;3**&nbsp;(41) | 5 / 3 | point | earth | enemy | 1 | 12 Power, 16 Focus | 6 s | none | 300 | – | 43 x 25 | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 3 x Focus damage, stunned for 0.5 s |
| **Boulder&nbsp;1**&nbsp;(42) | 6 / 1 | point | earth | enemy | 1 | none | 4.25 s | none | 200 | – | 30 x 20 | – | – | – | 1.2 s | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 2 x Focus damage, stunned for 0.5 s |
| **Boulder&nbsp;2**&nbsp;(43) | 6 / 2 | point | earth | enemy | 1 | 14 Focus | 5.5 s | none | 250 | – | 30 x 30 | – | – | – | 1.2 s | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 2.5 x Focus damage, stunned for 0.5 s |
| **Boulder&nbsp;3**&nbsp;(44) | 6 / 3 | point | earth | enemy | 1 | 12 Power, 16 Focus | 6 s | none | 300 | – | 70 x 50 | – | – | – | 1.2 s | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 3 x Focus damage, stunned for 0.5 s |
| **Healing&nbsp;1**&nbsp;(45) | 7 / 1 | point | earth | ally | 1 | none | 4.25 s | none | 200 | – | none | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each ally hit: +50 health |
| **Healing&nbsp;2**&nbsp;(46) | 7 / 2 | point | earth | ally | 1 | 14 Focus | 6 s | none | 300 | – | none | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each ally hit: +83 health |
| **Fire&nbsp;1**&nbsp;(64) | 9 / 1 | point | fire | enemy | 1 | none | 2.25 s | none | 200 | – | 16 x 10 | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 1 x Focus damage |
| **Fire&nbsp;2**&nbsp;(65) | 9 / 2 | point | fire | enemy | 1 | 14 Focus | 5 s | none | 300 | – | 30 x 15 | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 2 x Focus damage |
| **Fire&nbsp;3**&nbsp;(66) | 9 / 3 | point | fire | enemy | 1 | 12 Power, 16 Focus | 6 s | none | 400 | – | 40 x 25 | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 3 x Focus damage |
| **Fireball&nbsp;1**&nbsp;(67) | 10 / 1 | projectile | fire | enemy | 1 | none | 2.25 s | 0.5 s | 200 | – | 20 x 20 | – | – | – | – | 166.7 | 20 s (the default) | no | yes | no | – | – | – | – | – | – | each enemy hit: 1 x Focus damage, and a knockback as far as the damage |
| **Fireball&nbsp;2**&nbsp;(68) | 10 / 2 | projectile | fire | enemy | 1 | 14 Focus | 3.75 s | 0.5 s | 200 | – | 25 x 25 | – | – | – | – | 166.7 | 20 s (the default) | no | yes | no | – | – | – | – | – | – | each enemy hit: 2 x Focus damage, and a knockback as far as the damage |
| **Fireball&nbsp;3**&nbsp;(69) | 10 / 3 | projectile | fire | enemy | 1 | 12 Power, 16 Focus | 6 s | 0.5 s | 400 | – | 30 x 30 | – | – | – | – | 166.7 | 20 s (the default) | no | yes | no | – | – | – | – | – | – | each enemy hit: 3 x Focus damage, and a knockback as far as the damage |
| **Chain&nbsp;Explosion&nbsp;1**&nbsp;(70) | 11 / 1 | sweep | fire | enemy | 1 | none | 1.75 s | none | – | – | 50 x 200 | 4, every 0.4 s | – | – | – | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 2 x Focus damage, and a knockback as far as the damage |
| **Chain&nbsp;Explosion&nbsp;2**&nbsp;(71) | 11 / 2 | sweep | fire | enemy | 1 | 14 Focus | 2.25 s | none | – | – | 50 x 300 | 6, every 0.4 s | – | – | – | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 3 x Focus damage, and a knockback as far as the damage |
| **Reflection&nbsp;1**&nbsp;(89) | 13 / 1 | buff | ice | any | 1 | none | 3 s | none | – | – | – | – | 5 s | – | – | – | – | – | – | – | – | none | – | – | – | – | at the start, on the caster: reflects projectiles back at their senders; at the end, on the caster: no longer reflects projectiles |
| **Reflection&nbsp;2**&nbsp;(90) | 13 / 2 | buff | ice | any | 1 | 14 Focus | 3 s | none | – | – | – | – | 10 s | – | – | – | – | – | – | – | – | none | – | – | – | – | at the start, on the caster: reflects projectiles back at their senders; at the end, on the caster: no longer reflects projectiles |
| **Ice&nbsp;Ball&nbsp;1**&nbsp;(92) | 14 / 1 | projectile | ice | enemy | 1 | none | 2.25 s | 0.5 s | 200 | – | 15 x 15 | – | – | – | – | 166.7 | 20 s (the default) | yes | no | no | – | – | – | – | – | – | each enemy hit: 1 x Focus damage, and a knockback as far as the damage |
| **Ice&nbsp;Ball&nbsp;2**&nbsp;(93) | 14 / 2 | projectile | ice | enemy | 1 | 14 Focus | 3.75 s | 0.5 s | 200 | – | 15 x 15 | – | – | – | – | 166.7 | 20 s (the default) | yes | no | no | – | – | – | – | – | – | each enemy hit: 2 x Focus damage, and a knockback as far as the damage |
| **Ice&nbsp;Ball&nbsp;3**&nbsp;(94) | 14 / 3 | projectile | ice | enemy | 1 | 12 Power, 16 Focus | 6 s | 0.5 s | 400 | – | 20 x 20 | – | – | – | – | 166.7 | 20 s (the default) | yes | no | no | – | – | – | – | – | – | each enemy hit: 3 x Focus damage, and a knockback as far as the damage |
| **Frost&nbsp;1**&nbsp;(95) | 15 / 1 | point | ice | enemy | 1 | none | 6 s | none | 300 | – | none | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: stunned for 3 s |
| **Frost&nbsp;2**&nbsp;(96) | 15 / 2 | point | ice | enemy | 1 | 14 Focus | 10 s | none | 400 | – | none | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: stunned for 5 s |
| **Lightning&nbsp;1**&nbsp;(114) | 17 / 1 | point | wind | enemy | 1 | none | 2.75 s | none | 150 | – | 25 x 15 | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 1.5 x Focus damage |
| **Lightning&nbsp;2**&nbsp;(115) | 17 / 2 | point | wind | enemy | 1 | 14 Focus | 3.75 s | none | 200 | – | 20 x 20 | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: 2 x Focus damage |
| **Ball&nbsp;Lightning**&nbsp;(116) | 17 / 3 | projectile | wind | enemy | 1 | 12 Power, 16 Focus | 6 s | 0.5 s | 300 | – | 28 x 36 | – | – | – | – | 53.3 | 20 s | no | yes | yes | – | – | – | – | – | – | each enemy hit: 3 x Focus damage, and a knockback as far as the damage |
| **Wind&nbsp;Blast&nbsp;1**&nbsp;(117) | 18 / 1 | point | wind | enemy | 1 | none | 4 s | none | 150 | – | none | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: thrown away from the caster: 300 px, 2 px less for every pixel of distance from it |
| **Wind&nbsp;Blast&nbsp;2**&nbsp;(118) | 18 / 2 | point | wind | enemy | 1 | 14 Focus | 4 s | none | 200 | – | none | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: thrown away from the caster: 350 px, 2 px less for every pixel of distance from it |
| **Wind&nbsp;Blast&nbsp;3**&nbsp;(119) | 18 / 3 | point | wind | enemy | 1 | 12 Power, 16 Focus | 4 s | none | 250 | – | none | – | – | – | none | – | – | – | – | – | – | – | – | – | – | – | each enemy hit: thrown away from the caster: 400 px, 2 px less for every pixel of distance from it |
| **Wind&nbsp;Pressure&nbsp;1**&nbsp;(120) | 19 / 1 | area | wind | enemy | 1 | none | 6 s | none | – | 150 | – | – | 6 s | 0.03 s | none | – | – | – | – | – | – | – | – | no | yes | yes | each enemy hit: pushed 1 px away from the caster |
| **Wind&nbsp;Pressure&nbsp;2**&nbsp;(121) | 19 / 2 | area | wind | enemy | 1 | 14 Focus | 6 s | none | – | 200 | – | – | 6 s | 0.03 s | none | – | – | – | – | – | – | – | – | no | yes | yes | each enemy hit: pushed 2 px away from the caster |

## Weapons

Each character holds one weapon; it starts with its type's first. The basic strike deals (the weapon's damage factor + the strike's bonus damage) x the attacker's Power. A weapon's bonuses apply while it is held. Weapons are bought in a shop like items; an RL agent keeps the one it starts with.

| property | what it is |
| --- | --- |
| Type | The character type that can hold it. |
| Coins | Its price in a shop. |
| Requires | The Power and Focus (at their maximum) it needs. |
| Damage factor | The basic strike's damage factor with it in hand. |
| Element | The element its strikes count as; neutral counts as the attacker's own. |
| Max health, Power, Focus | Added to the holder's maxima while it is held. |
| Speed | Added to the holder's walking speed, in px/s. |
| Resistance | Added to the holder's resistance. |
| Experience | Added to the experience the holder earns. |
| Strike cooldown | The time after each strike before the next ability, the strike included. |
| Each hit also | What every strike with it does besides the damage. |

| Weapon | Type | Coins | Requires | Damage factor | Element | Max health | Power | Focus | Speed | Resistance | Experience | Strike cooldown | Each hit also |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Light&nbsp;Sword**&nbsp;(75) | warrior | 25 | 1 Power, 1 Focus | 1 | neutral | – | +2 | – | – | – | – | none | – |
| **Heavy&nbsp;Sword**&nbsp;(76) | warrior | 50 | 1 Power, 1 Focus | 1.25 | neutral | – | +3 | – | – | – | – | none | – |
| **War&nbsp;Axe**&nbsp;(77) | warrior | 100 | 1 Power, 1 Focus | 1.5 | neutral | – | +4 | – | – | – | – | none | – |
| **War&nbsp;Sword**&nbsp;(78) | warrior | 200 | 1 Power, 1 Focus | 1.75 | neutral | – | +5 | – | – | – | – | none | – |
| **Blade&nbsp;of&nbsp;Earth**&nbsp;(79) | warrior | 600 | 1 Power, 1 Focus | 1.75 | earth | +100 | +5 | – | – | +25% | – | none | – |
| **Blade&nbsp;of&nbsp;Fire**&nbsp;(80) | warrior | 600 | 1 Power, 1 Focus | 2 | fire | – | +6 | – | – | – | – | none | – |
| **Blade&nbsp;of&nbsp;Ice**&nbsp;(81) | warrior | 600 | 1 Power, 1 Focus | 1.75 | ice | – | +6 | – | – | – | – | none | the enemy is stunned for 1 s, at most once every 2 s |
| **Blade&nbsp;of&nbsp;Wind**&nbsp;(82) | warrior | 600 | 1 Power, 1 Focus | 2 | wind | – | +5 | – | +33 | – | – | none | – |
| **Ivory&nbsp;Staff**&nbsp;(100) | magician | 20 | 1 Power, 1 Focus | 1 | neutral | – | – | +2 | – | – | – | none | – |
| **Cleric's&nbsp;Staff**&nbsp;(101) | magician | 40 | 1 Power, 1 Focus | 1.1 | neutral | – | +2 | +3 | – | – | – | none | – |
| **Paladin's&nbsp;Staff**&nbsp;(102) | magician | 80 | 1 Power, 1 Focus | 1.25 | neutral | – | +3 | +4 | – | – | – | none | – |
| **Mage's&nbsp;Staff**&nbsp;(103) | magician | 160 | 1 Power, 1 Focus | 1.25 | neutral | – | – | +5 | – | – | – | none | – |
| **Staff&nbsp;of&nbsp;Earth**&nbsp;(104) | magician | 600 | 1 Power, 1 Focus | 1.25 | earth | +100 | – | +5 | – | +25% | – | none | – |
| **Staff&nbsp;of&nbsp;Fire**&nbsp;(105) | magician | 600 | 1 Power, 1 Focus | 1.5 | fire | – | – | +6 | – | – | – | none | – |
| **Staff&nbsp;of&nbsp;Ice**&nbsp;(106) | magician | 600 | 1 Power, 1 Focus | 1.25 | ice | – | – | +6 | – | – | – | none | the enemy is stunned for 1 s, at most once every 2 s |
| **Staff&nbsp;of&nbsp;Wind**&nbsp;(107) | magician | 600 | 1 Power, 1 Focus | 1.25 | wind | – | – | +5 | +33 | – | – | none | – |
