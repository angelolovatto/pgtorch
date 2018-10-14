import os, json, torch, click
from proj.common import logger
from proj.common.env_makers import EnvMaker
from proj.common.saver import SnapshotSaver
from proj.common.utils import set_global_seeds
from proj.common.tqdm_util import tqdm_out
from proj.algorithms import vanilla
from config import make_policy, make_baseline, make_optim


@click.command()
@click.argument("env")
@click.option("--log_dir", help="where to save checkpoint and progress data",
              type=str, default='data/')
@click.option("--n_iter", help="number of iterations to run",
              type=int, default=100)
@click.option("--n_batch", help="number of samples per iterations",
              type=int, default=2000)
@click.option("--n_envs", help="number of environments to run in parallel",
              type=int, default=8)
@click.option("--gamma", help="discount factor for expected return criterion",
              type=float, default=0.99)
@click.option("--gae_lambda", help="generalized advantage estimation factor",
              type=float, default=0.97)
@click.option("--interval", help="interval between each snapshot",
              type=int, default=10)
@click.option("--seed", help="for repeatability",
              type=int, default=None)
@click.option("--lr", help="learning rate for Adam",
              type=float, default=1e-3)
def main(env, log_dir, n_iter, n_batch, n_envs, gamma, gae_lambda, interval,
         seed, lr):
    """Runs vanilla pg on given environment with specified parameters."""
    
    seed = set_global_seeds(seed)
    exp_name = 'vanilla/' + env
    log_dir += exp_name + '/' + str(seed) + '/'
    os.system("rm -rf {}".format(log_dir))

    with tqdm_out(), logger.session(log_dir):
        with open(os.path.join(log_dir, 'variant.json'), 'at') as fp:
            json.dump(dict(exp_name=exp_name, seed=seed), fp)

        env_maker = EnvMaker(env)
        env = env_maker.make()
        policy = make_policy(env)
        baseline = make_baseline(env)
        optimizer, scheduler = make_optim(policy.parameters())

        vanilla(
            env=env,
            env_maker=env_maker,
            policy=policy,
            baseline=baseline,
            n_iter=n_iter,
            n_batch=n_batch,
            n_envs=n_envs,
            gamma=gamma,
            gae_lambda=gae_lambda,
            optimizer=optimizer,
            scheduler=scheduler,
            snapshot_saver=SnapshotSaver(log_dir, interval=interval)
        )

if __name__ == "__main__":
    main()
