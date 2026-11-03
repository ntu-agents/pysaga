"""Saga Online environment for EPyMARL.

Registered in an EPyMARL checkout by  python -m pysaga.epymarl <checkout>, which adds
to src/envs/__init__.py:

    from pysaga.epymarl.saga_wrapper import SagaWrapper

    def saga_fn(**kwargs) -> MultiAgentEnv:
        return SagaWrapper(**kwargs)

    REGISTRY["saga"] = saga_fn

Requires jpype1. The installed pysaga carries the simulation; in the repository's
checkout it uses the classes ./run-local.sh build compiles.
"""

from pysaga.env import SagaEnv as _SagaEnv


class SagaWrapper(_SagaEnv):
    """Adapts pysaga to the keyword arguments EPyMARL passes its environments.

    EPyMARL hands every environment common_reward and reward_scalarisation. The
    simulation produces a reward per agent, so both settings are honoured rather
    than validated away: common_reward False suits the independent learners
    (IQL, IA2C, IPPO) and True with sum or mean suits the centralised-critic
    algorithms (QMIX, VDN, MAPPO, COMA).

    It FORWARDS rather than repeating the parameter list, and that is the whole
    of the class now. Listing the arguments here made a second enumeration of
    them, and a second enumeration is a place to be incomplete: mode, team_size
    and reward were absent from it, so every one of the three went into **kwargs
    and was dropped in silence. A config asking for tdm, or for the sparse
    reward the balance work needs, got a dense-reward duel and said nothing --
    team modes could not be trained from a config at all.

    SagaEnv now refuses a keyword it does not know, so a name misspelt in a yaml
    fails at construction with the accepted list rather than training the wrong
    game. Nothing is absorbed on the way through here either, for that to hold.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
