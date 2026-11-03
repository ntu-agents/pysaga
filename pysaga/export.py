#!/usr/bin/env python3
"""Export an EPyMARL checkpoint as a saga-policy file, the network Java runs.

    python -m pysaga.export MODEL [--step N] [--agent I] [--config CONFIG]
                               [-o OUT.policy] [--check [STEPS]]

MODEL is a results/models/<token> directory (its latest step, or --step N), a
<token>/<step> directory, or an agent.th. The run's configuration -- the network's
shape, the input EPyMARL built for it, and the environment it trained in -- is read
from the sacred run with the same seed under results/sacred (or --config points at
a config.json). --agent picks the learner: the row of the one-hot a shared network
was given (ippo), or the sub-network (ippo_ns).

The file carries the world the policy was trained in -- slots, progression,
observability, every observation field by name -- so saga.sim.rl.NeuralPolicy can
refuse a world laid out differently. --check runs STEPS decisions of the exported
policy through Java and through this script's own numpy forward on the same
observations, and reports the largest logit difference and any disagreement in the
action chosen: the writer, the reader and the two forwards agree, or it says so.

Needs torch to read a checkpoint; the check needs jpype and the built simulation.
"""

import argparse
import glob
import json
import os
import re
import sys

import numpy as np


def resolve_model(path, step=None):
    p = os.path.abspath(path)
    if os.path.isfile(p) and os.path.basename(p) == "agent.th":
        return os.path.dirname(p)
    if os.path.isfile(os.path.join(p, "agent.th")):
        return p
    steps = [d for d in os.listdir(p) if d.isdigit() and os.path.isfile(os.path.join(p, d, "agent.th"))]
    if not steps:
        raise SystemExit("no agent.th under %s" % p)
    d = str(step) if step is not None else max(steps, key=int)
    if d not in steps:
        raise SystemExit("no step %s under %s (have %s)" % (d, p, ", ".join(sorted(steps, key=int))))
    return os.path.join(p, d)


def token_seed(model_dir):
    m = re.search(r"_seed(\d+)_", model_dir)
    return int(m.group(1)) if m else None


def find_config(model_dir, explicit=None):
    """The sacred config of the run that saved this model: by seed, newest wins."""
    if explicit:
        with open(explicit) as f:
            return json.load(f), explicit
    seed = token_seed(model_dir)
    if seed is None:
        raise SystemExit("cannot read a seed out of %s; give --config" % model_dir)
    # <results>/models/<token>/<step> -> <results>/sacred
    results = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(model_dir).rstrip("/"))))
    hits = []
    for cfg in glob.glob(os.path.join(results, "sacred", "**", "config.json"), recursive=True):
        try:
            with open(cfg) as f:
                c = json.load(f)
        except (OSError, ValueError):
            continue
        if c.get("seed") == seed:
            hits.append((os.path.getmtime(cfg), cfg, c))
    if not hits:
        raise SystemExit("no sacred run with seed %d under %s; give --config" % (seed, os.path.join(results, "sacred")))
    hits.sort()
    return hits[-1][2], hits[-1][1]


def load_state(model_dir, agent):
    """The tensors of one learner's network, as float32 numpy arrays."""
    import torch
    sd = torch.load(os.path.join(model_dir, "agent.th"), map_location="cpu")
    keys = list(sd.keys())
    prefix = ""
    if any(k.startswith("agents.") for k in keys):          # a non-shared controller
        prefix = "agents.%d." % agent
        if not any(k.startswith(prefix) for k in keys):
            raise SystemExit("no agent %d in the checkpoint (keys: %s)" % (agent, ", ".join(keys)))
    return {k[len(prefix):]: sd[k].detach().cpu().numpy().astype(np.float32)
            for k in keys if k.startswith(prefix)}, prefix != ""


def write_policy(path, tensors, obs, actions, hidden, gru, agents, progression, observability,
                 fields, agent_onehot, last_action, origin="", algorithm="", training=None, normaliser=None):
    """The saga-policy format: whitespace separated, read by NeuralPolicy.parse."""
    with open(path, "w") as f:
        f.write("saga-policy 1\n")
        f.write("obs %d actions %d hidden %d rnn %s\n" % (obs, actions, hidden, "gru" if gru else "mlp"))
        f.write("agents %d progression %d observability %s\n" % (agents, 1 if progression else 0, observability))
        f.write("fields %d %s\n" % (len(fields), " ".join(fields)))
        f.write("agent_onehot %d %s\n" % (len(agent_onehot), " ".join("%g" % v for v in agent_onehot)))
        f.write("last_action %d\n" % (1 if last_action else 0))
        words = str(origin).split()
        f.write("origin %d %s\n" % (len(words), " ".join(words)))
        # What trained it, one word: a replay names a trained opponent by it ("ippo, w-g2")
        if algorithm:
            if len(str(algorithm).split()) != 1:
                raise ValueError("algorithm is one word, not %r" % (algorithm,))
            f.write("algorithm %s\n" % algorithm)
        # How it was trained (training_of): what a bot in a round plays it by
        if training:
            f.write("kit %s type %d frame_skip %d mode %s team_size %d\n" % (
                training["kit"], training["type"], training["frame_skip"], training["mode"], training["team_size"]))
            if training.get("bar") is not None:
                f.write("bar %d %s\n" % (len(training["bar"]), " ".join(str(v) for v in training["bar"])))
        # The observation standardised for learning (pysaga.normalise), which NeuralPolicy applies
        if normaliser is not None:
            if len(normaliser.obs_mean) != obs:
                raise ValueError("the normaliser has %d inputs, the observation %d" % (len(normaliser.obs_mean), obs))
            f.write("input_mean %d %s\n" % (obs, " ".join("%.9g" % v for v in normaliser.obs_mean)))
            f.write("input_std %d %s\n" % (obs, " ".join("%.9g" % v for v in normaliser.obs_std)))
            f.write("input_clip %.9g\n" % normaliser.clip)
        for name, a in tensors.items():
            a = np.asarray(a, dtype=np.float32)
            rows, cols = (a.shape[0], a.shape[1]) if a.ndim == 2 else (a.shape[0], 1)
            f.write("tensor %s %d %d\n" % (name, rows, cols))
            # nine significant digits round-trip a float32 exactly
            f.write(" ".join("%.9g" % v for v in a.reshape(-1)) + "\n")
        f.write("end\n")


def forward(t, gru, x, h):
    """RNNAgent in numpy: the reference the Java forward is checked against.

    In float64, deliberately: the tensors are float32 and so is Java's arithmetic,
    but Accelerate's float32 matmul on macOS raises spurious divide-by-zero and
    overflow warnings on inputs that are perfectly finite, and a double reference is
    nearer the truth both implementations approximate.
    """
    t = {k: np.asarray(v, dtype=np.float64) for k, v in t.items()}
    x = np.asarray(x, dtype=np.float64)
    h = np.asarray(h, dtype=np.float64)
    z = np.maximum(0, t["fc1.weight"] @ x + t["fc1.bias"])
    if gru:
        gi = t["rnn.weight_ih"] @ z + t["rnn.bias_ih"]
        gh = t["rnn.weight_hh"] @ h + t["rnn.bias_hh"]
        hd = h.shape[0]
        r = 1 / (1 + np.exp(-(gi[:hd] + gh[:hd])))
        zz = 1 / (1 + np.exp(-(gi[hd:2 * hd] + gh[hd:2 * hd])))
        n = np.tanh(gi[2 * hd:] + r * gh[2 * hd:])
        h = (1 - zz) * n + zz * h
    else:
        h = np.maximum(0, t["rnn.weight"] @ z + t["rnn.bias"])
    return t["fc2.weight"] @ h + t["fc2.bias"], h


def training_of(env, kw, agent):
    """How the policy was trained, as a bot in a round needs it (NeuralPolicy.Training).

    The kit the agent's character held -- "dealt", or "basic" for the weapon strike
    alone, which is also how a run that learns its own build (progression) starts --
    its character type, the ticks a decision lasted, the mode and team size, and for a
    dealt kit the hotbar as the environment dealt it: read from the environment after
    a reset, so the file holds what training held, not a copy of the rule.
    """
    import jpype
    jenv = env._env
    progression = bool(kw.get("progression", False))
    kit = "basic" if progression else str(kw.get("kit", "dealt"))
    mode = str(kw.get("mode", "duel"))
    team_size = int(kw.get("team_size", 0)) if mode in ("tdm", "dom", "ma", "team_deathmatch", "domination", "monster_attack") else 0
    env.reset(seed=1)
    slot = int(jenv.slotOf(agent))
    stride = int(jpype.JClass("saga.sim.GameState").HOTBAR_STRIDE)
    hotbar = jenv.world().state().hotbar
    bar = [int(hotbar[slot * stride + k]) for k in range(stride)] if kit == "dealt" else None
    return dict(kit=kit, type=int(jenv.type(agent)), frame_skip=int(jenv.frameSkip()), mode=mode,
                team_size=team_size, bar=bar)


def env_kwargs(env_args):
    """The environment the run trained in, as pysaga takes it."""
    kw = {k: v for k, v in env_args.items() if k not in ("seed", "root", "key", "map_name")}
    from pysaga.env import DEFAULT_MAP
    kw["map_name"] = env_args.get("map_name", DEFAULT_MAP)
    if isinstance(kw.get("observability"), dict):
        raise SystemExit("the run's observability is written out as channels; register it under a name "
                         "(pysaga.register_observability) and train with that, so the file can carry it")
    return kw


def export(model_dir, config, agent, out):
    from pysaga.env import SagaEnv

    tensors, non_shared = load_state(model_dir, agent)
    kw = env_kwargs(config["env_args"])
    env = SagaEnv(**kw)
    jenv = env._env

    obs = int(jenv.obsSize())
    actions = int(jenv.totalActions())
    agents = int(jenv.encoder().agents())                # the characters the observation describes, monsters too
    fields = [str(n) for n in jenv.obsFieldNamesOfSlot(0)]
    gru = bool(config.get("use_rnn", True)) and "rnn.weight_ih" in tensors
    if bool(config.get("use_rnn", True)) != gru:
        raise SystemExit("the config says use_rnn=%s but the checkpoint holds %s" % (
            config.get("use_rnn"), "a GRU" if "rnn.weight_ih" in tensors else "a linear layer"))
    hidden = int(tensors["fc1.weight"].shape[0])
    last_action = bool(config.get("obs_last_action", False)) and not non_shared
    agent_id = bool(config.get("obs_agent_id", False)) and not non_shared
    n_learners = env.n_agents
    if agent >= n_learners:
        raise SystemExit("--agent %d, but the run had %d learner(s)" % (agent, n_learners))
    onehot = np.eye(n_learners, dtype=np.float32)[agent] if agent_id else np.zeros(0, dtype=np.float32)

    inputs = obs + (actions if last_action else 0) + len(onehot)
    got = tensors["fc1.weight"].shape[1]
    if got != inputs:
        raise SystemExit("fc1 takes %d inputs; the run's observation (%d) + last action (%d) + agent id (%d) make %d"
                         % (got, obs, actions if last_action else 0, len(onehot), inputs))
    if tensors["fc2.weight"].shape[0] != actions:
        raise SystemExit("fc2 gives %d actions; the environment has %d" % (tensors["fc2.weight"].shape[0], actions))

    origin = "%s agent %d seed %s" % (model_dir, agent, config.get("seed"))
    # The run's inputs were standardised by the environment (env_args normalise): the file carries
    # the same statistics, so the policy plays as it trained
    from pysaga.normalise import Normaliser
    norm = Normaliser.load(kw["normalise"]) if kw.get("normalise") else None
    write_policy(out, tensors, obs, actions, hidden, gru, agents, bool(kw.get("progression", False)),
                 env.observability, fields, onehot, last_action, origin,
                 algorithm=str(config.get("name") or ""), training=training_of(env, kw, agent), normaliser=norm)
    meta = dict(obs=obs, actions=actions, hidden=hidden, gru=gru, agents=agents, learners=n_learners,
                last_action=last_action, onehot=onehot, slot=int(jenv.slotOf(agent)), norm=norm)
    return env, tensors, meta


def check(env, tensors, meta, path, steps):
    """The Java policy against the numpy forward, on the same observations."""
    import jpype
    NeuralPolicy = jpype.JClass("saga.sim.rl.NeuralPolicy")
    jenv = env._env
    p = NeuralPolicy.load(path)
    p.bind(jenv.world(), jenv.observability())
    env.reset(seed=1)

    slot = meta["slot"]
    h = np.zeros(meta["hidden"], dtype=np.float32)
    last = -1
    worst = 0.0
    disagree = 0
    n = 0
    for _ in range(steps):
        # One state, two paths: Java is handed the raw observation and standardises it itself,
        # the reference the run's own (normalised, as the environment fed it)
        obs = np.array(jenv.obsOfSlot(slot), dtype=np.float32)
        avail = np.array(jenv.availActionsOfSlot(slot), dtype=np.int32)
        x = [meta["norm"].obs(obs) if meta.get("norm") is not None else obs]
        if meta["last_action"]:
            x.append(np.eye(meta["actions"], dtype=np.float32)[last] if last >= 0 else np.zeros(meta["actions"], np.float32))
        x.append(meta["onehot"])
        ref, h = forward(tensors, meta["gru"], np.concatenate(x), h)
        legal = np.where(avail != 0)[0]
        ref_best = int(legal[np.argmax(ref[legal])])

        a = int(p.act(jpype.JArray(jpype.JFloat)(obs.tolist()), jpype.JArray(jpype.JInt)(avail.tolist())))
        got = np.array(p.lastLogits(), dtype=np.float32)
        worst = max(worst, float(np.max(np.abs(got - ref))))
        if a != ref_best:
            disagree += 1
        last = a
        n += 1

        actions = [0] * env.n_agents
        actions[[int(jenv.slotOf(k)) for k in range(env.n_agents)].index(slot)] = a
        _, _, term, trunc, _ = env.step(actions)
        if term or trunc:
            env.reset(seed=n)
            h = np.zeros_like(h)
            last = -1
            p.reset()
    return worst, disagree, n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("--step", type=int)
    ap.add_argument("--agent", type=int, default=0)
    ap.add_argument("--config")
    ap.add_argument("-o", "--out")
    ap.add_argument("--check", nargs="?", const=300, type=int)
    args = ap.parse_args()

    model_dir = resolve_model(args.model, args.step)
    config, cfg_path = find_config(model_dir, args.config)
    out = args.out or (os.path.basename(os.path.dirname(model_dir)).split("_")[0]
                       + "-" + os.path.basename(model_dir) + "-a%d.policy" % args.agent)
    env, tensors, meta = export(model_dir, config, args.agent, out)
    print("exported %s (agent %d, %s, hidden %d, %d obs, %d actions, %d slots) from %s\n  config %s"
          % (out, args.agent, "gru" if meta["gru"] else "mlp", meta["hidden"], meta["obs"], meta["actions"],
             meta["agents"], model_dir, cfg_path))
    if args.check:
        worst, disagree, n = check(env, tensors, meta, out, args.check)
        ok = worst < 1e-4 and disagree == 0
        print("check: %d decisions, largest logit difference %.3g, %d action disagreements -> %s"
              % (n, worst, disagree, "PASS" if ok else "FAIL"))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
