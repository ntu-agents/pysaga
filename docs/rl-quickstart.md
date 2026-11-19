# Quickstart for training agents in Saga Online

A step-by-step tutorial, from installing to watching a trained agent play:

1. [Install](#1-install)
2. [A first look at the environment](#2-a-first-look-at-the-environment)
3. [Set up EPyMARL](#3-set-up-epymarl)
4. [Train](#4-train)
5. [Export the policy](#5-export-the-policy)
6. [Measure it against the bots](#6-measure-it-against-the-bots)
7. [Watch it play](#7-watch-it-play)
8. [Play against a policy in the game](#8-play-against-a-policy-in-the-game)
9. [Going further](#going-further)

Every option and detail left out here is in the [reference](rl-reference.md).

## 1. Install

Training runs entirely on your computer, with no root server, game server, screen or
sound. You need **Java 21 or newer** ([Adoptium](https://adoptium.net) has installers) and
**Python 3.9 or newer**. Download the RL package,
`pysaga-<version>-py3-none-any.whl`, from the
[latest release](https://github.com/ntu-agents/pysaga/releases/latest) into a new
folder, and in a terminal there:

```
python3 -m venv venv
source venv/bin/activate              # on Windows: venv\Scripts\activate
pip install pysaga-<version>-py3-none-any.whl
python -m pysaga.demo
```

The demo plays an episode with random actions, rewinds it, and prints the build and an
episode's state hash -- the same number on every computer running that build. If it
cannot find Java, set `JAVA_HOME` to your Java 21 installation.

## 2. A first look at the environment

Save this as `first.py` and run `python first.py`:

```python
import numpy as np
from pysaga import SagaEnv

env = SagaEnv(scripted={1: "melee"})      # a duel: you are agent 0, the game's melee bot is the other side
obs, info = env.reset(seed=1)
print("agents:", env.n_agents, "observation:", len(obs[0]), "actions:", env.get_total_actions())
rng = np.random.default_rng(1)
total, steps = 0.0, 0
while True:
    avail = env.get_avail_actions()
    actions = [rng.choice(np.flatnonzero(a)) for a in avail]   # a random action among those allowed
    obs, reward, terminated, truncated, info = env.step(actions)
    total += reward[0]; steps += 1     # one reward per learner
    if terminated or truncated:
        break
print("steps:", steps, "return:", round(total, 2), "stats:", env.get_stats())
```

What it shows:

- **The default game is a duel** on the map Ravenford, a warrior (agent 0) against a
  magician (agent 1). `scripted={1: "melee"}` gives the magician to one of the game's
  own bots, so you control the warrior alone and `n_agents` is 1.
- **Each decision**, an agent gets an observation of 293 numbers (itself, the other
  characters, the ground around it) and picks one of 109 actions (move, stop, select an
  ability, use it, learn, buy, use an item). `get_avail_actions` says which are allowed
  now.
- **An episode** is a round of 300 seconds of game time, 1500 decisions. It ends sooner
  when a side's score reaches 3; a kill scores the level of the character killed, 1 at
  the start. At the end the side with the most score wins.
- **The abilities are dealt.** In training each character starts with five abilities
  of its type's fire element in hotbar slots 0 to 4, and learns nothing more. The
  warrior has Explosion 1, 2 and 3 (blasts round itself) and Fire Run 1 and 2 (a run in
  flames that burns whoever it passes), and the magician Fireball 1, 2 and 3 (shots) and
  Fire 1 and 2 (fire falling on a target). An agent selects a slot and uses it. This is
  `env_args.kit=dealt`, the default. With `env_args.kit=basic` a character has its
  weapon strike alone, as when it enters a round in the game; with
  `env_args.progression=True` it starts with the strike and learns its own abilities
  with its points.

## 3. Set up EPyMARL

EPyMARL is a framework of multi-agent RL algorithms (IPPO, MAPPO, QMIX and others). In
the same folder, with the virtualenv still active:

```
git clone https://github.com/uoe-agents/epymarl.git
pip install torch sacred PyYAML gymnasium "setuptools<81"
python -m pysaga.epymarl epymarl
cd epymarl
python -m pysaga.epymarl.check_vec_runner .
```

`python -m pysaga.epymarl epymarl` registers Saga Online in that checkout, as the
environment `saga` and a runner, `vec`, that steps many worlds in one process. It also
writes `src/config/envs/saga.yaml`, the environment's settings, with a comment on every
option. The last line checks the runner, and ends with `ALL PASS`. Run the registration
again after upgrading the RL package.

## 4. Train

Still in `epymarl`:

```
python src/main.py --config=ippo --env-config=saga with \
    runner=vec batch_size_run=64 buffer_size=64 batch_size=64 \
    env_args.scripted=1:kite t_max=1000000 \
    save_model=True save_model_interval=250000
```

- `--config=ippo` picks the algorithm (`src/config/algs/`), and `--env-config=saga` the
  environment's settings file.
- Everything after `with` overrides a setting. `runner=vec batch_size_run=64
  buffer_size=64 batch_size=64` runs 64 worlds at once, much faster than EPyMARL's
  default runner.
- `env_args.scripted=1:kite` gives slot 1, the magician, to the `kite` bot, which keeps
  its distance and shoots. Your warrior has to learn to close in.
- `t_max=1000000` trains for a million steps. `save_model=True` saves the network every
  250,000 steps; EPyMARL saves nothing unless asked.

Every few seconds the log prints the latest evaluation. `test_win_team1_mean` is your
warrior's win rate, `test_return_mean` its return. On our test laptop the run took
about 75 seconds, and the win rate went:

| steps | 72,000 | 181,000 | 298,000 | 415,000 |
| --- | --- | --- | --- | --- |
| win rate | 66% | 87% | 92% | 100% |

Everything a run writes is under `results/`, its settings and figures in
`results/sacred/` and its networks in `results/models/<run>/<step>/`. Add
`use_tensorboard=True` to follow a run in TensorBoard.

## 5. Export the policy

The trained network is saved for PyTorch. Export it as a policy file, which the game
runs in Java:

```
ls results/models
python -m pysaga.export "results/models/<run>" -o ../warrior.policy --check
```

Put the folder name `ls` printed in place of `<run>`, in quotes, since it contains a space.
`--check` runs the exported policy and the PyTorch network side by side, and ends with
`PASS` when they agree.

## 6. Measure it against the bots

```
cd ..
python -m pysaga.balance --episodes 200 --p1 sample:warrior.policy --p2 kite
python -m pysaga.balance --episodes 200 --p1 sample:warrior.policy --p2 melee
```

Each line plays 200 seeded episodes, your policy against a bot, in a second or two, and
prints the win rates. `sample:` draws each action as training did; `neural:` takes the
best one. Ours won all 200 episodes against `kite`, and all 200 against `melee`, a bot
it never met in training.

The bots are `melee`, `hold` (stands still), `chase`, `flee`, `kite`, `capture`, `defend`
and `flag`.
A trained policy is a bot too, so `--p2 sample:other.policy` plays two policies against
each other.

## 7. Watch it play

Record a few episodes with EPyMARL's evaluation, from the `epymarl` folder:

```
cd epymarl
python src/main.py --config=ippo --env-config=saga with \
    checkpoint_path="results/models/<run>" evaluate=True save_replay=True \
    test_nepisode=8 runner=vec batch_size_run=8 buffer_size=8 batch_size=8 \
    env_args.scripted=1:kite
python -m pysaga.replay saga_replay.json -o replays.html
```

The evaluation writes `saga_replay.json`, with each episode's seed and actions, which
replay it exactly. `python -m pysaga.replay` checks every episode against the end state
recorded, and writes `replays.html`. Open it in a browser to step through each episode, with the map, the characters, their health
and their actions. The map is drawn plainly, with every cell coloured by whether it can be
walked on and seen through, which is what an agent perceives of the terrain. The package carries none of the game's pictures.

The same file plays in the game itself, drawn as the game draws it, with the sprites and
sounds:

```
java -jar saga-client.jar -replay saga_replay.json 0
```

with `saga-client.jar` of the same version, from the game's
[downloads repository](https://github.com/svalbrecht/saga-online-client/releases) (give its path if it is in another
folder); `0` is the episode, on whatever map it played. Space pauses, and the replay box's arrows step through decisions, change the episode
(among those played on the same map) and change which player the view follows.

## 8. Play against a policy in the game

A policy plays in a real round as a bot, through a client of its own, on any game
server. It plays the way it was trained. Its client sends the policy's actions, and
every player's game carries them out with the same rules as in training. It plays in
one of two modes, which the policy file chooses:

- **Kit mode**, for a policy trained with dealt abilities (`env_args.kit=dealt`, the
  default, as in this tutorial). The bot enters the round with the same five abilities
  it trained with, so the warrior above has Explosion and Fire Run.
- **Player mode**, for a policy trained with `env_args.progression=True`. The bot starts
  as a player does, with the weapon strike and its points, and learns abilities, spends
  points and buys and uses items through its own actions. A policy trained with
  `env_args.kit=basic` plays this way too, with the strike alone.

`-botmode kit` or `-botmode player` overrides the file's choice. A game server can
refuse trained abilities (its admin types `/setbotkits off`); a bot in kit mode then
plays with the weapon strike, and its log says so. It can also refuse bots altogether
(`/setbots off`).

**From the lobby**, the simplest way:

1. Copy `warrior.policy` into the `policies` folder of your Saga Online folder,
   `~/.saga-online/policies` (`%USERPROFILE%\.saga-online\policies` on Windows).
2. Join a game server, one in the server list or one you create (see
   [Starting your own game server](https://github.com/svalbrecht/saga-online-client/blob/main/docs/playing.md#starting-your-own-game-server)).
3. In its lobby, press **Add bot**, choose the policy, and in a round with teams its
   team.

The bot plays under your account until your game ends; no key or second account is
needed.

**From a terminal**, for a bot that runs without your game, on a server you name:

1. Have a game server, and note its name.
2. Make your account's bot key, once:

   ```
   java -jar saga-client.jar -makebotkey
   ```

   It asks your account's name and password and saves a key file, `bot.key`, in your
   Saga Online folder, readable by you alone. Your bots log in with it, with no second
   account and no password on the command line. Making the key again stops the old one
   working.
3. Join the server yourself, then start the bot in a terminal:

   ```
   java -jar saga-client.jar -headless -botkey -server "<server name>" \
       -team 1 -spawn 1 -policy sample:warrior.policy
   ```

`-headless` runs the bot with no window, so it plays the round and draws nothing. Leave it
out to watch the bot's view in a window. The two numbers are the bot's team and spawn
point; the policy file decides its type. The bot joins as `<your name>#1` and starts
playing once another player is in place. Run the command again for a second bot (`#2`),
up to eight at once. Add `-password "<password>"` for a server that asks for one.

A bot without a window follows its server from round to round. When the server lets it
go, it ends with an exit code saying why. 0 means the server stopped, 1 that it was
kicked, banned or refused, and 2 that the connection was lost.

On the server the bot counts as yours. An admin's `/kick <your name>#1` removes that bot,
and banning the bot bans your account. A bot never runs an admin command, even when you
are an admin, and sends no automatic problem reports.

Three things differ from training. A policy trained in a duel sees one other character, so in a round of four it sees and
aims at the first other player only. Its memory starts
afresh at each round, as at the start of a training episode, and runs on through its
deaths, as an episode does. And it decides
on what the game looked like two or three ticks (about a tenth of a second) before its
action takes effect, the time an action takes to reach every player's game, where in
training an action took effect at once.

## Going further

Change one setting at a time on the training command line, and measure again:

- **Another algorithm**: `--config=mappo`, `--config=ia2c` and EPyMARL's others are
  chosen the same way. We have tested IPPO.
- **Another mode**: `env_args.mode=tdm env_args.team_size=2` (Team Deathmatch, two a
  side), `env_args.mode=dom` (Domination, where teams take and hold capture points), or
  `env_args.mode=ma env_args.team_size=2` (Monster Attack, two agents on one team against
  spawned monsters). Monster Attack needs a map with monster homes, such as
  `env_args.map_name=Lastlight`, made for it, or a generated forest with
  `env_args.map_name=gen:forest`.
- **Another map**: `env_args.map_name=Greyhold`, or a new generated map every episode with
  `env_args.map_name=gen:forest env_args.map_seed=episode`.
- **Partial observability**: `env_args.observability=los`, where an agent sees only what
  is in its line of sight.
- **Another reward**: `env_args.reward=ladder`, which pays a win at the end, meant for
  `gamma=0.995`.
- **Learning from an expert**: clone a bot or a trained policy, measure how closely the
  clone plays, and start IPPO from it. See [Imitation and offline learning](imitation.md).

The [reference](rl-reference.md) lists every option and what each does.
