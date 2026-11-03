#!/usr/bin/env python3
"""Measure one configuration: N seeded episodes, a policy on each side, the table.

    python -m pysaga.balance --mode duel --episodes 200 --p1 melee --p2 kite
    python -m pysaga.balance --p1 sample:warrior.policy --p2 melee --kit basic

The bots are the game's own (melee, hold, chase, flee, kite, kite:MIN:MAX, capture,
defend), and a trained policy is a bot too: neural:<file> takes its best action,
sample:<file> draws as training did. Every option of the Java tool BalanceRun is
passed through; it runs in a Java of its own, which is about two orders faster than
stepping the episodes through Python.

The installed package runs the jar it carries; in the development repository,
./run-local.sh balance runs the same tool.
"""

import os
import shutil
import subprocess
import sys

from . import bridge


def java():
    home = os.environ.get("JAVA_HOME")
    if home:
        exe = os.path.join(home, "bin", "java.exe" if os.name == "nt" else "java")
        if os.path.isfile(exe):
            return exe
    found = shutil.which("java")
    if not found:
        raise SystemExit("No java found: install Java %d or later, or set JAVA_HOME." % bridge.MIN_JAVA)
    return found


def main():
    if not bridge.installed():
        raise SystemExit("In the development repository use ./run-local.sh balance, which compiles the tool.")
    root = bridge.repo_root()
    cmd = [java(), "-Djava.awt.headless=true", "-cp", bridge.classpath(root), "BalanceRun", root] + sys.argv[1:]
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
