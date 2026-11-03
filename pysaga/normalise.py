"""Input normalisation for learning, one module for every trainer.

Positions reach a network over 2048 (the same distance on every map, a decision of the
observation's), so a strike's 17 px reach is 0.008 of an input: too small a scale for a
network to learn from in reasonable time. Scaling for learning is the learner's, not the
observation's: a Normaliser standardises each input, x' = clip((x - mean) / std, +-clip).

Its statistics are FIXED -- fitted once from data and kept in a file beside the run -- not
running. So the environment stays stationary and Markov (a running normaliser is hidden
state no replay holds), a checkpoint and its normaliser cannot disagree, and a behaviour
clone's weights mean the same in a reinforcement learner fed through the same file. The
inputs are bounded by construction (positions in [0, 1], flags, fractions), so nothing
drifts to an unbounded value as a learner's states move away from those it was fitted on;
a feature nearly constant in the data that varies later is what the floor and the clip
are for.

Every trainer uses it: the environments apply it to what they return (normalise=<file>,
SagaEnv and VecSagaEnv: an EPyMARL env_arg), pysaga.imitate and pysaga.offline train with
it, and the policy file carries it (input_mean, input_std, input_clip), which NeuralPolicy
applies to the observation before its first layer. The critic's state is normalised by
state statistics where the file has them (MAPPO's critic reads the state; IPPO's reads obs).
"""

import pathlib

import numpy as np

FLOOR = 0.02    # the inputs live in [0, 1]: a 17 px reach (0.008) is still 0.4 of a unit
CLIP = 10.0     # as VecNormalize: a value far outside the data cannot blow a unit up


class Normaliser:
    def __init__(self, obs_mean, obs_std, state_mean=None, state_std=None, clip=CLIP):
        self.obs_mean = np.asarray(obs_mean, dtype=np.float32)
        self.obs_std = np.asarray(obs_std, dtype=np.float32)
        self.state_mean = None if state_mean is None else np.asarray(state_mean, dtype=np.float32)
        self.state_std = None if state_std is None else np.asarray(state_std, dtype=np.float32)
        self.clip = float(clip)
        if self.obs_mean.shape != self.obs_std.shape or np.any(self.obs_std <= 0):
            raise ValueError("a normaliser needs a positive std for every input it has a mean for")

    @staticmethod
    def _spread(x, floor):
        sd = x.std(0)
        # A constant input stays as it is (std 1, its mean taken off); any other, at least the floor
        return np.where(sd < 1e-6, 1.0, np.maximum(sd, floor)).astype(np.float32)

    @classmethod
    def fit(cls, obs, state=None, floor=FLOOR, clip=CLIP):
        """Statistics from data: rows of observations (and of states, for a critic that reads them)."""
        obs = np.asarray(obs, dtype=np.float64)
        sm = ss = None
        if state is not None:
            state = np.asarray(state, dtype=np.float64)
            sm, ss = state.mean(0), cls._spread(state, floor)
        return cls(obs.mean(0), cls._spread(obs, floor), sm, ss, clip)

    def obs(self, x):
        x = np.asarray(x, dtype=np.float32)
        return np.clip((x - self.obs_mean) / self.obs_std, -self.clip, self.clip).astype(np.float32)

    def state(self, x):
        x = np.asarray(x, dtype=np.float32)
        if self.state_mean is None:
            return x
        return np.clip((x - self.state_mean) / self.state_std, -self.clip, self.clip).astype(np.float32)

    def save(self, path):
        path = pathlib.Path(path)
        arrays = dict(obs_mean=self.obs_mean, obs_std=self.obs_std, clip=np.float32(self.clip))
        if self.state_mean is not None:
            arrays.update(state_mean=self.state_mean, state_std=self.state_std)
        with open(path, "wb") as f:     # np.savez would add .npz to a name without it
            np.savez(f, **arrays)
        return str(path)

    @classmethod
    def load(cls, path):
        z = np.load(str(path))
        return cls(z["obs_mean"], z["obs_std"], z["state_mean"] if "state_mean" in z else None,
                   z["state_std"] if "state_std" in z else None, float(z["clip"]))

    def torch(self):
        """mean, std and clip as tensors, for a network that applies them itself."""
        import torch
        return torch.as_tensor(self.obs_mean), torch.as_tensor(self.obs_std), self.clip


_SAID = set()


def for_environment(path):
    """The normaliser an environment applies (SagaEnv, VecSagaEnv: normalise=<file>). One fitted
    without the critic's state (pysaga.imitate's, pysaga.offline's) leaves the state as it is:
    harmless for IPPO, whose critic reads observations, not for MAPPO's -- so it says so, once
    per file."""
    norm = Normaliser.load(path)
    if norm.state_mean is None and str(path) not in _SAID:
        _SAID.add(str(path))
        print(f"Normaliser: {path} holds no statistics of the critic's state -- the state goes to "
              f"the learner unnormalised (fine for IPPO, whose critic reads observations)", flush=True)
    return norm
