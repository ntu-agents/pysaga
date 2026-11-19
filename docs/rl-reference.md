# Reference for training agents in Saga Online

This page explains how Saga Online works as a reinforcement learning environment, and
lists every option it accepts. If you are new to it, start with
[the tutorial](rl-quickstart.md). Learning from an expert's decisions (behaviour cloning,
DAgger, offline RL, starting IPPO from a clone) has [a page of its own](imitation.md).

1. [The game as a POSG](#1-the-game-as-a-posg)
2. [Actions](#2-actions)
3. [Observations](#3-observations)
4. [Rewards](#4-rewards)
5. [Maps](#5-maps)
6. [Bots and monsters](#6-bots-and-monsters)
7. [Other training options](#7-other-training-options)
8. [Setting up and running EPyMARL](#8-setting-up-and-running-epymarl)
9. [Exporting, evaluating, watching and playing against a trained policy](#9-exporting-evaluating-watching-and-playing-against-a-trained-policy)
10. [Versions](#10-versions)

## All options at a glance

Each option is a keyword argument of `SagaEnv` and `VecSagaEnv`, and an
`env_args.<option>` entry in EPyMARL. If you misspell an option, or give a value it does
not accept, the environment raises an error that names it. It never quietly falls back
to a default and trains a different game from the one you asked for.

| option | default | explained in |
| --- | --- | --- |
| `mode`, `team_size` | `"duel"`, `2` | [Modes](#modes) |
| `kit`, `progression` | `"dealt"`, `False` | [What a character starts with](#what-a-character-starts-with) |
| `observability` | `"full"`, with a terrain patch of radius 3 | [Choosing what agents perceive](#choosing-what-agents-perceive) |
| `reward` | `"dense"` | [Rewards](#4-rewards) |
| `common_reward`, `reward_scalarisation` | `False`, `"sum"` | [One reward for the team](#one-reward-for-the-team) |
| `map_name`, `map_seed`, `map_schedule` | `"Ravenford"`, `"fixed"`, none | [Maps](#5-maps) |
| `scripted` | none | [Bots](#bots) |
| `monsters` | `0` | [Monsters](#monsters) |
| `frame_skip` | `4` | [Time](#time) |
| `time_limit`, `score_limit`, `cutoff`, `lives` | `300`, the mode's own, none, `5` | [How an episode ends](#how-an-episode-ends) |
| `normalise` | none | [Normalised inputs](#normalised-inputs) |
| `seed` | none | [Seeds](#seeds) |
| `root` | none | [Where the game's data is](#where-the-games-data-is) |
| `n_envs`, `parallel`, `auto_reset` (`VecSagaEnv` only) | required, `True`, `False` | [Many worlds in one call](#many-worlds-in-one-call) |

## 1. The game as a POSG

Saga Online is modelled as a partially observable stochastic game (POSG):

| element | in Saga Online |
| --- | --- |
| agents *N* | the **learners**, the characters your algorithm controls (every character of the scenario that is not played by a bot) |
| state *s* | the whole simulation (`GameState`), with every character, every ability being cast, the capture points, the scores, the clock and the random number stream |
| actions *A<sub>i</sub>* | one discrete action per learner per decision ([section 2](#2-actions)), with a mask saying which actions are currently legal |
| transition *T(s, a)* | the simulation run forward by one decision |
| observations *O<sub>i</sub>(s)* | one vector per learner, chosen by the `observability` option ([section 3](#3-observations)) |
| rewards *R<sub>i</sub>(s, a, s')* | one number per learner, chosen by the `reward` option ([section 4](#4-rewards)) |

**The transition is deterministic once you know the state.** Everything random in the
game, such as the coins a kill pays or where a character spawns, is drawn from a random
number stream that is itself part of the state. So the same build, seed and actions
produce the same episode, bit for bit, on every machine. The next state depends only on
the current state and the actions, never on a clock or on thread timing. That is why a
saved state, once restored, continues exactly as the original would have.

**The `observability` option changes what agents observe, and nothing else.** The
transition *T* is identical in every mode. With `"full"`, every agent observes the whole
relevant state, so the game is a fully observable stochastic (Markov) game. With any
other mode it is a POSG. Because the game itself never changes, results under different
observability settings can be compared directly, since the agents play the same game and only
see different amounts of it.

**Bots and monsters are part of the environment.** A character played by a bot (see the
`scripted` option) or by the game itself (a monster) is not an agent. From the learners'
point of view its behaviour is simply part of the transition *T*. Only the remaining
characters are learners.

**The reward does not affect the game.** Nothing in the simulation reads the reward, so
changing the reward function changes what an outcome is worth to the agents, never what
happens.

### Time

| unit | length |
| --- | --- |
| tick (one step of the simulation) | 50 ms |
| decision (one call to `step()`) | `frame_skip` ticks, 4 by default = 200 ms |
| episode | 300 s of game time by default (`time_limit`) = 6000 ticks (1500 decisions at 4 ticks, 3000 at 2) |
| respawn after a death | 6 s for a player character; for monsters it depends on the kind ([section 6](#monsters)) |

An agent's action is applied on the first tick of the decision. Movement is "latched". A
move order keeps the character walking through the decision's remaining ticks and on
through later decisions, until the agent gives another move or a stop.

The tick length and the episode's length in game time are fixed. You choose the decision length.
With `frame_skip=2` an agent decides every 100 ms, and an episode then holds 3000 decisions. The
reward's time cost is per tick of play, so it costs the same per second at any rate. The
built-in bots are tuned for 4. A trained policy decides at the rate it was trained at, also in a bot's slot. One trained at 2 ticks, in an environment of 4, decides twice per step, and
the terminal shows a warning naming the slot and its rate. A discount factor looks half
as far in game time at 2 ticks as at 4.

### Modes

`mode` chooses the scenario. `team_size` sets the number of players on each side in the
two team modes.

| `mode` | sides | characters | character types | the score, and its default limit |
| --- | --- | --- | --- | --- |
| `"duel"` (or `"dm"`) | every character is its own side | 2, in slots 0 and 1 | slot 0 is a warrior, slot 1 a magician | a character's score, 3 |
| `"tdm"` (or `"team_deathmatch"`) | teams 1 and 2 | 2 x `team_size`; slot *i* plays for team 1 + (*i* mod 2) | team 1 are warriors, team 2 magicians | the team's players' scores, 10 |
| `"dom"` (or `"domination"`) | teams 1 and 2 | as in `"tdm"` | as in `"tdm"` | the team's points, 30 |
| `"ma"` (or `"monster_attack"`) | team 1, against the monsters | `team_size`, all on team 1 | warriors and magicians by turns | monsters the team killed, 30 |
| `"ctf"` (or `"capture_the_flag"`) | teams 1 and 2 | as in `"tdm"` | as in `"tdm"` | the flags the team carried home, 3 |

**A score** in a duel and in `"tdm"` is the sum of the levels of the players a character killed, each taken at its death. A kill of
a level 4 player scores 4. A death nobody caused (a
bounce tile, the Elixir of Death) scores nothing. Kills are counted apart from it.

Every character occupies a numbered **slot** in the world. Slots matter for naming bots
([section 6](#bots)) and for the order in which characters appear in observations.

- **Where characters start.** In a duel, the two characters spawn at random walkable
  places 40 to 140 px apart. That is close enough for a random policy to land a first hit
  soon, which makes the damage reward discoverable. In the team modes, each team starts on
  the spawn points the map gives that team.
- **Domination.** A team captures a point when exactly one team has a living character
  within 30 px of it for 5 seconds without a break. If both teams stand on it, the count
  stops. Each point a team holds earns it 1 point per second.
- **Capture the flag.** Each team's flag stands at its base, a `flag` point of the map (the
  map needs one for each team; the shipped maps and every generated one have them). A
  player takes another team's flag by walking within 16 px of it, and scores 1 for its team
  by carrying it within 16 px of its own base while its own flag stands there; the scored
  flag goes home 5 seconds later. A carrier that dies, leaves, changes team or turns
  invisible drops the flag where it stands; a player of the flag's team who reaches it
  returns it home, and untouched it goes home after 15 seconds. A player carries one flag at a time. When two players could take a
  flag, the nearer one takes it, and a player returning a flag goes before one taking it. Every
  agent sees whether it carries a flag, whether each other character does (`carrying`,
  status), and each team's flag in four places of its own block (`flag1:` to `flag4:`). These say where the flag is (gated
  by position, tested where the flag is), its state (home, carried, dropped, away) and
  whether it is the agent's team's flag. The critic's state holds every
  flag's state and place.
- **Monster Attack.** All agents play on one team against monsters the game spawns. It spawns one every 6 seconds while fewer
  than 4 are up. Over the round this rises in a straight line, to one every 2 seconds and 12
  up at the round's end (at most the size of the pool). Each monster spawns at one of the map's
  monster homes (the map must have at least one), its kind is drawn among the seven, and one in
  ten is a **Mega Monster** with 3 x the health, 2 x the strength and 4 x the reward of its kind. A monster
  picks a living player to hunt -- a player already hunted by *a* monsters weighs
  1 / (1 + *a*)<sup>2</sup>, so the least hunted are the likeliest -- and keeps it until one
  of the two dies; then it picks again. Its slot is freed 2 seconds after it dies, for
  the next spawn. The pool's 8 slots come after the agents' slots (`monsters=n` sets another size). Each
  slot is a block of the observation, all zeros while it is empty. Every monster killed scores
  a point for the team. The team may die `lives` times for each player present (5 by default).
  The death that uses up that budget ends the round as **overrun**, which means the team lost.

### How an episode ends

An episode is a round of the game, and the round runs on its clock. You choose its end:

| option | meaning | default |
| --- | --- | --- |
| `time_limit` | seconds of game time the round lasts. At its end the mode names the winner and the episode is **terminated** | `300` |
| `score_limit` | the round ends sooner, **terminated**, when a side's score reaches it. `None` is the mode's own (table above), `0` none | the mode's |
| `cutoff` | seconds after which an episode is cut off with no winner, **truncated**; EPyMARL's `info["episode_limit"]` is then True | none |
| `lives` | Monster Attack: deaths a player before the team is overrun | `5` |

These are seconds, not decisions, so `frame_skip` does not change what they mean. A length that
is not a whole number of decisions is refused, and so is an episode with neither a time limit
nor a cutoff. **The winner** in a duel is the character with the most score, then the most
kills, then the fewest deaths. In `"tdm"` the same rules apply to the team totals. In
domination the team with the most points wins, in capture the flag the team with the most
flags carried home, and in Monster Attack the team wins unless it was overrun. Sides still equal are a **draw** -- common in a
duel, because two characters can kill each other in the same tick, and in a round where
nobody scored.
- **A death does not end the episode.** The character comes back 6 seconds later at its
  spawn point with full health. It keeps its learned abilities and its points.

### What EPyMARL sees

`SagaEnv` implements EPyMARL's `MultiAgentEnv` interface:

| method | returns |
| --- | --- |
| `reset(seed=None)` | `(observations, info)`, a list with one NumPy vector per learner and the same dictionary as `get_env_info()` |
| `step(actions)` | `(observations, rewards, terminated, truncated, info)`. `rewards` is a list with one number per learner, or a single number if `common_reward` is on. When the episode ends, `info` holds the episode's figures ([Episode figures](#episode-figures)) and `episode_limit`, which is True when the episode was truncated rather than terminated |
| `get_obs()`, `get_obs_agent(i)`, `get_obs_size()` | the observations ([section 3](#3-observations)) |
| `get_state()`, `get_state_size()` | the state for a centralised critic ([The state for a centralised critic](#the-state-for-a-centralised-critic)) |
| `get_avail_actions()`, `get_avail_agent_actions(i)`, `get_total_actions()` | the action masks and the number of actions ([section 2](#2-actions)) |
| `get_env_info()` | `state_shape`, `obs_shape`, `n_actions`, `n_agents`, `episode_limit` (the most decisions an episode lasts: 1500 by default) |
| `get_stats()` | the episode's figures, including one list entry per learner |

Learners are numbered in slot order, skipping the slots played by bots. For example, with
a bot in slot 0 of a duel, learner 0 is the character in slot 1. `env.slot_of(i)` returns
the slot of learner *i*. All learners have the same observation size and the same number
of actions.

## 2. Actions

Each learner picks one integer per decision from a single flat list of actions, laid out
the way SMAC lays out its own. The **mask** (`get_avail_actions()`) says which actions
are legal right now, 1 for legal and 0 for not. An agent must pick a legal action.

The list has the same layout in every scenario. Only the block of "use on a target"
actions grows with the number of characters, so the number of actions is

> **108 + (C - 1)**, where *C* is the number of characters in the world (learners, bots and monsters together)

That is 109 actions in a duel, 111 in a 2v2 and 115 in a 4v4. Blocks a scenario does not
use stay in the list and are simply masked. So a network trained with one setting, say
with progression off, has the right number of outputs for another setting, say with
progression on.

In the table, *t* = C - 1 is the number of possible targets:

| index | action | legal when |
| --- | --- | --- |
| 0 | **no-op**, which changes nothing (a latched move continues) | always. It is the only legal action while the character is dead, stunned or thrown |
| 1-8 | **move** N, NE, E, SE, S, SW, W or NW. The character keeps walking that way until it gets another move or a stop | alive and not stunned |
| 9 | **stop** walking | alive and not stunned |
| 10-18 | **select** hotbar slot 0-8 as the ability to use | the slot holds an ability |
| 19 | **use** the selected ability without a target (the basic strike, an area attack or a buff) | the ability needs no target, the cooldown is over, and its other conditions are met (alive, not stunned, high enough stats) |
| 20 to 19 + *t* | **use** the selected ability **on target** *k* | the ability needs a target, and target *k* is alive, an enemy (or an ally, for an ability aimed at allies), within range and line of sight, and **perceived** by this learner |
| 20 + *t* to 39 + *t* | **learn** the next ability of row *r* (0-19), which also puts it in the first free hotbar slot | `progression` is on, and the character can learn the row's next ability ([Progression](#progression)) |
| 40 + *t* to 59 + *t* | **place** the most advanced ability learned in row *r* into the first free hotbar slot | `progression` is on, and the character has learned at least one ability of the row |
| 60 + *t* to 68 + *t* | **clear** hotbar slot 0-8 | `progression` is on, and the slot holds an ability |
| 69 + *t* to 71 + *t* | **spend** a skill point on health, strength or intelligence | `progression` is on, and the character has an unspent skill point |
| 72 + *t* to 87 + *t* | **buy** item 0-15 ([Items](#items)) | a shop that sells the item is within 50 px with a clear line of sight, the character has enough coins, and its bag has room |
| 88 + *t* to 107 + *t* | **use** the item in bag slot 0-19 | the bag slot holds an item that can be used |

**Targets.** Target *k* is the *k*-th other character in slot order, the same character
that block *k* of the observation describes. A learner cannot target a character whose
position it does not perceive ([section 3](#3-observations)). If it could, an agent could
find hidden enemies by checking which attacks the mask allows.

**Facing.** Characters only ever face north, east, south or west, and a move turns them.
A diagonal move keeps the current facing if it is one of the diagonal's two directions.
A character facing east that moves northeast still faces east. Otherwise it turns to the
diagonal's north or south part. Facing matters, because the basic strike hits a box in
front of the character, and some abilities fire the way it faces.

**One cooldown per character.** Using any ability, the basic strike included, starts the
character's single cooldown. No ability can be used until it ends. The basic strike also
holds the attacker in place for about a quarter of a second.

### What a character starts with

| | `kit="dealt"` (default) | `kit="basic"` | `progression=True` |
| --- | --- | --- | --- |
| hotbar | warrior: Explosion 1-3 and Fire Run 1-2 (slots 0-4); magician: Fireball 1-3 and Fire 1-2 | Strike 1, the basic strike | Strike 1 |
| element | fire | neutral | neutral, until it learns an ability of an element |
| can learn abilities | no (the learning actions are masked) | no | yes |

In all three cases a character starts with 100 health, 10 strength and 10 intelligence
(its starting weapon adds 2 to its type's own stat), 1 ability point, 2 skill points,
10 coins, a Small Health Potion and its type's first weapon.

**Strength and intelligence** are shown in the game as **Power** and **Focus**; the
observation and the tables keep the names strength and intelligence. They matter the same
way for both types: a weapon strike (the basic strike, a monster's bite, a shield's
counter-damage) scales with the attacker's strength, and every other damaging ability
with the caster's intelligence.

**`kit="basic"` matches the game.** It is exactly what a character has when it enters a
round in the real game. So if you want a policy to play in the game as a bot that starts
like a player ("player mode", [section 9](#9-exporting-evaluating-watching-and-playing-against-a-trained-policy)), train it with
`kit="basic"` or with `progression=True`. You cannot set both, since `progression=True` already
starts from the basic strike, and adds learning on top.

### Progression

With `progression=True`, an agent builds its own character during the episode:

- **The ability tree** has 20 rows, four for each of five elements (neutral, earth,
  fire, ice, wind, numbered 0 to 4). Row *r* of element *e* has the number 4*e* + *r*.
  Warriors and magicians have different trees ([The ability trees](#the-ability-trees)).
  Each row is learned in order, so the learn action for a row always offers that row's
  next unlearned ability.
- **One element per episode.** A character starts out neutral and may learn from any row.
  The first time it learns an ability of an element (anything but neutral), it commits to
  that element, and the rows of the other three elements stay closed until the episode ends.
- **Cost.** Every ability costs 1 ability point. Every ability after the first in a row
  also requires minimums of strength and intelligence. An ability of the character's own
  type asks its type's stat (strength for a warrior, intelligence for a magician): 14 for
  the second ability of a row, 16 for the third and 18 for the fourth; from the third on it
  also asks the other stat, 12 and then 14. An ability both types share (the Strikes, the
  Surges and the element auras) asks both stats alike, 12 and then 14. What a buff, a
  channel or a potion lends does not count toward a requirement; skill points and the
  weapon in hand do. The requirement only applies when learning, so an ability already
  learned stays usable. Each ability's requirement is in the
  [abilities and weapons reference](abilities.md).
- **Points and levels.** Each new level gives 1 ability point and 2 skill points.
  Spending a skill point gives +10 maximum health (and +10 health), +1 strength, or +1
  intelligence. Characters gain experience by dealing damage. Level 2 takes 10
  experience, and each further level takes 1.5 times as much as the one before.

### The ability trees

Each type's rows, with each row's abilities in the order they are learned. Every
ability's numbers (damage, range, area, duration, cooldown, requirement) and every
weapon's are in the [abilities and weapons reference](abilities.md).

| row | element | warrior | magician |
| --- | --- | --- | --- |
| 0 | neutral | Strike 1-3 | Strike 1-3 |
| 1 | neutral | Life Surge 1-2, Life Spring 1-2 | Life Surge 1-2, Life Drain 1-2 |
| 2 | neutral | Power Surge 1-2, Power Spring 1-2 | Power Surge 1-2, Power Drain 1-2 |
| 3 | neutral | Focus Surge 1-2, Focus Spring 1-2 | Focus Surge 1-2, Focus Drain 1-2 |
| 4 | earth | Earth Aura 1-3 | Earth Aura 1-3 |
| 5 | earth | Earthquake 1-3 | Earth Thrust 1-3 |
| 6 | earth | Healing Spring 1-3 | Boulder 1-3 |
| 7 | earth | Passage 1-3 | Healing 1-2 |
| 8 | fire | Fire Aura 1-3 | Fire Aura 1-3 |
| 9 | fire | Fire Run 1-2 | Fire 1-3 |
| 10 | fire | Explosion 1-3 | Fireball 1-3 |
| 11 | fire | Fire Shield 1-3 | Chain Explosion 1-2 |
| 12 | ice | Ice Aura 1-3 | Ice Aura 1-3 |
| 13 | ice | Ice Shield 1-3 | Reflection 1-2 |
| 14 | ice | Ice Spike 1-3 | Ice Ball 1-3 |
| 15 | ice | Frost Nova 1-3 | Frost 1-2 |
| 16 | wind | Wind Aura 1-3 | Wind Aura 1-3 |
| 17 | wind | Wind Run 1-2 | Lightning 1-2, Ball Lightning |
| 18 | wind | Shockwave 1-3 | Wind Blast 1-3 |
| 19 | wind | Wind Draft 1-2 | Wind Pressure 1-2 |

**Elements.** The elements beat each other in a circle. Earth beats fire, fire beats ice,
ice beats wind, and wind beats earth. An attack deals 20% more damage to a character of
the element it beats, and 20% less to a character of the element that beats it. An
attack that has no element of its own, such as the basic strike, counts as the
attacker's element.

### Items

Agents can buy and use items in every scenario, with or without progression. Buy action
*k* buys item *k*:

| *k* | item | price in coins |
| --- | --- | --- |
| 0 | Small Health Potion | 5 |
| 1 | Large Health Potion | 15 |
| 2 | Small Power Potion | 10 |
| 3 | Large Power Potion | 25 |
| 4 | Small Focus Potion | 10 |
| 5 | Large Focus Potion | 25 |
| 6 | Book of Life: raises maximum health | 60 |
| 7 | Book of Power: raises maximum strength | 60 |
| 8 | Book of Focus: raises maximum intelligence | 60 |
| 9 | Book of Experience | 100 |
| 10 | Elixir of Life: restores full health | 50 |
| 11 | Elixir of Haste: +50% speed for 10 s | 20 |
| 12 | Devil's Elixir: +50% health, strength and speed and -50% intelligence for 10 s, then the character loses a quarter of its health | 50 |
| 13 | Elixir of Death: kills the character that drinks it, and takes one of its kills away | 10 |
| 14 | Scroll of Teleportation: not available in the environment, always masked | 20 |
| 15 | no item: always masked | |

To buy, a character must stand within 50 px of a shop that sells the item, with a clear
line of sight to it. Characters earn coins by killing. A kill pays the victim's level
plus a random 0 to 10, and a monster pays its own reward ([Monsters](#monsters)). The bag has 20 slots. It also holds the character's weapon, which
cannot be used as an item. Only one of the two timed items (11 and 12) can be active at a
time.

## 3. Observations

Each learner receives one vector per decision. It contains **facts the character could
observe**, such as positions, health, what each character is casting, and the terrain nearby. It
contains no computed predictions, no countdowns and no memory of the past. A character
the learner cannot perceive right now is shown as zeros, not as where it was last seen.
Remembering is the policy's job, for example with a recurrent network.

**The vector has the same length in every observability mode.** Information a learner
does not perceive is set to zero and flagged as unknown, never removed. So the network's
input size does not depend on the mode, and a policy cannot tell which mode it is in from
the length of its input. With *C* characters and a terrain radius *r*, the length is

> **120 + 74 x (C - 1) + 2 x (2r + 1)<sup>2</sup> + 1**

where the last number is the clock. That is 293 in a duel (with the default radius 3), 441 in
a 2v2 and 737 in a 4v4.

`env.describe_obs(i)` returns learner *i*'s observation as a dictionary
`{field name: value}`, which is handy for checking what each number means.

### The layout

The observation is the learner's own block, then one block for each other character in
slot order (bots and monsters included), then the terrain patch.

**The learner's own block** has 120 numbers and is always filled in:

| fields | meaning and scale |
| --- | --- |
| `alive` | 1 if alive, 0 if dead |
| `health`, `strength`, `intelligence` | the current value divided by its maximum |
| `x`, `y` | the position in pixels, divided by 2048. The same scale on every map (2048 px is the width of the largest map the game plays) |
| `facing` | the facing direction divided by 8 (north 0, east 0.25, south 0.5, west 0.75) |
| `moving` | 1 while the character is walking |
| `cooldown` | milliseconds of cooldown left, divided by 5000, at most 1 |
| `locked` | 1 while the character is stunned or held in place |
| `level` | the level divided by 20, at most 1 |
| `kills`, `npc-kills` | players killed divided by 5, and monsters killed divided by 5, each at most 1 |
| `score` | the character's score (the levels of the players it killed) divided by 20, at most 1 |
| `type:warrior`, `type:magician` | the character type, one-hot |
| `cat:neutral`, `cat:earth`, `cat:fire`, `cat:ice`, `cat:wind` | the element, one-hot |
| `npc` | always 0, since a learner is never a monster |
| `mega` | always 0, since a learner is never a monster |
| `resistance` | the share of incoming damage the character ignores |
| `speed` | walking speed in px/s, divided by 200 |
| `knockback` | pixels the character still has to fly after being knocked back, divided by 200 |
| `visible` | 0 while the character is invisible (during a teleport, such as Passage), else 1 |
| `reflect` | 1 while the character reflects projectiles |
| `retal:dmg`, `retal:lock` | 1 while a shield hits back at attackers, with damage or with a freeze respectively |
| `sel:0` ... `sel:8` | the selected hotbar slot, one-hot |
| `spell:*` (32 numbers) | which of the character's abilities are active ([Casts](#casts)) |
| `cast0:*`, `cast1:*` (8 numbers each) | the character's moving casts ([Casts](#casts)) |
| `carrying` | capture the flag: 1 while the learner carries a flag |
| `flag1:*` ... `flag4:*` (8 numbers each) | capture the flag: each team's flag -- `known:position`, `dx`, `dy` (where it is, from the learner, in pixels divided by 2048, filled in when the learner perceives that place), `home`, `carried`, `dropped`, `away` (its state, one-hot) and `mine` (1 for the learner's own team's). All zeros in other modes and for a team the map gives no flag |

**Each other character's block** has 74 numbers. They are grouped by **reveal group**.
A group's numbers are filled in only if the learner currently perceives that group of
facts about the character ([Choosing what agents perceive](#choosing-what-agents-perceive));
otherwise they are zeros.

| reveal group | fields | meaning |
| --- | --- | --- |
| (always present) | `known:existence`, `known:position`, `known:health`, `known:identity`, `known:status` | 1 for each group the learner perceives, 0 for each it does not |
| position | `dx`, `dy`, `line-of-sight` | the other character's position minus the learner's, in pixels divided by 2048; and 1 if no wall stands between them |
| health | `health`, `alive` | as in the own block |
| identity | `same-team`, `type:*` (2), `cat:*` (5), `npc`, `mega` | 1 if it is on the learner's team; its type and element; 1 if it is a monster; 1 if it is a Mega Monster (Monster Attack) |
| status | `reflect`, `retal:dmg`, `retal:lock`, `locked`, `facing`, `carrying`, `spell:*` (32) | as in the own block; `carrying` 1 while it carries a flag |
| decided at the cast's own position | `cast0:*`, `cast1:*` (8 each) | the character's moving casts ([Casts](#casts)) |

A block for an empty slot is all zeros.

**The terrain patch** has 2 x (2r + 1)<sup>2</sup> numbers. It covers a square of
(2r + 1) x (2r + 1) map cells (a cell is 16 x 16 px) centred on the learner's own cell.
First come the walk flags of these cells, then their sight flags, each row by row from
the top left. A walk flag is 1 where a character can walk; a sight flag is 1 where a
character can see through. Cells beyond the edge of the map are 0. The fields are named
`self:terrain:walk:dx,dy` and `self:terrain:sight:dx,dy`. The patch is the same in every
observability mode.

**The clock** is the observation's last number, `self:clock`. It is the share of the round left,
1 at its start and 0 at its end (1 throughout a round with no time limit), which a player reads
off the game information window. `"+noclock"` after a mode leaves it out
(`"los+noclock"`, `"los+terrain:2+noclock"`), and `"clock": False` in a dictionary.

### Casts

- **Spell flags.** For each character, 32 flags say which of its abilities are active at
  this moment. They follow the layout of its ability tree, with the four neutral rows
  (`spell:n<row>.<tier>`) and the four rows of the character's own element
  (`spell:e<row>.<tier>`), four tiers each. A flag is 1 while the ability in that place,
  cast by that character, is running.
- **Moving casts.** Two places per character describe casts that move through the world,
  which are a projectile, a falling boulder (shown where it will land) or a sweep (shown where its
  front has reached). Each place holds `known:position`, `known:kind`, `dx`, `dy` (relative
  to the learner, in pixels divided by 2048), `vx`, `vy` (velocity in px/s divided by 200),
  `row` ((row + 1) / 8) and `tier` ((tier + 1) / 4). If a character has more than two
  moving casts at once, only two are shown.
- **A cast is perceived where the cast is**, not where its caster stands. A learner can
  see a projectile while its caster is out of sight, and the other way round.
  `known:position` says whether `dx` and `dy` are filled in, and `known:kind` whether the
  rest is.

### Choosing what agents perceive

The `observability` option is a mode's name (with arguments where it takes them), or a
dictionary ([Writing a mode out](#writing-a-mode-out)).

| mode | what a learner perceives about another character |
| --- | --- |
| `"full"` (or `"fo"`) | everything, wherever it is, even when it is invisible |
| `"los"` | everything, if no wall blocks the line between them, at any distance. An invisible character is not seen. This is the rule a human player plays by |
| `"sight:<px>"` | as `"los"`, but only within *px* pixels |
| `"cone:<px>:<degrees>"` | as `"sight"`, but only within a forward cone that many degrees wide. Facing then matters for seeing as well as for hitting |
| `"squad:<px>"` | as `"sight:<px>"`, plus team mates always, wherever they are |
| `"hearing:<sight px>:<hear px>"` | as `"sight"` up to the first distance; beyond it, up to the second distance, only that the character exists and where it is, even through walls |
| `"radar:<px>"` | as `"sight:<px>"`; beyond that, only that the character exists, but not where. Such a character cannot be targeted |

`pysaga.observability_modes()` returns this list.

**The terrain patch** is included in every mode with radius 3, unless you change it.
`"los+terrain:5"` uses radius 5, and `"los+terrain:0"` leaves the patch out. The radius
can be 0 to 16. In a dictionary, write `"terrain": r`. `"+noclock"` leaves out the clock
(the observation's last number, above), and a mode's name includes it only when the clock is off.

**Reveal groups and channels.** Each mode is made of one or more **channels**. A channel
is a condition, such as a maximum range, a clear line of sight or a cone, plus the reveal
groups it grants when the condition holds. A learner knows a group of facts about another
character if any one of the mode's channels grants it. The reveal groups are:

| group | what it reveals |
| --- | --- |
| `existence` | that the character is in the world (always granted along with any other group) |
| `position` | where it is, and whether a wall stands between it and the learner |
| `health` | its health, and whether it is alive |
| `identity` | its team, its type, its element, and whether it is a monster |
| `status` | its facing, its active effects, and what it is casting |
| `all`, `none` | every group, or no group |

To name several groups, join them with `|`, as in `"existence|position"`.

The action mask uses the same rule, so a learner can only target a character whose position
it perceives.

#### Writing a mode out

Instead of a name, `observability` can be a dictionary in one of three forms (a named mode
with its arguments, a single channel, or a list of channels).

```python
{"mode": "sight", "range": 300}                    # a named mode and its arguments
{"mode": "cone", "range": 300, "fov_degrees": 90}
{"mode": "hearing", "range": 300, "hearing_range": 600}

{"range": 300, "line_of_sight": True}              # a single channel

{"channels": [                                     # several channels
    {"range": 300, "line_of_sight": True, "reveals": "all"},
    {"range": 800, "reveals": "existence|position"},
 ], "terrain": 2}
```

The keys of a channel:

| key | default | meaning |
| --- | --- | --- |
| `range` | 0, meaning unlimited | the maximum distance in pixels |
| `line_of_sight` | False | if True, no wall may block the line between the two characters |
| `fov_degrees` | 360 | the width of a forward cone, in degrees |
| `allies_only` | False | if True, the channel only applies to team mates, like a squad radio |
| `respect_invisibility` | True | if True, the channel does not see invisible characters |
| `reveals` | `"all"` | the reveal groups the channel grants |

A key that is not listed here is an error. Channels can only add information, never take
it away. To make other characters visible with their health hidden, give no channel the
`health` group.

**Naming your own mode.** After `pysaga.register_observability("ourmodel", spec)`, you can
write `observability="ourmodel"` anywhere a mode name is accepted. Registering a built-in
name, or a name already used by a different mode, is an error.

### The state for a centralised critic

`get_state()` returns the privileged state for a centralised critic. It holds everything
about every character, whatever the observability mode, with absolute positions. Its
length is **79 x C + 26**, which is 184 in a duel and 342 in a 2v2. For each character it holds `x`,
`y`, `health`, `strength`, `intelligence`, its team number, its type (2 numbers),
`alive`, `cooldown`, its element (5), `npc`, `mega`, `reflect`, `retal` (2), `visible`, `locked`,
`knockback`, `facing`, the selected slot (9), the 32 spell flags, and two moving casts of
seven numbers each (in use, x, y, vx, vy, row, tier). Then come the four flags of capture the flag, with six numbers each. They
hold the flag's state (home, carried, dropped, away, one-hot) and where it is (x, y, in pixels
divided by 2048), and are all zeros in other modes and for a team the map gives no flag. The last two numbers are the share of
the episode's game time that has passed and the simulation's tick divided by 100,000.

It is not the complete simulation state. It leaves out the random number stream on
purpose, because a critic that could read it would learn to predict the random draws instead of
learning the game. It also leaves out each character's bag, learned abilities and level.

## 4. Rewards

The `reward` option defines *R<sub>i</sub>(s, a, s')*, one number per learner per
decision. The environment does not shape or normalise rewards; if you want shaping,
add it in your learner.

| `reward` | each decision, a learner receives |
| --- | --- |
| `"dense"` (default) | +0.01 per point of damage dealt, -0.01 per point of damage taken, +5 per kill, -5 per death, and -0.01 per decision |
| `"sparse"` | +1 per kill, -1 per death |
| `"ladder"` | +0.25 per kill, -0.25 per death, +0.001 per point of damage dealt, -0.001 per point taken, -0.0002 per decision, and +0.0625 per monster killed. At the end of the episode, +1 to every learner on the winning side and -1 to the others. Meant to be used with a discount factor of 0.995 |
| `"zero"` | 0, for measuring the environment rather than training a policy |
| a dictionary of weights | the weighted sum of the terms below ([Weights](#weights)) |
| a Python function | whatever the function returns ([A reward of your own](#a-reward-of-your-own)) |

`"dense"` makes one kill worth as much as 500 points of damage, and pays almost as much
for ending an episode quickly as for winning it. It remains the default only so that new
results stay comparable with earlier ones. `"ladder"` makes winning the main objective.

### Weights

A dictionary such as `{"kill": 1, "death": -1, "win": 5}` defines the reward as a
weighted sum. For each term, the learner receives the weight times how much that quantity
changed during the decision. Use a negative weight for anything that should be a cost.

| term | measures, for this learner |
| --- | --- |
| `damage_dealt` | points of damage it dealt |
| `damage_taken` | points of damage it took |
| `kill` | players it killed |
| `death` | times it died |
| `npc_kill` | monsters it killed (these never count as `kill`) |
| `experience` | experience it gained |
| `level_up` | levels it gained |
| `ability_learned` | abilities it learned |
| `score` | points its team scored, which are Domination points, flags carried home in capture the flag, or monsters killed in Monster Attack (always 0 in a duel and in `"tdm"`, where `kill` pays) |
| `capture` | the flags this agent itself carried home (capture the flag); its team's point is in `score` already |
| `time` | 1 per decision, so the weight itself is added every decision; a negative weight makes a time penalty |
| `win` | only at the decision that ends the episode, +weight for every learner on the winning side, -weight for the others -- at the score limit and at the time limit alike, and -weight for every learner when Monster Attack's team is overrun. Nothing when the episode is truncated or drawn |

An unknown term is an error that lists the valid ones. A dictionary cannot be given on
an EPyMARL command line ([section 8](#8-setting-up-and-running-epymarl)), so set weights in the yaml file, or in
Python.

### One reward for the team

With `common_reward=True`, `step()` returns a single number instead of one per learner,
the learners' rewards added up (`reward_scalarisation="sum"`) or averaged (`"mean"`).
EPyMARL's centralised algorithms (QMIX, VDN, MAPPO, COMA) expect this. Its independent
ones (IQL, IA2C, IPPO) use one reward per learner. Only use a common reward when all
learners are on the same side, with the other side played by bots. If learners on
opposing sides shared one reward, their rewards would cancel out.

### A reward of your own

```python
def reward(prev, actions, next, env):
    # prev, next: the simulation state before and after the decision (GameState)
    # actions: the learners' actions in this decision
    out = []
    for i in range(env.n_agents):
        s = env.slot_of(i)                 # the state's arrays are indexed by slot, not learner
        out.append((next.dmgDealtTotal[s] - prev.dmgDealtTotal[s]) * 0.01
                   + (next.kills[s] - prev.kills[s]))
    return out

env = SagaEnv(reward=reward)
```

The function must return one number per learner. The state's arrays that are most useful
here are `health`, `maxHealth`, `alive`, `kills`, `deaths`, `npcKills`,
`dmgDealtTotal`, `dmgTakenTotal`, `experience`, `level`, `team`, `teamScore` (indexed by
team) and `posX`, `posY` (in pixels times 256). The function is not told the winner. To
reward a win, use the `win` weight in a dictionary instead, or read
`env.get_stats()["winner"]` inside your function. It is 0 while nobody has won, and the
winning team's number once a team has.

A Python reward costs 4 to 13 µs per decision. That is negligible next to training a
network, but significant if you run the environment inside a fast planning or search
loop. `VecSagaEnv` does not accept a Python reward, because it would run once per world
per step. Use a name or a dictionary of weights there; those run in Java at no cost.

## 5. Maps

`map_name` says where the map comes from, `map_seed` says how often it changes, and
`map_schedule` switches maps as training progresses.

### Where a map comes from

| `map_name` | the map |
| --- | --- |
| `"Ravenford"` (default), `"Greyhold"`, `"Frostmere"`, `"Northgate"`, `"Hearthcross"`, `"Longreach"`, `"Mazeholt"`, `"Kingshill"`, `"Riftholm"`, `"Tristwater"`, `"Lastlight"`, `"Cinderhold"`, `"Glimmerdeep"`, `"Stilthaven"` or `"Green"` | a map that comes with the game |
| a path such as `"/path/to/map.json"` | a map file in the saga-map format ([docs/maps/saga-map.md](maps/saga-map.md)) |
| `"gen:<template>[:<key>=<value>...][@<seed>]"` | a map made by the generator, for example `"gen:forest:trees=120@7"`. Without `@<seed>`, the seed is 1 |

The maps that come with the game:

| map | size in cells | style | what it contains |
| --- | --- | --- | --- |
| Ravenford | 63 x 47 | a river and its crossings | a river splits the map; a bridge and two fords are the three captures; a village with a shop on each bank |
| Greyhold | 63 x 47 | fortress ruins | walls with gates round a courtyard with fallen-in floor and an inner keep; three captures on the middle line; the camps outside |
| Frostmere | 63 x 47 | frozen islands | home islands joined by snow causeways to two outer islands; the central island and its capture are reached only by teleport pads |
| Northgate | 64 x 56 | walled town | a dense grid of houses and cobbled roads, four captures |
| Hearthcross | 60 x 50 | four yards | four houses with yards at the corners and roads to a stone plaza; for 2 to 4 teams, four captures |
| Longreach | 127 x 40 | a long canyon | a wide strip between cliffs with chasms in the floor; five captures in a row to fight over, one step at a time; bounce pads throw a player forward |
| Mazeholt | 93 x 93 | a walled maze | a labyrinth with no line of sight down its corridors; a team in each corner, every one equally far from the paved centre; five captures; for 2 to 4 teams |
| Kingshill | 80 x 60 | a siege, not mirrored | one side holds a walled fort, the other a camp across a stream; captures in the keep, on the bridge and at the mill |
| Riftholm | 51 x 41 | islands over a rift | the smallest map, five islands joined only by one-way teleport stones in a ring; a spell crosses the rift, nobody walks it; three captures |
| Tristwater | 73 x 66 | three countries | made for three teams. Three rivers meet in a lake and part the land into three equal countries, each a 120 degree turn of the others; a ford on each river and an island in the lake are the four captures |
| Lastlight | 95 x 72 | a hamlet in a dark wood | made for Monster Attack, a fenced hamlet with four gates, twelve monster homes in clearings at the forest's edge |
| Cinderhold | 63 x 47 | a volcanic waste | a lava moat round an island crossed by four bridges, a raised rock at its heart holding the main capture; each side camps on a raised rock climbed by two ladders |
| Glimmerdeep | 71 x 51 | a cavern underground | a rift down the middle that blocks walking and not sight, crossed only on three bridges, the middle one by an island with the main capture; an ice ledge on each side to watch the bridges from; boulders the only cover from sight |
| Stilthaven | 71 x 51 | a lake crossed on boardwalks | two fishing villages face each other across a lake crossed only by footbridges: three long lanes joined by crosswalks and a cross in the middle with the main capture, a capture on the north and south lanes; short docks to islets with slimes. The water blocks walking and not sight, so casters fire from lane to lane |
| Green | 61 x 51 | plain grass | two spawn points and nothing else, for tests |

A cell is 16 x 16 px, and every map but Green has shops. If you ask for more monsters than the map
has homes for, `reset()` raises an error.

### Generated maps

A generator spec is a template name followed by `<key>=<value>` settings, separated by
colons. Every setting has a default. An unknown key, or a value out of range, is an
error that lists the valid choices.

Each template's own settings, with their defaults in brackets. "Per half" counts one side
of a symmetric map; "per 1000" counts per 1000 cells of the map:

| template | its own settings |
| --- | --- |
| `arena` | `gap` (12): the fewest cells between two sides' spawn points, 4 to 400; `cover` (6): wall pieces per 1000; `rocks` (8): per 1000 |
| `field` | `fields` (2): fenced fields per half; `trees` (15): per 1000; `hedges` (6): hedgerows with gaps that part the map into paddocks, 0 to 12; `orchards` (2): blocks of oaks, in rows or loose, from one up to this many per side; `streams` (1): bridged streams between a side and the middle, 0 none, 1 on one map in two, 2 on every map; `ditches` (2) and `fences` (3): water a cell wide in hedge lines, and fences along straight stretches of road, each map gets between none and this many; `animals` (2) |
| `forest` | `trees` (90) and `oaks` (12): small and large trees per 1000; `woods` (`any`): `green`, `autumn`, `pine`, or `any` for one drawn per map; `paths` (2): path width, 1 to 4; `cliffs` (2): raised ground, small to large, a large one now and then with a smaller one on its top; each map gets between none and this many per half, 0 to 6; `cottages` (1): cottages standing alone among the trees, each map gets between none and this many per side, 0 to 4 |
| `village` | `houses` (5): per half; `trees` (12): per 1000; `fields` (2) and `ponds` (2): each map gets between none and this many per half; `rivers` (1): a river through the village or beside it in place of the ponds, on no map (0), one map in three (1) or every map (2); `animals` (2); `villagers` (3) |
| `lava` | `lava` (120): cells in lava pools per 1000; `rivers` (1): rivers of lava down each half, crossed by bridges, each map gets between none and this many, 0 to 2; `cliffs` (3): as the forest's; `rocks` (10) and `embers` (20): per 1000. A bridge crosses lava from shore to shore. Mirrored by default |
| `ice` | `chasm` (100): cells in black chasms per 1000, which block walking and not sight; `rifts` (1): winding chasms down each half, crossed by bridges, each map gets between none and this many, 0 to 2; `cliffs` (3): raised ice, from one up to this many per half; `crystals` (24) and `rocks` (4): per 1000. Mirrored by default |

Settings every template takes:

| setting | default | allowed values |
| --- | --- | --- |
| `size` | `61x51` | width x height in cells, from 20x20 to 512x512 for training. The game client only plays maps from 50x40 to 128x128 |
| `symmetry` | `mirror` for an arena, lava or ice, `rot2` for the others | `none`, `mirror`, `rot2` (turned 180 degrees) or `rot4` (turned 90 degrees, which needs a square map and 4 teams) |
| `teams` | 2 | 2 to 4 |
| `spawns` | 0 | spawn points per team, 1 to 4; 0 lets the map's size decide: 1 up to 2,500 cells, up to 2 up to 5,500, up to 3 above |
| `captures` | 1 | capture points, 0 to 8 |
| `shops` | 1 | shops per team, 0 to 2 |
| `teleports` | 0 | pairs of teleports per half, 0 to 4 |
| `bounces` | 0 | bounce tiles per half, 0 to 4 |
| `monsters` | 0 for an arena, 6 for a forest, 4 for the others | monster homes on the map, 0 to 16 |
| `name` | none | the map's name |

`animals` and `villagers` are decoration only. The game client draws them, but they do
not exist in the simulation, so agents never see or meet them. Spawn points stand where
the seed puts them, each side's at least half the map's width from every other side's. A
symmetric map is fair by construction, as each team is as far from every capture point, and from its own shops,
as every other team.

### How often the map changes

| `map_seed` | |
| --- | --- |
| `"fixed"` (default) | the same map in every episode. A generated map is made from the seed written in `map_name` |
| `"episode"` | a newly generated map in every episode, its seed derived from the episode's seed. Replaying an episode with the same seed therefore replays the same map |

`"episode"` only works with a generated map. Generated maps are never saved to disk, because the
same spec, seed and generator version always produce the identical map.

### A curriculum over maps

`map_schedule` switches maps as training progresses. Each entry gives a number of
environment steps and the map to use from that step on:

```
map_schedule="0:gen:arena|2000000:gen:forest:trees=150"
map_schedule=[(0, "gen:arena"), (2000000, "gen:forest:trees=150")]
```

Every entry is checked when the environment is created. A schedule works with
`VecSagaEnv`, which EPyMARL's `runner=vec` uses. Before each batch, the runner switches
to the latest entry whose step has been reached (`VecSagaEnv.advance(t_env)`), and logs
`Map: <source> from t_env <N>`. A single `SagaEnv` does not accept a schedule, because it
does not know how many training steps have passed.

You can also change the map between episodes yourself with
`set_map_source(map_name, map_seed)`; the change takes effect at the next `reset()`.
`map_info()` describes the current episode's map (where it came from, its seed and its
hash).

## 6. Bots and monsters

### Bots

The `scripted` option hands slots to bots, so learners face fixed opponents or play
alongside fixed team mates. The learners are the characters in the remaining slots.

| bot | how it plays |
| --- | --- |
| `melee` | walks up to the nearest enemy and uses its selected ability once the enemy is in reach |
| `hold` | stands still |
| `chase` | walks toward the nearest enemy, but never attacks |
| `flee` | runs away from the nearest enemy |
| `kite` | keeps the nearest enemy 60 to 140 px away, and fires whenever its cooldown allows |
| `kite:<min>:<max>` | the same, keeping the enemy between *min* and *max* pixels away |
| `capture` | stands on the map's first capture point |
| `defend` | stands on the map's first capture point, and attacks only enemies that come within 70 px of it |
| `guard:<slot>` | stays near the character in *slot*, walking round bounce and teleport tiles, and fights enemies that come within 80 px of that character. While that character is dead, it guards that character's spawn point |
| `flag` | capture the flag: carries a flag home when it has one, returns its own team's dropped flag, else goes for the nearest flag it can take |
| `neural:<file>` | a trained policy exported by `pysaga.export`, always taking its best action |
| `sample:<file>` | the same policy, drawing its action at random from its action probabilities, as during training. Use this to reproduce the win rates of a training log |

The game's own bots (all but the last two) read the world directly, so the
`observability` option does not limit them. A trained policy perceives the world through
the environment's observability mode, exactly like a learner. A policy file can only be
used in an environment with the same observation layout it was trained on (the same
number of characters and the same terrain radius); otherwise loading it fails with an
error naming the first field that differs. `capture` and `defend` are refused on a map
that has no capture point.

The forms `scripted` takes:

| `scripted` | gives bots |
| --- | --- |
| `"melee"` | every slot except slot 0 |
| `["melee", "kite"]` | slots 1, 2, ... in order |
| `{0: "melee"}` | the named slots. Here slot 0 is a bot and the learner is in slot 1 |
| `{1: ["melee", "kite"]}` | with `VecSagaEnv`, different bots in different worlds. World *i* gets the bot at position *i* mod 2 of the list. This mixes opponents within one batch |
| `"0:melee"`, `"0:melee,2:kite"`, `"1:melee\|kite"` | the same forms written as a string, for a command line |

At least one slot must be left for a learner. `n_agents`, the observations, masks,
rewards and statistics then cover the learners only. A learner still observes every
character, bots included, so the observation has the same length whether an opponent
is a bot or another learner. `save_state()` also saves each bot's internal memory
([Saving and rewinding](#saving-and-rewinding)).

### Monsters

`monsters=n` puts monsters on the first *n* monster homes of the map. A monster is
controlled by the game. It is an enemy of every agent. It attacks a character that comes
within its notice range, chases it within its leash range of home, bites it, and walks
back home when it loses its target. A monster that is hit while it has no target
(standing, wandering or walking home) chases whoever hit it, however far from home, until
that character dies, leaves, turns invisible or cannot be walked to. If the hitter stands
where no walk leads (across water, on an island), the monster runs straight away from it
for 2 seconds instead. A monster can be damaged and knocked back at any time, also while
walking home, and it does not regain health at home. Monsters
occupy the slots after the agents' slots, so each monster adds a block to the observation
(with its `npc` flag set to 1) and a target to the action space.

| monster (its kind in a map file) | health | bite damage | notices characters within | leash | respawns after | its killer gets |
| --- | --- | --- | --- | --- | --- | --- |
| slime | 30 | 5, every 1 s | 80 px | 160 px | 20 s | 5 experience, 5 coins |
| skeleton | 60 | 8, every 0.6 s | 128 px | 192 px | 25 s | 10 experience, 8 coins |
| pig | 100 | 12, every 0.5 s | 112 px | 160 px | 30 s | 15 experience, 12 coins |
| golem | 150 | 15, every 0.9 s | 96 px | 128 px | 40 s | 25 experience, 20 coins |
| blue-slime | 45 | 7, every 0.9 s | 80 px | 160 px | 20 s | 8 experience, 8 coins |
| red-slime | 60 | 9, every 0.8 s | 80 px | 160 px | 20 s | 11 experience, 10 coins |
| bull | 120 | 14, every 0.6 s | 112 px | 160 px | 30 s | 18 experience, 15 coins |

You choose how many monsters, not which kinds. Each home in a map file names the kind of
monster that stands there, and homes are filled in the order the map lists them, so
`monsters=3` gives the kinds of the map's first three homes. Most maps that come
with the game have homes. Ravenford has 6, and Lastlight, made for Monster Attack, has 12;
Green, Hearthcross and Riftholm have none. A generated map has as many homes as its
`monsters` setting says (`gen:forest` has 6), of kinds its template chooses. Killing a
monster counts in the `npc_kill` reward term and the `npc-kills` observation field,
never as a `kill`, and towards the score only in Monster Attack.

## 7. Other training options

### Seeds

The `seed` option sets the seed of the first episode. `reset(seed=n)` plays exactly the
episode with seed *n*. Each `reset()` without a seed plays the next seed, so a run plays seed, seed + 1,
seed + 2, and so on. In `VecSagaEnv`, episode *e* of world *i* has seed
seed + *e* x `n_envs` + *i*, so no two episodes of a run share a seed.

### Many worlds in one call

`VecSagaEnv(n_envs, ...)` holds `n_envs` worlds and steps all of them in one call into
Java. It takes all of `SagaEnv`'s options, plus:

| option | default | meaning |
| --- | --- | --- |
| `n_envs` | required | the number of worlds |
| `parallel` | True | step the worlds on parallel threads. The results are identical either way |
| `auto_reset` | False | what happens to a world whose episode has ended. False: it waits, keeping its last observation and receiving zero reward, until the whole batch is reset (one batch of whole episodes, as an episode runner wants). True: it starts its next episode within the same step, with its seed plus `n_envs` (a continuous stream of experience) |

`step(actions)` takes an array of shape `(n_envs, n_agents)` and returns arrays of
observations, of shape `(n_envs, n_agents, obs_size)`, states `(n_envs, state_size)`,
masks `(n_envs, n_agents, n_actions)`, rewards `(n_envs, n_agents)` (or `(n_envs,)` with
`common_reward`), and the terminated and truncated flags `(n_envs,)`. 64 worlds take
about 130 µs per step. `episode_info(i)`, `get_stats(i)`, `state_hash(i)`, `map_info(i)`
and `episode_seed(i)` answer for world *i*.

### Episode figures

When an episode ends, `info` (and `episode_info()`) holds only numbers, because EPyMARL
adds them up over a batch and logs their means:

- `kills`, `deaths` and `damage`: the learners' totals;
- `decisions`: the episode's length;
- `win_team<n>`: 1 if team *n* won, else 0, for each team in the episode;
- `draw`: 1 if the episode was a draw;
- `lost`: 1 if Monster Attack's team was overrun.

So `test_win_team1_mean` in EPyMARL's log is team 1's win rate. `get_stats()` also gives
`winner` (the winning team's number; 0 if the episode was truncated, -1 for a draw, -2 when
Monster Attack's team was overrun) and
one entry per learner in `kills_per_agent`, `deaths_per_agent`, `damage_per_agent`,
`team_per_agent` and `type_per_agent` (0 for a warrior, 1 for a magician).

### Saving and rewinding

`env.save_state()` saves the current episode, both the world and each bot's internal memory.
`env.load_state()` restores it exactly, as often as you like, which supports planning
and search. `env.state_hash()` returns a hash of the current state. Two states with the
same hash are identical.

### Normalised inputs

`normalise=<file>` makes the environment return each observation standardised, x' =
clip((x - mean) / std, -10, 10), with fixed statistics from a file that `pysaga.normalise` fitted on
data. The state is normalised too where the file holds state statistics. Positions are
divided by 2048, so a melee reach of 17 px is 0.008 of an input, and a network learns far
faster from standardised inputs. The statistics never change during a run, so the
environment stays Markov. A policy file exported from such a run carries them and the game
applies them, while bots and `describe_obs()` still read raw values. See
[Normalised inputs](imitation.md#4-normalised-inputs) for fitting a file.

### Where the game's data is

`root` is the folder holding the game's data (its content tables and maps). Leave it
unset. An installed pysaga then uses the copy of the data that ships inside the package,
and refuses a folder from a different version.

## 8. Setting up and running EPyMARL

```
git clone https://github.com/uoe-agents/epymarl.git
pip install torch sacred PyYAML gymnasium "setuptools<81"
python -m pysaga.epymarl epymarl            # registers Saga Online in that checkout
cd epymarl
python src/main.py --config=ippo --env-config=saga with \
    runner=vec batch_size_run=64 buffer_size=64 batch_size=64 \
    env_args.mode=tdm env_args.scripted=1:melee
```

`python -m pysaga.epymarl <checkout>` clones EPyMARL if the folder is empty, registers
the environment and its vectorised runner, and writes `src/config/envs/saga.yaml`, which
lists every option on this page with its default. Run it again after upgrading pysaga.
`--check` says whether a checkout matches the installed pysaga.
`python -m pysaga.epymarl.check_vec_runner <checkout>` checks that the vectorised runner
fills its batches exactly as single environments would.

- **`runner=vec`** steps all worlds in one process, with one call into Java per step.
  `batch_size_run` is the number of worlds. It is several times faster than EPyMARL's
  parallel runner, whose speed is limited by the training process, not by the
  simulation.
- **Options** go on the command line as `env_args.<option>=<value>`. A dictionary cannot
  be given there, because sacred turns it into separate keys the yaml file does not have, and
  refuses them. So write `scripted` in its string form, and set reward weights, an
  observability dictionary or a schedule given as a list in the yaml file.
- **`common_reward` and `reward_scalarisation`** are EPyMARL's own options, set outside
  `env_args`. EPyMARL passes them on to the environment.
- **The yaml file's training defaults** are 2,050,000 steps (`t_max`), an evaluation of
  32 episodes every 50,000 steps (`test_nepisode`, `test_interval`), and a log line every
  50,000 steps. With `reward=ladder`, set `gamma=0.995`.
- **Evaluation is sampled play for IPPO and MAPPO.** Their action selector ignores
  `test_greedy`, so the test curves draw actions from the policy's probabilities. Measure
  a final policy greedily with `neural:` ([section 9](#9-exporting-evaluating-watching-and-playing-against-a-trained-policy)).
- **`learner=saga_ppo_learner`** is EPyMARL's PPO learner with separate `actor_lr` and
  `critic_lr`, and `actor_hold_steps` to hold the actor still at first, for a run started
  from a behaviour clone ([Start IPPO from a clone](imitation.md#5-start-ippo-from-a-clone)).
  With its defaults it is the stock learner.

## 9. Exporting, evaluating, watching and playing against a trained policy

**Export** a checkpoint as a policy file, which runs in Java:

```
python -m pysaga.export results/models/<run>/<step> -o warrior.policy --check 200
```

`--check` runs the exported network in Java and in NumPy side by side, and reports any
disagreement. A policy file records the observation layout it was trained on, and
cannot be loaded into an environment laid out differently.

**Evaluate** it against the bots, or one policy against another, on seeded episodes:

```
python -m pysaga.balance --mode duel --episodes 200 --p1 sample:warrior.policy --p2 melee
```

**Watch** it play. EPyMARL's evaluation with `save_replay=True` (or calling
`SagaEnv.save_replay()` yourself) writes a replay file holding the environment's options, and
each episode's seed and actions, with the hash of the state the episode ended on. Then

```
python -m pysaga.replay saga_replay.json -o replays.html
```

writes a page to open in a browser. It shows the map and every character's position,
health and actions, decision by decision. Each episode is replayed first, and checked
against its recorded hash.

The page draws each map plainly. Every cell is coloured by the two terrain flags an agent
observes, as walked and seen through, seen through but not walked (water, a pit, a chasm, a
cliff, a fence), or neither (a wall, a house). The points are marked, with spawns in their team's colour, and capture points, shops, bounces, teleports with a dotted line to where they
land, and monster homes. The package carries none of the game's pictures, so the page
shows no tiles. The same file plays in the real game, drawn as the game draws it, with
its graphics and sound:

```
java -jar saga-client.jar -replay saga_replay.json
```

This works for an episode on any map, whether one that comes with the game, a map file of your
own (the replay file carries its text) or a generated map (rebuilt from its spec and
seed). It needs the game client of the same version as the pysaga that recorded the file.
`java -jar saga-client.jar -replay saga_replay.json 3` plays episode 3. During the
replay, Space pauses and resumes; the arrows in the replay window step through decisions,
switch between the episodes played on the same map, and change which character the view
follows.

**Play against it in a game.** A policy file can play as a bot in a real round:

- **From the lobby:** the **Add bot** button starts one of your policies from your
  policies folder (`~/.saga-online/policies`). The bot plays under your account as
  `<your name>#N`, and stops when your game ends.
- **From a command line:** start a game client with `-policy neural:<file>` or
  `-policy sample:<file>`, and with either `-botkey [file]` (the bot plays under your
  account, logged in with a key that `-makebotkey [file]` creates once; up to eight such
  bots can play at once) or `-a <user> <password> <w|m> <team> <spawn>` to log in with an
  account of its own. `-server`, `-team`, `-spawn` and `-password` (the server's password,
  if it has one) say where it plays. The tutorial's step 8 walks through it.
- **Without a window:** add `-headless`. The bot then follows its server from round to
  round, and exits with a code saying why it stopped (0 if the server stopped, 1 if it was
  kicked, banned or refused, 2 if the connection was lost).

The bot decides at the rate it was trained at (every four ticks unless trained otherwise),
on the ticks that rate divides, so every bot of one rate decides together. Every player's game applies its
actions with the same code the environment uses, whether they are moves, casts,
learning, skill points, purchases or items. How the bot starts depends on how the policy
was trained:

| | kit mode | player mode |
| --- | --- | --- |
| used for | a policy trained with `kit="dealt"` | a policy trained with `kit="basic"` or `progression=True` |
| starts with | the abilities it was dealt in training, in the same hotbar slots | the basic strike and the starting points, like a player |
| character type | the type it trained as | the type it trained as |

- `-botmode kit` or `-botmode player` overrides this choice.
- Kit mode needs a policy file exported by the current version of `pysaga.export`, which
  records how the policy was trained (the kit, its hotbar slots, the character type, the
  decision rate). A file from an older version always plays in player mode, as the type
  given on the command line.
- The game server's admin can refuse bots altogether (`/setbots off`), or refuse dealt
  abilities (`/setbotkits off`), in which case a kit-mode bot plays with the basic strike
  instead.
- The bot observes as many other characters as it trained with, the first ones in the
  round in slot order.
- Its recurrent memory is cleared at the start of each round, and runs on through its
  deaths, as in a training episode.
- In a real round, the state it decides on is two or three ticks older than the tick its
  action takes effect on. In training there was no such delay.

## 10. Versions

Each release's RL package, its game client (on the game's
[downloads repository](https://github.com/svalbrecht/saga-online-client/releases), the release of the same version) and the servers are
built from one version, named in `PUBLISHED.txt`. A replay file reproduces its recorded hash only with the version that
recorded it. A policy file trained on an older version refuses to load when the
observation layout has changed since, and names the field that differs.
