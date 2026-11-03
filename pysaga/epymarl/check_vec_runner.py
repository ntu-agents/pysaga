#!/usr/bin/env python3
"""The vec runner fills its batch with exactly what N single environments would.

    python -m pysaga.epymarl.check_vec_runner <epymarl checkout> [n_envs] [key=value ...]

key=value sets an env_args entry, as a command line's "with env_args.key=value"
does: map_name=gen:forest map_seed=episode runs the batch on a map per episode.

Needs jpype, torch and the checkout set up by python -m pysaga.epymarl. Builds the arguments the way src/main.py does -- default.yaml,
the saga env config, the ippo alg config -- runs ONE batch through VecRunner with
the untrained policy, and then replays every world: its seed and the actions the
runner wrote into the batch, through a single SagaEnv, comparing the rewards, the
terminal flags, the observations, the masks and the state stored at every
timestep. That is the runner's whole job, and it is the part no environment test
can see: which row went to which world, at which timestep, in which dtype.
"""

import os
import sys
import types

import numpy as np
import torch as th
import yaml


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    checkout = os.path.abspath(sys.argv[1])
    n_envs = int(sys.argv[2]) if len(sys.argv) > 2 and "=" not in sys.argv[2] else 6
    overrides = dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a)
    sys.path.insert(0, os.path.join(checkout, "src"))

    from pysaga.env import SagaEnv
    from pysaga.epymarl.vec_runner import VecRunner
    from components.episode_buffer import ReplayBuffer
    from components.transforms import OneHot
    from controllers import REGISTRY as mac_REGISTRY
    from utils.logging import Logger, get_logger

    def load(rel):
        with open(os.path.join(checkout, "src", "config", rel)) as f:
            return yaml.safe_load(f)

    def update(d, u):
        for k, v in u.items():
            if isinstance(v, dict):
                d[k] = update(d.get(k, {}), v)
            else:
                d[k] = v
        return d

    config = load("default.yaml")
    config = update(config, load("envs/saga.yaml"))
    config = update(config, load("algs/ippo.yaml"))
    config.update(runner="vec", batch_size_run=n_envs, buffer_size=n_envs, batch_size=n_envs,
                  seed=12345, use_cuda=False, device="cpu")
    config["env_args"]["seed"] = config["seed"]
    config["env_args"].update(overrides)
    args = types.SimpleNamespace(**config)

    logger = Logger(get_logger())
    runner = VecRunner(args=args, logger=logger)
    env_info = runner.get_env_info()
    args.n_agents = env_info["n_agents"]
    args.n_actions = env_info["n_actions"]
    args.state_shape = env_info["state_shape"]

    scheme = {
        "state": {"vshape": env_info["state_shape"]},
        "obs": {"vshape": env_info["obs_shape"], "group": "agents"},
        "actions": {"vshape": (1,), "group": "agents", "dtype": th.long},
        "avail_actions": {"vshape": (env_info["n_actions"],), "group": "agents", "dtype": th.int},
        "terminated": {"vshape": (1,), "dtype": th.uint8},
    }
    scheme["reward"] = {"vshape": (1,)} if args.common_reward else {"vshape": (args.n_agents,)}
    groups = {"agents": args.n_agents}
    preprocess = {"actions": ("actions_onehot", [OneHot(out_dim=args.n_actions)])}
    buffer = ReplayBuffer(scheme, groups, args.buffer_size, env_info["episode_limit"] + 1,
                          preprocess=preprocess, device="cpu")
    mac = mac_REGISTRY[args.mac](buffer.scheme, groups, args)
    runner.setup(scheme=scheme, groups=groups, preprocess=preprocess, mac=mac)

    th.manual_seed(args.seed)
    batch = runner.run(test_mode=False)

    fail = 0

    def check(what, ok, detail=""):
        nonlocal fail
        print("  %-60s %s%s" % (what, "PASS" if ok else "FAIL", ("   " + detail) if detail else ""))
        if not ok:
            fail += 1

    filled = batch["filled"][:, :, 0].numpy()
    lengths = filled.sum(axis=1) - 1               # filled at reset, then once per step
    print("one batch of %d episodes, lengths %s, t_env %d" % (n_envs, lengths.tolist(), runner.t_env))
    check("t_env counts every step of every world", runner.t_env == int(lengths.sum()))
    check("every episode ran to a terminal or the limit", all(1 <= l <= env_info["episode_limit"] for l in lengths))

    print("\nreplaying every world through a single SagaEnv:")
    mismatch = {"map": 0, "reward": 0, "terminated": 0, "obs": 0, "avail": 0, "state": 0, "end": 0}
    for i in range(n_envs):
        single = SagaEnv(map_name=args.env_args["map_name"], map_seed=args.env_args.get("map_seed", "fixed"),
                         common_reward=args.common_reward, reward_scalarisation=args.reward_scalarisation)
        single.reset(seed=runner.env.episode_seed(i))
        if single.map_info()["sim_hash"] != runner.env.map_info(i)["sim_hash"]:
            mismatch["map"] += 1
        # What the batch holds before the first step must be what the world showed
        if not np.array_equal(batch["obs"][i, 0].numpy(), np.array(single.get_obs(), dtype=np.float32)):
            mismatch["obs"] += 1
        length = int(lengths[i])
        ended_at = None
        for t in range(length):
            acts = batch["actions"][i, t, :, 0].numpy().tolist()
            obs, r, term, trunc, _ = single.step(acts)
            stored_r = batch["reward"][i, t].numpy()
            if not np.allclose(stored_r, np.asarray(r, dtype=np.float32).reshape(-1)):
                mismatch["reward"] += 1
            if int(batch["terminated"][i, t, 0]) != int(term):
                mismatch["terminated"] += 1
            if not np.array_equal(batch["obs"][i, t + 1].numpy(), np.array(obs, dtype=np.float32)):
                mismatch["obs"] += 1
            if not np.array_equal(batch["avail_actions"][i, t + 1].numpy(), np.array(single.get_avail_actions())):
                mismatch["avail"] += 1
            if not np.array_equal(batch["state"][i, t + 1].numpy(), single.get_state()):
                mismatch["state"] += 1
            if term or trunc:
                ended_at = t
                break
        if ended_at != length - 1:
            mismatch["end"] += 1
    for k, v in mismatch.items():
        check("%s matches in every world at every timestep" % k, v == 0, "%d mismatches" % v)

    # The runner logs its stats at the end of the batch and clears them, as the
    # parallel runner does, so they are read back from the logger
    logged = {k: v[-1][1] for k, v in logger.stats.items()}
    check("the logged episode length is the batch's mean", "ep_length_mean" in logged
          and abs(float(logged["ep_length_mean"]) - float(lengths.mean())) < 1e-6,
          "%s against %.3f" % (logged.get("ep_length_mean"), lengths.mean()))
    check("the episode info reached the log, per team", {"kills_mean", "win_team1_mean", "win_team2_mean", "draw_mean", "episode_limit_mean"} <= set(logged),
          ", ".join(sorted(k for k in logged if k.endswith("_mean"))))
    check("every logged value is a number", all(isinstance(v, (int, float, np.integer, np.floating, bool)) for v in logged.values()))

    print("\n" + ("ALL PASS" if fail == 0 else "%d FAILURE(S)" % fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
