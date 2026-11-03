"""EPyMARL's PPO learner, with the actor's learning rate its own and an actor held still at first.

Registered by import as "saga_ppo_learner" (python -m pysaga.epymarl), like the vec runner:
EPyMARL is not edited. With its defaults it IS the stock learner -- actor_lr and critic_lr
are EPyMARL's lr, actor_hold_steps 0 -- so a comparison run through it is fair.

An actor initialised from a behaviour clone starts beside a critic that knows nothing: the
first updates' advantages are noise, and can undo the clone before the critic has learned
anything (the plan normalise-and-bc-init, arm C2). actor_hold_steps holds the actor still
(its learning rate 0) for that many environment steps while the critic learns; the actor's
optimiser still sees the gradients meanwhile, so its moment estimates are warm when it moves.

    learner=saga_ppo_learner actor_lr=... critic_lr=... actor_hold_steps=500000
"""

from learners.ppo_learner import PPOLearner


class SagaPPOLearner(PPOLearner):

    def __init__(self, mac, scheme, logger, args):
        super().__init__(mac, scheme, logger, args)
        self.actor_lr = float(getattr(args, "actor_lr", None) or args.lr)
        self.critic_lr = float(getattr(args, "critic_lr", None) or args.lr)
        self.actor_hold_steps = int(getattr(args, "actor_hold_steps", 0) or 0)
        for g in self.critic_optimiser.param_groups:
            g["lr"] = self.critic_lr
        self._said = None

    def train(self, batch, t_env, episode_num):
        held = t_env < self.actor_hold_steps
        for g in self.agent_optimiser.param_groups:
            g["lr"] = 0.0 if held else self.actor_lr
        if self._said != held:
            self._said = held
            self.logger.console_logger.info(
                "Actor %s at t_env %d (actor lr %g, critic lr %g, held until %d)"
                % ("held still" if held else "learning", t_env, self.actor_lr, self.critic_lr, self.actor_hold_steps))
        super().train(batch, t_env, episode_num)
