# Imitation and offline learning in Saga Online

This page shows how to learn a policy from an expert's decisions rather than from reward.
You collect data from a bot or a trained policy, clone it, check how closely the clone matches
the expert, and start reinforcement learning from the clone. The expert's data is made by
the simulation, so none of this needs recorded play from people.

It assumes you have installed pysaga and read [the tutorial](rl-quickstart.md). The tools
need PyTorch (`pip install torch`), which EPyMARL needs anyway.

1. [The tools](#1-the-tools)
2. [Clone an expert](#2-clone-an-expert)
3. [Measure the clone](#3-measure-the-clone)
4. [Normalised inputs](#4-normalised-inputs)
5. [Start IPPO from a clone](#5-start-ippo-from-a-clone)
6. [Offline RL on a fixed dataset](#6-offline-rl-on-a-fixed-dataset)
7. [What we found](#7-what-we-found)

## 1. The tools

| module | what it does |
| --- | --- |
| `pysaga.imitate` | plays an expert against an opponent and records its decisions, trains a clone (behaviour cloning, with DAgger), and measures the clone against the expert |
| `pysaga.normalise` | input standardisation with fixed statistics, shared by every trainer and carried in policy files |
| `pysaga.offline` | behaviour cloning and discrete IQL on a fixed dataset, with a command line |
| `saga_ppo_learner` | EPyMARL's PPO learner with separate actor and critic learning rates, and an actor that can be held still at first |

An **expert** is any bot name the environment accepts ([Bots](rl-reference.md#bots)), either
one of the game's scripted bots or `neural:<file>` for a trained policy. A clone is written as
an ordinary policy file, so a clone plays wherever a policy file plays, in `pysaga.balance`,
in a scripted slot, or as a bot in a real game round.

## 2. Clone an expert

`pysaga.imitate` works in a duel on the basic kit (the weapon strike alone), on an open map
with full observability unless you say otherwise. Here the expert is the `melee` bot and its opponent is the `kite` bot:

```python
from pysaga import imitate as im

env, _ = im.make_env()                       # make_env(map_name=..., observability=...) for others

# The expert's decisions: observations, actions and masks, episode by episode
data = im.run(env, "melee", "kite", episodes=1000, seed=1, record=True)["data"]

# A recurrent clone, trained by masked behaviour cloning
net, info = im.train_gru(data, steps=20000)
print("held-out accuracy", info["heldout_acc"])
im.export(net, "clone.policy", env, "full", 4, False)   # observability, decision rate, last-action input
```

- **The harness.** `im.run` plays both sides tick by tick, each deciding at its own rate (4
  ticks unless you set `pace` and `opp_pace`). `delay` makes the first player's actions land
  that many ticks after it decided, as in a networked game ([Lag](#lag)).
- **Masked cloning.** An action the mask does not allow gets no probability. A label the
  mask refuses is left out of training and counted, since a masked clone could never take it.
- **Held-out data.** A tenth of the episodes is held back, and `heldout_acc` is the share
  of their decisions the clone labels as the expert did.
- `im.train` trains a feed-forward clone instead. Use the recurrent one unless your expert
  decides from the current observation alone ([What we found](#7-what-we-found)).

**DAgger.** A clone visits states the expert never does, and nobody told it what to do
there. DAgger lets the clone play, asks the expert at every state it reaches, adds those
labels to the data and trains again:

```python
history = im.dagger(env, "melee", "kite", data, rounds=3, episodes=300, seed=7,
                    out_dir=".", name="clone", trainer=im.train_gru, steps=20000)
```

Each round writes `clone-dagger<k>.policy` and prints its held-out accuracy and its
agreement with the expert on its own states. The expert only labels the states; it does not act.

## 3. Measure the clone

Held-out accuracy says little about how a clone plays, because its errors take it to
states the data never held. `im.measure` plays the clone against the opponent with a copy
of the expert beside it, asked at every decision, and plays the expert itself on the same
seeds:

```python
m = im.measure(env, "clone-dagger3.policy", "melee", "kite", episodes=500)
im.report(m)
```

It reports:

- **on-policy agreement**: the share of the clone's own decisions on which the expert
  would have chosen the same action. 90% or more passes;
- **outcomes**: kills, deaths, damage dealt and taken and episode length, each as the
  clone's and the expert's means, with the 95% interval of the difference. A mean passes
  when that interval lies within 10% of the expert's mean (or a small floor);
- **shares** of won, lost, drawn and timed-out episodes. Each passes within 5 points of the
  expert's.

`m["confusion_top"]` lists which actions the two most often disagree on. The clone is
played greedily (its best action), so the measure has no sampling noise of its own.

### Lag

In a networked game an action lands a few ticks after the player decided. A clone trained
without delay and played with it (or the other way round) sees states its data never held:

```python
data = im.run(env, "melee", "kite", 1000, seed=1, record=True, delay=2)["data"]
m = im.measure(env, "clone.policy", "melee", "kite", episodes=500, delay=2)
```

`opp_delay` delays the opponent's actions in the same way.

To see how a policy holds up as lag grows, sweep the delay. Each row plays the same seeds,
so the rows differ by the delay alone:

```
python -m pysaga.imitate lag-sweep clone.policy --opponent kite --shadow melee \
    --delays 0,1,2,3,5 --recorded rounds/*.npz --episodes 200
```

It prints the shares of episodes won, lost, drawn and timed out, the kills and deaths, the
agreement with the shadow, and how many ticks the policy's actions took to land. Both
players are delayed unless you pass `--opponent-undelayed`.

`--recorded` adds a row that plays under the same lag as recorded real rounds. Each action's delay is
drawn from the `seen_distance` values of the datasets you name (section 6), so the jitter
of recorded play is included. An action never lands before the one decided before it.
Recorded bots are left out unless you pass `--with-bots`.

The same from Python:

```python
recorded = im.recorded_delays(["rounds/round-0000.npz"])
rows = im.lag_sweep(env, "neural:clone.policy", "kite", delays=(0, 2, 5), recorded=recorded, shadow="melee")
im.report_sweep(rows)
```

`im.run` takes `delays=` and `opp_delays=` (lists to draw from) for any other use.

## 4. Normalised inputs

An observation's numbers mostly lie between 0 and 1, and positions are divided by 2048.
So the 17 pixels of the weapon strike's reach are 0.008 of an input, too small for a
network to learn from quickly. `pysaga.normalise` standardises each input with **fixed**
statistics fitted once from data, as x' = clip((x - mean) / std, -10, 10) with a std of at
least 0.02.

- **Fixed, not running.** The environment then stays Markov, a checkpoint and its
  normaliser cannot disagree, and a clone's weights mean the same to a reinforcement
  learner fed through the same file.
- **In a policy file.** `im.export` and `pysaga.export` write the normaliser into the
  policy file, and the game applies it before the network's first layer.
- **In the environment.** `normalise=<file>` (`env_args.normalise` in EPyMARL) makes
  `SagaEnv` and `VecSagaEnv` return normalised observations, and a normalised state where
  the file holds state statistics. `describe_obs()` and the bots still see raw values.

Fitting one on expert data, and training a clone on it:

```python
from pysaga.normalise import Normaliser

norm = Normaliser.fit(data["obs"])           # Normaliser.fit(obs, state) for MAPPO's critic too
norm.save("melee.norm")
net, info = im.train_gru(data, hidden=128, normaliser=norm)
```

A clone trained without `normaliser=` fits its own on its training data. A file fitted
without the critic's state leaves the state raw, which is fine for IPPO (its critic reads
observations) but not for MAPPO; the environment says so once.

## 5. Start IPPO from a clone

Reinforcement learning from scratch on the basic kit never finds the 17-pixel strike. In
our runs every IPPO seed ended as a runner that dealt no damage. Starting from a clone
solves that. The steps:

1. **Train the clone on the normaliser** the run will use, as in [section 4](#4-normalised-inputs),
   with the shape of EPyMARL's agent, which is a GRU (`im.train_gru`) whose `hidden` is
   EPyMARL's `hidden_dim`, with no extra inputs. Collect its data on the map the run will train
   on. `im.make_env()` plays the open map, whose path `im.open_map()` returns.
2. **Make a base checkpoint** with a short run of the configuration you will train, so its
   critic and the file layout are EPyMARL's own. In the EPyMARL checkout:

   ```
   python src/main.py --config=ippo --env-config=saga with \
       runner=vec batch_size_run=64 buffer_size=64 batch_size=64 \
       use_rnn=True hidden_dim=128 obs_agent_id=False obs_last_action=False \
       learner=saga_ppo_learner save_model=True save_model_interval=1 t_max=1 \
       env_args.kit=basic env_args.reward=ladder env_args.scripted=1:melee \
       env_args.map_name=/path/to/open60x50.json env_args.normalise=/path/to/melee.norm
   ```

   It saves one checkpoint, `results/models/<run>/<step>/`. A map given as a path is
   written into the run's folder name, so the step folder sits a few levels deeper. Look for the folder holding `agent.th`.
3. **Put the clone into it:**

   ```python
   from pysaga import imitate as im
   path = im.epymarl_init("clone.policy", "<the step folder>", "bcinit", "melee.norm", lr=5e-4)   # lr is the actor's learning rate
   ```

   This copies the checkpoint, replaces the actor's weights with the clone's and gives the
   actor a fresh optimiser. It refuses a clone trained on another normaliser.
4. **Train from it** with the same command line, setting `t_max` as you want,
   `save_model_interval` back to its usual value, and `checkpoint_path=<path> load_step=0`.

`saga_ppo_learner` is EPyMARL's PPO learner with three more options, `actor_lr` and
`critic_lr` (both EPyMARL's `lr` unless set) and `actor_hold_steps`, which holds the actor
still while the new critic learns. With its defaults it is the stock learner. In our runs
the hold made no difference.

**Train against more than one opponent.** A policy started from a clone of `melee` and
trained against the melee bot alone learned to beat it, and timed out against `kite`, which
it never met ([What we found](#7-what-we-found)). `env_args.scripted=1:melee|kite` mixes them.

**EPyMARL's test curves are sampled play for IPPO and MAPPO**, whatever `test_greedy` says,
because their action selector ignores it. A clone that draws 90% of its episodes when played
greedily draws 75% when sampled. Measure a final policy with `im.measure` or `pysaga.balance`, which
play it greedily (`neural:`) or sampled (`sample:`) as you choose.

## 6. Offline RL on a fixed dataset

`pysaga.offline` trains behaviour cloning and discrete IQL (implicit Q-learning) on a
dataset, with the masks respected throughout. Its networks are feed-forward, in EPyMARL's
agent shape, and are written as policy files:

```
python -m pysaga.offline native --policy melee --opponent melee --episodes 20 --out data/melee
python -m pysaga.offline native --policy chase --opponent melee --episodes 20 --out data/chase
python -m pysaga.offline iql --data data/melee data/chase --out iql.policy
python -m pysaga.offline bc  --data data/melee data/chase --out bc.policy
python -m pysaga.offline evaluate --policy iql.policy --opponent melee --episodes 200
```

- `native` plays a bot in the learner's slot of a duel and writes its decisions, in the
  layout below. `--frame-skip` sets the decision rate.
- `bc` and `iql` train on one or more datasets. All must share a decision rate.
- `evaluate` plays a policy against a bot, drawing its actions from its probabilities
  (`sample:`), and prints its mean return and the shares of won, lost, drawn and timed-out
  episodes.

A dataset is a folder of `.npz` files in the D4RL layout that most offline-RL code reads. Each
file holds the arrays `observations`, `actions`, `masks`, `rewards`, `terminals`, `timeouts`,
`episode` and `ticks`, with one row per decision, and a JSON file beside it describes its
episodes and settings.

The game goes on changing after play is recorded, so a dataset says which version of it each
decision comes from. `dynamics` holds, for each row, the number of the game's rules the round
was played under: it is raised whenever the game starts to play differently, a new rule or a
retuned table. `fields` names every column of `observations`. A recorded round is converted
with the version of the game that converts it, so rounds of older versions come out in the
same layout as new ones. Their `dynamics` says they were played by other rules. You can keep
them, condition a model on the column, or leave them out: `offline.load(dirs, dynamics={3})`
reads only the episodes played under dynamics 3, and every transition it returns carries its
`dynamics`.

Four more arrays describe network lag, for analysing or debugging a policy trained on
recorded play:

- `seen_distance` is the lag of the input a decision is labelled with, in ticks of 50 ms.
  It counts from the state the player saw to the tick the input took effect, so it holds
  the input delay and any wait on another player. It is 2 or 3 on a quiet link and larger
  on a slow one, and -1 where the label is a no-op or the recording has no seen ticks.
- `diverged` is 1 where the player's own game had come apart from the round as recorded,
  so the player may have seen another picture than the observation.
- `elapsed_ms` is real time. It is the milliseconds on the player's own machine between its
  game reaching the previous decision's tick and this one's. For a game keeping up, it is the decision's number of ticks times 50. A larger value is a game that waited for another player or
  stood still, and a smaller one is a game catching up afterwards. It is -1 for an episode's
  first decision and where the recording has no times.
- `late_label` is 1 where the label's input was given on an earlier decision's state, for
  example the second of two orders given within one decision. That observation is newer
  than what the player acted on and may already show the input's effect, so you may want
  to drop those rows.

For example, to compare a policy's agreement with the players on laggy and quiet decisions:

```python
d = np.load("round.npz")
slow = d["seen_distance"] >= 4
print(agreement[slow].mean(), agreement[(d["seen_distance"] >= 0) & ~slow].mean())
```

A dataset played headlessly (`native`) has no network. Its `seen_distance` and `elapsed_ms`
are -1 and its two flags 0 throughout.
`native` plays a duel on the basic kit, under line-of-sight observability and the ladder
reward.

## 7. What we found

All results are on the basic kit, warrior against warrior, with the `melee` bot as the expert,
evaluated over 300 to 500 episodes with the clone played greedily. The clones were trained on hundreds
of thousands of expert decisions, with three or four rounds of DAgger.

**What made cloning work.** Each of these was found by a failure:

1. **Normalised inputs.** Without them the clone repeated strikes out of reach for ever.
   With them, on-policy agreement rose from 70% to 89%.
2. **A recurrent network.** The melee bot stops one decision before it strikes, so the
   same observation is labelled "stop" or "strike" by what it did last. Feed-forward clones
   stalled at about 70%. With a GRU and DAgger they reached 93 to 99%.
3. **DAgger.** It labels the clone's own states, which the expert never visits.

**How close the clones came:**

| expert against | on-policy agreement | outcomes |
| --- | --- | --- |
| `kite` | 96.7% | every measure equivalent |
| `melee` | 99.3% | every mean equivalent; draws 89% against the expert's 99% |
| `hold` | 93.7% | equivalent but for episode length |
| `kite`, on Mazeholt (a maze), `los` | 60% | not equivalent: wins 29% against 52% |
| `kite`, on Mazeholt, `full` | 55% | not equivalent: wins 36% against 52% |

**Walls break cloning, not hidden information.** The bot walks the maze by a path field
over the whole map, and the clone sees 3 blocks of terrain round itself. Full observability
did no better than line of sight.

**Lag.** The expert plays very differently with delay (against `kite` it won 59% at no
delay, 6% at 2 ticks and 99.8% at 5), and a clone matches best at the delay it was trained
at. One trained without delay agreed 96.7% at no delay, 80% at 2 ticks and 70% at 5. Train at the delay
the policy will play with, or across a range of delays.

**IPPO from a clone** (IPPO, GRU of 128, 10 million steps, three seeds an arm, against
the melee bot, ladder reward):

| start | against `melee` | against `kite` (never trained on) |
| --- | --- | --- |
| scratch, raw inputs | no wins, 56-58% losses, no damage dealt | 100% timeouts |
| scratch, normalised | no wins, 47-76% losses, no damage dealt | about 100% timeouts |
| the clone, normalised | 99-100% wins, about 7 damage taken an episode | 98-100% timeouts |
| the clone itself | 90% draws | 21% wins, 63% losses |
| the melee bot itself | 99% draws | 58% wins |

Normalisation alone did not let IPPO learn; starting from the clone did, within about 3
million steps, by turning the clone's mutual kills into wins. RL changed about a quarter
of the clone's decisions. The price was overfitting to the one opponent it trained against.
