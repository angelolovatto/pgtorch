import torch, multiprocessing as mp
from torch.nn.utils import parameters_to_vector, vector_to_parameters
from proj.utils import logger
from proj.utils.tqdm_util import trange
from proj.common.models import default_baseline
from proj.common.env_pool import EnvPool
from proj.common.sampling import parallel_collect_samples, compute_pg_vars
from proj.common.utils import conjugate_gradient, fisher_vec_prod, flat_grad
from proj.common.log_utils import *


def line_search(f, x0, dx, expected_improvement, y0=None, accept_ratio=0.1,
                backtrack_ratio=0.8, max_backtracks=15, atol=1e-7):

    if y0 is None:
        y0 = f(x0)

    if expected_improvement >= atol:
        for exp in range(max_backtracks):
            ratio = backtrack_ratio ** exp
            x = x0 - ratio * dx
            y = f(x)
            actual_improvement = y0 - y
            # Armijo condition
            if actual_improvement >= expected_improvement * ratio * accept_ratio:
                logger.logkv("ExpectedImprovement", expected_improvement * ratio)
                logger.logkv("ActualImprovement", actual_improvement)
                logger.logkv("ImprovementRatio", actual_improvement /
                             (expected_improvement * ratio))
                return x

    logger.logkv("ExpectedImprovement", expected_improvement)
    logger.logkv("ActualImprovement", 0.)
    logger.logkv("ImprovementRatio", 0.)
    return x0


def trpo(env_maker, policy, baseline=None, steps=int(1e6), batch=2000,
         n_envs=mp.cpu_count(), gamma=0.99, gaelam=0.97, kl_frac=0.2,
         delta=0.01, val_iters=80, val_lr=1e-3, linesearch=True):

    if baseline is None:
        baseline = default_baseline(policy)

    logger.save_config(locals())
    env = env_maker.make()
    policy = policy.pop('class')(env, **policy)
    baseline = baseline.pop('class')(env, **baseline)
    val_optim = torch.optim.Adam(baseline.parameters(), lr=val_lr)
    loss_fn = torch.nn.MSELoss()

    # Algorithm main loop
    with EnvPool(env_maker, n_envs=n_envs) as env_pool:
        for updt in trange(steps // batch, desc="Training", unit="updt"):
            logger.info("Starting iteration {}".format(updt))
            logger.logkv("Iteration", updt)

            logger.info("Start collecting samples")
            buffer = parallel_collect_samples(env_pool, policy, batch)

            logger.info("Computing policy gradient variables")
            all_obs, all_acts, all_advs = compute_pg_vars(
                buffer, policy, baseline, gamma, gaelam
            )

            # subsample for fisher vector product computation
            if kl_frac < 1.:
                n_samples = int(kl_frac*len(all_obs))
                indexes = torch.randperm(len(all_obs))[:n_samples]
                subsamp_obs = all_obs.index_select(0, indexes)
            else:
                subsamp_obs = all_obs

            logger.info("Computing policy gradient")
            new_dists = policy.dists(all_obs)
            old_dists = new_dists.detach()
            surr_loss = -torch.mean(
                new_dists.likelihood_ratios(old_dists, all_acts) * all_advs
            )
            pol_grad = flat_grad(surr_loss, policy.parameters())

            logger.info("Computing truncated natural gradient")
            F_0 = lambda v: fisher_vec_prod(v, subsamp_obs, policy)
            descent_direction = conjugate_gradient(F_0, pol_grad)
            scale = torch.sqrt(
                2.0 * delta *
                (1. / (descent_direction.dot(F_0(descent_direction))) + 1e-8)
            )
            descent_step = descent_direction * scale

            if linesearch:
                logger.info("Performing line search")
                expected_improvement = pol_grad.dot(descent_step).item()

                @torch.no_grad()
                def f_barrier(params):
                    vector_to_parameters(params, policy.parameters())
                    new_dists = policy.dists(all_obs)
                    surr_loss = -torch.mean(
                        new_dists.likelihood_ratios(old_dists, all_acts) \
                        * all_advs
                    )
                    avg_kl = kl(old_dists, new_dists).mean().item()
                    return surr_loss.item() if avg_kl < delta else float('inf')

                new_params = line_search(
                    f_barrier,
                    parameters_to_vector(policy.parameters()),
                    descent_step,
                    expected_improvement,
                    y0=surr_loss.item()
                )
            else:
                new_params = parameters_to_vector(policy.parameters()) \
                             - descent_step
            vector_to_parameters(new_params, policy.parameters())

            logger.info("Updating baseline")
            targets = buffer["returns"]
            for _ in range(val_iters):
                val_optim.zero_grad()
                loss_fn(baseline(all_obs), targets).backward()
                val_optim.step()

            logger.info("Logging information")
            logger.logkv('TotalNSamples', (updt+1) * (batch - (batch % n_envs)))
            log_reward_statistics(env)
            log_baseline_statistics(buffer)
            log_action_distribution_statistics(old_dists)
            log_average_kl_divergence(old_dists, policy, all_obs)
            logger.dumpkvs()

            logger.info("Saving snapshot")
            logger.save_state(
                updt+1,
                dict(
                    alg=dict(last_iter=updt),
                    policy=policy.state_dict(),
                    baseline=baseline.state_dict(),
                    val_optim=val_optim.state_dict(),
                )
            )
