#!/usr/bin/env python3
"""Render a saga-replay file -- what the environment's save_replay() writes -- as a page you can watch.

    python -m pysaga.replay saga_replay.json [-o replays.html] [--title NAME] [--intro TEXT]

EPyMARL's own replay switch is the way to get one: with a checkpoint,

    python src/main.py --config=ippo --env-config=saga with checkpoint_path=results/models/<token> \\
        evaluate=True save_replay=True test_nepisode=8 runner=vec batch_size_run=8 ...

runs the evaluation episodes and then calls the environment's save_replay(), which
writes saga_replay.json in the working directory: the environment's options, and for
every world its last episode's seed and action sequence plus the state hash it ended
on. The simulation is deterministic, so that is the whole episode. This script
rebuilds the environment from the file, replays each episode, checks the hash it
reaches against the one recorded (a different build or content table would play a
different game and say so), and writes one page with the map, every character's
position, health and facing at every decision, each learner's action, and the action
mix -- replay_viewer.html (beside this file) with the data embedded. Each map is drawn plain:
every cell coloured by whether it can be walked and seen through, which is what an agent
perceives of the terrain, with its points marked. The package carries none of the game's
pictures. To watch an episode as the game draws it, with its sprites and sounds, play the
file in the client: java -jar saga-client.jar -replay FILE [N] (./run-local.sh replay FILE [N]
in a checkout).
"""

import argparse
import base64
import json
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DIRN = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
TYPES = {0: "warrior", 1: "magician"}


def load(path):
    with open(path) as f:
        r = json.load(f)
    if "episodes" not in r:                   # the first format: one episode, no environment
        # It was recorded on Arcadia, the map the game shipped with until 2026 and no longer
        # does: naming it makes the replay fail on the missing map rather than play elsewhere
        r = {"env": {"map_name": "Arcadia"}, "episodes": [{"world": 0, "seed": r["seed"], "actions": r["actions"]}]}
        print("note: %s names no environment; assuming the default duel on Arcadia" % path)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("replay")
    ap.add_argument("-o", "--out", default="replays.html")
    ap.add_argument("--title", default="Saga Replays")
    ap.add_argument("--intro", default="")
    args = ap.parse_args()

    from pysaga import bridge
    from pysaga.env import SagaEnv
    root = bridge.repo_root()

    r = load(args.replay)
    env_args = dict(r.get("env", {}))
    file_scripted = env_args.pop("scripted", None)       # the first format kept the bots here
    learner = env_args.pop("learner", None) or "learner"  # what trained the learners: a name, not an option
    env_args.pop("normalise", None)   # the learners' input scaling: outside the dynamics, a replay needs no file of it
    if env_args.get("reward") == "custom":
        env_args.pop("reward")
    envs = {}

    def env_for(scripted):
        """One environment per distinct set of bots: a batch may hold several."""
        key = json.dumps(scripted, sort_keys=True)
        if key not in envs:
            envs[key] = SagaEnv(scripted={int(k): v for k, v in scripted.items()} or None, **env_args)
        return envs[key]

    # A map's picture is drawn from the map the episode played on: no picture is stored with a map, and a file of version 2 names each
    # episode's map -- a generated one by its source and seed, any other by its text,
    # carried in the file ("maps") so that a shipped map changed since replays as it was
    import jpype
    from pysaga.bridge import start_jvm
    start_jvm(root)
    render = jpype.JClass("saga.map.render.RenderTool")
    game_dir = jpype.JClass("java.io.File")(os.path.join(root, "game"))
    map_texts = r.get("maps", {})
    map_seed = env_args.get("map_seed", "fixed")
    tmp = tempfile.mkdtemp(prefix="saga-replay-")
    pictures = {}

    def source_of(entry):
        """What the episode's map is made from here: its text where the file carries it."""
        if entry["seed"] < 0 and entry["sim_hash"] in map_texts:
            path = os.path.join(tmp, entry["sim_hash"][:16] + ".json")
            if not os.path.exists(path):
                with open(path, "w") as f:
                    f.write(map_texts[entry["sim_hash"]])
            return path, "fixed"
        return entry["source"], (map_seed if entry["seed"] >= 0 else "fixed")

    def uri(png):
        return "data:image/png;base64," + base64.b64encode(png).decode()

    def picture(jenv):
        """A map's picture: plain, by walk and sight, with its points."""
        h = str(jenv.mapSimHash())
        if h not in pictures:
            plain = bytes(render.plainPngOfText(game_dir, jenv.mapText()))
            w, hh = struct.unpack(">II", plain[16:24])
            pictures[h] = {"w": int(w), "h": int(hh), "plain": uri(plain)}
        return h

    seconds = int(env_args.get("frame_skip", 4)) * 0.05   # the file's ticks of 50 ms a decision

    episodes = []
    mismatch = 0
    learners = []
    for e in r["episodes"]:
        scripted = e.get("scripted", file_scripted) or {}
        scripted = {int(k): v for k, v in scripted.items()}
        env = env_for(scripted)
        jenv = env._env
        st = jenv.world().state()
        n_slots = int(jenv.nCharacters())              # the agents' slots, then the monsters
        learners = [int(jenv.slotOf(k)) for k in range(env.n_agents)]

        def snap(actions):
            row = [int(st.tick)]
            for s in range(n_slots):
                row += [int(st.pixelX(s)), int(st.pixelY(s)), int(st.health[s]), int(st.alive[s]), int(st.facing[s]),
                        int(st.kbRemaining[s] > 0)]
            row += [int(a) for a in actions] if actions is not None else [-1] * len(learners)
            return row

        entry = e.get("map")
        if entry is not None:
            source, mode = source_of(entry)
            env.set_map_source(source, mode)
        env.reset(seed=int(e["seed"]))
        map_ok = entry is None or str(jenv.mapSimHash()) == entry["sim_hash"]
        map_key = picture(jenv)
        def name(s):
            if int(st.kind[s]) != 0:
                kind = jenv.world().npcKind(s)
                return "%s (monster)" % (str(kind.name) if kind is not None else "monster")
            return ("%s, team %d" % (TYPES.get(int(st.type[s]), "?"), int(st.team[s]))
                    + ((" (" + scripted[s] + " bot)") if scripted and s in scripted else ""))

        slots = [{"slot": s, "team": int(st.team[s]), "type": TYPES.get(int(st.type[s]), str(int(st.type[s]))),
                  "name": name(s)}
                 for s in range(n_slots)]
        frames = []
        done = False
        for acts in e["actions"]:
            if done:
                break
            frames.append(snap(acts))
            _, _, term, trunc, _ = env.step(acts)
            done = term or trunc
        frames.append(snap(None))
        h = int(jenv.hash())
        ok = map_ok and (("hash" not in e) or int(e["hash"]) == h)
        if not ok:
            mismatch += 1
        w = int(jenv.winner())
        own = set(int(st.team[s]) for s in learners)
        if w > 0:
            result = ("won" if w in own and len(own) == 1 else "lost" if w not in own else "team %d won" % w)
        elif w < 0:
            result = "draw"
        else:
            result = "time ran out"
        cls = "good" if result == "won" else "bad" if result == "lost" else "warn"
        kills = sum(int(st.kills[s]) for s in learners)
        deaths = sum(int(st.deaths[s]) for s in learners)
        dealt = sum(int(st.dmgDealtTotal[s]) for s in learners)
        taken = sum(int(st.dmgTakenTotal[s]) for s in learners)
        label = "world %d, seed %d" % (int(e.get("world", 0)), int(e["seed"]))
        label = learner + " " + label
        if scripted:
            label = learner + " vs " + ", ".join(scripted[s] for s in sorted(scripted)) + " -- world %d, seed %d" % (int(e.get("world", 0)), int(e["seed"]))
        episodes.append({"label": label, "map": map_key, "result": result + ("" if ok else " (replay differs)" if map_ok else " (another map)"), "resultClass": cls,
                         "summary": "%d decisions, %d kills, %d deaths, dealt %d, taken %d" % (len(frames) - 1, kills, deaths, dealt, taken),
                         "slots": slots, "learners": learners, "frames": frames})
        print("%-40s %-14s %4d decisions  hash %s%s" % (label, result, len(frames) - 1, "ok" if ok else "DIFFERS",
                                                       "" if map_ok else "  (the map is not the one recorded)"))

    bots = sorted(set(v for e in r["episodes"] for v in (e.get("scripted", file_scripted) or {}).values()))
    data = {"maps": pictures,
            "seconds_per_decision": seconds,
            "intro": args.intro or ("Replayed from %s: %s, %s kit%s." % (
                os.path.basename(args.replay), env_args.get("mode", "duel"), env_args.get("kit", "dealt"),
                (", learner against " + ", ".join(bots)) if bots else "")),
            "episodes": episodes}
    with open(os.path.join(HERE, "replay_viewer.html")) as f:
        page = f.read()
    page = page.replace("/*__TITLE__*/", args.title).replace("/*__DATA__*/", json.dumps(data).replace("</", "<\\/"))
    with open(args.out, "w") as f:
        f.write(page)
    print("wrote %s (%d episodes, %d bytes)%s" % (args.out, len(episodes), os.path.getsize(args.out),
                                                  "" if not mismatch else "; %d episode(s) did not replay to the recorded hash" % mismatch))
    return 1 if mismatch else 0


if __name__ == "__main__":
    sys.exit(main())
