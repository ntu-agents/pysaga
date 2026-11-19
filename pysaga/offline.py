"""Offline learning on recorded rounds: masked behaviour cloning and discrete IQL.

The design test of the human play data plan trains these on the datasets
pysaga.dataset writes (recorded rounds) and on native ones (the same bots in the
environment, native()), and plays the result in Java, in balance and in a client.

The networks have the shape of EPyMARL's agent without its recurrence -- fc1, a hidden
layer (named rnn, as NeuralPolicy reads an MLP agent), fc2 -- so pysaga.export's
write_policy makes a saga-policy file of one, and NeuralPolicy plays it: sample:<file> in
a scripted slot, a bot in a round.

    python -m pysaga.offline native --policy melee --opponent melee --episodes 20 --out <dir>
    python -m pysaga.offline bc  --data <dir>... --out policy.txt [--type 0] [--steps N] [--seed S]
    python -m pysaga.offline iql --data <dir>... --out policy.txt [--type 0] [--steps N] [--seed S]
    python -m pysaga.offline evaluate --policy policy.txt [--opponent melee] [--episodes 200]

Masks are respected everywhere: an action the mask refuses has no probability, and no
value is backed up through one. Plain torch: no offline-RL library.
"""

import argparse
import glob
import json
import os
import pathlib

import numpy as np

from . import bridge
from .dataset import write_round, Pseudonyms
from .env import _observability, _reward, _scenario

MAP = None            # the design test's map: the fixture every client scenario plays


def _map():
    return MAP or str(pathlib.Path(bridge.fixtures(), "Greenhaven.json"))


def _env(opponent, observability="los", reward="ladder", map_name=None, root=None, frame_skip=4):
    """A duel on the basic kit at a decision rate, the learner's slot left to a collector, the other to `opponent`."""
    bridge.start_jvm(root)
    import jpype
    import jpype.imports  # noqa: F401
    from saga.sim.rl import SagaEnv, Scenario, Observability, RewardFunction
    obs = _observability(Observability, observability)
    sc = _scenario(Scenario, "duel", map_name or _map(), 1, False, kit="basic", frame_skip=frame_skip)
    env = SagaEnv(bridge.repo_root(root), sc, obs)
    env.setScripted(1, opponent)
    env.setReward(_reward(RewardFunction, reward))
    return env, obs


def native(policy, opponent, episodes, out, seed=1, observability="los", reward="ladder", name="native", frame_skip=4):
    """The same bot played headlessly in the learner's slot: the native dataset, in the same layout."""
    env, obs = _env(opponent, observability, reward, frame_skip=frame_skip)
    import jpype
    from saga.sim.rl import PolicyDataset
    from .dataset import lag_arrays, layout_of
    d = PolicyDataset.collect(env, policy, obs, int(episodes), int(seed))
    dynamics = int(jpype.JClass("saga.sim.World").DYNAMICS)
    fields = [str(f) for f in env.obsFieldNames(0)]
    trajectories = []
    for tr in d.trajectories:
        n = int(tr.length)
        trajectories.append(dict(
            who=str(policy), slot=int(tr.slot), bot=True, type=int(tr.type),
            observations=np.asarray(tr.obs, dtype=np.float32).reshape(n, int(d.obsSize)),
            actions=np.asarray(tr.actions, dtype=np.int64),
            masks=np.asarray(tr.masks, dtype=np.int8).reshape(n, int(d.totalActions)),
            rewards=np.asarray(tr.rewards, dtype=np.float32),
            ticks=np.asarray(tr.ticks, dtype=np.int64),
            dynamics=np.full(n, dynamics, dtype=np.int32),
            **lag_arrays(tr),                       # a headless episode has no lag: -1 and 0 throughout
            terminated=bool(tr.terminated), truncated=bool(tr.truncated)))
    made = dict(observability=observability, agents=int(d.agents), progression=False, reward=reward,
                frame_skip=int(d.frameSkip), obs_size=int(d.obsSize), n_actions=int(d.totalActions),
                layout=layout_of(fields, int(d.totalActions), int(d.agents)), fields=fields, dynamics=dynamics,
                schema=int(jpype.JClass("saga.sim.GameState").SCHEMA),
                native=dict(policy=policy, opponent=opponent, episodes=int(episodes), seed=int(seed)))
    counts = {str(k): int(d.counts.get(k)) for k in d.counts.keySet()}
    return write_round(trajectories, counts, made, out, name, Pseudonyms(None))


def load(dirs, type_=None, dynamics=None):
    """Transitions from datasets' npz files: (s, a, r, s', done, mask, mask'), the episodes of one character type.

    Datasets of one decision rate only: a transition is a decision, and two rates are two
    different problems, and of one observation layout (each dataset's JSON says it; datasets
    of two are aligned first, python -m pysaga.dataset align). The rate comes back as
    data["frame_skip"], which training passes on to the policy file and evaluation to the
    environment. Each transition's dynamics (the
    World.DYNAMICS its round was played under) comes back as data["dynamics"], for a model
    that conditions on it; dynamics, a set, keeps only the episodes played under those."""
    obs, act, rew, nxt, done, mask, nmask, dyn = [], [], [], [], [], [], [], []
    rates, layouts = {}, {}
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, "*.npz"))):
            z = np.load(f)
            meta = json.load(open(f[:-4] + ".json"))
            rates.setdefault(int(meta.get("frame_skip", 4)), []).append(f)
            layouts.setdefault(meta.get("layout", "unnamed"), []).append(f)
            ep = z["episode"]
            for k, e in enumerate(meta["episodes"]):
                if type_ is not None and e.get("type") != type_:
                    continue
                rows = np.nonzero(ep == k)[0]
                if len(rows) < 2:
                    continue
                played = int(z["dynamics"][rows[0]])
                if dynamics is not None and played not in dynamics:
                    continue
                dyn.append(np.full(len(rows) - 1, played, dtype=np.int32))
                o, a, r, m = z["observations"][rows], z["actions"][rows], z["rewards"][rows], z["masks"][rows]
                end = bool(e.get("terminated"))
                obs.append(o[:-1]); act.append(a[:-1]); rew.append(r[:-1]); mask.append(m[:-1])
                nxt.append(o[1:]); nmask.append(m[1:])
                dn = np.zeros(len(rows) - 1, dtype=np.float32)
                if end:
                    dn[-1] = 1.0
                done.append(dn)
    if len(rates) > 1:
        raise SystemExit("datasets of different decision rates (frame_skip %s) cannot be trained on together: %s"
                         % (sorted(rates), {k: v[:2] for k, v in rates.items()}))
    if len(layouts) > 1:
        raise SystemExit("datasets of different observation layouts cannot be trained on together until aligned "
                         "(python -m pysaga.dataset align): %s" % {k: v[:2] for k, v in layouts.items()})
    if not obs:
        raise SystemExit("no episodes in %s" % (dirs,))
    cat = np.concatenate
    return dict(obs=cat(obs), act=cat(act), rew=cat(rew), nxt=cat(nxt), done=cat(done),
                mask=cat(mask).astype(np.float32), nmask=cat(nmask).astype(np.float32), dynamics=cat(dyn),
                frame_skip=next(iter(rates)))


def _torch():
    import torch
    import torch.nn as nn

    class Net(nn.Module):
        """fc1, a hidden layer, fc2 -- EPyMARL's agent shape without its recurrence."""
        def __init__(self, n_in, n_out, hidden=128):
            super().__init__()
            self.fc1 = nn.Linear(n_in, hidden)
            self.rnn = nn.Linear(hidden, hidden)
            self.fc2 = nn.Linear(hidden, n_out)

        def forward(self, x):
            return self.fc2(torch.relu(self.rnn(torch.relu(self.fc1(x)))))

    return torch, nn, Net


def _masked(logits, mask):
    return logits.masked_fill(mask <= 0, -1e9)


def _normalised(data, normaliser):
    """The data's observations standardised (pysaga.normalise): the normaliser given, or one fitted on them.

    The network trains on standardised inputs and the file carries the statistics, which
    NeuralPolicy applies: positions over 2048 are too small a scale to learn from."""
    from .normalise import Normaliser
    norm = normaliser if normaliser is not None else Normaliser.fit(data["obs"])
    out = dict(data)
    out["obs"] = norm.obs(data["obs"])
    if "nxt" in data:
        out["nxt"] = norm.obs(data["nxt"])
    return out, norm


def train_bc(data, steps=20000, hidden=128, lr=1e-3, batch=256, seed=1, normaliser=None):
    """Masked behaviour cloning: the label's log-probability among the actions the mask allows."""
    torch, nn, Net = _torch()
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    data, norm = _normalised(data, normaliser)
    t = {k: torch.as_tensor(v) for k, v in data.items() if isinstance(v, np.ndarray)}
    net = Net(t["obs"].shape[1], t["mask"].shape[1], hidden)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    n = len(t["act"])
    for step in range(steps):
        i = torch.as_tensor(rng.integers(0, n, batch))
        logits = _masked(net(t["obs"][i]), t["mask"][i])
        loss = nn.functional.cross_entropy(logits, t["act"][i])
        opt.zero_grad(); loss.backward(); opt.step()
    net.normaliser = norm
    return net


def train_iql(data, steps=20000, hidden=128, lr=3e-4, batch=256, seed=1, gamma=0.99, tau=0.7, beta=3.0,
              normaliser=None):
    """Discrete IQL: Q by expectile regression on V, V of the data's actions, the policy by advantage-weighted cloning."""
    torch, nn, Net = _torch()
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    data, norm = _normalised(data, normaliser)
    t = {k: torch.as_tensor(v) for k, v in data.items() if isinstance(v, np.ndarray)}
    n_in, n_act = t["obs"].shape[1], t["mask"].shape[1]
    q1, q2, v, pi = Net(n_in, n_act, hidden), Net(n_in, n_act, hidden), Net(n_in, 1, hidden), Net(n_in, n_act, hidden)
    q1t, q2t = Net(n_in, n_act, hidden), Net(n_in, n_act, hidden)
    q1t.load_state_dict(q1.state_dict()); q2t.load_state_dict(q2.state_dict())
    oq = torch.optim.Adam(list(q1.parameters()) + list(q2.parameters()), lr=lr)
    ov = torch.optim.Adam(v.parameters(), lr=lr)
    op = torch.optim.Adam(pi.parameters(), lr=lr)
    n = len(t["act"])
    for step in range(steps):
        i = torch.as_tensor(rng.integers(0, n, batch))
        s, a, r, s2, d = t["obs"][i], t["act"][i], t["rew"][i], t["nxt"][i], t["done"][i]
        with torch.no_grad():
            qt = torch.min(q1t(s), q2t(s)).gather(1, a[:, None]).squeeze(1)
        # V: an expectile of the data's Q
        diff = qt - v(s).squeeze(1)
        w = torch.where(diff > 0, tau, 1 - tau)
        lv = (w * diff ** 2).mean()
        ov.zero_grad(); lv.backward(); ov.step()
        # Q: one step through V, never through an action the mask refuses
        with torch.no_grad():
            target = r + gamma * (1 - d) * v(s2).squeeze(1)
        lq = ((q1(s).gather(1, a[:, None]).squeeze(1) - target) ** 2).mean() + \
             ((q2(s).gather(1, a[:, None]).squeeze(1) - target) ** 2).mean()
        oq.zero_grad(); lq.backward(); oq.step()
        # The policy: the data's actions, weighted by their advantage
        with torch.no_grad():
            adv = qt - v(s).squeeze(1)
            weight = torch.clamp(torch.exp(beta * adv), max=100.0)
        logp = torch.log_softmax(_masked(pi(s), t["mask"][i]), dim=1).gather(1, a[:, None]).squeeze(1)
        lp = -(weight * logp).mean()
        op.zero_grad(); lp.backward(); op.step()
        with torch.no_grad():
            for net, tgt in ((q1, q1t), (q2, q2t)):
                for p_, pt in zip(net.parameters(), tgt.parameters()):
                    pt.mul_(0.995).add_(0.005 * p_)
    pi.normaliser = norm
    return pi


def export(net, path, observability="los", algorithm="bc", root=None, frame_skip=4):
    """A saga-policy file of the network, laid out for the design test's duel on the basic kit, at its data's rate."""
    from .export import write_policy
    env, obs = _env("melee", observability, root=root, frame_skip=frame_skip)
    fields = [str(f) for f in env.obsFieldNamesOfSlot(0)]
    # The observability as a spec the reader parses back, its terrain radius stated (pysaga's rule)
    spec = observability if "terrain" in str(observability) else "%s+terrain:%d" % (observability, int(obs.terrain()))
    tensors = {k: v.detach().numpy() for k, v in net.state_dict().items()}
    hidden = int(tensors["fc1.weight"].shape[0])
    env.reset(1)
    import jpype
    stride = int(jpype.JClass("saga.sim.GameState").HOTBAR_STRIDE)
    training = dict(kit="basic", type=int(env.type(0)), frame_skip=int(env.frameSkip()), mode="duel",
                    team_size=0, bar=None)
    write_policy(path, tensors, len(fields), int(tensors["fc2.weight"].shape[0]), hidden, False,
                 int(env.encoder().agents()), False, spec, fields, [], False,
                 origin="pysaga.offline", algorithm=algorithm, training=training,
                 normaliser=getattr(net, "normaliser", None))
    return path


def evaluate(policy, opponent="melee", episodes=200, seed=1000, observability="los", reward="ladder", frame_skip=None):
    """A policy (a file, or a bot's name) in the learner's slot: win, loss, draw and timeout shares, mean return.

    In an environment of the policy file's own decision rate; a bot's name plays at
    frame_skip (4 if not given). A file asked to play at another rate is refused."""
    spec = policy if not os.path.isfile(str(policy)) else "sample:" + os.path.abspath(policy)
    if os.path.isfile(str(policy)):
        # The file's rate as the game reads it (NeuralPolicy, the one reader of the format)
        bridge.start_jvm(None)
        import jpype
        own = int(jpype.JClass("saga.sim.rl.NeuralPolicy").weights(os.path.abspath(policy)).training.frameSkip)
        if frame_skip is not None and int(frame_skip) != own:
            raise SystemExit("%s decides every %d ticks, not %d" % (policy, own, int(frame_skip)))
        frame_skip = own
    env, obs = _env(opponent, observability, reward, frame_skip=int(frame_skip or 4))
    from saga.sim.rl import PolicyDataset
    r = [float(x) for x in PolicyDataset.evaluate(env, spec, obs, int(episodes), int(seed))]
    return dict(win=r[0], loss=r[1], draw=r[2], timeout=r[3], ret=r[4])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline learning on recorded rounds.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("native"); n.add_argument("--policy", default="melee"); n.add_argument("--opponent", default="melee")
    n.add_argument("--episodes", type=int, default=20); n.add_argument("--seed", type=int, default=1); n.add_argument("--out", required=True)
    n.add_argument("--frame-skip", type=int, default=4, help="ticks of 50 ms a decision (4)")
    for name in ("bc", "iql"):
        t = sub.add_parser(name); t.add_argument("--data", nargs="+", required=True); t.add_argument("--out", required=True)
        t.add_argument("--type", type=int); t.add_argument("--steps", type=int, default=20000); t.add_argument("--seed", type=int, default=1)
    e = sub.add_parser("evaluate"); e.add_argument("--policy", required=True); e.add_argument("--opponent", default="melee")
    e.add_argument("--episodes", type=int, default=200); e.add_argument("--seed", type=int, default=1000)
    e.add_argument("--frame-skip", type=int, default=None, help="for a bot's name; a policy file plays at its own rate")
    a = ap.parse_args(argv)
    if a.cmd == "native":
        meta = native(a.policy, a.opponent, a.episodes, a.out, a.seed, frame_skip=a.frame_skip)
        print("Native: %d episode(s), %d decisions in %s" % (len(meta["episodes"]), sum(x["decisions"] for x in meta["episodes"]), a.out))
    elif a.cmd in ("bc", "iql"):
        data = load(a.data, a.type)
        net = (train_bc if a.cmd == "bc" else train_iql)(data, steps=a.steps, seed=a.seed)
        export(net, a.out, algorithm=a.cmd, frame_skip=data["frame_skip"])
        print("%s: trained on %d transitions, written to %s" % (a.cmd.upper(), len(data["act"]), a.out))
    else:
        print(json.dumps(evaluate(a.policy, a.opponent, a.episodes, a.seed, frame_skip=a.frame_skip)))


if __name__ == "__main__":
    main()
