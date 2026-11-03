"""A vectorised runner for EPyMARL, over pysaga's VecSagaEnv.

Registered in an EPyMARL checkout by  python -m pysaga.epymarl <checkout>, which adds
to src/runners/__init__.py, beside the episode and parallel runners:

    from pysaga.epymarl.vec_runner import VecRunner
    REGISTRY["vec"] = VecRunner

Then select it, with as many worlds as the batch is wide:

    python src/main.py --config=ippo --env-config=saga \\
        with runner=vec batch_size_run=64 buffer_size=64 batch_size=64

(on the command line: the algorithm config outranks the environment config, so
these cannot be set in saga.yaml).

Why. The parallel runner keeps a process, a JVM and a pipe per environment, and
spends its time in the PARENT: the forward pass, the batch bookkeeping and the
pipes cost about 600 microseconds per step of ten environments while the ten
workers wait, so more workers do not help. This runner keeps N worlds in one JVM in
this process (saga.sim.rl.VecEnv), steps them in one call, and does one forward
pass and one batch update per step for all of them -- everything per step is
shared by N worlds, and N can be 64 or 256 where ten JVMs were already a lot.

It is a peer of ParallelRunner: the same interface, and the same episode
semantics -- a batch of N whole episodes, in which a world that has finished waits
for the longest -- so the learner, the configs and the logging are untouched, and
the batch it fills is exactly what N single environments would have filled
(pysaga.epymarl.check_vec_runner replays every world to prove it).
"""

from functools import partial

import numpy as np
import torch as th

from components.episode_buffer import EpisodeBatch

from pysaga.vec import VecSagaEnv


class VecRunner:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger
        self.batch_size = self.args.batch_size_run

        if self.args.env != "saga":
            raise ValueError(
                "the vec runner drives pysaga's vectorised environment, so env must "
                "be 'saga', not %r" % self.args.env)

        env_args = dict(self.args.env_args)
        env_args["common_reward"] = self.args.common_reward
        env_args["reward_scalarisation"] = self.args.reward_scalarisation
        self.env = VecSagaEnv(self.batch_size, **env_args)
        # The algorithm's name, for a replay file's player names: the runner is the
        # one party that knows it
        if hasattr(self.env, "set_learner_name"):
            self.env.set_learner_name(getattr(args, "name", None))

        self.env_info = self.env.get_env_info()
        self.episode_limit = self.env_info["episode_limit"]
        self.t = 0
        self.t_env = 0

        self.train_returns = []
        self.test_returns = []
        self.train_stats = {}
        self.test_stats = {}

        self.log_train_stats_t = -100000

    def setup(self, scheme, groups, preprocess, mac):
        self.new_batch = partial(
            EpisodeBatch,
            scheme,
            groups,
            self.batch_size,
            self.episode_limit + 1,
            preprocess=preprocess,
            device=self.args.device,
        )
        self.mac = mac
        self.scheme = scheme
        self.groups = groups
        self.preprocess = preprocess

    def get_env_info(self):
        return self.env_info

    def save_replay(self):
        self.env.save_replay()

    def close_env(self):
        self.env.close()

    def reset(self):
        self.batch = self.new_batch()
        # A map curriculum moves on with the steps taken (VecSagaEnv.advance), and says so
        if hasattr(self.env, "advance"):
            source = self.env.advance(self.t_env)
            if source != getattr(self, "_map_source", None):
                self.logger.console_logger.info("Map: %s from t_env %d" % (source, self.t_env))
                self._map_source = source
        obs, state, avail = self.env.reset()
        self.batch.update(
            {"state": th.from_numpy(state),
             "avail_actions": th.from_numpy(avail),
             "obs": th.from_numpy(obs)},
            ts=0,
        )
        self.t = 0
        self.env_steps_this_run = 0

    def run(self, test_mode=False):
        self.reset()

        n = self.batch_size
        if self.args.common_reward:
            episode_returns = [0.0 for _ in range(n)]
        else:
            episode_returns = [np.zeros(self.args.n_agents) for _ in range(n)]
        episode_lengths = [0 for _ in range(n)]
        self.mac.init_hidden(batch_size=n)
        terminated = [False for _ in range(n)]
        final_env_infos = []  # filled in ORDER OF TERMINATION, as the parallel runner does

        while True:
            envs_not_terminated = [b for b, termed in enumerate(terminated) if not termed]
            if not envs_not_terminated:
                break

            # One forward pass for every world still running
            actions = self.mac.select_actions(
                self.batch,
                t_ep=self.t,
                t_env=self.t_env,
                bs=envs_not_terminated,
                test_mode=test_mode,
            )
            cpu_actions = actions.to("cpu").numpy()
            self.batch.update(
                {"actions": actions.unsqueeze(1)},
                bs=envs_not_terminated, ts=self.t, mark_filled=False,
            )

            # One step for every world. A finished world is skipped by the
            # environment whatever it is given; the no-op it gets here is never used.
            all_actions = np.zeros((n, self.args.n_agents), dtype=np.int32)
            all_actions[envs_not_terminated] = cpu_actions
            obs, state, avail, reward, term, trunc = self.env.step(all_actions)

            bs = envs_not_terminated
            reward_bs = np.asarray(reward, dtype=np.float32)[bs].reshape(len(bs), -1)
            # A world stopped by the time limit is not a terminal state: the value
            # of its last observation is still bootstrapped, as the parallel runner
            # does through info["episode_limit"].
            term_bs = term[bs].astype(np.uint8).reshape(len(bs), 1)

            for k, idx in enumerate(bs):
                episode_returns[idx] += reward[idx]
                episode_lengths[idx] += 1
                if not test_mode:
                    self.env_steps_this_run += 1
                if term[idx] or trunc[idx]:
                    info = self.env.episode_info(idx)
                    info["episode_limit"] = bool(trunc[idx])
                    final_env_infos.append(info)
                    terminated[idx] = True

            self.batch.update(
                {"reward": th.from_numpy(reward_bs), "terminated": th.from_numpy(term_bs)},
                bs=bs, ts=self.t, mark_filled=False,
            )

            self.t += 1

            # What the same worlds see next, this step's finishers included
            self.batch.update(
                {"state": th.from_numpy(np.ascontiguousarray(state[bs])),
                 "avail_actions": th.from_numpy(np.ascontiguousarray(avail[bs])),
                 "obs": th.from_numpy(np.ascontiguousarray(obs[bs]))},
                bs=bs, ts=self.t, mark_filled=True,
            )

        if not test_mode:
            self.t_env += self.env_steps_this_run

        cur_stats = self.test_stats if test_mode else self.train_stats
        cur_returns = self.test_returns if test_mode else self.train_returns
        log_prefix = "test_" if test_mode else ""
        infos = [cur_stats] + final_env_infos
        cur_stats.update(
            {
                k: sum(d.get(k, 0) for d in infos)
                for k in set.union(*[set(d) for d in infos])
            }
        )
        cur_stats["n_episodes"] = n + cur_stats.get("n_episodes", 0)
        cur_stats["ep_length"] = sum(episode_lengths) + cur_stats.get("ep_length", 0)

        cur_returns.extend(episode_returns)

        n_test_runs = max(1, self.args.test_nepisode // n) * n
        if test_mode and (len(self.test_returns) == n_test_runs):
            self._log(cur_returns, cur_stats, log_prefix)
        elif self.t_env - self.log_train_stats_t >= self.args.runner_log_interval:
            self._log(cur_returns, cur_stats, log_prefix)
            if hasattr(self.mac.action_selector, "epsilon"):
                self.logger.log_stat(
                    "epsilon", self.mac.action_selector.epsilon, self.t_env
                )
            self.log_train_stats_t = self.t_env

        return self.batch

    def _log(self, returns, stats, prefix):
        # As ParallelRunner._log, so the two runners' logs read alike
        if self.args.common_reward:
            self.logger.log_stat(prefix + "return_mean", np.mean(returns), self.t_env)
            self.logger.log_stat(prefix + "return_std", np.std(returns), self.t_env)
        else:
            for i in range(self.args.n_agents):
                self.logger.log_stat(
                    prefix + f"agent_{i}_return_mean",
                    np.array(returns)[:, i].mean(),
                    self.t_env,
                )
                self.logger.log_stat(
                    prefix + f"agent_{i}_return_std",
                    np.array(returns)[:, i].std(),
                    self.t_env,
                )
            total_returns = np.array(returns).sum(axis=-1)
            self.logger.log_stat(
                prefix + "total_return_mean", total_returns.mean(), self.t_env
            )
            self.logger.log_stat(
                prefix + "total_return_std", total_returns.std(), self.t_env
            )
        returns.clear()

        for k, v in stats.items():
            if k != "n_episodes":
                self.logger.log_stat(
                    prefix + k + "_mean", v / stats["n_episodes"], self.t_env
                )
        stats.clear()
