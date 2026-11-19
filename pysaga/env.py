"""EPyMARL environment for Saga Online.

Implements src/envs/multiagentenv.py from uoe-agents/epymarl as that file defines
it, including the Gymnasium-style five-tuple from step() and reset(seed, options).

Written against EPyMARL main. Older PyMARL-era forks return a three-tuple from step
and assume a scalar team reward; if your checkout is one of those, the differences
are the step signature and common_reward handling, nothing structural.

Why a native environment rather than the gymma wrapper: gymma's
get_avail_agent_actions returns all ones, and this game has a great many genuinely
unavailable actions -- abilities on cooldown, not yet learned, below their stat
minimum, or simply absent from the hotbar, plus dead and stunned agents. Expressing
those is the whole point of the mask.
"""

import numpy as np

from . import bridge


#: Accepted values for `mode`, with the aliases each one answers to.
#:
#: The modes are the game's (saga.map.Modes, read through the JVM by _scenario):
#: a mode's short name (dm, tdm, dom, ma, ...) or its long one, with an underscore
#: where it reads better (team_deathmatch, monster_attack), and "duel" for dm.
#: No second list is kept here, so the names accepted cannot drift from the game's.
MODES = ("duel", "a mode's short or long name: saga.map.Modes")


class MultiAgentEnv(object):
    """Minimal stand-in so pysaga imports without EPyMARL on the path."""
    pass


try:                                     # prefer the real base class when present
    from envs.multiagentenv import MultiAgentEnv          # noqa: F811
except Exception:                                          # pragma: no cover
    pass


# The map an environment plays when none is named: one shipped map, the same as Java's
# saga.sim.rl.MapSource.DEFAULT_MAP (the conformance holds the two equal).
DEFAULT_MAP = "Ravenford"


class SagaEnv(MultiAgentEnv):

    def __init__(self, map_name=DEFAULT_MAP, seed=None, root=None,
                 common_reward=False, reward_scalarisation="sum",
                 observability="full", progression=False, reward="dense",
                 mode="duel", team_size=2, scripted=None, kit="dealt", map_seed="fixed",
                 map_schedule=None, monsters=0, frame_skip=4, normalise=None,
                 time_limit=300, score_limit=None, cutoff=None, lives=5, **kwargs):
        """
        map_name is where the map comes from: a map of the game folder
        ("Ravenford"), a map file ("/path/to/map.json"), or the generator
        ("gen:forest:trees=120", with an optional "@seed"). map_seed says how often
        it changes: "fixed" (one map; a generated one from its own seed) or
        "episode" (a generated map for every episode, from a seed drawn from the
        episode's, so the episode's seed names its map). set_map_source changes it
        between episodes -- a curriculum.

        observability selects the observation function, and nothing else. The
        transition function is identical in every mode, so the environment is a
        stochastic game under "full" and a partially observable stochastic game
        otherwise -- the same game, observed differently.

        Accepts either a spec string or a mapping:

            "full"                          every agent sees everything
            "los"                           the game's own rule: unobstructed line
            "sight:300"                     line of sight within 300 px
            "cone:300:90"                   a 90 degree forward cone
            "squad:300"                     sight, team mates always reporting
            "hearing:300:600"               see to 300, hear position to 600
            "radar:300"                     see to 300, know something exists

            {"mode": "sight", "range": 300}
            {"channels": [
                {"range": 300, "line_of_sight": True, "reveals": "all"},
                {"range": 800, "reveals": "existence|position"},
            ]}

            {"range": 300, "line_of_sight": True}    one channel, field by field

        The observation vector is the same width in every mode: an entity that
        cannot be seen is zeroed and flagged rather than dropped, so network
        shapes do not depend on the setting and a policy cannot read the mode off
        its own input size.

        Each channel grants a set of REVEAL GROUPS -- existence, position, health,
        identity, status -- and an observer's knowledge is the union over the
        channels that admit the target. So "I can hear roughly where you are but
        not what condition you are in" is expressible, and a group that is not
        revealed is zeroed with its own known flag saying so.

        reward selects R(s, a, s'). A name or a dict of weights runs in Java and
        costs nothing; a callable runs here and costs 4-13 microseconds a decision,
        which is invisible under training and ruinous inside a Java planning loop.

            "dense"                        the default, and what every result so far
                                           was measured against
            "sparse"                       kills and deaths only
            {"kill": 1, "death": -1}       a linear combination, still in Java
            f(prev, actions, next, env)    anything at all, in Python

        A callable receives both GameState objects and returns one value per agent.
        Shaping, potentials and normalisation are deliberately absent: they belong
        to the learner, not to the definition of the game.

        It describes the present moment only. Nothing here remembers where an
        enemy went -- that is the agent's job, and it is what a recurrent policy
        is for. An observation carrying history would be a function of the
        trajectory rather than of the state.

        kit is "dealt" (each type's fire kit, the default) or "basic": the weapon
        strike alone, which is what a character has in the real client -- the kit
        a policy needs if it is to play there (neural:<file>).

        monsters fills the first n of the map's monster homes (0, the default, is
        none): characters the world drives, hostile to every agent, after the
        agents' slots. Each is another block of the observation and another action
        target; a kill of one counts in npcKills, which the "npc_kill" reward term
        weighs and "kill" does not. A map with fewer homes is refused at reset.

        scripted gives slots to the game's own bots (melee, kite, kite:MIN:MAX,
        hold, chase, flee, capture, defend), so a learner faces a fixed opponent:

            "melee"                  every slot but the first is a melee bot
            ["melee", "kite"]        slots 1, 2, ... in order
            {0: "melee"}             slot 0 is the bot; the learner is slot 1
            "0:melee"                the same as a string, for a command line:
                                     entries "slot:name" separated by commas,
                                     and "|" between names to spread over worlds

        The learners are the slots left over, and everything here -- n_agents,
        observations, masks, rewards, stats -- counts and indexes them alone. A
        learner still observes every character, bots included, so the observation
        is the same width whether an opponent is scripted or learned.
        """
        # An unrecognised keyword is REFUSED, not absorbed.
        #
        # EPyMARL hands an environment whatever sits under env_args in the yaml, so
        # this is exactly where a typo arrives -- and `**kwargs` swallowed it.
        # mode, team_size and reward were reachable here and unreachable through
        # saga_wrapper for that reason: the wrapper listed the arguments it
        # forwarded, three were missing from the list, and tdm could not be trained
        # from a config at all while every config that asked for it ran a duel.
        #
        # The named parameters above are the one enumeration; the wrapper forwards
        # rather than repeating them.
        if kwargs:
            raise TypeError(
                "unknown argument(s) %s -- accepted: %s"
                % (", ".join(sorted(repr(k) for k in kwargs)),
                   "map_name, seed, root, common_reward, reward_scalarisation, "
                   "observability, progression, reward, mode, team_size, scripted, kit, map_seed, "
                   "map_schedule, monsters, frame_skip, normalise, time_limit, score_limit, cutoff, lives"))
        if map_schedule:
            # The schedule moves on with the environment steps the RUNNER counts:
            # the vectorised runner calls VecSagaEnv.advance, and nothing tells a
            # single environment the step count. Refused rather than ignored.
            raise ValueError("map_schedule needs the vectorised environment (runner=vec), "
                             "which is told the step count; this one would play map_name throughout")

        # The inputs standardised for learning (pysaga.normalise): what get_obs and get_state
        # return, from fixed statistics in a file. describe_obs stays raw; a bot in a scripted
        # slot reads the world through its own encoder and its own file's statistics
        from .normalise import for_environment
        self.normalise = None if normalise is None else str(normalise)
        self._norm = None if normalise is None else for_environment(normalise)

        bridge.start_jvm(root)
        import jpype
        import jpype.imports                                # noqa: F401
        from saga.sim.rl import SagaEnv as JSagaEnv, Scenario

        self._jpype = jpype
        self.common_reward = common_reward
        self.reward_scalarisation = reward_scalarisation

        from saga.sim.rl import Observability

        # mode picks the scenario: "duel" is the 1v1 deathmatch every result so far
        # used; "tdm" and "dom" are team modes and spawn from the map's own points,
        # without which both sides would start mixed together.
        #
        # An unknown name THROWS rather than falling through to the duel. It used
        # to, and a typo in a yaml then trained a 1v1 for a week while every log
        # line said "tdm" -- the same failure the reward names are strict about,
        # and for the same reason: a run that looked like it measured something it
        # did not.
        scenario = _scenario(Scenario, mode, map_name, team_size, progression, kit, monsters, frame_skip,
                             time_limit, score_limit, cutoff, lives)
        self.round = _round_record(scenario)

        self.mode = mode
        self.monsters = int(monsters)
        self.frame_skip = int(scenario.frameSkip)
        self.map_name = map_name
        self.team_size = int(team_size)
        self.kit = kit
        obs_spec = _observability(Observability, observability)
        # The spec as given where it is a string, which Observability.parse reads back -- a
        # replay file rebuilds its environment from it; a partial mode's name ("po [los
        # ->all]") does not parse -- with its terrain radius stated, so the record means the
        # same whatever the default radius becomes. A mapping is recorded by its name.
        if isinstance(observability, str):
            self.observability = (observability if "+terrain:" in observability.lower()
                                  else "%s+terrain:%d" % (observability, int(obs_spec.terrain())))
        else:
            self.observability = str(obs_spec.name())
        self.progression = bool(progression)

        self._env = JSagaEnv(bridge.repo_root(root), scenario, obs_spec)
        self.map_seed = str(map_seed)
        if self.map_seed != "fixed":
            self._env.setMapSource(map_name, self.map_seed)    # refused here, by name, if no map

        # Bots in the slots `scripted` names; the learners are the rest. Read
        # BEFORE the counts below, which are the learners'.
        for slot, spec in _scripted_specs(scripted, int(self._env.nSlots()), 1)[0].items():
            self._env.setScripted(slot, spec)
        self.scripted = {slot: spec for slot, spec in
                         _scripted_specs(scripted, int(self._env.nSlots()), 1)[0].items()}

        self.n_agents = int(self._env.nAgents())
        self.episode_limit = int(self._env.episodeLimit())
        self._obs_size = int(self._env.obsSize())
        self._state_size = int(self._env.stateSize())
        self._n_actions = int(self._env.totalActions())

        from saga.sim.rl import RewardFunction
        self._reward_fn = None
        fn = _reward(RewardFunction, reward)
        if fn is None:
            # Python-side: the Java default keeps running, and its answer is
            # discarded. Cheaper than a Java callback and keeps user code here.
            self._reward_fn = reward
        else:
            self._env.setReward(fn)
        self.reward_name = ("custom" if self._reward_fn
                            else str(self._env.reward()))

        self._seed = 0 if seed is None else int(seed)
        self._episode = 0
        self._replay = None
        self._saved_replay = None

    # ------------------------------------------------------------------ core

    def reset(self, seed=None, options=None):
        """Returns (observations, info), as EPyMARL's base class documents.

        An explicit seed reproduces that exact episode, which is the Gymnasium
        contract and what any replay or bisect depends on. Only an unseeded reset
        advances, so successive training episodes differ.
        """
        if seed is not None:
            episode_seed = int(seed)
            self._seed = episode_seed
            self._episode = 0
        else:
            episode_seed = self._seed + self._episode
            self._episode += 1

        self._env.reset(episode_seed)
        self._replay = {"seed": int(episode_seed), "actions": [], "map": _map_entry(self._env)}
        return self.get_obs(), self.get_env_info()

    def set_map_source(self, map_name, map_seed="fixed"):
        """Where the map comes from from the next reset on (see __init__): a curriculum's step."""
        self._env.setMapSource(str(map_name), str(map_seed))
        self.map_name, self.map_seed = str(map_name), str(map_seed)

    def slot_of(self, agent_id):
        """The world slot learner agent_id stands in: the slots left over by `scripted`,
        in order. GameState arrays -- what a Python reward reads -- are indexed by slot."""
        return int(self._env.slotOf(int(agent_id)))

    def map_info(self):
        """The map of the episode under way: its source, the generator's seed (-1 for
        a map that is a name or a file), its name and its simHash."""
        return dict(_map_entry(self._env), name=str(self._env.mapName()))

    def step(self, actions):
        """Returns (obs, reward, terminated, truncated, info)."""
        actions = [int(a) for a in actions]
        if self._replay is not None:
            self._replay["actions"].append(actions)

        self._env.step(self._jpype.JArray(self._jpype.JInt)(actions))

        if self._reward_fn is None:
            rewards = [float(r) for r in self._env.rewards()]
        else:
            rewards = list(self._reward_fn(self._env.prevState(), actions,
                                           self._env.world().state(), self))
            rewards = [float(r) for r in rewards]
        reward = self._scalarise(rewards) if self.common_reward else rewards

        terminated = bool(self._env.terminated())
        truncated = bool(self._env.truncated())

        info = {}
        if terminated or truncated:
            info.update(self.episode_info())
            # PyMARL-family runners look for this key to separate a real terminal
            # state from a time limit, which must not be bootstrapped the same way.
            info["episode_limit"] = truncated

        return self.get_obs(), reward, terminated, truncated, info

    def episode_info(self):
        """What the end of an episode tells the runner: numbers only.

        EPyMARL's runners SUM every entry of this dict over the episodes of a batch
        and log the mean, so an entry that is not a number breaks training at the
        first episode -- which the per-agent lists get_stats() gained for the
        balance work did: `unsupported operand type(s) for +: 'int' and 'list'`.
        The lists stay in get_stats() for a direct caller; this hands the runner
        the summed keys and, in place of `winner` (a team NUMBER, whose sum means
        nothing), one flag per team and one for a draw -- so `test_win_team1_mean`
        in the log IS that team's win rate, which the summed kills could never give.
        """
        return _episode_info(self._env)

    def _scalarise(self, rewards):
        if self.reward_scalarisation == "mean":
            return float(sum(rewards) / len(rewards))
        return float(sum(rewards))

    # ------------------------------------------------------- observations

    def get_obs(self):
        return [self.get_obs_agent(i) for i in range(self.n_agents)]

    def get_obs_agent(self, agent_id):
        obs = np.asarray(self._env.obs(int(agent_id)), dtype=np.float32).copy()
        return obs if self._norm is None else self._norm.obs(obs)

    def get_obs_size(self):
        return self._obs_size

    def get_state(self):
        state = np.asarray(self._env.state(), dtype=np.float32).copy()
        return state if self._norm is None else self._norm.state(state)

    def get_state_size(self):
        return self._state_size

    # ------------------------------------------------------------ actions

    def get_avail_actions(self):
        # Every agent's mask in one question of the state the actions meet (SagaEnv.availActionsFlat)
        flat = np.asarray(self._env.availActionsFlat(), dtype=np.int64)
        return list(flat.reshape(self.n_agents, -1).copy())

    def get_avail_agent_actions(self, agent_id):
        # Through the buffer protocol, not element by element: boxing 109 Java ints
        # into Python ints cost 58 us per agent, which was four fifths of a whole
        # environment step. The runner turns it into a tensor either way.
        return np.asarray(self._env.availActions(int(agent_id)), dtype=np.int64).copy()

    def get_total_actions(self):
        return self._n_actions

    # ------------------------------------------------------------- extras

    def describe_obs(self, agent_id=0):
        """The observation as {field name: value}, for debugging and logging.

        Built from the same table the encoder writes from, so it cannot disagree
        with the real vector. Costs nothing during training -- it is only ever
        built when asked.
        """
        names = [str(n) for n in self._env.obsFieldNames(int(agent_id))]
        values = self.get_obs_agent(agent_id)
        return dict(zip(names, (float(v) for v in values)))

    def get_env_info(self):
        return {
            "state_shape": self.get_state_size(),
            "obs_shape": self.get_obs_size(),
            "n_actions": self.get_total_actions(),
            "n_agents": self.n_agents,
            "episode_limit": self.episode_limit,
        }

    def get_stats(self):
        """Episode statistics.

        The four summed keys are what EPyMARL logs and they keep their meaning. They
        are also useless on their own for balance: in a symmetric duel one agent's
        kill is the other's death, so the sums are equal by construction and no win
        rate can be read out of them. Hence the per-agent lists and the winner.

        `winner` is a TEAM, which is the same question in every mode -- deathmatch
        gives each character its own side, so the duel's agents are already teams 1
        and 2. It is 0 when the episode ran out of time without a decision, which is
        a distinct outcome from a draw and should not be folded into one.
        """
        return _stats(self._env)

    def render(self):
        raise NotImplementedError("saga.sim is headless; render via the game client")

    def close(self):
        pass

    def seed(self, seed=None):
        if seed is not None:
            self._seed = int(seed)
        return self._seed

    def set_learner_name(self, name):
        """What trained the learners -- an algorithm's name -- for a replay file's
        player names. The runner says it; nothing in the environment knows it."""
        self.learner_name = None if name is None else str(name)

    def replay_env(self):
        """The options this environment was built with, as a replay file records them."""
        return {"map_name": self.map_name, "map_seed": self.map_seed, "mode": self.mode, "team_size": self.team_size,
                "kit": self.kit, "progression": self.progression, "monsters": self.monsters,
                "frame_skip": self.frame_skip, "observability": self.observability, **self.round,
                "reward": self.reward_name, "learner": getattr(self, "learner_name", None),
                "normalise": self.normalise}

    def save_replay(self, path="saga_replay.json"):
        """The episode since the last reset, as a saga-replay file.

        The environment's options, the seed, the bots, the action sequence and the
        state hash the episode has reached: the simulation is deterministic, so that is the
        whole episode, and pysaga.replay rebuilds the environment from the
        file, replays it and checks the hash. EPyMARL calls this after an
        evaluation run started with save_replay=True.
        """
        import json
        if self._replay is None:
            return
        with open(path, "w") as f:
            json.dump({"format": "saga-replay", "version": REPLAY_VERSION, "env": self.replay_env(),
                       "maps": _map_texts([(self._replay["map"], self._env)]),
                       "episodes": [{"world": 0, "seed": self._replay["seed"], "actions": self._replay["actions"],
                                     "hash": int(self._env.hash()), "map": self._replay["map"],
                                     "scripted": {str(k): v for k, v in self.scripted.items()}}]}, f)

    # --------------------------------------- beyond the EPyMARL interface

    def save_state(self):
        """Saves the episode: the world, and a copy of each scripted bot with its memory.

        Enables planning and search, not just resets. Refused between a decision's
        begin and end, and for a bot that cannot be copied (SagaEnv.saveState).
        """
        self._env.saveState()
        self._saved_replay = None if self._replay is None else (self._replay, len(self._replay["actions"]))

    def load_state(self):
        """Puts the episode back as it was saved.

        The world and the bots come back; the decision count, the end flags, the
        winner and the totals are read from the world, so they come back with it;
        the rewards are zero, since there is no last step. The actions recorded for
        the replay since the save are dropped too, so a replay saved afterwards
        holds the future that was actually played.
        """
        self._env.loadState()
        if self._saved_replay is not None:
            replay, recorded = self._saved_replay
            del replay["actions"][recorded:]
            self._replay = replay

    def state_hash(self):
        """The determinism oracle. Identical inputs must give an identical trace."""
        return int(self._env.hash())


KITS = ("dealt", "basic")

# A replay file's version. 2: every episode names its map (source, the generator's
# seed, simHash), and a map that is a name or a file travels in the file ("maps"),
# so a shipped map changed or retired later does not change what the file replays.
REPLAY_VERSION = 2


def _map_entry(jenv):
    """The map of the episode a Java SagaEnv is in, as a replay file records it."""
    return {"source": str(jenv.mapSource()), "seed": int(jenv.mapSeed()), "sim_hash": str(jenv.mapSimHash())}


def _map_texts(pairs):
    """{simHash: map file text} for every map of (entry, Java env) that is not
    generated -- a generated map is made again from its source and seed."""
    out = {}
    for entry, jenv in pairs:
        if entry["seed"] < 0 and entry["sim_hash"] not in out and str(jenv.mapSimHash()) == entry["sim_hash"]:
            out[entry["sim_hash"]] = str(jenv.mapText())
    return out


def _scenario(Scenario, mode, map_name, team_size, progression, kit="dealt", monsters=0, frame_skip=4,
              time_limit=300, score_limit=None, cutoff=None, lives=5):
    """The Java Scenario for a mode -- the one place the mode names are read.

    Shared by SagaEnv and VecSagaEnv, so neither can enumerate the modes a second
    time. An unknown name THROWS rather than falling through to the duel. It used
    to, and a typo in a yaml then trained a 1v1 for a week while every log line
    said "tdm" -- the same failure the reward names are strict about, and for the
    same reason: a run that looked like it measured something it did not.

    progression=True hands the agent an empty tree and its own points to spend;
    False deals it a fixed build. The ACTION SPACE IS IDENTICAL either way -- the
    learning indices are reserved and merely masked -- so a policy trained on one
    has the right shape for the other. Applied to whatever scenario the mode chose,
    rather than selected alongside it: written as another branch it was
    unreachable in a team mode, and the episode dealt fixed builds while reporting
    progression=True.
    """
    # The mode by the game's own list (Scenario.modeOf: saga.map.Modes, "duel" and
    # underscores accepted); Monster Attack's team_size is its players, monsters=n
    # its pool (8 if 0)
    import jpype
    number = int(Scenario.modeOf(str(mode)))
    if number < 0:
        names = [str(n) for n in jpype.JClass("saga.map.Modes").NAMES]
        raise ValueError("unknown mode %r -- one of: duel, %s" % (mode, ", ".join(names)))
    scenario = Scenario.ofMode(number, map_name, int(team_size or 0))
    if kit not in KITS:
        raise ValueError("unknown kit %r -- one of: %s" % (kit, ", ".join(KITS)))
    if progression and kit == "basic":
        raise ValueError("kit='basic' is the weapon strike alone with nothing to learn; "
                         "progression starts from the same strike and earns the rest -- choose one")
    if progression:
        scenario = Scenario.withProgression(scenario)
    elif kit == "basic":
        # The client character's kit: the weapon strike alone. A policy meant to
        # play in the real client is trained on this, since the dealt kits are
        # abilities the client's character does not have.
        scenario = Scenario.withBasicKit(scenario)
    if int(monsters) < 0:
        raise ValueError("monsters=%r: a number of the map's homes to fill, 0 or more" % (monsters,))
    if int(monsters) > 0:
        # A third transformation: the map's monsters out, whatever the mode and kit --
        # in Monster Attack, the size of the pool its spawner fills.
        scenario = Scenario.withNpcs(scenario, int(monsters))
    # The decision rate: ticks of 50 ms a decision, 4 the default. An episode stays as long
    # in game time, and the reward's time term is priced per tick, so another rate is the
    # same problem at another resolution. The scripted bots and the balance tables are
    # fitted to 4. A trained policy in a scripted slot decides at its own rate, on the
    # world's ticks that rate divides, and the environment warns once when rates differ.
    if int(frame_skip) < 1:
        raise ValueError("frame_skip=%r: ticks a decision lasts, 1 or more" % (frame_skip,))
    # The episode's end, the user's to say (Scenario.withRound): the round's clock in seconds
    # (time_limit; at its end the mode names the winner and the episode is TERMINATED), an
    # earlier end at a score (score_limit; the mode's own when None, 0 for none), a cutoff in
    # seconds that TRUNCATES with no winner (None for none), and Monster Attack's deaths per
    # player. A length the decision rate does not divide is refused, and so is an episode
    # with no end at all.
    for name, value in (("time_limit", time_limit), ("cutoff", cutoff)):
        if value is not None and float(value) < 0:
            raise ValueError("%s=%r: seconds of game time, 0 or more" % (name, value))
    if score_limit is not None and int(score_limit) < 0:
        raise ValueError("score_limit=%r: a score, 0 for none" % (score_limit,))
    if int(lives) < 1:
        raise ValueError("lives=%r: Monster Attack's deaths per player, 1 or more" % (lives,))
    try:
        round_ticks = int(Scenario.ticksOf(float(time_limit), "time_limit")) if time_limit else 0
        cut_ticks = int(Scenario.ticksOf(float(cutoff), "cutoff")) if cutoff else 0
        limit = int(scenario.scoreLimit) if score_limit is None else int(score_limit)
        scenario = Scenario.withRound(scenario, round_ticks, limit, cut_ticks, int(lives), int(frame_skip))
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(str(e).split(": ", 1)[-1]) from None
    return scenario


def _round_record(scenario):
    """The episode's end as a replay file records it: seconds, the score limit and lives."""
    tick = 1000.0 / int(scenario.TICK_MS)
    seconds = lambda t: (int(t) / tick) if int(t) else None
    return {"time_limit": seconds(scenario.roundTicks), "score_limit": int(scenario.scoreLimit),
            "cutoff": seconds(scenario.cutoffTicks), "lives": int(scenario.lives)}


def _reward(RewardFunction, reward):
    """The Java reward for a spec: a name or a dict of weights. None for a callable."""
    if callable(reward):
        return None
    if isinstance(reward, dict):
        return RewardFunction.weighted({str(k): float(v) for k, v in reward.items()})
    return RewardFunction.byName(str(reward))


def _scripted_string(spec, n_slots):
    """The command-line form of `scripted`, as a dict.

    "kite" is every slot but the first; "0:melee" names a slot; entries are
    separated by commas ("0:melee,2:kite"); "|" inside a name lists bots to spread
    over the worlds ("1:melee|kite"). A bot name may itself hold colons
    ("1:kite:60:140"): an entry names a slot only when what stands before its first
    colon is a number. A string form exists because sacred turns a dict on the
    command line into nested config keys ("env_args.scripted.1=kite") and refuses
    any the yaml does not declare, while a string passes through it untouched.
    """
    entries = [e.strip() for e in spec.split(",") if e.strip()]
    out = {}
    for e in entries:
        head, sep, rest = e.partition(":")
        if sep and head.strip().isdigit():
            names = [n.strip() for n in rest.split("|")]
            out[int(head)] = names if len(names) > 1 else names[0]
        elif len(entries) == 1:
            names = [n.strip() for n in e.split("|")]
            return {s: (names if len(names) > 1 else names[0]) for s in range(1, n_slots)}
        else:
            raise ValueError("a scripted string with several entries gives each a slot, "
                             "like '0:melee,2:kite': %r" % (spec,))
    return out


def _scripted_specs(spec, n_slots, n_worlds):
    """Which slots the bots take, per world: [{slot: name}, ...], one dict a world.

    A string names the bot for every slot but the first, or slots by number in
    the command-line form (_scripted_string); a list names slots 1, 2, ... in
    order; a dict names slots explicitly. A dict value may itself be a list,
    which spreads over the WORLDS -- {1: ["melee", "kite"]} gives world i the bot
    at i % 2 -- so a batch can hold mixed opponents with one learner across them.
    Refuses a slot out of range, and a world with nothing left to learn.
    """
    if spec is None:
        return [dict() for _ in range(n_worlds)]
    if isinstance(spec, str):
        spec = _scripted_string(spec, n_slots)
    elif isinstance(spec, (list, tuple)):
        spec = {s + 1: name for s, name in enumerate(spec)}
    elif not isinstance(spec, dict):
        raise TypeError("scripted must be a bot name, a list of names or a dict of slot: name, not %r" % (spec,))

    out = []
    for w in range(n_worlds):
        row = {}
        for slot, name in spec.items():
            slot = int(slot)
            if not 0 <= slot < n_slots:
                raise ValueError("scripted slot %d is out of range: the scenario has %d slots" % (slot, n_slots))
            if isinstance(name, (list, tuple)):
                name = name[w % len(name)]
            row[slot] = str(name)
        if len(row) >= n_slots:
            raise ValueError("every slot is scripted: nothing left to learn")
        out.append(row)
    return out


def _stats(jenv):
    """get_stats() of one Java environment: the summed keys, the winner and the lists.

    The lists are the LEARNERS'. teams_in_round is every side in the world, bots
    included, so a win flag exists for the side a learner fights even when nobody
    learns on it.
    """
    n = int(jenv.nAgents())
    kills = [int(jenv.kills(i)) for i in range(n)]
    deaths = [int(jenv.deaths(i)) for i in range(n)]
    damage = [int(jenv.damage(i)) for i in range(n)]
    teams = [int(jenv.team(i)) for i in range(n)]
    types = [int(jenv.type(i)) for i in range(n)]
    sides = sorted({int(jenv.slotTeam(s)) for s in range(int(jenv.nSlots()))})

    return {
        "teams_in_round": sides,
        "kills": sum(kills),
        "deaths": sum(deaths),
        "damage": sum(damage),
        "decisions": int(jenv.decisions()),

        "winner": int(jenv.winner()),
        "kills_per_agent": kills,
        "deaths_per_agent": deaths,
        "damage_per_agent": damage,
        "team_per_agent": teams,
        "type_per_agent": types,
    }


def _episode_info(jenv):
    """episode_info() of one Java environment: numbers only -- see SagaEnv.episode_info."""
    stats = _stats(jenv)
    info = {k: stats[k] for k in ("kills", "deaths", "damage", "decisions")}
    winner = stats["winner"]
    for team in stats["teams_in_round"]:
        info["win_team%d" % team] = 1 if winner == team else 0
    info["draw"] = 1 if winner == jenv.WINNER_DRAW else 0
    info["lost"] = 1 if winner == jenv.WINNER_LOST else 0
    return info


def observability_modes(root=None):
    """The mode names a string spec can use, with the arguments each takes.

    Reads the same table the parser dispatches on, so it cannot advertise a mode
    that does not exist -- which is the failure this replaced: to find out that
    `cone` took two numbers you had to read the parser.
    """
    bridge.start_jvm(root)

    # The import hook is what makes a Java package importable, and starting the
    # JVM does not install it. SagaEnv does this too, a few lines before its own
    # import -- so a module-level helper that only started the JVM failed with
    # "No module named 'saga'", which reads like a missing build.
    import jpype.imports                                     # noqa: F401

    from saga.sim.rl import Observability

    return [str(m) for m in Observability.modes()]


def register_observability(name, spec, root=None):
    """Gives a mode of your own a name, usable anywhere a built-in name is.

    Without it a custom mode is written out wherever it is used -- every script,
    every config -- and changing it means changing every copy.

        register_observability("ourmodel", {"channels": [
            {"range": 300, "line_of_sight": True, "reveals": "all"},
            {"range": 600,                        "reveals": "existence|position"},
        ]})

        SagaEnv(observability="ourmodel")

    A built-in name is refused, and so is re-registering a different mode under a
    name already taken: silently redefining one would change what every past run
    meant while every one of them still reported the old name.
    """
    bridge.start_jvm(root)

    import jpype.imports                                     # noqa: F401

    from saga.sim.rl import Observability

    Observability.register(name, _observability(Observability, spec))


def _observability(Observability, spec):
    """Builds an Observability from a string, a mapping, or one already built.

    A terrain patch -- the walk and sight flags of the blocks within r of the
    agent's own, appended to its observation -- is "+terrain:r" after a mode's name
    ("los+terrain:4") or "terrain": r in a mapping. It widens the observation, so a
    policy trained without it does not bind to an environment with it. The clock --
    the share of the round left, the observation's last number -- is on unless
    "+noclock" follows the name or "clock": False stands in the mapping.
    """
    if isinstance(spec, dict):
        # A key nothing reads is refused, as every other option is: a typo in a
        # mapping would otherwise build a different mode with no word said.
        allowed = (_MODE_KEYS.get(spec.get("mode")) if "mode" in spec
                   else {"channels", "terrain", "clock"} if "channels" in spec
                   else _CHANNEL_KEYS | {"terrain", "clock"})
        if allowed is None:
            raise ValueError("unknown observability mode %r -- one of: %s"
                             % (spec.get("mode"), ", ".join(sorted(_MODE_KEYS))))
        unknown = sorted(set(spec) - allowed)
        if unknown:
            raise ValueError("observability %r: unknown key(s) %s -- accepted here: %s"
                             % (spec, ", ".join(unknown), ", ".join(sorted(allowed))))
    if isinstance(spec, dict) and "clock" in spec:
        rest = {k: v for k, v in spec.items() if k != "clock"}
        return _observability(Observability, rest or None).withClock(bool(spec["clock"]))
    if isinstance(spec, dict) and "terrain" in spec:
        rest = {k: v for k, v in spec.items() if k != "terrain"}
        return _observability(Observability, rest or None).withTerrain(int(spec["terrain"]))
    if spec is None:
        return Observability.full()
    if isinstance(spec, str):
        return Observability.parse(spec)
    if not isinstance(spec, dict):
        return spec                                  # already a Java Observability

    from saga.sim.rl import Channel, ObsLayout

    # An explicit channel list: the general form, for a mode with no preset.
    if "channels" in spec:
        built = [_channel(Channel, ObsLayout, c) for c in spec["channels"]]
        return Observability(built)

    mode = spec.get("mode")
    if mode == "full":
        return Observability.full()
    if mode == "los":
        return Observability.lineOfSight()
    if mode == "sight":
        return Observability.sight(int(spec["range"]))
    if mode == "squad":
        return Observability.squad(int(spec["range"]))
    if mode == "radar":
        return Observability.radar(int(spec["range"]))
    if mode == "cone":
        return Observability.cone(int(spec["range"]), float(spec["fov_degrees"]))
    if mode == "hearing":
        return Observability.hearing(int(spec["range"]), int(spec["hearing_range"]))

    # No mode and no channel list: one channel built field by field, so a single
    # dimension can be varied without inventing a preset for it.
    return Observability([_channel(Channel, ObsLayout, spec)])


# The keys a mapping may hold: one channel written out, or a named mode's arguments.
_CHANNEL_KEYS = {"range", "line_of_sight", "respect_invisibility", "allies_only", "reveals", "fov_degrees"}
_MODE_KEYS = {"full": {"mode", "terrain", "clock"}, "los": {"mode", "terrain", "clock"},
              "sight": {"mode", "range", "terrain", "clock"}, "squad": {"mode", "range", "terrain", "clock"},
              "radar": {"mode", "range", "terrain", "clock"}, "cone": {"mode", "range", "fov_degrees", "terrain", "clock"},
              "hearing": {"mode", "range", "hearing_range", "terrain", "clock"}}


def _channel(Channel, ObsLayout, spec):
    unknown = sorted(set(spec) - _CHANNEL_KEYS)
    if unknown:
        raise ValueError("observability channel %r: unknown key(s) %s -- accepted: %s"
                         % (spec, ", ".join(unknown), ", ".join(sorted(_CHANNEL_KEYS))))
    b = Channel.Builder()
    b.sightRangePx = int(spec.get("range", 0))
    b.requireLineOfSight = bool(spec.get("line_of_sight", False))
    b.respectInvisibility = bool(spec.get("respect_invisibility", True))
    b.alliesOnly = bool(spec.get("allies_only", False))
    b.reveals = ObsLayout.parseGroups(str(spec.get("reveals", "all")))
    if "fov_degrees" in spec:
        b.fov(float(spec["fov_degrees"]))
    return b.build()
