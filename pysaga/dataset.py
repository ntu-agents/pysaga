"""Recorded rounds as offline-RL and imitation datasets (the human play data plan).

A round a recording server recorded is stitched into one recording on the root server
(saga.sim.RoundStitch: round.flight.gz) and made its state record by the build that
recorded it (saga.sim.Ingest: states.gz, every tick's state by field name). This turns the
record into the environment's trajectories with THIS build -- saga.sim.rl.RoundDataset
restores each tick, lifted into this build's schema, and for every player at every decision
takes the observation an agent in its place would have had, the action that stands for what
the player did, the mask and the reward -- so rounds of older builds convert too, and writes
them in the D4RL layout most offline-RL code reads:

    observations (N, obs)   actions (N,)   masks (N, n_actions)   rewards (N,)
    terminals (N,)          timeouts (N,)  episode (N,)           ticks (N,)
    dynamics (N,)           fields (obs,)

one row a decision -- its observation at the start of its window, its label what the
player did in the window -- the episodes one after another; terminals marks the last decision of
a player whose round ended, timeouts that of one who left first or whose recording stops.
dynamics is each decision's round's World.DYNAMICS -- a number raised whenever the game
came to play differently -- so one export may hold rounds of several versions and a
researcher may filter (--dynamics) or condition on it; fields names every observation
column (the layout). A round's episodes, its versions (dynamics, schema, content tables,
builds, map, layout) and the conversion's counts (what was delayed, queued, refused by the
mask, turned into an event) go into its JSON beside it, and every export writes a
datasheet.

Names never leave: a player is a pseudonym, from a mapping file kept with the recordings
(--pseudonyms), and new players get the next free one. The raw layer -- the stitched
recording itself, exact -- is exported with its names replaced the same way (--raw).

    python -m pysaga.dataset <round folder or states.gz>... --out <dir>
        [--observability los] [--agents 2] [--reward ladder] [--frame-skip 4]
        [--progression] [--pseudonyms players.json] [--raw] [--dynamics 3[,4]]
    python -m pysaga.dataset align <target dataset> <datasets>... --out <dir>
        datasets of another observation layout projected into the target's, by field name
"""

import argparse
import gzip
import json
import os
import pathlib
import re

import numpy as np

from . import bridge
from .env import _observability, _reward


def record_path(path):
    """A round's state record: a round folder's states.gz, or the file named."""
    path = pathlib.Path(path)
    if path.is_dir():
        path = path / "states.gz"
    if not path.is_file():
        raise SystemExit("%s: no state record -- the round is ingested first, by the build that recorded it "
                         "(saga-ingest on the root server, ./run-local.sh round-ingest on the dev stack)" % path)
    return path


def record_header(path):
    """A state record's header, read without the game: its keys in order (a key may repeat), and its schema.
    The layout is StateRecord's: a text is a big-endian int length and its UTF-8 bytes."""
    import struct
    with gzip.open(record_path(path), "rb") as f:
        def text():
            n = struct.unpack(">i", f.read(4))[0]
            return f.read(n).decode("utf-8")
        if text() != "saga-states 2":
            raise SystemExit("%s is not a state record" % path)
        pairs = [(text(), text()) for _ in range(struct.unpack(">i", f.read(4))[0])]
        schema = struct.unpack(">i", f.read(4))[0]
    return pairs, schema


def versions(path):
    """What a round was played and recorded by: dynamics, schema, content tables, build, map."""
    pairs, schema = record_header(path)
    h = {}
    for k, v in pairs:
        h.setdefault(k, v)
    return dict(dynamics=int(h["dynamics"]), schema=schema, content=h.get("content"),
                build=h.get("build"), statebuild=h.get("statebuild"), map=h.get("map"), simhash=h.get("simhash"))


def layout_of(fields, n_actions, agents):
    """A short name for an observation and action layout: what a policy or another dataset must match."""
    import hashlib
    text = "\n".join(fields) + "\nactions %d\nagents %d" % (n_actions, agents)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def convert(round_, observability="los", agents=2, progression=False, reward="ladder", frame_skip=4, root=None):
    """A round's trajectories, from its state record with this build: a list of dicts of arrays, the counts,
    and what they were made under. Observations, masks, rewards and labels are this build's, on the recorded
    states lifted into this build's schema (saga.sim.StateRecord): a round of an older build converts too."""
    path = record_path(round_)
    bridge.start_jvm(root)
    import jpype
    import jpype.imports                                # noqa: F401
    from saga.sim import StateRecord
    from saga.sim.rl import RoundDataset, Observability, RewardFunction

    rec = StateRecord.Round(jpype.JClass("java.io.File")(str(path)))
    game = jpype.JClass("java.io.File")(str(pathlib.Path(bridge.repo_root(root), "game")))
    worlds = rec.worlds(game)
    d = RoundDataset.convert(rec, worlds, _observability(Observability, observability), int(agents),
                             bool(progression), _reward(RewardFunction, reward), int(frame_skip))
    dynamics = int(rec.get("dynamics"))
    out = []
    for tr in d.trajectories:
        n = int(tr.length)
        out.append(dict(
            who=str(tr.who), slot=int(tr.slot), bot=bool(tr.bot), type=int(tr.type),
            observations=np.asarray(tr.obs, dtype=np.float32).reshape(n, int(d.obsSize)),
            actions=np.asarray(tr.actions, dtype=np.int64),
            masks=np.asarray(tr.masks, dtype=np.int8).reshape(n, int(d.totalActions)),
            rewards=np.asarray(tr.rewards, dtype=np.float32),
            ticks=np.asarray(tr.ticks, dtype=np.int64),
            dynamics=np.full(n, dynamics, dtype=np.int32),
            **lag_arrays(tr),
            terminated=bool(tr.terminated), truncated=bool(tr.truncated)))
    counts = {str(k): int(d.counts.get(k)) for k in d.counts.keySet()}
    if rec.mapDiffers():
        counts["map_differs: the round's map compiles to another simHash in this build"] = 1
    fields = [str(f) for f in d.fields] if d.fields is not None else []
    made = dict(observability=str(observability), agents=int(agents), progression=bool(progression),
                reward=reward if isinstance(reward, (str, dict)) else str(reward), frame_skip=int(frame_skip),
                obs_size=int(d.obsSize), n_actions=int(d.totalActions),
                layout=layout_of(fields, int(d.totalActions), int(agents)), fields=fields,
                dynamics=dynamics, schema=int(rec.schema), content=rec.get("content"),
                build=rec.get("build"), statebuild=rec.get("statebuild"), map=rec.get("map"), simhash=rec.get("simhash"),
                round=rec.get("round"), over=rec.get("over"),
                # Whether each input's seen tick was recorded: without it an observation can be up
                # to two ticks newer than anything the player could have seen (RoundDataset)
                seen_ticks="missing" if counts.get("inputs with no seen tick (filed by the tick they landed)") else "recorded")
    return out, counts, made


def lag_arrays(tr):
    """A trajectory's figures for whoever studies lag, one a decision (RoundDataset).

    seen_distance: how many ticks after the state its player saw the labelled input landed --
    the input's whole lag -- or -1 where the label is no input of the player's (a no-op) or the
    recording has no seen ticks. diverged: 1 where the player's client first held another state
    than the observation's, or than one its window's inputs were made on, so the player may
    have seen another picture than the observation. elapsed_ms: the milliseconds on the
    player's own machine between its game stepping the last decision's tick and this one's
    (frame_skip x 50 on a machine keeping up), -1 for a trajectory's first decision and where
    the recording has no times. late_label: 1 where the label's input was seen in an earlier
    window than the decision's, so the observation is newer than the state the player acted on.
    """
    return dict(seen_distance=np.asarray(tr.seenDistance, dtype=np.int16),
                diverged=np.asarray(tr.apart, dtype=np.int8),
                elapsed_ms=np.asarray(tr.elapsedMs, dtype=np.int32),
                late_label=np.asarray(tr.late, dtype=np.int8))


class Pseudonyms:
    """Account names to pseudonyms, kept in a file beside the recordings and never exported."""

    def __init__(self, path=None):
        self.path = pathlib.Path(path) if path else None
        self.map = json.loads(self.path.read_text(encoding="utf-8")) if self.path and self.path.is_file() else {}

    def of(self, who):
        account, _, bot = who.partition("#")
        if account not in self.map:
            used = {int(v.split("-")[1]) for v in self.map.values() if re.fullmatch(r"player-\d+", v)}
            self.map[account] = "player-%04d" % (max(used, default=0) + 1)
        return self.map[account] + ("#" + bot if bot else "")

    def save(self):
        if self.path:
            tmp = self.path.with_suffix(".part")
            tmp.write_text(json.dumps(self.map, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(self.path)


def pseudonymise(text, names):
    """A recording with every player's name replaced: its slot, stitched and install headers."""
    out = []
    for line in text.split("\n"):
        if line.startswith("H slot "):
            f = line.split(" ")
            tail = f[-3:] if len(f) >= 6 and f[-3] == "from" else []
            who = " ".join(f[3:len(f) - len(tail)])
            line = " ".join(f[:3] + [names.of(who)] + tail)
        elif line.startswith("H stitched "):
            f = line.split(" ")
            line = " ".join(f[:2] + [names.of(" ".join(f[2:-1]))] + f[-1:])
        elif line.startswith("H install "):
            f = line.split(" ")
            line = " ".join(f[:3] + [names.of(" ".join(f[3:]))])
        out.append(line)
    return "\n".join(out)


def write_round(trajectories, counts, made, out, name, names):
    """One round's npz (D4RL layout) and its JSON."""
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if not trajectories:
        return None
    cat = lambda key: np.concatenate([t[key] for t in trajectories])
    terminals = np.concatenate([np.eye(1, len(t["actions"]), len(t["actions"]) - 1, dtype=np.int8)[0] * int(t["terminated"])
                                for t in trajectories])
    timeouts = np.concatenate([np.eye(1, len(t["actions"]), len(t["actions"]) - 1, dtype=np.int8)[0] * int(t["truncated"])
                               for t in trajectories])
    episode = np.concatenate([np.full(len(t["actions"]), k, dtype=np.int32) for k, t in enumerate(trajectories)])
    np.savez_compressed(out / (name + ".npz"), observations=cat("observations"), actions=cat("actions"),
                        masks=cat("masks"), rewards=cat("rewards"), ticks=cat("ticks"), dynamics=cat("dynamics"),
                        fields=np.array(made["fields"], dtype=str),
                        seen_distance=cat("seen_distance"), diverged=cat("diverged"),
                        elapsed_ms=cat("elapsed_ms"), late_label=cat("late_label"),
                        terminals=terminals, timeouts=timeouts, episode=episode)
    meta = dict({k: v for k, v in made.items() if k != "fields"}, counts=counts, episodes=[
        dict(player=names.of(t["who"]), bot=t["bot"], type=t["type"], decisions=len(t["actions"]),
             terminated=t["terminated"], truncated=t["truncated"],
             first_tick=int(t["ticks"][0]), last_tick=int(t["ticks"][-1]),
             # Lag at a glance: the inputs whose seen distance is known, the largest, and the decisions apart
             inputs_with_seen_distance=int((t["seen_distance"] >= 0).sum()),
             max_seen_distance=int(t["seen_distance"].max(initial=-1)),
             diverged_decisions=int(t["diverged"].sum()),
             # Real time: the decisions whose elapsed time is known, the longest, and the labels placed late
             decisions_with_elapsed_ms=int((t["elapsed_ms"] >= 0).sum()),
             max_elapsed_ms=int(t["elapsed_ms"].max(initial=-1)),
             late_labels=int(t["late_label"].sum())) for t in trajectories])
    (out / (name + ".json")).write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    return meta


DATASHEET = """The rounds of this dataset were played on recording servers of Saga Online by players
who agreed to it, under a pseudonym and without chat. Each round's players recorded it on
their own machines and the root server stitched their recordings into one (only what they
agreed on; every part replayed to its hashes first).

A decision is taken every frame_skip ticks of 50 ms, on the ticks frame_skip divides, its
observation the state at the start of its window (that tick and the frame_skip - 1 after
it), and its label what the player did on what it could see in the window: every input
carries the newest state its player could have seen when it was taken (its seen tick), and
is filed in the window that tick falls in, however later it landed. So an observation is
never newer than anything the player could have seen -- older by up to frame_skip - 1 ticks,
and by the player's own reaction time -- and holds nothing of the action it is labelled
with. The observations, masks, rewards and labels are those of the build that converted
the round, on the states the round went through: each round says the dynamics it was
played under (dynamics, one a decision too) and the build that recorded it. A round of an
older dynamics was played by other rules; the dynamics column lets a model tell them apart
or a filter leave them out. A round recorded before seen ticks existed (seen_ticks "missing" in a round's JSON)
files an input by the tick it landed, and its observations can be up to two ticks newer
than what the player saw. An order (a cast,
a learn, a slot of the bar, a skill point, a purchase, an item used) is labelled one at a
time, in the order given -- a second in one window waits for the next, whose observation
then already shows it, and is counted; a cast needs "select the slot" first when another is
selected, so it spans two windows. Otherwise the label is the movement the player asked by
the window's end, where the latched direction differs, else a no-op. Weapons bought or taken in hand, team and spawn point changes,
gifts, sales and element choices have no action: they are events, counted. The counts
say how many orders were delayed, queued, refused by the mask, and turned into events.

Observations are the environment's (ObsEncoder) under the stated observability and number
of agents: an observer sees the first agents - 1 other characters present, in slot order,
monsters included -- a change of agents changes what is seen. Labels are measured against
known decisions in the design test, not claimed exact. Human players react with their
own lag; a recorded scripted player's decisions land two or three ticks after they are
made.

Four arrays say what the network did to a decision, one row a decision like the rest.
seen_distance is the labelled input's lag in ticks of 50 ms: how long after the state its
player saw the input landed, the input delay and any wait on another player included (2 or
3 on a quiet link, more on a slow one); -1 where the label is no input of the player's (a
no-op) or the recording has no seen ticks. It is a lower bound on a person's lag, whose own
reaction comes on top. diverged is 1 where the player's own game first held another state
than the observation shows, or than one the window's inputs were made on -- its game had
come apart from the others' for those ticks, repaired later or not -- so the player may have
seen another picture than the observation. elapsed_ms is real time: the milliseconds on the
player's own machine between its game stepping the decision before's tick and this one's.
A machine keeping up reads the decision's ticks x 50; more is a game that waited for another
player or stood still, less one catching up afterwards. It is -1 for an episode's first
decision and where a recording has no times (one made before they were recorded, or a
player whose own game's parts are missing). No date is kept: a player's times count from its
first tick in the round. late_label is 1 where the label's input was seen in an earlier
window than the decision's -- a second order given in one window, an input seen before the
episode's first decision -- so the observation is newer than the state the player acted on
and may already show what the input did; drop those rows where that matters. Nothing else
of the network is recorded: no round trips, no packet loss.
"""


def _npz_files(paths):
    out = []
    for p in paths:
        p = pathlib.Path(p)
        out += sorted(p.glob("*.npz")) if p.is_dir() else [p]
    return out


def align(target, datasets, out):
    """Datasets projected into a target's observation layout by field name (pysaga.dataset align): a field the
    target has is copied where a dataset has it and 0 where it has not -- a known: flag 0, nothing known -- and a
    field the target lacks is dropped, each counted in the JSON; every other array as it was. So datasets of two
    observation versions concatenate. Refused across different agents or action spaces, which no projection of
    observations reconciles. target is a dataset (npz, or a folder's first) whose layout the others take."""
    tf = _npz_files([target])
    if not tf:
        raise SystemExit("no dataset at %s to take a layout from" % target)
    tmeta = json.loads(tf[0].with_suffix(".json").read_text(encoding="utf-8"))
    fields = [str(f) for f in np.load(tf[0])["fields"]]
    where = {f: j for j, f in enumerate(fields)}
    layout = layout_of(fields, int(tmeta["n_actions"]), int(tmeta["agents"]))
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for f in _npz_files(datasets):
        meta = json.loads(f.with_suffix(".json").read_text(encoding="utf-8"))
        if int(meta["n_actions"]) != int(tmeta["n_actions"]) or int(meta["agents"]) != int(tmeta["agents"]):
            raise SystemExit("%s has %s actions and %s agents, the target %s and %s: no alignment crosses action spaces or agents"
                             % (f, meta["n_actions"], meta["agents"], tmeta["n_actions"], tmeta["agents"]))
        z = dict(np.load(f))
        src = [str(x) for x in z["fields"]]
        have = {x: i for i, x in enumerate(src)}
        obs = np.zeros((len(z["observations"]), len(fields)), dtype=np.float32)
        copied = [j for j, x in enumerate(fields) if x in have]
        obs[:, copied] = z["observations"][:, [have[fields[j]] for j in copied]]
        added = [x for x in fields if x not in have]
        dropped = [x for x in src if x not in where]
        z["observations"], z["fields"] = obs, np.array(fields, dtype=str)
        np.savez_compressed(out / f.name, **z)
        meta.update(obs_size=len(fields), layout=layout,
                    aligned=dict(was=meta.get("layout"), copied=len(copied), added=added, dropped=dropped))
        (out / f.with_suffix(".json").name).write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
        print("Align: %s -> layout %s: %d fields copied, %d added at 0, %d dropped" % (f.name, layout, len(copied), len(added), len(dropped)))


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["align"]:
        al = argparse.ArgumentParser(prog="python -m pysaga.dataset align",
                                     description="Datasets projected into a target dataset's observation layout.")
        al.add_argument("target", help="a dataset (npz, or a folder) whose layout the others take")
        al.add_argument("datasets", nargs="+", help="npz files or folders of them")
        al.add_argument("--out", required=True)
        b = al.parse_args(argv[1:])
        align(b.target, b.datasets, b.out)
        return
    ap = argparse.ArgumentParser(description="Recorded rounds as offline-RL datasets.")
    ap.add_argument("rounds", nargs="+", help="round folders (with states.gz, ingested) or state records")
    ap.add_argument("--out", required=True)
    ap.add_argument("--observability", default="los")
    ap.add_argument("--agents", type=int, default=2)
    ap.add_argument("--reward", default="ladder")
    ap.add_argument("--frame-skip", type=int, default=4)
    ap.add_argument("--progression", action="store_true")
    ap.add_argument("--pseudonyms", help="the account-to-pseudonym file, kept with the recordings")
    ap.add_argument("--raw", action="store_true", help="also export each stitched recording, names replaced")
    ap.add_argument("--dynamics", help="only rounds of these dynamics, e.g. 3 or 3,4 (World.DYNAMICS when recorded)")
    a = ap.parse_args(argv)
    wanted = None if not a.dynamics else {int(x) for x in a.dynamics.split(",")}

    names = Pseudonyms(a.pseudonyms)
    out = pathlib.Path(a.out)
    total, sheet = {}, []
    layouts = set()
    for k, r in enumerate(a.rounds):
        v = versions(r)
        if wanted is not None and v["dynamics"] not in wanted:
            print("Dataset: %s left out -- dynamics %d, not %s" % (r, v["dynamics"], a.dynamics))
            continue
        trajectories, counts, made = convert(r, a.observability, a.agents, a.progression, a.reward, a.frame_skip)
        layouts.add(made["layout"])
        name = "round-%04d" % k
        meta = write_round(trajectories, counts, made, out, name, names)
        if meta is None:
            print("Dataset: %s holds no decision" % r)
            continue
        if a.raw:
            with gzip.open(record_path(r).parent / "round.flight.gz", "rt", encoding="utf-8") as f:
                text = f.read()
            with gzip.open(out / (name + ".flight.gz"), "wt", encoding="utf-8") as f:
                f.write(pseudonymise(text, names))
        for key, v in counts.items():
            total[key] = total.get(key, 0) + v
        sheet.append(dict(name=name, build=made["build"], simhash=made["simhash"], map=made["map"],
                          dynamics=made["dynamics"], schema=made["schema"], content=made["content"],
                          statebuild=made["statebuild"], layout=made["layout"],
                          episodes=len(meta["episodes"]), decisions=sum(e["decisions"] for e in meta["episodes"])))
        print("Dataset: %s -> %s, %d episode(s), %d decisions" % (r, name, len(meta["episodes"]), sheet[-1]["decisions"]))
    names.save()
    out.mkdir(parents=True, exist_ok=True)
    (out / "datasheet.json").write_text(json.dumps(dict(
        rounds=sheet, counts=total, observability=a.observability, agents=a.agents, reward=a.reward,
        frame_skip=a.frame_skip, progression=a.progression, layouts=sorted(layouts), rules=DATASHEET), indent=1) + "\n",
        encoding="utf-8")
    print("Dataset: %d round(s) written to %s, with datasheet.json" % (len(sheet), out))


if __name__ == "__main__":
    main()
