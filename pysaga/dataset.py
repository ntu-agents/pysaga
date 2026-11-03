"""Recorded rounds as offline-RL and imitation datasets (the human play data plan).

A round a recording server recorded is stitched into one recording on the root server
(saga.sim.RoundStitch: round.flight.gz). This turns it into the environment's
trajectories -- saga.sim.rl.RoundDataset replays it and, for every player at every
decision, takes the observation an agent in its place would have had, the action that
stands for what the player did, the mask and the reward -- and writes them in the
D4RL layout most offline-RL code reads:

    observations (N, obs)   actions (N,)   masks (N, n_actions)   rewards (N,)
    terminals (N,)          timeouts (N,)  episode (N,)           ticks (N,)

one row a decision -- its observation at the start of its window, its label what the
player did in the window -- the episodes one after another; terminals marks the last decision of
a player whose round ended, timeouts that of one who left first or whose recording stops.
A round's episodes and the conversion's counts (what was delayed, queued, refused by the
mask, turned into an event) go into its JSON beside it, and every export writes a
datasheet.

Names never leave: a player is a pseudonym, from a mapping file kept with the recordings
(--pseudonyms), and new players get the next free one. The raw layer -- the stitched
recording itself, exact -- is exported with its names replaced the same way (--raw).

    python -m pysaga.dataset <round folder or round.flight.gz>... --out <dir>
        [--observability los] [--agents 2] [--reward ladder] [--frame-skip 4]
        [--progression] [--pseudonyms players.json] [--raw]
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


def _read(path):
    path = pathlib.Path(path)
    if path.is_dir():
        path = path / "round.flight.gz"
    if str(path).endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return path, f.read()
    return path, path.read_text(encoding="utf-8")


def convert(stitched, observability="los", agents=2, progression=False, reward="ladder", frame_skip=4, root=None):
    """A stitched round's trajectories: a list of dicts of arrays, the counts, and what they were made under."""
    bridge.start_jvm(root)
    import jpype
    import jpype.imports                                # noqa: F401
    from saga.sim import FlightRecording
    from saga.sim.rl import RoundDataset, Observability, RewardFunction

    path, text = _read(stitched)
    rec = FlightRecording.parse(jpype.JClass("java.io.StringReader")(text))
    game = jpype.JClass("java.io.File")(str(pathlib.Path(bridge.repo_root(root), "game")))
    worlds = FlightRecording.worlds(game, rec, str(path))
    d = RoundDataset.convert(rec, worlds, _observability(Observability, observability), int(agents),
                             bool(progression), _reward(RewardFunction, reward), int(frame_skip))
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
            terminated=bool(tr.terminated), truncated=bool(tr.truncated)))
    counts = {str(k): int(d.counts.get(k)) for k in d.counts.keySet()}
    made = dict(observability=str(observability), agents=int(agents), progression=bool(progression),
                reward=reward if isinstance(reward, (str, dict)) else str(reward), frame_skip=int(frame_skip),
                obs_size=int(d.obsSize), n_actions=int(d.totalActions),
                build=rec.get("build"), map=rec.get("map"), simhash=rec.get("simhash"),
                round=rec.get("round"), over=rec.get("over"),
                # Whether each input's seen tick was recorded: without it an observation can be up
                # to two ticks newer than anything the player could have seen (RoundDataset)
                seen_ticks="missing" if counts.get("inputs with no seen tick (filed by the tick they landed)") else "recorded")
    return out, counts, made


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
                        masks=cat("masks"), rewards=cat("rewards"), ticks=cat("ticks"),
                        terminals=terminals, timeouts=timeouts, episode=episode)
    meta = dict(made, counts=counts, episodes=[
        dict(player=names.of(t["who"]), bot=t["bot"], type=t["type"], decisions=len(t["actions"]),
             terminated=t["terminated"], truncated=t["truncated"],
             first_tick=int(t["ticks"][0]), last_tick=int(t["ticks"][-1])) for t in trajectories])
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
with. A round recorded before seen ticks existed (seen_ticks "missing" in a round's JSON)
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
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Recorded rounds as offline-RL datasets.")
    ap.add_argument("rounds", nargs="+", help="round folders (with round.flight.gz) or stitched recordings")
    ap.add_argument("--out", required=True)
    ap.add_argument("--observability", default="los")
    ap.add_argument("--agents", type=int, default=2)
    ap.add_argument("--reward", default="ladder")
    ap.add_argument("--frame-skip", type=int, default=4)
    ap.add_argument("--progression", action="store_true")
    ap.add_argument("--pseudonyms", help="the account-to-pseudonym file, kept with the recordings")
    ap.add_argument("--raw", action="store_true", help="also export each stitched recording, names replaced")
    a = ap.parse_args(argv)

    names = Pseudonyms(a.pseudonyms)
    out = pathlib.Path(a.out)
    total, sheet = {}, []
    for k, r in enumerate(a.rounds):
        trajectories, counts, made = convert(r, a.observability, a.agents, a.progression, a.reward, a.frame_skip)
        name = "round-%04d" % k
        meta = write_round(trajectories, counts, made, out, name, names)
        if meta is None:
            print("Dataset: %s holds no decision" % r)
            continue
        if a.raw:
            _, text = _read(r)
            with gzip.open(out / (name + ".flight.gz"), "wt", encoding="utf-8") as f:
                f.write(pseudonymise(text, names))
        for key, v in counts.items():
            total[key] = total.get(key, 0) + v
        sheet.append(dict(name=name, build=made["build"], simhash=made["simhash"], map=made["map"],
                          episodes=len(meta["episodes"]), decisions=sum(e["decisions"] for e in meta["episodes"])))
        print("Dataset: %s -> %s, %d episode(s), %d decisions" % (r, name, len(meta["episodes"]), sheet[-1]["decisions"]))
    names.save()
    (out / "datasheet.json").write_text(json.dumps(dict(
        rounds=sheet, counts=total, observability=a.observability, agents=a.agents, reward=a.reward,
        frame_skip=a.frame_skip, progression=a.progression, rules=DATASHEET), indent=1) + "\n", encoding="utf-8")
    print("Dataset: %d round(s) written to %s, with datasheet.json" % (len(sheet), out))


if __name__ == "__main__":
    main()
