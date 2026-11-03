#!/usr/bin/env python3
"""Set an EPyMARL checkout up for Saga Online, or check one that is.

    python -m pysaga.epymarl <checkout> [--url URL]
    python -m pysaga.epymarl <checkout> --check

Clones EPyMARL into <checkout> if nothing is there, and registers the environment, the
vectorised runner and the saga PPO learner there BY IMPORT: lines in src/envs/__init__.py,
src/runners/__init__.py and src/learners/__init__.py import them from this package, so none is ever copied into
the checkout -- a copy goes stale without a word (the runner in a checkout once lagged
the repository's by a change, and a run used the old one while every test of the new
one passed). The one file EPyMARL needs as a file, src/config/envs/saga.yaml (sacred
reads the folder), is written with a first line naming this package's build;
--check says whether it still matches the installed package, and running again
rewrites it. Every step is safe to run again.

A checkout set up by the older tools/epymarl_setup.py -- links into the repository and
blocks importing them -- is moved over to this.
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://github.com/uoe-agents/epymarl.git"

MARK = "# -- Saga Online (python -m pysaga.epymarl) --"
OLDMARK = "# -- Saga Online (tools/epymarl_setup.py) --"

ENVS = MARK + '''
from pysaga.epymarl.saga_wrapper import SagaWrapper


def saga_fn(**kwargs) -> MultiAgentEnv:
    return SagaWrapper(**kwargs)


REGISTRY["saga"] = saga_fn
'''

RUNNERS = MARK + '''
from pysaga.epymarl.vec_runner import VecRunner

REGISTRY["vec"] = VecRunner
'''

LEARNERS = MARK + '''
from pysaga.epymarl.saga_learner import SagaPPOLearner

REGISTRY["saga_ppo_learner"] = SagaPPOLearner
'''

# Left by the older setup: links to the repository's copies of the two modules
OLDLINKS = ["src/envs/saga_wrapper.py", "src/runners/vec_runner.py"]

YAML = "src/config/envs/saga.yaml"

# EPyMARL imports smaclite eagerly, so its envs package fails to import without
# smaclite installed, whichever environment is asked for. Imported where it is used.
SMAC_EAGER = "from .smaclite_wrapper import SMACliteWrapper\n"
SMAC_USE = "    return SMACliteWrapper(**kwargs)\n"
SMAC_LAZY = "    from .smaclite_wrapper import SMACliteWrapper\n" + SMAC_USE


def say(done, what):
    print("  %-8s %s" % ("did" if done else "ok", what))


def build():
    from pysaga import bridge
    return bridge.build()


def yaml_text():
    """saga.yaml as this package writes it: a first line naming the build."""
    with open(os.path.join(HERE, "saga.yaml")) as f:
        body = f.read()
    return ("# Written by python -m pysaga.epymarl for pysaga build %s; run it again after "
            "upgrading pysaga.\n" % build()) + body


def write_yaml(checkout):
    target = os.path.join(checkout, YAML)
    want = yaml_text()
    if os.path.islink(target):
        os.remove(target)                     # the older setup's link
    elif os.path.isfile(target) and open(target).read() == want:
        return say(False, "%s is this build's" % YAML)
    with open(target, "w") as f:
        f.write(want)
    say(True, "wrote %s" % YAML)


def drop_old_links(checkout):
    for rel in OLDLINKS:
        target = os.path.join(checkout, rel)
        if os.path.islink(target):
            os.remove(target)
            say(True, "removed the older setup's link %s" % rel)


def register(path, text, what):
    body = open(path).read()
    if OLDMARK in body:
        # The older block was appended: it runs from its mark to the end of the file
        body = body[:body.index(OLDMARK)].rstrip("\n") + "\n"
        open(path, "w").write(body)
        say(True, "removed the older registration from %s" % "/".join(path.replace(os.sep, "/").split("/")[-3:]))
    if MARK in body:
        return say(False, what)
    open(path, "w").write(body.rstrip("\n") + "\n\n\n" + text)
    say(True, what)


def lazy_smaclite(path):
    body = open(path).read()
    # at the START of a line: the moved import holds the same words, indented
    if "\n" + SMAC_EAGER not in body:
        return say(False, "smaclite is imported where it is used")
    if SMAC_USE not in body:
        raise SystemExit("src/envs/__init__.py is not laid out as expected: cannot move the smaclite import")
    open(path, "w").write(body.replace("\n" + SMAC_EAGER, "\n").replace(SMAC_USE, SMAC_LAZY))
    say(True, "moved the smaclite import into smaclite_fn")


def check(checkout):
    """Whether the checkout is set up for this package; 0 when it is."""
    faults = []
    for rel in ("src/envs/__init__.py", "src/runners/__init__.py", "src/learners/__init__.py"):
        path = os.path.join(checkout, rel)
        if not os.path.isfile(path) or MARK not in open(path).read():
            faults.append("%s does not register Saga Online" % rel)
    target = os.path.join(checkout, YAML)
    if not os.path.isfile(target) or os.path.islink(target):
        faults.append("%s is missing, or the older setup's link" % YAML)
    elif open(target).read() != yaml_text():
        m = re.search(r"build (\S+);", open(target).readline())
        if m and m.group(1) == build():
            faults.append("%s has been changed since it was written" % YAML)
        else:
            faults.append("%s is %s, and the installed pysaga is build %s"
                          % (YAML, ("build " + m.group(1)) if m else "not this package's", build()))
    for rel in OLDLINKS:
        if os.path.lexists(os.path.join(checkout, rel)):
            faults.append("%s is left from the older setup" % rel)
    for f in faults:
        print("  stale    " + f)
    if faults:
        print("\nRun  python -m pysaga.epymarl %s  to set it up again." % checkout)
        return 1
    say(False, "%s is set up for pysaga build %s" % (checkout, build()))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("checkout")
    ap.add_argument("--url", default=URL)
    ap.add_argument("--check", action="store_true", help="say whether the checkout matches this package; change nothing")
    a = ap.parse_args()
    checkout = os.path.abspath(os.path.expanduser(a.checkout))

    if a.check:
        if not os.path.isdir(os.path.join(checkout, "src")):
            raise SystemExit("%s is not an EPyMARL checkout" % checkout)
        return check(checkout)

    if not os.path.isdir(os.path.join(checkout, "src")):
        if os.path.exists(checkout) and os.listdir(checkout):
            raise SystemExit("%s exists and is not an EPyMARL checkout" % checkout)
        subprocess.check_call(["git", "clone", "-q", a.url, checkout])
        say(True, "cloned %s" % a.url)
    else:
        say(False, "a checkout is at %s" % checkout)

    drop_old_links(checkout)
    write_yaml(checkout)
    lazy_smaclite(os.path.join(checkout, "src/envs/__init__.py"))
    register(os.path.join(checkout, "src/envs/__init__.py"), ENVS, "the saga environment is registered")
    register(os.path.join(checkout, "src/runners/__init__.py"), RUNNERS, "the vec runner is registered")
    register(os.path.join(checkout, "src/learners/__init__.py"), LEARNERS, "the saga PPO learner is registered")

    # What a run needs, asked of the Python that will run it.
    missing = []
    for mod, pip in [("torch", "torch"), ("sacred", "sacred"), ("yaml", "PyYAML"), ("jpype", "jpype1"),
                     ("pkg_resources", "'setuptools<81'"), ("gymnasium", "gymnasium")]:
        try:
            __import__(mod)
        except Exception:
            missing.append(pip)
    if missing:
        print("\nmissing in %s:\n    pip install %s" % (sys.executable, " ".join(missing)))
        return 1
    say(False, "every package a run imports is installed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
