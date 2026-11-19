<p align="center"><img src="docs/logo.png" alt="pySaga" width="327"></p>

pySaga is a Python interface and toolset for [EPyMARL](https://github.com/uoe-agents/epymarl) that lets you train multi-agent reinforcement learning (MARL)
policies for [Saga Online](https://github.com/svalbrecht/saga-online-client), a 2D top-down
multiplayer action-RPG.
In the game, warriors and magicians fight with weapons and abilities on generated maps, in five game modes: Deathmatch, Team Deathmatch, Domination,
Monster Attack and Capture the Flag. The simulation is deterministic and runs inside your
Python process, with no server, and a saved state restores exactly.

The package provides:

- environments with a Gym-style interface, and a vectorised one that steps many worlds in
  one call, with a choice of observability (full, line of sight, a cone of view and others),
  rewards (zero-sum if you want them), maps and opponents (the game's scripted bots or trained policies);
- EPyMARL's algorithms, IPPO and MAPPO among them, set up to train on these environments;
- tools to export a trained policy, evaluate it against the game's bots, and watch its
  episodes as replays in a browser or in the game;
- learning from an expert, with behaviour cloning, DAgger and offline RL.

A trained policy also plays in the game itself as a bot, so you can play against it.

## Play

1. Install Java 21 or newer.
2. Download `saga-client.jar` from the game's [downloads repository](https://github.com/svalbrecht/saga-online-client/releases/latest).
3. Double-click it, or run `java -jar saga-client.jar`.

You need an account on a root server, and a network that reaches the root server and
its game servers, as [its playing guide](https://github.com/svalbrecht/saga-online-client/blob/main/docs/playing.md) explains.

## Train

Install the package from the latest release (Java 21 or newer, Python 3.9 or newer):

```
pip install pysaga-<version>-py3-none-any.whl
python -m pysaga.demo
```

The demo plays one episode with random actions, checks that a saved state restores
exactly, and prints a state hash that is the same on every machine running the same
build.

An episode of Team Deathmatch, two against two under line-of-sight observability, with
one of the four characters played by the game's own melee bot and the other three by
random actions:

```python
import numpy as np
from pysaga import SagaEnv

env = SagaEnv(mode="tdm", team_size=2, observability="los", scripted={1: "melee"})
rng = np.random.default_rng(0)

obs, _ = env.reset(seed=1)
done = False
while not done:
    # one action per learning agent, drawn from the actions its mask allows
    actions = [rng.choice(np.flatnonzero(avail)) for avail in env.get_avail_actions()]
    obs, rewards, terminated, truncated, _ = env.step(actions)
    done = terminated or truncated

print(env.get_stats())
```

Training needs no root server or game server, since the simulation runs inside your
Python process. EPyMARL, policy export, evaluation against the game's bots, and replays you can
watch in a browser or in the game itself, are all in [docs/rl-quickstart.md](docs/rl-quickstart.md).

## In this repository

| | |
| --- | --- |
| [docs/rl-quickstart.md](docs/rl-quickstart.md) | a tutorial: install, train an agent with EPyMARL, measure it, watch it, play against it |
| [docs/rl-reference.md](docs/rl-reference.md) | the RL package in full, with the environment, every option and the tools |
| [docs/imitation.md](docs/imitation.md) | learning from an expert: behaviour cloning, DAgger, offline RL, IPPO started from a clone |
| [docs/abilities.md](docs/abilities.md) | every ability and weapon, with its numbers |
| [docs/maps/](docs/maps/) | the map format, its schema, and a prompt for writing maps with a language model |
| [docs/ADMIN_COMMANDS.md](docs/ADMIN_COMMANDS.md) | the commands of a game server's administrators |
| `pysaga/` | the RL package's Python code |
| [maps/](maps/) | maps contributed by the community, in the saga-map format |
| [configs/](configs/) | contributed training configurations and scripts that reproduce a result |
| [policies/](policies/) | contributed trained policy files |
| `PUBLISHED.txt` | the build this repository's published files come from |
| [LICENSE](LICENSE), [LICENSE-SIMULATION.md](LICENSE-SIMULATION.md), [NOTICE](NOTICE) | the licences of the Python code, the bundled simulation and the contributions |

Contributions of maps, configurations and trained policies are welcome as pull requests
into `maps/`, `configs/` and `policies/`. Everything else here, this README, `docs/` and
`pysaga/` among it, is copied from the game's own repository at each release. To suggest
a change to one of those files, open an issue rather than a pull request.

## Reporting problems

- **The RL package** (installing it, the environment, EPyMARL, export, replays, these
  docs): this repository's [Issues](https://github.com/ntu-agents/pysaga/issues). Give
  pysaga's version (`pip show pysaga`) and, if you can, a seed or a replay file that shows it.
- **The game** (the client, servers, playing): the downloads repository's
  [Issues](https://github.com/svalbrecht/saga-online-client/issues), and a report sent from
  the game, as its [playing guide](https://github.com/svalbrecht/saga-online-client/blob/main/docs/playing.md#reporting-a-problem) explains.
