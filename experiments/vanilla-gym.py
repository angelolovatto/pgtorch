import os
import torch
import click
from proj.common import logger
from proj.common.env_makers import EnvMaker
from proj.common.saver import SnapshotSaver
from proj.common.utils import set_global_seeds
from proj.common.models import MlpPolicy, MlpBaseline
from proj.common.tqdm_util import tqdm_out
from proj.algorithms import vanilla


@click.command()
@click.argument("env")
@click.option("--log_dir", help="where to save checkpoint and progress data", type=str, default='data/')
@click.option("--n_iter", help="number of iterations to run", type=int, default=100)
@click.option("--n_batch", help="number of samples per iter", type=int, default=2000)
@click.option("--n_envs", help="number of environments to run in parallel", type=int, default=8)
@click.option("--lr", help="learning rate for Adam", type=float, default=1e-3)
@click.option("--interval", help="interval between each snapshot", type=int, default=10)
@click.option("--seed", help="for repeatability", type=int, default=None)
def main(env, log_dir, n_iter, n_batch, n_envs, lr, interval, seed):
    """Runs vanilla pg on given environment with specified parameters."""
    
    seed = set_global_seeds(seed)
    log_dir += 'vanilla-' + env + '-' + str(seed) + '/'
    os.system("rm -rf {}".format(log_dir))

    with tqdm_out(), logger.session(log_dir):
        env_maker = EnvMaker(env)
        env = env_maker.make()
        ob_space, ac_space = env.observation_space, env.action_space
        policy = MlpPolicy(ob_space, ac_space)
        baseline = MlpBaseline(ob_space, ac_space)
        optimizer = torch.optim.Adam(policy.parameters(), lr=lr)

        vanilla(
            env=env,
            env_maker=env_maker,
            policy=policy,
            baseline=baseline,
            n_iter=n_iter,
            n_batch=n_batch,
            n_envs=n_envs,
            optimizer=optimizer,
            snapshot_saver=SnapshotSaver(log_dir, interval=interval)
        )

if __name__ == "__main__":
    main()
