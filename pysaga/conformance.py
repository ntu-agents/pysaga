#!/usr/bin/env python3
"""Check that pysaga satisfies the EPyMARL MultiAgentEnv contract.

Verifies shapes and signatures against src/envs/multiagentenv.py, and -- the part
that matters and that gymma cannot express -- the availability mask: every agent
always has an action, and a dead agent may only no-op. That the mask and the world
agree on each action is the Java side's (ObsEncoder asks the world's own rules).
"""

import sys

import numpy as np

from pysaga.env import SagaEnv


def _child_env():
    """The environment a child Python runs pysaga in: this package, wherever it is
    -- a checkout or site-packages -- first on its path."""
    import os
    import pysaga
    top = os.path.dirname(os.path.dirname(os.path.abspath(pysaga.__file__)))
    return dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in (top, os.environ.get("PYTHONPATH", "")) if p))

fail = 0

# Greenhaven, the map these checks were written on -- a test map now, beside homes.json:
# a melee bot meets a still learner on it, and its layout is what the numbers below assume.
def _greenhaven():
    import os
    from pysaga import bridge
    return os.path.join(bridge.fixtures(), "Greenhaven.json")


GREENHAVEN = _greenhaven()


def check(what, ok, detail=""):
    global fail
    print("  %-52s %s%s" % (what, "PASS" if ok else "FAIL", ("   " + detail) if detail else ""))
    if not ok:
        fail += 1


def main():
    # The map an environment plays unnamed is a shipped one, named the same on both sides
    import jpype
    from pysaga.env import DEFAULT_MAP
    print("the default map:")
    plain = SagaEnv()
    plain.reset(seed=1)
    java_default = str(jpype.JClass("saga.sim.rl.MapSource").DEFAULT_MAP)
    check("pysaga's default is Java's", DEFAULT_MAP == java_default, "%s, %s" % (DEFAULT_MAP, java_default))
    check("an environment named nothing plays it, by its name", plain.map_info()["name"] == DEFAULT_MAP,
          plain.map_info()["name"])

    env = SagaEnv(map_name=GREENHAVEN)
    info = env.get_env_info()

    print("get_env_info:")
    for key in ("state_shape", "obs_shape", "n_actions", "n_agents", "episode_limit"):
        check("has %s" % key, key in info, str(info.get(key)))
    check("n_agents matches the attribute", info["n_agents"] == env.n_agents)
    check("episode_limit matches the attribute", info["episode_limit"] == env.episode_limit)

    print("\nreset and step signatures:")
    out = env.reset(seed=1)
    check("reset returns (obs, info)", isinstance(out, tuple) and len(out) == 2,
          "%d values" % len(out))
    obs, _ = out
    check("one observation per agent", len(obs) == env.n_agents)
    check("observation width matches obs_shape",
          all(len(o) == info["obs_shape"] for o in obs))
    check("state width matches state_shape", len(env.get_state()) == info["state_shape"])
    check("one action mask per agent", len(env.get_avail_actions()) == env.n_agents)
    check("mask width matches n_actions",
          all(len(a) == info["n_actions"] for a in env.get_avail_actions()))

    res = env.step([0] * env.n_agents)
    check("step returns the five-tuple", isinstance(res, tuple) and len(res) == 5,
          "%d values" % len(res))
    obs, reward, terminated, truncated, extra = res
    check("terminated and truncated are separate booleans",
          isinstance(terminated, bool) and isinstance(truncated, bool))
    check("reward is per agent when common_reward is off",
          isinstance(reward, list) and len(reward) == env.n_agents)

    shared = SagaEnv(map_name=GREENHAVEN, common_reward=True, reward_scalarisation="sum")
    shared.reset(seed=1)
    _, r, _, _, _ = shared.step([0] * shared.n_agents)
    check("common_reward gives a scalar", isinstance(r, float), str(round(r, 4)))

    print("\nmask honesty:")
    env.reset(seed=3)
    rng = np.random.default_rng(0)
    illegal = 0
    for _ in range(400):
        avail = env.get_avail_actions()
        for a in avail:
            if sum(a) == 0:
                illegal += 1                      # no action at all is never valid
        # An empty mask is counted above, not chosen from: a choice from nothing would
        # throw before the count could report
        acts = [int(rng.choice(np.flatnonzero(np.asarray(a)))) if sum(a) else 0 for a in avail]
        _, _, term, trunc, _ = env.step(acts)
        if term or trunc:
            env.reset()
    check("every agent always has at least one action", illegal == 0)

    env.reset(seed=4)
    st = env._env.world().state()
    st.alive[0] = 0
    mask = env.get_avail_agent_actions(0)
    check("a dead agent may only no-op", sum(mask) == 1 and mask[0] == 1)

    print("\ndeterminism through the bridge:")
    def trace(seed):
        env.reset(seed=seed)
        r = np.random.default_rng(5)
        out = []
        for _ in range(120):
            acts = [int(r.choice(np.flatnonzero(np.asarray(a)))) for a in env.get_avail_actions()]
            env.step(acts)
            out.append(env.state_hash())
        return out
    check("identical seeds give identical hash traces", trace(11) == trace(11), "120 decisions")
    check("different seeds diverge", trace(11) != trace(12))

    print("\nthe end of an episode, as a runner reads it:")
    env.reset(seed=6)
    info = {}
    for _ in range(env.episode_limit):
        _, _, term, trunc, info = env.step([0] * env.n_agents)
        if term or trunc:
            break
    check("the info dict holds numbers only", bool(info) and all(
          isinstance(v, (int, float, bool, np.integer, np.floating)) for v in info.values()),
          ", ".join(sorted(info)))
    check("a win flag per team, and a draw flag",
          {"win_team1", "win_team2", "draw"} <= set(info))

    vectorised()
    scripted()
    neural()
    replay()
    rewind()
    rate()
    maps()
    terrain()
    monsters()

    print("\n" + ("ALL PASS" if fail == 0 else "%d FAILURE(S)" % fail))
    return 1 if fail else 0


def rewind():
    """A rewind through the bridge: the end flags, the counts and the rewards come
    back with the world, and the replay's recorded actions are cut back to the save."""
    import json, os, tempfile
    print("\na rewind, through the bridge:")
    env = SagaEnv(map_name=GREENHAVEN, scripted="melee")
    env.reset(seed=21)
    rng = np.random.default_rng(21)
    pick = lambda: [int(rng.choice(np.flatnonzero(np.asarray(a)))) for a in env.get_avail_actions()]
    for _ in range(20):
        env.step(pick())
    env.save_state()
    at_save = (int(env._env.decisions()), int(env._env.damage(0)), int(env._env.kills(0)))
    future = []
    for _ in range(env.episode_limit):
        a = pick()
        future.append(a)
        _, _, term, trunc, _ = env.step(a)
        if term or trunc:
            break
    ended, end_hash, end_winner = term or trunc, env.state_hash(), int(env._env.winner())
    env.load_state()
    j = env._env
    check("played to its end and loaded, the episode is not over",
          ended and not j.terminated() and not j.truncated() and j.winner() == 0,
          "%d decisions on, winner %d then" % (len(future), end_winner))
    check("the counts are the save's, the rewards zero",
          (int(j.decisions()), int(j.damage(0)), int(j.kills(0))) == at_save and not any(j.rewards()),
          str(at_save))
    for a in future:
        env.step(a)
    check("and replaying reaches the same end", env.state_hash() == end_hash and int(j.winner()) == end_winner)
    env.load_state()
    other = [pick() for _ in range(5)]
    for a in other:
        env.step(a)
    path = os.path.join(tempfile.mkdtemp(), "rewound.json")
    env.save_replay(path)
    actions = json.load(open(path))["episodes"][0]["actions"]
    check("a replay saved after a rewind holds the future played",
          len(actions) == 20 + len(other) and actions[-len(other):] == other,
          "%d actions recorded" % len(actions))


def vectorised():
    """The vectorised environment is N single ones, seen through the bridge."""
    from pysaga.vec import VecSagaEnv

    print("\nvectorised environment:")
    n = 3
    vec = VecSagaEnv(n, map_name=GREENHAVEN)
    info = vec.get_env_info()
    obs, state, avail = vec.reset(seed=50)
    check("obs is (n_envs, n_agents, obs_shape)", obs.shape == (n, vec.n_agents, info["obs_shape"]), str(obs.shape))
    check("state is (n_envs, state_shape)", state.shape == (n, info["state_shape"]), str(state.shape))
    check("avail is (n_envs, n_agents, n_actions)", avail.shape == (n, vec.n_agents, info["n_actions"]), str(avail.shape))

    singles = [SagaEnv(map_name=GREENHAVEN) for _ in range(n)]
    for i, e in enumerate(singles):
        e.reset(seed=vec.episode_seed(i))
    rng = np.random.default_rng(1)
    over = [False] * n
    mismatch = 0
    steps = 0
    while steps < 1600 and not all(over):
        acts = np.zeros((n, vec.n_agents), dtype=np.int32)
        for i in range(n):
            for a in range(vec.n_agents):
                acts[i, a] = rng.choice(np.flatnonzero(avail[i, a]))
        obs, state, avail, rewards, term, trunc = vec.step(acts)
        steps += 1
        for i, e in enumerate(singles):
            if over[i]:
                # Left alone: the same hash as when it finished, no reward
                if vec.state_hash(i) != e.state_hash() or rewards[i].any():
                    mismatch += 1
                continue
            o, r, t, tr, _ = e.step(acts[i].tolist())
            if vec.state_hash(i) != e.state_hash():
                mismatch += 1
            if not (np.array_equal(obs[i], np.array(o, dtype=np.float32))
                    and np.array_equal(state[i], e.get_state())
                    and np.array_equal(avail[i], np.array(e.get_avail_actions()))
                    and np.allclose(rewards[i], r)
                    and bool(term[i]) == t and bool(trunc[i]) == tr):
                mismatch += 1
            over[i] = t or tr
    check("every world matches its single environment, step for step",
          mismatch == 0 and steps > 0, "%d steps, %d mismatches" % (steps, mismatch))
    check("every world finished and was then left alone", all(over), "%d of %d" % (sum(over), n))

    info = vec.episode_info(0)
    check("a world's episode info holds numbers only", all(
          isinstance(v, (int, float, bool, np.integer, np.floating)) for v in info.values()))

    refused = False
    try:
        VecSagaEnv(2, reward=lambda *a: [0, 0])
    except TypeError:
        refused = True
    check("a Python reward is refused", refused)



def scripted():
    """A bot in a slot, and the learner alone on the runner's side of the bridge."""
    from pysaga.vec import VecSagaEnv

    print("\nscripted opponents:")
    env = SagaEnv(map_name=GREENHAVEN, scripted="melee", reward="ladder")
    check("one learner against the bot", env.n_agents == 1 and env.get_env_info()["n_agents"] == 1)
    check("the ladder reward by name", env.reward_name == "ladder", env.reward_name)
    env.reset(seed=7)
    st = env._env.world().state()
    x0, y0 = int(st.posX[1]), int(st.posY[1])
    info = {}
    for _ in range(env.episode_limit):
        _, _, term, trunc, info = env.step([0])
        if term or trunc:
            break
    check("the bot moved on its own while the learner stood still", (int(st.posX[1]), int(st.posY[1])) != (x0, y0))
    check("the episode ended (a melee bot kills a still learner)", term, "%d decisions" % info.get("decisions", -1))
    check("both sides have a win flag though only one learns", {"win_team1", "win_team2"} <= set(info), ", ".join(sorted(info)))

    other = SagaEnv(map_name=GREENHAVEN, scripted={0: "melee"})
    other.reset(seed=1)                       # types are dealt at reset
    check("the learner may be the second slot", other.n_agents == 1 and other.get_stats()["type_per_agent"] == [1],
          str(other.get_stats()["type_per_agent"]))

    vec = VecSagaEnv(4, map_name=GREENHAVEN, scripted={1: ["melee", "kite"]})
    obs, state, avail = vec.reset(seed=1)
    check("a vectorised batch of one learner against mixed bots", obs.shape == (4, 1, env.get_obs_size())
          and [r[1] for r in vec.scripted] == ["melee", "kite", "melee", "kite"], str([r[1] for r in vec.scripted]))

    refused = False
    try:
        SagaEnv(map_name=GREENHAVEN, scripted={0: "melee", 1: "melee"})
    except Exception:
        refused = True
    check("a scenario with every slot scripted is refused", refused)

    # The command-line form. sacred turns a dict given after "with" into nested
    # keys and refuses any the yaml does not declare, so a string has to carry
    # the same information.
    s = SagaEnv(map_name=GREENHAVEN, scripted="0:melee")
    check("the string form names a slot (\"0:melee\")", s.n_agents == 1 and s.scripted == {0: "melee"}, str(s.scripted))
    vec2 = VecSagaEnv(4, map_name=GREENHAVEN, scripted="1:melee|kite:60:140")
    check("and spreads a | list over the worlds, colons in a name kept",
          [r[1] for r in vec2.scripted] == ["melee", "kite:60:140", "melee", "kite:60:140"], str([r[1] for r in vec2.scripted]))
    refused = False
    try:
        SagaEnv(map_name=GREENHAVEN, scripted="melee,kite")
    except ValueError:
        refused = True
    check("several entries without slots are refused", refused)


def neural():
    """A trained policy's file runs in Java as this side's own forward says.

    The file is written here from random weights through the export's writer, so
    the writer, the reader and the two forwards -- Java's and numpy's -- are held
    to one another on real observations, for the MLP and for the GRU; then the
    file is a bot by name in a scripted slot. A checkpoint is not needed for that,
    and torch is not either.
    """
    import os
    import tempfile
    import jpype
    from pysaga import export as rl_export

    print("\nthe trained policy in Java:")
    env = SagaEnv(map_name=GREENHAVEN)
    jenv = env._env
    obs, actions = int(jenv.obsSize()), int(jenv.totalActions())
    fields = [str(n) for n in jenv.obsFieldNamesOfSlot(0)]
    NeuralPolicy = jpype.JClass("saga.sim.rl.NeuralPolicy")
    rng = np.random.default_rng(3)
    path = None
    for gru in (False, True):
        kind = "gru" if gru else "mlp"
        hidden = 16
        onehot = np.array([1, 0], np.float32)
        last_action = gru
        inputs = obs + (actions if last_action else 0) + len(onehot)
        u = lambda *shape: rng.uniform(-0.3, 0.3, shape).astype(np.float32)
        t = {"fc1.weight": u(hidden, inputs), "fc1.bias": u(hidden), "fc2.weight": u(actions, hidden), "fc2.bias": u(actions)}
        if gru:
            t.update({"rnn.weight_ih": u(3 * hidden, hidden), "rnn.weight_hh": u(3 * hidden, hidden),
                      "rnn.bias_ih": u(3 * hidden), "rnn.bias_hh": u(3 * hidden)})
        else:
            t.update({"rnn.weight": u(hidden, hidden), "rnn.bias": u(hidden)})
        path = os.path.join(tempfile.gettempdir(), "saga-conformance-%s.policy" % kind)
        trained = rl_export.training_of(env, {}, 0)
        rl_export.write_policy(path, t, obs, actions, hidden, gru, 2, False, env.observability, fields, onehot, last_action,
                               "rl_conformance random weights", algorithm="conformance", training=trained)
        p = NeuralPolicy.load(path)
        check("the %s export names what trained it, and Java reads it" % kind,
              str(NeuralPolicy.weights(path).algorithm) == "conformance", str(NeuralPolicy.weights(path).algorithm))
        tr = NeuralPolicy.weights(path).training
        check("%s: the export says how it was trained -- the dealt kit, its type and pace -- and Java reads it" % kind,
              str(tr.kit) == "dealt" and int(tr.type) == trained["type"] and int(tr.frameSkip) == trained["frame_skip"]
              and bool(tr.dealt())
              and [int(v) for v in tr.bar] == trained["bar"], "%s type %d bar %s" % (tr.kit, int(tr.type), trained["bar"]))
        p.bind(jenv.world(), jenv.observability())
        env.reset(seed=4)
        h = np.zeros(hidden, np.float64)
        last, worst, disagree, steps = -1, 0.0, 0, 0
        for _ in range(150):
            o = np.array(jenv.obsOfSlot(0), np.float32)
            av = np.array(jenv.availActionsOfSlot(0), np.int32)
            x = [o]
            if last_action:
                x.append(np.eye(actions, dtype=np.float32)[last] if last >= 0 else np.zeros(actions, np.float32))
            x.append(onehot)
            ref, h = rl_export.forward(t, gru, np.concatenate(x), h)
            legal = np.where(av != 0)[0]
            ref_best = int(legal[np.argmax(ref[legal])])
            a = int(p.act(jpype.JArray(jpype.JFloat)(o.tolist()), jpype.JArray(jpype.JInt)(av.tolist())))
            got = np.array(p.lastLogits(), np.float64)
            worst = max(worst, float(np.abs(got - ref).max()))
            disagree += a != ref_best
            last = a
            steps += 1
            _, _, term, trunc, _ = env.step([a, 0])
            if term or trunc:
                break
        check("%s: the file round-trips and Java's logits match numpy's (%d steps)" % (kind, steps), worst < 1e-4,
              "largest difference %.3g" % worst)
        check("%s: the action is the argmax over the mask" % kind, disagree == 0, "%d disagreements" % disagree)

    basic = SagaEnv(map_name=GREENHAVEN, kit="basic", scripted="melee")
    basic.reset(seed=1)
    bars = list(basic._env.world().state().hotbar)
    stride = int(jpype.JClass("saga.sim.GameState").HOTBAR_STRIDE)
    learn_first = int(jpype.JClass("saga.sim.Actions").learnFirst(1))
    check("kit=basic deals the weapon strike alone, with nothing to learn",
          bars[:stride] == [0] + [-1] * (stride - 1) and bars[stride:2 * stride] == [0] + [-1] * (stride - 1)
          and not any(basic.get_avail_agent_actions(0)[learn_first:learn_first + 20]), str(bars[:stride]))
    refused = False
    try:
        SagaEnv(map_name=GREENHAVEN, kit="fancy")
    except ValueError:
        refused = True
    check("an unknown kit is refused", refused)

    s = SagaEnv(map_name=GREENHAVEN, scripted="neural:" + path)
    s.reset(seed=2)
    ended = False
    for _ in range(s.episode_limit):
        _, _, term, trunc, _ = s.step([0])
        if term or trunc:
            ended = True
            break
    check("a scripted slot takes neural:<file> and plays an episode", ended and s.scripted == {1: "neural:" + path},
          str(s.scripted))
    s = SagaEnv(map_name=GREENHAVEN, scripted="sample:" + path)
    s.reset(seed=2)
    ended = False
    for _ in range(s.episode_limit):
        _, _, term, trunc, _ = s.step([0])
        if term or trunc:
            ended = True
            break
    check("a scripted slot takes sample:<file> and plays an episode", ended, str(s.scripted))


def _page_maps(page):
    """The maps a replay page embeds: its data block, read back."""
    import json
    import os
    if not os.path.exists(page):
        return {}
    html = open(page).read()
    start = html.index('<script id="replay-data" type="application/json">') + len('<script id="replay-data" type="application/json">')
    return json.loads(html[start:html.index("</script>", start)].replace("<\\/", "</"))["maps"]


def _png_size(uri):
    """A PNG data URI's width and height, from its header."""
    import base64
    import struct
    raw = base64.b64decode(uri.split(",", 1)[1])
    return tuple(int(v) for v in struct.unpack(">II", raw[16:24]))


def rate():
    """frame_skip: another decision rate is an episode as long in game time, recorded, replayed to its hash."""
    import json
    import os
    import tempfile

    print("\nthe decision rate:")
    four, two = SagaEnv(map_name=GREENHAVEN), SagaEnv(map_name=GREENHAVEN, frame_skip=2)
    check("frame_skip=2 decides twice as often in an episode as long", two.episode_limit == 2 * four.episode_limit
          and int(two._env.frameSkip()) == 2, "%d against %d" % (two.episode_limit, four.episode_limit))
    refused = False
    try:
        SagaEnv(map_name=GREENHAVEN, frame_skip=0)
    except ValueError:
        refused = True
    check("a rate below a tick is refused", refused)
    env = SagaEnv(map_name=GREENHAVEN, kit="basic", scripted="0:melee", frame_skip=2)
    env.reset(seed=7)
    rng = np.random.default_rng(3)
    for _ in range(120):
        legal = [a for a, ok in enumerate(env.get_avail_agent_actions(0)) if ok]
        _, _, term, trunc, _ = env.step([int(rng.choice(legal))])
        if term or trunc:
            break
    path = os.path.join(tempfile.gettempdir(), "saga-conformance-rate.json")
    env.save_replay(path)
    r = json.load(open(path))
    options = {k: v for k, v in r["env"].items() if k != "learner"}
    again = SagaEnv(scripted={int(k): v for k, v in r["episodes"][0]["scripted"].items()}, **options)
    again.reset(seed=r["episodes"][0]["seed"])
    for acts in r["episodes"][0]["actions"]:
        again.step(acts)
    check("a replay file says its rate, and replays at it to its hash", r["env"].get("frame_skip") == 2
          and again.state_hash() == r["episodes"][0]["hash"], str(r["env"].get("frame_skip")))
    import jpype
    sc = jpype.JClass("saga.sim.rl.ReplayPlayer").scenarioOf(
        jpype.JClass("saga.sim.rl.ReplayFile").read(jpype.JClass("java.io.File")(path)))
    check("and the game's own replay player reads the rate from it", int(sc.frameSkip) == 2
          and int(sc.episodeTicks) == int(four._env.scenario().episodeTicks), "%d %d" % (int(sc.frameSkip), int(sc.episodeTicks)))


def replay():
    """A replay file holds everything needed to play the episode again, and says so with a hash."""
    import json
    import os
    import tempfile
    from pysaga.vec import VecSagaEnv

    print("\nreplay files:")
    env = SagaEnv(map_name=GREENHAVEN, kit="basic", scripted="0:melee")
    env.reset(seed=11)
    rng = np.random.default_rng(5)
    for _ in range(60):
        avail = env.get_avail_agent_actions(0)
        legal = [a for a, ok in enumerate(avail) if ok]
        _, _, term, trunc, _ = env.step([int(rng.choice(legal))])
        if term or trunc:
            break
    path = os.path.join(tempfile.gettempdir(), "saga-conformance-replay.json")
    env.set_learner_name("ippo")
    env.save_replay(path)
    r = json.load(open(path))
    check("the file names its environment, its bots, its learner, and ends on a hash",
          r.get("format") == "saga-replay" and r["env"]["kit"] == "basic" and r["episodes"][0]["scripted"] == {"0": "melee"}
          and r["env"]["learner"] == "ippo" and "hash" in r["episodes"][0], str(r.get("env")))
    options = {k: v for k, v in r["env"].items() if k != "learner"}   # a name, not an option
    again = SagaEnv(scripted={int(k): v for k, v in r["episodes"][0]["scripted"].items()}, **options)
    again.reset(seed=r["episodes"][0]["seed"])
    for acts in r["episodes"][0]["actions"]:
        again.step(acts)
    check("replaying it from the file reaches the recorded hash", again.state_hash() == r["episodes"][0]["hash"],
          "%d against %d" % (again.state_hash(), r["episodes"][0]["hash"]))

    # A melee bot against a learner that stands still, so one world ends inside
    # the loop: its rows must stop at its end, the others' run on to the batch's.
    vec = VecSagaEnv(3, map_name=GREENHAVEN, kit="basic", scripted="1:melee|kite")
    vec.reset(seed=4)
    steps, first_over = 0, None
    for _ in range(2000):
        _, _, _, _, term, trunc = vec.step(np.zeros((3, 1), dtype=np.int32))
        steps += 1
        if first_over is None and (term | trunc).any():
            first_over = int(np.argmax(term | trunc))
            break
    vec.save_replay(path)
    r = json.load(open(path))
    rows = [len(x["actions"]) for x in r["episodes"]]
    check("a world's rows stop at its episode's end, the others' run on", first_over is not None
          and rows[first_over] == steps and all(n == steps for n in rows), "over %s, rows %s after %d steps" % (first_over, rows, steps))
    for _ in range(5):
        _, _, _, _, term, trunc = vec.step(np.zeros((3, 1), dtype=np.int32))
    over = term | trunc
    vec.save_replay(path)
    r = json.load(open(path))
    rows = [len(x["actions"]) for x in r["episodes"]]
    # A world still running has five rows more; one that ended meanwhile stopped
    # where it ended (the first run saw world 2 end one step after world 0).
    check("and five steps later the finished world has not grown, the running ones have", rows[first_over] == steps
          and all((rows[w] == steps + 5) if not over[w] else (steps <= rows[w] <= steps + 5) for w in range(3) if w != first_over),
          "rows %s, over %s" % (rows, over.tolist()))
    check("the vectorised environment writes every world's episode, each with its own bot", len(r["episodes"]) == 3
          and [x["world"] for x in r["episodes"]] == [0, 1, 2] and [x["scripted"]["1"] for x in r["episodes"]] == ["melee", "kite", "melee"],
          str([(x.get("world"), x.get("scripted")) for x in r["episodes"]]))
    options = {k: v for k, v in r["env"].items() if k != "learner"}
    again = SagaEnv(scripted={int(k): v for k, v in r["episodes"][1]["scripted"].items()}, **options)
    again.reset(seed=r["episodes"][1]["seed"])
    for acts in r["episodes"][1]["actions"]:
        again.step(acts)
    check("and a world of it replays to its hash in a single environment", again.state_hash() == r["episodes"][1]["hash"],
          "%d against %d" % (again.state_hash(), r["episodes"][1]["hash"]))


def maps():
    """Where the map comes from: a generated map per episode, a curriculum, and a
    replay file of either that plays its episodes again on their own maps."""
    import json
    import os
    import subprocess
    import tempfile
    from pysaga.vec import VecSagaEnv

    print("\nmaps that change:")
    src = "gen:forest:size=50x40"
    vec = VecSagaEnv(4, map_name=src, map_seed="episode", kit="basic", scripted="1:melee")
    vec.reset(seed=3)
    infos = [vec.map_info(i) for i in range(4)]
    check("a generated map per episode: four worlds, four maps", len(set(m["sim_hash"] for m in infos)) == 4
          and all(m["seed"] >= 0 and m["source"] == src for m in infos), ", ".join(m["name"] for m in infos))
    rng = np.random.default_rng(8)
    for _ in range(60):
        _, _, avail, _, _, _ = vec.step(np.array([[int(rng.choice(np.flatnonzero(avail_w[0])))]
                                                  for avail_w in vec._read()[2]], dtype=np.int32))
    path = os.path.join(tempfile.gettempdir(), "saga-conformance-maps.json")
    vec.save_replay(path)
    r = json.load(open(path))
    check("the file says each episode's map, and carries no generated one", r["version"] == 2 and r["maps"] == {}
          and [e["map"]["sim_hash"] for e in r["episodes"]] == [m["sim_hash"] for m in infos]
          and r["env"]["map_seed"] == "episode", str(r["env"].get("map_seed")))
    options = {k: v for k, v in r["env"].items() if k != "learner"}
    e2 = r["episodes"][2]
    one = SagaEnv(scripted={int(k): v for k, v in e2["scripted"].items()}, **options)
    one.reset(seed=e2["seed"])
    for acts in e2["actions"]:
        one.step(acts)
    check("a world of it replays in a single environment, on its own map, to its hash",
          one.map_info()["sim_hash"] == e2["map"]["sim_hash"] and one.state_hash() == e2["hash"],
          "%d against %d" % (one.state_hash(), e2["hash"]))
    page = os.path.join(tempfile.gettempdir(), "saga-conformance-maps.html")
    run = subprocess.run([sys.executable, "-m", "pysaga.replay", path, "-o", page], env=_child_env(),
                         capture_output=True, text=True)
    check("rl_replay plays every episode on its own map to its hash", run.returncode == 0
          and run.stdout.count("hash ok") == 4, (run.stdout + run.stderr).strip().splitlines()[-1] if (run.stdout + run.stderr).strip() else "")
    pics = _page_maps(page)
    check("and the page carries each map plain, of its size, and no picture of the game",
          len(pics) == 4 and all(m.get("plain") and _png_size(m["plain"]) == (m["w"], m["h"]) and set(m) == {"w", "h", "plain"}
                                 for m in pics.values()),
          "%d maps" % len(pics))

    named = SagaEnv(map_name=GREENHAVEN, kit="basic", scripted="0:melee")
    named.reset(seed=2)
    named.step([0])
    named.save_replay(path)
    r = json.load(open(path))
    h = r["episodes"][0]["map"]["sim_hash"]
    check("a map of the game travels in the file, by its simHash", list(r["maps"]) == [h] and r["episodes"][0]["map"]["seed"] == -1
          and '"format": "saga-map"' in r["maps"][h], h[:12])
    run = subprocess.run([sys.executable, "-m", "pysaga.replay", path, "-o", page], env=_child_env(), capture_output=True, text=True)
    check("and replays from the text it carries", run.returncode == 0 and "hash ok" in run.stdout, run.stdout.strip()[-80:])

    # A map naming a tileset nobody has still replays, plain like any other
    text = json.loads(r["maps"][h])
    text["tileset"] = "nowhere"
    own = os.path.join(tempfile.gettempdir(), "saga-conformance-untiled.json")
    with open(own, "w") as f:
        json.dump(text, f)
    untiled = SagaEnv(map_name=own, kit="basic", scripted="0:melee")
    untiled.reset(seed=2)
    untiled.step([0])
    untiled.save_replay(path)
    run = subprocess.run([sys.executable, "-m", "pysaga.replay", path, "-o", page], env=_child_env(), capture_output=True, text=True)
    pics = _page_maps(page) if run.returncode == 0 else {}
    check("a map naming a tileset nobody has replays, plain",
          run.returncode == 0 and "hash ok" in run.stdout and len(pics) == 1 and all(m.get("plain") for m in pics.values()),
          (run.stdout + run.stderr).strip()[-120:])

    print("\na curriculum over maps:")
    cur = VecSagaEnv(2, map_name=GREENHAVEN, map_schedule="0:gen:arena:size=50x40|100:" + GREENHAVEN + "|300:gen:lakes:size=60x50")
    cur.advance(0)
    cur.reset(seed=1)
    a = cur.map_info(0)["source"]
    cur.advance(150)
    cur.reset()
    b = cur.map_info(1)["source"]
    cur.advance(10 ** 6)
    cur.reset()
    c = cur.map_info(0)["source"]
    check("each entry from its step on", (a, b, c) == ("gen:arena:size=50x40", GREENHAVEN, "gen:lakes:size=60x50"), "%s, %s, %s" % (a, b, c))
    for bad, words in (("x:gen:arena", "steps"), ("0:gen:arena:houses=3", "has no setting")):
        try:
            VecSagaEnv(1, map_schedule=bad)
            why = None
        except Exception as e:
            why = str(e)
        check("a schedule entry refused at once: %s" % bad, why is not None and words in why, str(why)[:90])
    try:
        SagaEnv(map_schedule="0:gen:arena")
        why = None
    except ValueError as e:
        why = str(e)
    check("a schedule on a single environment is refused, not ignored", why is not None and "runner=vec" in why, str(why)[:80])
    try:
        SagaEnv(map_name=GREENHAVEN, map_seed="episode")
        why = None
    except Exception as e:
        why = str(e)
    check("a map per episode of one map is refused", why is not None and "only a generated map" in why, str(why)[:90])


def terrain():
    """The terrain round an agent, asked for by name or in a mapping."""
    print("\nthe terrain patch:")
    base = SagaEnv(map_name=GREENHAVEN, observability="los+terrain:0")
    default = SagaEnv(map_name=GREENHAVEN, observability="los")
    named = SagaEnv(map_name=GREENHAVEN, observability="los+terrain:2")
    mapped = SagaEnv(map_name=GREENHAVEN, observability={"mode": "los", "terrain": 2})
    check("by name and in a mapping, 50 numbers more", named.get_obs_size() == mapped.get_obs_size() == base.get_obs_size() + 50,
          "%d, %d, %d" % (base.get_obs_size(), named.get_obs_size(), mapped.get_obs_size()))
    import jpype
    r = int(jpype.JClass("saga.sim.rl.Observability").DEFAULT_TERRAIN)
    patch = 2 * (2 * r + 1) ** 2
    check("a mode that names no radius has the default patch of %d, %d numbers, and records it" % (r, patch),
          default.get_obs_size() == base.get_obs_size() + patch and default.observability == "los+terrain:%d" % r,
          default.observability)
    named.reset(seed=3)
    d = named.describe_obs(0)
    check("named, and the agent's own block walkable", d.get("self:terrain:walk:0,0") == 1.0 and "self:terrain:sight:2,2" in d,
          str(d.get("self:terrain:walk:0,0")))
    check("the environment says which it is, as it was asked", named.observability == "los+terrain:2", named.observability)
    import json, os, tempfile
    named.step([0, 0])
    path = os.path.join(tempfile.gettempdir(), "saga-conformance-terrain.json")
    named.save_replay(path)
    r = json.load(open(path))
    options = {k: v for k, v in r["env"].items() if k != "learner"}
    again = SagaEnv(**options)
    again.reset(seed=r["episodes"][0]["seed"])
    for acts in r["episodes"][0]["actions"]:
        again.step(acts)
    check("a replay under it rebuilds its environment and reaches the hash", again.get_obs_size() == named.get_obs_size()
          and again.state_hash() == r["episodes"][0]["hash"], options["observability"])


def monsters():
    """The map's monsters, asked for by number: blocks and targets, a replay of them."""
    import json, os, subprocess, tempfile
    from pysaga.vec import VecSagaEnv
    print("\nmonsters:")
    from pysaga import bridge
    homes = os.path.join(bridge.fixtures(), "homes.json")
    none = SagaEnv(map_name=homes, kit="basic")
    two = SagaEnv(map_name=homes, kit="basic", monsters=2)
    block = len([n for n in two._env.obsFieldNames(0) if str(n).startswith("a1:")])
    check("two monsters add two blocks to the observation and two targets",
          two.get_obs_size() == none.get_obs_size() + 2 * block
          and two.get_total_actions() == none.get_total_actions() + 2 and two.n_agents == none.n_agents,
          "obs %d -> %d, actions %d -> %d" % (none.get_obs_size(), two.get_obs_size(),
                                             none.get_total_actions(), two.get_total_actions()))
    try:
        SagaEnv(map_name=homes, monsters=-1)
        check("a negative number is refused", False)
    except ValueError as e:
        check("a negative number is refused", "monsters" in str(e), str(e))

    vec = VecSagaEnv(2, map_name=homes, kit="basic", monsters=2, scripted="1:melee")
    _, _, avail = vec.reset(seed=7)
    rng = np.random.default_rng(7)
    for _ in range(150):
        acts = np.zeros((2, 1), dtype=np.int32)
        for w in range(2):
            acts[w, 0] = int(rng.choice(np.flatnonzero(avail[w, 0])))
        _, _, avail, _, _, _ = vec.step(acts)
    path = os.path.join(tempfile.gettempdir(), "saga-conformance-monsters.json")
    vec.save_replay(path)
    r = json.load(open(path))
    check("the replay file records the monsters", r["env"].get("monsters") == 2, str(r["env"].get("monsters")))
    options = {k: v for k, v in r["env"].items() if k != "learner"}
    again = SagaEnv(scripted={int(k): v for k, v in r["episodes"][1]["scripted"].items()}, **options)
    again.reset(seed=r["episodes"][1]["seed"])
    for acts in r["episodes"][1]["actions"]:
        again.step(acts)
    check("and a world of it replays to its hash, monsters and all", again.state_hash() == r["episodes"][1]["hash"],
          "%d against %d" % (again.state_hash(), r["episodes"][1]["hash"]))
    page = os.path.join(tempfile.gettempdir(), "saga-conformance-monsters.html")
    run = subprocess.run([sys.executable, "-m", "pysaga.replay", path, "-o", page], env=_child_env(), capture_output=True, text=True)
    shown = run.returncode == 0 and "slime (monster)" in open(page).read()
    check("rl_replay plays it to its hash and names the monsters on the page", shown,
          (run.stdout + run.stderr).strip().splitlines()[-1] if (run.stdout + run.stderr).strip() else "")


if __name__ == "__main__":
    sys.exit(main())
