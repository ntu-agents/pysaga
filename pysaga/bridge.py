"""JVM startup and classpath for the Saga simulation core.

JPype runs the simulation in-process, so there is no serialisation per step and no
socket. One JVM per Python process: under a parallel runner each worker forks and
starts its own, which is why the JVM must be started after the fork, never before.

Two ways to find the simulation and its data:

- INSTALLED (the wheel): the package carries both, `_data/saga-sim.jar` and
  `_data/game/`. Nothing outside the package is read -- not SAGA_ROOT, not SAGA_BUILD:
  a developer's checkout exported in the environment would otherwise put the wheel's
  classes on another build's tables and maps, and nothing would say so (the tables'
  checksums guard a hand edit, not a build). An explicit root= is accepted only when its
  game/BUILD names the wheel's own build.
- A CHECKOUT: the repository the package sits in (or SAGA_ROOT), with the classes
  run-local.sh compiles (SAGA_BUILD, by default ~/.saga-online/build).
"""

import os
import pathlib
import subprocess

_STARTED = False

# The classes are compiled with --release 21, so an older JVM cannot load them -- it
# starts, and the first class fails with UnsupportedClassVersionError out of JPype. And
# floating point is only reproducible because strictfp has been the default since
# JDK 17 (JEP 306). So the minimum is enforced, not assumed.
MIN_JAVA = 21

_DATA = pathlib.Path(__file__).resolve().parent / "_data"


def installed():
    """True when this package is the wheel, carrying its own simulation and data."""
    return (_DATA / "saga-sim.jar").is_file()


def _build_of(root):
    f = pathlib.Path(root, "game", "BUILD")
    return f.read_text().strip() if f.is_file() else None


def repo_root(explicit=None):
    """The folder holding game/: the wheel's own data, or the checkout."""
    if installed():
        if not (_DATA / "game").is_dir():
            raise RuntimeError("This installation of pysaga is broken: %s is there and %s is not. "
                               "Reinstall the wheel." % (_DATA / "saga-sim.jar", _DATA / "game"))
        if explicit:
            mine, theirs = _build_of(_DATA), _build_of(explicit)
            if theirs != mine:
                raise RuntimeError("root=%s holds the data of build %s, and this installed pysaga is build %s: "
                                   "the simulation would run on another build's tables and maps. Leave root "
                                   "out to use the package's own data." % (explicit, theirs or "(none named)", mine))
            return str(pathlib.Path(explicit).resolve())
        return str(_DATA)
    if explicit:
        return str(pathlib.Path(explicit).resolve())
    env = os.environ.get("SAGA_ROOT")
    if env:
        return str(pathlib.Path(env).resolve())
    return str(pathlib.Path(__file__).resolve().parent.parent)


def classpath(root):
    """The simulation's classes: the wheel's jar, or where run-local.sh compiles them."""
    if installed():
        return str(_DATA / "saga-sim.jar")
    home  = os.environ.get("SAGA_HOME", os.path.expanduser("~/.saga-online"))
    build = os.environ.get("SAGA_BUILD", os.path.join(home, "build"))
    if not pathlib.Path(build, "saga/sim/rl/SagaEnv.class").exists():
        raise RuntimeError(
            "Simulation classes not found in %s.\n"
            "Build them first:  ./run-local.sh build" % build)
    return build


def build():
    """The build this package runs: the wheel's, or the checkout's compiled classes'."""
    if installed():
        return _build_of(_DATA) or "unknown"
    try:
        props = pathlib.Path(classpath(None), "saga", "build.properties").read_text()
        for line in props.splitlines():
            if line.startswith("stamp="):
                return line[len("stamp="):]
    except Exception:
        pass
    return "dev"


def fixtures():
    """The small maps the conformance checks use: the wheel's copy, or the checkout's."""
    if installed():
        return str(_DATA / "fixtures")
    return str(pathlib.Path(repo_root(), "tools", "simtest", "maps"))


def _libjvm(java_home):
    for rel in ("lib/server/libjvm.dylib", "lib/server/libjvm.so",
                "jre/lib/server/libjvm.dylib", "bin/server/jvm.dll"):
        p = pathlib.Path(java_home, rel)
        if p.exists():
            return str(p)
    return None


def find_jvm():
    """Pick a JVM new enough to be deterministic.

    JPype's default is whichever JVM the OS registered first, which on a machine
    with several installed is easily the oldest -- here it selects Corretto 8 while
    `java` on PATH is Temurin 21. Prefer JAVA_HOME, then ask macOS for a modern one,
    then fall back to JPype's choice.
    """
    import jpype

    home = os.environ.get("JAVA_HOME")
    if home:
        found = _libjvm(home)
        if found:
            return found

    try:                                     # macOS keeps a registry of JVMs
        home = subprocess.check_output(
            ["/usr/libexec/java_home", "-v", "%d+" % MIN_JAVA],
            stderr=subprocess.DEVNULL).decode().strip()
        found = _libjvm(home)
        if found:
            return found
    except Exception:
        pass

    return jpype.getDefaultJVMPath()


def start_jvm(root=None):
    """Idempotent. Safe to call from every environment instance."""
    global _STARTED
    import jpype

    if jpype.isJVMStarted():
        _STARTED = True
        return

    root = repo_root(root)

    # saga.sim cannot import saga.gc, so nothing here can reach AWT. Asserting
    # headless makes an accidental dependency fail loudly rather than by opening a
    # window on a training machine.
    # --enable-native-access: JPype reaches Java through JNI, which Java 24 and later
    # warn about at every start unless allowed; Java 21 accepts the option too.
    jpype.startJVM(
        find_jvm(),
        "-Djava.awt.headless=true",
        "--enable-native-access=ALL-UNNAMED",
        classpath=[classpath(root)],
        convertStrings=True,
    )

    version = str(jpype.JClass("java.lang.System").getProperty("java.version"))
    head = version.split(".")[0]
    if head.isdigit() and int(head) < MIN_JAVA:
        raise RuntimeError(
            "Java %s is too old: the simulation needs %d or later. "
            "Set JAVA_HOME to a newer JDK." % (version, MIN_JAVA))

    _STARTED = True
