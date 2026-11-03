"""N environments stepped in one call.

Training is bound by what runs per step of the runner -- the forward pass, the
batch bookkeeping, and with a process per environment the pipes and pickling --
not by the simulation, which costs about a microsecond a decision. Ten worker
processes stepped 4,000 decisions a second between them with the training process
as the bottleneck. So the lever is width: many worlds stepped in one Java call, so
that every per-step cost is shared by all of them.

VecSagaEnv holds N SagaEnvs inside one JVM (saga.sim.rl.VecEnv). step() takes an
(N, agents) array of actions and returns arrays: observations (N, agents, obs),
state (N, state), masks (N, agents, actions), rewards (N, agents) -- or (N,) with
common_reward -- and two (N,) flags. No pipes, no pickling, no per-element
conversion; 64 worlds step in about 130 microseconds.

A world whose episode has ended is SKIPPED by step -- its rows keep the terminal
values, its reward row is zero -- which is what an episode runner wants: a batch of
N whole episodes, finished ones waiting for the longest. auto_reset=True gives the
other behaviour, for a continuous rollout: a finished world is reset inside the same
step, with its seed plus N, and its rows then hold the new episode's first
observation while the flags say the old one ended.

It knows nothing of EPyMARL. pysaga/epymarl/vec_runner.py is the adapter that
makes EPyMARL drive it; any other loop can drive it directly.
"""

import numpy as np

from . import bridge
from .env import (DEFAULT_MAP, MODES, REPLAY_VERSION, _episode_info, _map_entry, _map_texts, _observability, _reward,
                  _scenario, _scripted_specs, _stats)


class VecSagaEnv(object):

    def __init__(self, n_envs, map_name=DEFAULT_MAP, seed=None, root=None,
                 common_reward=False, reward_scalarisation="sum",
                 observability="full", progression=False, reward="dense",
                 mode="duel", team_size=2, parallel=True, auto_reset=False,
                 scripted=None, kit="dealt", map_seed="fixed", map_schedule=None, monsters=0, frame_skip=4, normalise=None, **kwargs):
        """The options of SagaEnv, read by the same code, plus:

        n_envs      how many worlds
        parallel    step the worlds on parallel threads (identical results)
        auto_reset  restart a finished world inside the step that ended it
        scripted    bots in the slots it names, as SagaEnv takes it; a dict value
                    that is a list spreads over the worlds, {1: ["melee", "kite"]}
                    giving world i the bot at i % 2 -- mixed opponents, one learner
                    ("1:melee|kite" on a command line)
        map_seed    "fixed" or "episode", as SagaEnv takes it
        map_schedule  a curriculum over maps: the map from a number of environment
                    steps on, "0:gen:arena|2000000:gen:forest:trees=150" or a list of
                    (steps, source) pairs. advance(t_env) moves to the entry due;
                    the vec runner calls it before every batch. map_name is the map
                    until the first entry is due.

        A Python reward is refused: it would run per world per step and give back
        most of what the vectorised path saves. A name or a dict of weights runs in
        Java and costs nothing.
        """
        if kwargs:
            raise TypeError(
                "unknown argument(s) %s -- accepted: %s"
                % (", ".join(sorted(repr(k) for k in kwargs)),
                   "n_envs, map_name, seed, root, common_reward, "
                   "reward_scalarisation, observability, progression, reward, "
                   "mode, team_size, parallel, auto_reset, scripted, kit, map_seed, map_schedule, monsters, frame_skip, normalise"))
        if callable(reward):
            raise TypeError(
                "a Python reward runs per world per step; the vectorised "
                "environment takes a reward name or a dict of weights, which run "
                "in Java")

        bridge.start_jvm(root)
        import jpype
        import jpype.imports                                # noqa: F401
        from saga.sim.rl import Observability, RewardFunction, Scenario
        from saga.sim.rl import VecEnv as JVecEnv

        self._jpype = jpype
        self.common_reward = common_reward
        self.reward_scalarisation = reward_scalarisation
        self.mode = mode
        self.map_name = map_name
        self.team_size = int(team_size)
        self.kit = kit
        self.progression = bool(progression)

        self.monsters = int(monsters)
        # The inputs standardised for learning, as SagaEnv does (pysaga.normalise)
        from .normalise import for_environment
        self.normalise = None if normalise is None else str(normalise)
        self._norm = None if normalise is None else for_environment(normalise)
        scenario = _scenario(Scenario, mode, map_name, team_size, progression, kit, monsters, frame_skip)
        self.frame_skip = int(scenario.frameSkip)
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

        self.n_envs = int(n_envs)
        n_slots = int(scenario.agents)
        rows = _scripted_specs(scripted, n_slots, self.n_envs)
        self.scripted = rows
        table = jpype.JArray(jpype.JString, 2)(
            [[row.get(s) for s in range(n_slots)] for row in rows])
        self._vec = JVecEnv(bridge.repo_root(root), scenario, obs_spec, self.n_envs, table)
        self._vec.setReward(_reward(RewardFunction, reward))
        self._vec.setParallel(bool(parallel))
        self._vec.setAutoReset(bool(auto_reset))
        self.map_seed = str(map_seed)
        self.map_schedule = _schedule(map_schedule)
        from saga.sim.rl import MapSource
        for _, source in self.map_schedule:                  # every entry refused now, by name, not when it falls due
            MapSource.parse(source, self.map_seed)
        # The schedule's entry due at the start replaces map_name from the first episode
        first = [source for t, source in self.map_schedule if t <= 0]
        if first:
            self.map_name = first[-1]
        if self.map_name != map_name or self.map_seed != "fixed":
            self._vec.setMapSource(self.map_name, self.map_seed)
        self.reward_name = str(self._vec.env(0).reward())

        self.n_agents = int(self._vec.nAgents())
        self.episode_limit = int(self._vec.episodeLimit())
        self._obs_size = int(self._vec.obsSize())
        self._state_size = int(self._vec.stateSize())
        self._n_actions = int(self._vec.totalActions())

        self._jint = jpype.JArray(jpype.JInt)
        self._jlong = jpype.JArray(jpype.JLong)

        self._seed = 0 if seed is None else int(seed)
        self._episode = 0
        self._episode_seeds = np.zeros(self.n_envs, dtype=np.int64)
        # One row of actions per step for every world, and where each world's
        # episode began in it: a list per world cost 64 appends a step
        self._replay = None
        self._replay_start = np.zeros(self.n_envs, dtype=np.int64)
        # ... and where it ended, or -1 while it runs: a world that finishes before
        # the batch keeps receiving rows the environment skips, and a file that
        # carried them read as an episode of the batch's length
        self._replay_end = np.full(self.n_envs, -1, dtype=np.int64)

    # ------------------------------------------------------------------ core

    def reset(self, seed=None):
        """A fresh episode in every world. Returns (obs, state, avail).

        Episode e of world i is seeded seed + e * n_envs + i, so no two episodes
        of a run share a seed, and an explicit seed reproduces the whole batch --
        the Gymnasium contract, and what any replay or bisect depends on. Only an
        unseeded reset advances, so successive batches differ.
        """
        if seed is not None:
            self._seed = int(seed)
            self._episode = 0
        base = self._seed + self._episode * self.n_envs
        self._episode += 1

        seeds = base + np.arange(self.n_envs, dtype=np.int64)
        self._vec.reset(self._jlong(seeds.tolist()))
        self._episode_seeds = seeds
        self._maps = [_map_entry(self._vec.env(i)) for i in range(self.n_envs)]
        self._replay = []
        self._replay_start[:] = 0
        self._replay_end[:] = -1
        return self._read()

    def step(self, actions):
        """One decision in every world still in its episode.

        actions is (n_envs, n_agents), or that many flat. Returns
        (obs, state, avail, rewards, terminated, truncated): rewards (n_envs,
        n_agents), or (n_envs,) with common_reward; the flags (n_envs,) booleans.
        """
        acts = np.ascontiguousarray(actions, dtype=np.int32).reshape(-1)
        if acts.size != self.n_envs * self.n_agents:
            raise ValueError("actions must be (%d, %d), got %d values"
                             % (self.n_envs, self.n_agents, acts.size))
        if self._replay is not None:
            self._replay.append(acts.reshape(self.n_envs, self.n_agents).copy())

        self._vec.step(self._jint(acts))

        obs, state, avail = self._read()
        rewards = np.asarray(self._vec.rewards(), dtype=np.float32).reshape(
            self.n_envs, self.n_agents).copy()
        if self.common_reward:
            rewards = (rewards.mean(axis=1) if self.reward_scalarisation == "mean"
                       else rewards.sum(axis=1))
        terminated = np.asarray(self._vec.terminated()).astype(bool)
        truncated = np.asarray(self._vec.truncated()).astype(bool)
        if self._replay is not None:
            ended = (terminated | truncated) & (self._replay_end < 0)
            self._replay_end[ended] = len(self._replay)
        return obs, state, avail, rewards, terminated, truncated

    def reset_env(self, i, seed=None):
        """A fresh episode in world i alone, for a loop of one's own."""
        s = int(self._vec.seed(i)) + self.n_envs if seed is None else int(seed)
        self._vec.resetEnv(int(i), s)
        self._episode_seeds[i] = s
        self._maps[i] = _map_entry(self._vec.env(int(i)))
        if self._replay is not None:
            self._replay_start[i] = len(self._replay)
            self._replay_end[i] = -1

    def _read(self):
        n, a = self.n_envs, self.n_agents
        obs = np.asarray(self._vec.obs(), dtype=np.float32).reshape(n, a, self._obs_size).copy()
        state = np.asarray(self._vec.state(), dtype=np.float32).reshape(n, self._state_size).copy()
        avail = np.asarray(self._vec.avail(), dtype=np.int32).reshape(n, a, self._n_actions).copy()
        if self._norm is not None:
            obs, state = self._norm.obs(obs), self._norm.state(state)
        return obs, state, avail

    # ------------------------------------------------------------- extras

    def get_env_info(self):
        return {
            "state_shape": self._state_size,
            "obs_shape": self._obs_size,
            "n_actions": self._n_actions,
            "n_agents": self.n_agents,
            "episode_limit": self.episode_limit,
            "n_envs": self.n_envs,
        }

    def episode_info(self, i):
        """What the end of world i's episode tells a runner: numbers only."""
        return _episode_info(self._vec.env(int(i)))

    def get_stats(self, i):
        """World i's statistics, the per-agent lists included."""
        return _stats(self._vec.env(int(i)))

    def episode_seed(self, i):
        return int(self._episode_seeds[i])

    def state_hash(self, i):
        """World i's determinism oracle."""
        return int(self._vec.env(int(i)).hash())

    def set_map_source(self, map_name, map_seed=None):
        """Every world's map from the next reset on (SagaEnv.set_map_source)."""
        seed_mode = self.map_seed if map_seed is None else str(map_seed)
        self._vec.setMapSource(str(map_name), seed_mode)
        self.map_name, self.map_seed = str(map_name), seed_mode

    def advance(self, t_env):
        """Moves to the map the schedule has due at t_env environment steps, if it is
        another: the next reset plays on it. Without a schedule, nothing."""
        due = None
        for t, source in self.map_schedule:
            if t <= t_env:
                due = source
        if due is not None and due != self.map_name:
            self.set_map_source(due)
        return self.map_name

    def map_info(self, i):
        """World i's map in the episode under way (SagaEnv.map_info)."""
        jenv = self._vec.env(int(i))
        return dict(_map_entry(jenv), name=str(jenv.mapName()))

    def set_learner_name(self, name):
        """What trained the learners, for a replay file's player names (SagaEnv.set_learner_name)."""
        self.learner_name = None if name is None else str(name)

    def save_replay(self, path="saga_replay.json", i=None):
        """Every world's episode since its last reset, as one saga-replay file (world i alone if given).

        The same format SagaEnv writes: the options, and per world its seed, its
        bots, its action rows and the state hash it has reached. A world that finished
        before the batch did keeps receiving rows the environment skips; its rows are
        cut at the step its episode ended, so the file's count IS the episode's length
        (a replay showed "282 / 1500" for an episode that was over at 282).
        """
        import json
        if self._replay is None:
            return
        worlds = range(self.n_envs) if i is None else [int(i)]
        episodes = []
        for w in worlds:
            end = int(self._replay_end[w]) if self._replay_end[w] >= 0 else len(self._replay)
            actions = [row[w].tolist() for row in self._replay[int(self._replay_start[w]):end]]
            episodes.append({"world": int(w), "seed": self.episode_seed(w), "actions": actions,
                             "hash": self.state_hash(w), "map": self._maps[w],
                             "scripted": {str(k): v for k, v in self.scripted[w].items()}})
        # The bots and the map are per EPISODE: a batch may hold a different one in every world.
        env = {"map_name": self.map_name, "map_seed": self.map_seed, "mode": self.mode, "team_size": self.team_size,
               "kit": self.kit, "progression": self.progression, "monsters": self.monsters,
               "frame_skip": self.frame_skip,
               "observability": self.observability,
               "reward": self.reward_name, "learner": getattr(self, "learner_name", None),
               "normalise": self.normalise}
        maps = _map_texts([(self._maps[w], self._vec.env(w)) for w in worlds])
        with open(path, "w") as f:
            json.dump({"format": "saga-replay", "version": REPLAY_VERSION, "env": env, "maps": maps,
                       "episodes": episodes}, f)

    def close(self):
        pass


def _schedule(spec):
    """[(steps, source)] in order of steps, from "0:gen:arena|500000:gen:forest" or a
    list of pairs. A source may hold colons; the steps are what comes before the first."""
    if spec is None or spec == "":
        return []
    items = spec.split("|") if isinstance(spec, str) else list(spec)
    out = []
    for item in items:
        if isinstance(item, str):
            if ":" not in item:
                raise ValueError("a map_schedule entry is steps:source, not %r" % item)
            t, source = item.split(":", 1)
        else:
            t, source = item
        try:
            t = int(t)
        except ValueError:
            raise ValueError("a map_schedule entry starts with a number of steps, not %r" % (t,))
        out.append((t, str(source).strip()))
    return sorted(out, key=lambda e: e[0])
