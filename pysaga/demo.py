"""Exercise the environment: a random-policy episode, then a rewind check.

    python -m pysaga.demo
"""

import os
import time

import numpy as np

from . import bridge
from .env import DEFAULT_MAP, SagaEnv


def random_actions(env, rng):
    """Uniform over the available actions, which is what a mask is for."""
    out = []
    for avail in env.get_avail_actions():
        choices = np.flatnonzero(np.asarray(avail))
        out.append(int(rng.choice(choices)))
    return out


def main():
    rng = np.random.default_rng(0)
    env = SagaEnv(map_name=DEFAULT_MAP)

    info = env.get_env_info()
    print("environment")
    for k, v in info.items():
        print("   %-14s %s" % (k, v))

    obs, _ = env.reset(seed=42)
    print("\nshapes")
    print("   obs          %s x %d agents" % (np.shape(obs[0]), len(obs)))
    print("   state        %s" % (np.shape(env.get_state()),))
    print("   avail        %s" % (np.shape(env.get_avail_actions()),))

    print("\nepisode")
    total = np.zeros(env.n_agents)
    steps = 0
    t0 = time.time()
    while True:
        actions = random_actions(env, rng)
        obs, reward, terminated, truncated, extra = env.step(actions)
        total += np.asarray(reward, dtype=float)
        steps += 1
        if terminated or truncated:
            break
    dt = time.time() - t0
    print("   %d decisions in %.2fs (%.0f/s)" % (steps, dt, steps / dt))
    print("   ended by      %s" % ("termination" if terminated else "time limit"))
    print("   return        %s" % np.round(total, 2))
    print("   stats         %s" % extra)

    print("\nrewind across the bridge")
    env.reset(seed=7)
    for _ in range(25):
        env.step(random_actions(env, rng))
    env.save_state()
    at = env.state_hash()

    forward = []
    replay_rng = np.random.default_rng(99)
    for _ in range(30):
        env.step(random_actions(env, replay_rng))
        forward.append(env.state_hash())

    env.load_state()
    print("   restore exact       %s" % (env.state_hash() == at))

    again = []
    replay_rng = np.random.default_rng(99)
    for _ in range(30):
        env.step(random_actions(env, replay_rng))
        again.append(env.state_hash())
    print("   replay identical    %s  (%d decisions)" % (forward == again, len(again)))

    print("\ndeterminism")
    print("   build               %s" % bridge.build())
    print("   state hash          %d  (seed 42, 300 decisions chosen by rule:" % fixed_episode(env))
    print("                       the same number on every machine running this build)")

    # The replay goes where a player of the installed package can find it; a checkout
    # keeps its working files in the home folder, as run-local.sh does
    if bridge.installed():
        out = os.path.abspath("saga_replay.json")
    else:
        out = os.path.join(os.environ.get("SAGA_HOME", os.path.expanduser("~/.saga-online")),
                           "local", "saga_replay.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
    env.save_replay(out)
    print("   replay written      %s" % out)
    env.close()


def fixed_episode(env):
    """One episode's state hash with no random number generator in it: every action is
    picked by a rule from the available ones, so the hash depends on nothing but the
    simulation -- which StrictMath makes the same on every processor and Java."""
    env.reset(seed=42)
    for step in range(300):
        actions = []
        for agent, avail in enumerate(env.get_avail_actions()):
            choices = np.flatnonzero(np.asarray(avail))
            actions.append(int(choices[(step * 7 + agent * 3) % len(choices)]))
        _, _, terminated, truncated, _ = env.step(actions)
        if terminated or truncated:
            break
    return env.state_hash()


if __name__ == "__main__":
    main()
