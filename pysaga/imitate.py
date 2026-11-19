"""Behaviour cloning matched against its expert (the plan bc-matches-expert).

An expert -- a scripted bot or a trained policy -- plays a duel against an opponent in
the imitation harness (saga.sim.rl.Imitation): tick by tick, each on the world's grid at
its own rate, the expert's action landing `delay` ticks after it was decided. Its
decisions make the dataset: each one's observation, mask and the expert's action. A clone
is trained on them by masked behaviour cloning, written as a saga-policy file, and played
in the same harness with a shadow copy of the expert asked at every one of its
decisions. No reward is read anywhere: imitation needs none.

What "matches" means is the plan's, and is measured here:

  agreement   the share of the clone's decisions on which the shadow expert chose the
              same action (on the clone's own states), and on held-out expert states;
  outcomes    kills, deaths, damage dealt and taken, episode length, and the shares of
              won, lost, drawn and timed-out episodes, against the expert's own;
  equivalent  each share within 5 points, each per-episode mean's 95% Welch interval of
              the difference inside +-max(10% of the expert's mean, a floor).

A library, used from Python: docs/imitation.md (public/docs here) walks through it. One
command besides, for a policy's play under lag:

    python -m pysaga.imitate lag-sweep <policy> [--opponent kite] [--shadow melee]
        [--delays 0,1,2,3,5] [--recorded rounds/*.npz] [--episodes 200]

plays the policy with its actions landing each delay late, and with delays drawn per
action from recorded play (the seen_distance of datasets pysaga.dataset wrote), and prints
the outcomes and the agreement with the shadow, a row a delay.
"""

import argparse
import json
import math
import os
import pathlib

import numpy as np

from . import bridge
from .env import _observability
from .normalise import Normaliser

FLOORS = dict(kills=0.05, deaths=0.05, dealt=2.0, taken=2.0, ticks=20.0)
SHARES = ("win", "loss", "draw", "timeout")


def open_map():
    return str(pathlib.Path(bridge.fixtures(), "open60x50.json"))


def make_env(map_name=None, observability="full", root=None):
    """A duel of two learners on the basic kit at frame_skip 1: the harness's environment."""
    bridge.start_jvm(root)
    import jpype.imports  # noqa: F401
    from saga.sim.rl import SagaEnv, Scenario, Observability
    obs = _observability(Observability, observability)
    sc = Scenario.withFrameSkip(Scenario.withBasicKit(Scenario.duel(map_name or open_map())), 1)
    return SagaEnv(bridge.repo_root(root), sc, obs), obs


def run(env, actor, opponent, episodes, seed, pace=4, opp_pace=4, delay=0, epsilon=0.0,
        shadow=None, actor_lag=0, shadow_lag=0, record=False, opp_delay=0, delays=None, opp_delays=None):
    """Episodes of `actor` against `opponent` in the harness: outcomes, agreement, and the decisions if recorded.

    `delays` and `opp_delays`, where given, are lists of delays in ticks: each action's delay
    is drawn from its player's list (every entry equally likely) in place of the fixed one.
    """
    import jpype
    from saga.sim.rl import Imitation
    ints = lambda xs: None if xs is None else jpype.JArray(jpype.JInt)([int(x) for x in xs])
    r = Imitation.play(env, actor, int(actor_lag), shadow, int(shadow_lag), opponent, int(pace), int(opp_pace),
                       int(delay), int(opp_delay), ints(delays), ints(opp_delays), float(epsilon), int(episodes),
                       int(seed), bool(record))
    out = dict(kills=np.asarray(r.kills, float), deaths=np.asarray(r.deaths, float),
               dealt=np.asarray(r.dealt, float), taken=np.asarray(r.taken, float),
               ticks=np.asarray(r.ticks, float), outcome=np.asarray(r.outcome, int),
               decisions=int(r.decisions), agreed=int(r.agreed),
               landed_after=np.asarray(r.landedAfter, dtype=np.int64), never_landed=int(r.neverLanded))
    if shadow is not None:
        n = int(env.totalActions())
        out["confusion"] = np.asarray(r.confusion, dtype=np.int64).reshape(n, n)
        out["margin_agreed"] = np.asarray(r.marginAgreed, dtype=np.int64)
        out["margin_disagreed"] = np.asarray(r.marginDisagreed, dtype=np.int64)
    if record:
        d = r.data
        obs, act, mask, ep = [], [], [], []
        for k, tr in enumerate(d.trajectories):
            n = int(tr.length)
            obs.append(np.asarray(tr.obs, dtype=np.float32).reshape(n, int(d.obsSize)))
            act.append(np.asarray(tr.actions, dtype=np.int64))
            mask.append(np.asarray(tr.masks, dtype=np.int8).reshape(n, int(d.totalActions)))
            ep.append(np.full(n, k, dtype=np.int32))
        out["data"] = dict(obs=np.concatenate(obs), act=np.concatenate(act), mask=np.concatenate(mask),
                           episode=np.concatenate(ep))
    return out


def merge(*datas):
    """Datasets one after another, their episodes renumbered apart."""
    out, base = {k: [] for k in ("obs", "act", "mask", "episode")}, 0
    for d in datas:
        for k in ("obs", "act", "mask"):
            out[k].append(d[k])
        out["episode"].append(d["episode"] + base)
        base += int(d["episode"].max()) + 1
    return {k: np.concatenate(v) for k, v in out.items()}


def shift(data):
    """The falsifier: each label replaced by the next decision's in its episode (the last dropped)."""
    keep = np.nonzero(data["episode"][:-1] == data["episode"][1:])[0]
    return dict(obs=data["obs"][keep], act=data["act"][keep + 1], mask=data["mask"][keep],
                episode=data["episode"][keep])


def inputs(data, last_action, n_actions):
    """The network's input: the observation, and the previous label as a one-hot (zeros at an episode's start)."""
    x = data["obs"]
    if not last_action:
        return x
    prev = np.zeros((len(x), n_actions), dtype=np.float32)
    rows = np.nonzero(np.r_[False, data["episode"][1:] == data["episode"][:-1]])[0]
    prev[rows, data["act"][rows - 1]] = 1.0
    return np.concatenate([x, prev], axis=1)


def _torch():
    import torch
    import torch.nn as nn

    class Standardise(nn.Module):
        """The observation part of the input standardised as pysaga.normalise does it -- the
        same statistics NeuralPolicy applies from the file -- the last action untouched."""
        def __init__(self, norm):
            super().__init__()
            self.register_buffer("mean", torch.as_tensor(norm.obs_mean))
            self.register_buffer("std", torch.as_tensor(norm.obs_std))
            self.clip = float(norm.clip)

        def forward(self, x):
            n = self.mean.shape[0]
            z = torch.clamp((x[..., :n] - self.mean) / self.std, -self.clip, self.clip)
            return torch.cat([z, x[..., n:]], dim=-1)

    class Net(nn.Module):
        """fc1, a hidden layer, fc2 -- EPyMARL's agent shape without its recurrence (what NeuralPolicy reads)."""
        def __init__(self, n_in, n_out, hidden, norm=None):
            super().__init__()
            self.norm = Standardise(norm) if norm is not None else None
            self.normaliser = norm
            self.fc1 = nn.Linear(n_in, hidden)
            self.rnn = nn.Linear(hidden, hidden)
            self.fc2 = nn.Linear(hidden, n_out)

        def forward(self, x):
            if self.norm is not None:
                x = self.norm(x)
            return self.fc2(torch.relu(self.rnn(torch.relu(self.fc1(x)))))

    class Recurrent(nn.Module):
        """fc1, a GRU cell, fc2 -- EPyMARL's RNNAgent, which NeuralPolicy plays as rnn gru."""
        def __init__(self, n_in, n_out, hidden, norm=None):
            super().__init__()
            self.norm = Standardise(norm) if norm is not None else None
            self.normaliser = norm
            self.fc1 = nn.Linear(n_in, hidden)
            self.rnn = nn.GRUCell(hidden, hidden)
            self.fc2 = nn.Linear(hidden, n_out)

        def forward(self, x, h):
            """One step: logits and the next hidden state."""
            if self.norm is not None:
                x = self.norm(x)
            h = self.rnn(torch.relu(self.fc1(x)), h)
            return self.fc2(h), h

    Net.Recurrent = Recurrent
    return torch, nn, Net


def _episodes(data, rows):
    """The episodes the rows belong to, each as (start, end) of a contiguous run."""
    ep = data["episode"]
    cut = np.r_[0, np.nonzero(ep[1:] != ep[:-1])[0] + 1, len(ep)]
    return [(int(a), int(b)) for a, b in zip(cut[:-1], cut[1:]) if ep[a] in rows]


def train_gru(data, steps=20000, hidden=256, lr=1e-3, batch=64, chunk=32, burn=8, seed=1, holdout=0.1,
              last_action=False, normaliser=None):
    """Masked BC of a GRU clone, on chunks of episodes.

    A chunk starting inside an episode runs `burn` decisions from a zero hidden state before
    its labels count; one starting at an episode's first decision counts from there, as the
    policy plays (NeuralPolicy starts each episode from zero)."""
    torch, nn, Net = _torch()
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    n_actions = data["mask"].shape[1]
    x = inputs(data, last_action, n_actions)
    ok = data["mask"][np.arange(len(data["act"])), data["act"]] != 0
    eps = np.unique(data["episode"])
    held = set(rng.choice(eps, max(1, int(len(eps) * holdout)), replace=False).tolist()) if holdout else set()
    train_eps = _episodes(data, set(eps.tolist()) - held)
    held_eps = _episodes(data, held)
    tr_rows = np.concatenate([np.arange(a, b) for a, b in train_eps])
    # The inputs standardised (pysaga.normalise): the normaliser given -- one a reinforcement
    # learner will be fed through too -- or one fitted on the training episodes
    norm = normaliser if normaliser is not None else Normaliser.fit(data["obs"][tr_rows])
    net = Net.Recurrent(x.shape[1], n_actions, hidden, norm)
    X = torch.as_tensor(x, dtype=torch.float32)
    A = torch.as_tensor(data["act"])
    M = torch.as_tensor(data["mask"].astype(np.float32))
    OK = torch.as_tensor(ok)
    # Chunk starts: every decision of a training episode with `chunk` decisions after it in the episode
    starts, first = [], []
    for a, b in train_eps:
        if b - a >= chunk:
            r = np.arange(a, b - chunk + 1)
            starts.append(r)
            first.append(r == a)
    starts, first = np.concatenate(starts), np.concatenate(first)
    heads = np.nonzero(first)[0]
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    offs = torch.arange(chunk)
    for step in range(steps):
        # A quarter of the chunks from an episode's start, the rest anywhere
        pick = np.where(rng.random(batch) < 0.25, rng.choice(heads, batch), rng.integers(0, len(starts), batch))
        s0 = torch.as_tensor(starts[pick])
        f0 = torch.as_tensor(first[pick])
        idx = s0[:, None] + offs[None, :]
        h = torch.zeros(batch, hidden)
        loss, count = 0.0, 0
        for t in range(chunk):
            q, h = net(X[idx[:, t]], h)
            w = OK[idx[:, t]] & (f0 | (t >= burn))
            if w.any():
                q = q.masked_fill(M[idx[:, t]] <= 0, -1e9)
                loss = loss + nn.functional.cross_entropy(q[w], A[idx[:, t]][w], reduction="sum")
                count += int(w.sum())
        loss = loss / max(1, count)
        opt.zero_grad(); loss.backward()
        nn.utils.clip_grad_norm_(net.parameters(), 10.0)
        opt.step(); sched.step()

    def acc(episodes):
        """Each episode played through from a zero hidden state, as the policy plays."""
        if not episodes:
            return float("nan")
        good = total = 0
        with torch.no_grad():
            for k in range(0, len(episodes), 256):
                group = episodes[k:k + 256]
                T = max(b - a for a, b in group)
                h = torch.zeros(len(group), hidden)
                for t in range(T):
                    live = [(j, a + t) for j, (a, b) in enumerate(group) if a + t < b]
                    js = torch.as_tensor([j for j, _ in live]); rows = torch.as_tensor([r for _, r in live])
                    q, hn = net(X[rows], h[js])
                    h = h.clone(); h[js] = hn
                    p = q.masked_fill(M[rows] <= 0, -1e9).argmax(1)
                    w = OK[rows]
                    good += int((p[w] == A[rows][w]).sum()); total += int(w.sum())
        return good / max(1, total)
    info = dict(train_acc=acc(train_eps[:200]), heldout_acc=acc(held_eps), refused=int((~ok).sum()),
                rows=int(len(tr_rows)), gru=True, hidden=hidden, steps=steps, chunk=chunk, burn=burn,
                last_action=bool(last_action))
    return net, info


def train(data, steps=30000, hidden=256, lr=1e-3, batch=512, seed=1, last_action=False, holdout=0.1, standardise=True,
          normaliser=None):
    """Masked BC. A label the mask refuses is left out (counted): a masked policy can never take it.

    Episodes are split, a `holdout` share held back for the held-out accuracy."""
    torch, nn, Net = _torch()
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    n_actions = data["mask"].shape[1]
    x = inputs(data, last_action, n_actions)
    ok = data["mask"][np.arange(len(data["act"])), data["act"]] != 0
    eps = np.unique(data["episode"])
    held = set(rng.choice(eps, max(1, int(len(eps) * holdout)), replace=False).tolist()) if holdout else set()
    is_held = np.isin(data["episode"], list(held))
    tr = np.nonzero(ok & ~is_held)[0]
    va = np.nonzero(ok & is_held)[0]
    X = torch.as_tensor(x, dtype=torch.float32)
    A = torch.as_tensor(data["act"])
    M = torch.as_tensor(data["mask"].astype(np.float32))
    norm = None
    if standardise:
        norm = normaliser if normaliser is not None else Normaliser.fit(data["obs"][tr])
    net = Net(x.shape[1], n_actions, hidden, norm)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    for step in range(steps):
        i = torch.as_tensor(rng.choice(tr, batch))
        logits = net(X[i]).masked_fill(M[i] <= 0, -1e9)
        loss = nn.functional.cross_entropy(logits, A[i])
        opt.zero_grad(); loss.backward(); opt.step(); sched.step()

    def acc(rows):
        if len(rows) == 0:
            return float("nan")
        with torch.no_grad():
            p = net(X[rows]).masked_fill(M[rows] <= 0, -1e9).argmax(1)
        return float((p == A[rows]).float().mean())
    info = dict(train_acc=acc(tr[:200000]), heldout_acc=acc(va), refused=int((~ok).sum()), rows=int(len(tr)),
                heldout_rows=int(len(va)), last_action=bool(last_action), hidden=hidden, steps=steps,
                standardise=bool(standardise))
    return net, info


def export(net, path, env, observability, pace, last_action, origin="pysaga.imitate"):
    """The clone as a saga-policy file NeuralPolicy plays, at decision rate `pace`, its normaliser in it."""
    gru = "rnn.weight_ih" in net.state_dict()
    from .export import write_policy
    obs = env.observability()
    spec = observability if "terrain" in str(observability) else "%s+terrain:%d" % (observability, int(obs.terrain()))
    fields = [str(f) for f in env.obsFieldNamesOfSlot(env.slotOf(0))]
    tensors = {k: v.detach().numpy() for k, v in net.state_dict().items() if not k.startswith("norm.")}
    env.reset(1)
    training = dict(kit="basic", type=int(env.type(0)), frame_skip=int(pace), mode="duel", team_size=0, bar=None)
    write_policy(path, tensors, len(fields), int(tensors["fc2.weight"].shape[0]), int(tensors["fc1.weight"].shape[0]),
                 gru, int(env.encoder().agents()), False, spec, fields, [], bool(last_action),
                 origin=origin, algorithm="bc", training=training, normaliser=net.normaliser)
    return path


def shares(res):
    o = res["outcome"]
    return dict(win=float((o == 1).mean()), loss=float((o == 2).mean()), draw=float((o == 3).mean()),
                timeout=float((o == 0).mean()))


def summary(res):
    s = {k: float(res[k].mean()) for k in FLOORS}
    s.update(shares(res))
    if res.get("decisions"):
        s["agreement"] = res["agreed"] / res["decisions"]
    return s


def equivalent(expert, clone):
    """The plan's measure 2: each share within 5 points, each mean's difference interval inside the margin."""
    rows, ok = {}, True
    se, sc = shares(expert), shares(clone)
    for k in SHARES:
        d = sc[k] - se[k]
        good = abs(d) <= 0.05
        rows[k] = dict(expert=se[k], clone=sc[k], diff=d, ok=good)
        ok &= good
    for k, floor in FLOORS.items():
        a, b = expert[k], clone[k]
        d = b.mean() - a.mean()
        half = 1.96 * math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        margin = max(0.1 * abs(a.mean()), floor)
        good = abs(d) + half <= margin
        rows[k] = dict(expert=float(a.mean()), clone=float(b.mean()), diff=float(d), ci=float(half),
                       margin=float(margin), ok=bool(good))
        ok &= good
    return ok, rows


def head_to_head(env, a, b, episodes, seed, pace=4, opp_pace=4):
    """`a` against `b`: the plan's measure 3 -- a share of the decided episodes, or per-side symmetry if few are decided."""
    r = run(env, a, b, episodes, seed, pace=pace, opp_pace=opp_pace)
    o = r["outcome"]
    decided = int(((o == 1) | (o == 2)).sum())
    out = dict(decided=decided, a_wins=int((o == 1).sum()), b_wins=int((o == 2).sum()), draws=int((o == 3).sum()))
    if decided >= 50:
        out["ok"] = max(out["a_wins"], out["b_wins"]) <= 0.6 * decided
    else:
        # The mirror match draws: each side's kills against its deaths, damage dealt against taken
        sym = {}
        for x, y, floor in (("kills", "deaths", 0.05), ("dealt", "taken", 2.0)):
            d = r[x] - r[y]
            half = 1.96 * d.std(ddof=1) / math.sqrt(len(d))
            margin = max(0.1 * abs(r[y].mean()), floor)
            sym[x + "-" + y] = dict(diff=float(d.mean()), ci=float(half), margin=float(margin),
                                    ok=bool(abs(d.mean()) + half <= margin))
        out["symmetric"] = sym
        out["ok"] = all(v["ok"] for v in sym.values())
    return out


def confusion_top(conf, k=8):
    """The most frequent disagreements, shadow action -> clone action."""
    c = conf.copy()
    np.fill_diagonal(c, 0)
    idx = np.dstack(np.unravel_index(np.argsort(-c, axis=None)[:k], c.shape))[0]
    return [(int(i), int(j), int(c[i, j])) for i, j in idx if c[i, j] > 0]


def write(out_dir, name, obj):
    p = pathlib.Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    (p / (name + ".json")).write_text(json.dumps(obj, indent=1, default=float) + "\n")


def dagger(env, expert, opponent, data, rounds, episodes, seed, out_dir, name, pace=4, observability="full",
           eval_episodes=200, eval_seed=100000, trainer=None, delay=0, opp_delay=0, **train_kw):
    """DAgger: the clone plays, the expert labels every state it reaches, the clone retrains on all of it.

    Returns each round's clone file, its training info and its on-policy agreement."""
    history = []
    for k in range(rounds + 1):
        net, info = (trainer or train)(data, **train_kw)
        p = export(net, str(pathlib.Path(out_dir, "%s-dagger%d.policy" % (name, k))), env, observability, pace,
                   train_kw.get("last_action", False))
        ev = run(env, "neural:" + p, opponent, eval_episodes, eval_seed, pace=pace, shadow=expert,
                 delay=delay, opp_delay=opp_delay)
        history.append(dict(round=k, policy=p, rows=int(len(data["act"])), info=info, summary=summary(ev)))
        print("DAgger %s round %d: %d rows, held-out %.4f, on-policy agreement %.4f, win %.3f, timeout %.3f"
              % (name, k, len(data["act"]), info["heldout_acc"], history[-1]["summary"]["agreement"],
                 history[-1]["summary"]["win"], history[-1]["summary"]["timeout"]), flush=True)
        if k == rounds:
            break
        more = run(env, "neural:" + p, opponent, episodes, seed + 1000 * (k + 1), pace=pace, shadow=expert, record=True,
                   delay=delay, opp_delay=opp_delay)
        data = merge(data, more["data"])
    return history


def measure(env, clone, expert, opponent, episodes=500, seed=200000, pace=4, delay=0, opp_delay=0):
    """The plan's measures 1 and 2 for a clone file: on-policy agreement, outcomes and their equivalence."""
    cl = run(env, "neural:" + clone, opponent, episodes, seed, pace=pace, shadow=expert, delay=delay, opp_delay=opp_delay)
    ex = run(env, expert, opponent, episodes, seed, pace=pace, delay=delay, opp_delay=opp_delay)
    ok, rows = equivalent(ex, cl)
    s = summary(cl)
    return dict(clone=clone, agreement=s["agreement"], agreement_ok=s["agreement"] >= 0.9,
                outcomes_ok=ok, outcomes=rows, clone_summary=s, expert_summary=summary(ex),
                confusion_top=confusion_top(cl["confusion"]))


def report(m):
    print("  agreement %.4f (%s), outcomes %s" % (m["agreement"], "pass" if m["agreement_ok"] else "FAIL",
                                                   "equivalent" if m["outcomes_ok"] else "NOT equivalent"))
    for k, v in m["outcomes"].items():
        extra = " +-%.3f margin %.3f" % (v["ci"], v["margin"]) if "ci" in v else ""
        print("    %-8s expert %9.3f  clone %9.3f  diff %+8.3f%s %s" % (k, v["expert"], v["clone"], v["diff"], extra,
                                                                      "ok" if v["ok"] else "NO"))


def strip_seen(text):
    """A recording as though no seen tick had been recorded: each input then filed by the tick it landed."""
    out = []
    for line in text.split("\n"):
        f = line.split(" ")
        if line.startswith("T ") and len(f) == 7:
            line = " ".join(f[:6])
        elif line.startswith("O ") and len(f) == 6:
            line = " ".join(f[:5])
        out.append(line)
    return "\n".join(out)


def client_data(rounds, seen=True, frame_skip=2, observability="full", type_=0, root=None):
    """Recorded rounds' trajectories of one character type, as a dataset (labels by seen tick, or by landing tick)."""
    import gzip
    import jpype
    from saga.sim import FlightRecording
    from saga.sim.rl import RoundDataset, Observability, RewardFunction
    obs, act, mask, ep, base = [], [], [], [], 0
    counts = {}
    for r in rounds:
        path = pathlib.Path(r, "round.flight.gz")
        text = gzip.open(path, "rt", encoding="utf-8").read()
        if not seen:
            text = strip_seen(text)
        rec = FlightRecording.parse(jpype.JClass("java.io.StringReader")(text))
        game = jpype.JClass("java.io.File")(str(pathlib.Path(bridge.repo_root(root), "game")))
        worlds = FlightRecording.worlds(game, rec, str(path))
        d = RoundDataset.convert(rec, worlds, _observability(Observability, observability), 2, False,
                                 RewardFunction.ZERO, int(frame_skip))
        for k in d.counts.keySet():
            counts[str(k)] = counts.get(str(k), 0) + int(d.counts.get(k))
        for tr in d.trajectories:
            if int(tr.type) != type_ or int(tr.length) < 2:
                continue
            n = int(tr.length)
            obs.append(np.asarray(tr.obs, dtype=np.float32).reshape(n, int(d.obsSize)))
            act.append(np.asarray(tr.actions, dtype=np.int64))
            mask.append(np.asarray(tr.masks, dtype=np.int8).reshape(n, int(d.totalActions)))
            ep.append(np.full(n, base, dtype=np.int32))
            base += 1
    return dict(obs=np.concatenate(obs), act=np.concatenate(act), mask=np.concatenate(mask),
                episode=np.concatenate(ep)), counts


def accuracy(net, data, hidden):
    """A GRU clone's agreement with a dataset's labels, each episode played from a zero hidden state."""
    torch, nn, Net = _torch()
    X = torch.as_tensor(data["obs"]); A = torch.as_tensor(data["act"]); M = torch.as_tensor(data["mask"].astype(np.float32))
    ok = data["mask"][np.arange(len(data["act"])), data["act"]] != 0
    good = total = 0
    with torch.no_grad():
        for a, b in _episodes(data, set(np.unique(data["episode"]).tolist())):
            h = torch.zeros(1, hidden)
            for r in range(a, b):
                q, h = net(X[r:r + 1], h)
                if ok[r]:
                    total += 1
                    good += int(q.masked_fill(M[r:r + 1] <= 0, -1e9).argmax(1)[0] == A[r])
    return good / max(1, total)


def read_policy(path, root=None):
    """A saga-policy file's tensors (name -> array) and its normaliser (mean, std, clip; None
    where the file has none), read by the game's own reader (NeuralPolicy.weights): one reader of
    the format, so this one cannot drift from what plays the file."""
    bridge.start_jvm(root)
    import jpype
    w = jpype.JClass("saga.sim.rl.NeuralPolicy").weights(str(path))
    tensors = {str(n): np.asarray(w.tensor(n), dtype=np.float32).reshape(tuple(int(d) for d in w.shape(n)))
               for n in w.tensorNames()}
    if w.inputMean is None:
        return tensors, (None, None, None)
    return tensors, (np.asarray(w.inputMean, dtype=np.float32), np.asarray(w.inputStd, dtype=np.float32),
                     float(w.inputClip))


def epymarl_init(clone, base_step_dir, out_root, normaliser_file, lr):
    """An EPyMARL checkpoint whose actor is a behaviour clone: IPPO initialised from BC.

    base_step_dir is a checkpoint a short run of the same configuration wrote (models/<token>/<t>):
    its critic and the critic's optimiser are kept -- after one update on a random actor's data,
    as good as random. Its agent.th is replaced by the clone's weights, and agent_opt.th by a
    fresh Adam over them, never stepped, so the clone's parameters do not inherit the moments of
    a random actor's update (the Fable session's review). The clone must have been trained on the
    normaliser the run's environment applies: its file's statistics are checked against it.
    Returns the checkpoint_path to give EPyMARL (load_step 0 takes its one step)."""
    import shutil
    import torch
    from .normalise import Normaliser
    tensors, (mean, std, clip) = read_policy(clone)
    norm = Normaliser.load(normaliser_file)
    if mean is None or not (np.allclose(mean, norm.obs_mean, atol=1e-6) and np.allclose(std, norm.obs_std, atol=1e-6)
                            and abs(clip - norm.clip) < 1e-6):
        raise SystemExit("%s was not trained on the normaliser %s: its weights would mean something else there"
                         % (clone, normaliser_file))
    base = pathlib.Path(base_step_dir)
    out = pathlib.Path(out_root) / base.name
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(base, out)
    agent = torch.load(base / "agent.th", map_location="cpu")
    state = {}
    for k, v in agent.items():
        if k not in tensors:
            raise SystemExit("the clone has no %s, which EPyMARL's agent holds" % k)
        t = torch.as_tensor(tensors[k]).reshape(v.shape)
        state[k] = t
    torch.save(state, out / "agent.th")
    params = [torch.nn.Parameter(state[k].clone()) for k in agent.keys()]
    torch.save(torch.optim.Adam(params, lr=lr).state_dict(), out / "agent_opt.th")
    return str(out.parent)


def recorded_delays(paths, bots=False):
    """The seen distances of recorded datasets (pysaga.dataset's .npz files), every decision
    that has one: the lag the players' inputs really had, to draw a harness's delays from.
    Bots' decisions are left out unless asked for, where the JSON beside a file says whose
    each episode is."""
    out = []
    for path in paths:
        d = np.load(path)
        if "seen_distance" not in d.files:
            raise SystemExit("%s has no seen_distance: it was written before lag was recorded" % path)
        seen, keep = d["seen_distance"], np.ones(len(d["seen_distance"]), dtype=bool)
        meta = pathlib.Path(str(path)[:-4] + ".json")
        if not bots and meta.is_file():
            episodes = json.loads(meta.read_text(encoding="utf-8")).get("episodes", [])
            is_bot = np.array([bool(e.get("bot")) for e in episodes], dtype=bool)
            if len(is_bot) > int(d["episode"].max(initial=-1)):
                keep = ~is_bot[d["episode"]]
        out.append(seen[keep & (seen >= 0)])
    out = np.concatenate(out) if out else np.zeros(0, dtype=np.int64)
    if not len(out):
        raise SystemExit("no decision of %s has a seen distance" % ", ".join(str(p) for p in paths))
    return out.astype(np.int64)


def policy_pace(spec, default=4, root=None):
    """The rate a policy decides at: a file's own frame_skip, else `default` (a bot's name)."""
    if not (spec.startswith("neural:") or spec.startswith("sample:")):
        return int(default)
    bridge.start_jvm(root)
    import jpype
    nets = jpype.JClass("saga.sim.rl.NeuralPolicy")
    return int(nets.weights(nets.specFile(spec)).training.frameSkip)


def lag_sweep(env, policy, opponent, delays=(0, 1, 2, 3, 5), recorded=None, shadow=None, episodes=200,
              seed=300000, pace=None, opp_pace=4, opponent_delayed=True):
    """A policy's play as its actions land later: a row per fixed delay, and one with each
    action's delay drawn from `recorded` (a list of delays in ticks: recorded_delays).

    Each row holds the shares of episodes won, lost, drawn and timed out, the per-episode
    means, the agreement with `shadow` where one is given, and the mean ticks the policy's
    actions took to land. The opponent's actions are delayed the same way unless
    `opponent_delayed` is False: two players of one round share its lag. The same seeds are
    played in every row, so rows differ by the delay alone.
    """
    pace = policy_pace(policy) if pace is None else int(pace)
    rows = []

    def row(name, **kw):
        res = run(env, policy, opponent, episodes, seed, pace=pace, opp_pace=opp_pace, shadow=shadow, **kw)
        s = summary(res)
        bins = res["landed_after"]
        s["mean_delay"] = float((bins * np.arange(len(bins))).sum() / max(1, bins.sum()))
        s["delay"] = name
        rows.append(s)

    for d in delays:
        row(str(int(d)), delay=int(d), opp_delay=int(d) if opponent_delayed else 0)
    if recorded is not None and len(recorded):
        row("recorded", delays=recorded, opp_delays=recorded if opponent_delayed else None)
    return rows


def report_sweep(rows):
    agree = any("agreement" in r for r in rows)
    print("  %-9s %6s %6s %6s %8s %7s %7s%s  %s" % ("delay", "win", "loss", "draw", "timeout", "kills", "deaths",
                                                   "  agreement" if agree else "", "landed after (ticks)"))
    for r in rows:
        print("  %-9s %5.1f%% %5.1f%% %5.1f%% %7.1f%% %7.2f %7.2f%s  %.2f"
              % (r["delay"], 100 * r["win"], 100 * r["loss"], 100 * r["draw"], 100 * r["timeout"], r["kills"], r["deaths"],
                 ("  %8.1f%%" % (100 * r["agreement"]) if "agreement" in r else "           ") if agree else "",
                 r["mean_delay"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Imitation tools: a policy's play under lag.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("lag-sweep", help="a policy's outcomes and agreement as its actions land later")
    s.add_argument("policy", help="a policy file, or a bot's name")
    s.add_argument("--opponent", default="kite")
    s.add_argument("--shadow", help="a policy asked at every decision what it would do: the agreement column")
    s.add_argument("--delays", default="0,1,2,3,5", help="fixed delays to play, in ticks of 50 ms")
    s.add_argument("--recorded", nargs="+", help="datasets (.npz) whose seen distances a row's delays are drawn from")
    s.add_argument("--with-bots", action="store_true", help="draw from recorded bots' decisions too")
    s.add_argument("--opponent-undelayed", action="store_true", help="delay the policy's actions alone")
    s.add_argument("--episodes", type=int, default=200)
    s.add_argument("--seed", type=int, default=300000)
    s.add_argument("--map", help="a map's name or file (the open test map)")
    s.add_argument("--observability", default="full")
    s.add_argument("--pace", type=int, help="ticks a decision, for a bot's name (a policy file plays at its own)")
    s.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    policy = a.policy if ":" in a.policy or not os.path.exists(a.policy) else "neural:" + a.policy
    env, _ = make_env(a.map, a.observability)
    recorded = recorded_delays(a.recorded, bots=a.with_bots) if a.recorded else None
    rows = lag_sweep(env, policy, a.opponent, delays=[int(x) for x in a.delays.split(",") if x != ""],
                     recorded=recorded, shadow=a.shadow, episodes=a.episodes, seed=a.seed, pace=a.pace,
                     opponent_delayed=not a.opponent_undelayed)
    if a.json:
        print(json.dumps(rows))
        return
    print("Lag sweep: %s against %s, %d episodes a row%s" % (policy, a.opponent, a.episodes,
          "" if a.opponent_undelayed else ", both players delayed"))
    if recorded is not None:
        q = np.percentile(recorded, [50, 90, 99])
        print("  recorded: %d inputs, delay median %d, 90%% %d, 99%% %d, most %d ticks"
              % (len(recorded), q[0], q[1], q[2], recorded.max()))
    report_sweep(rows)


if __name__ == "__main__":
    main()
