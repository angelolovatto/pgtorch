from torch.nn.utils import parameters_to_vector, vector_to_parameters
from torch.autograd import grad
from torch.distributions.kl import kl_divergence as kl
from proj.common.utils import conjugate_gradient
from proj.common.alg_utils import *


def line_search(f, x0, ):
    
    return scale

def tnpg(env, env_maker, policy, baseline, n_iter=100, n_batch=2000,
         n_envs=mp.cpu_count(), kl_subsamp_ratio=0.5, step_size=0.01,
         last_iter=-1, gamma=0.99, gae_lambda=0.97, snapshot_saver=None):

    # Algorithm main loop
    with EnvPool(env_maker, n_envs=n_envs) as env_pool:
        for iter in trange(last_iter + 1, n_iter, desc="Training",
                           unit="updt", file=std_out(), dynamic_ncols=True):
            logger.info("Starting iteration {}".format(iter))
            logger.logkv("Iteration", iter)
            
            logger.info("Start collecting samples")
            trajs = parallel_collect_samples(env_pool, policy, n_batch)
            
            logger.info("Computing policy gradient variables")
            all_obs, all_acts, all_advs, all_dists = compute_pg_vars(
                trajs, policy, baseline, gamma, gae_lambda
            )

            # subsample for kl divergence computation
            if kl_subsamp_ratio < 1.:
                indexes = torch.randperm(
                    len(all_obs))[:int(kl_subsamp_ratio*len(all_obs))]
                subsamp_obs = torch.index_select(all_obs, 0, indexes)
                subsamp_dists = policy.distribution(torch.index_select(
                    all_dists.flatparam(), 0, indexes
                ))
            else:
                subsamp_obs = all_obs
                subsamp_dists = all_dists

            logger.info("Computing policy gradient")
            surr_loss = - torch.mean(
                policy.dists(all_obs).log_prob(all_acts) * all_advs)
            pol_grad = torch.cat([
                g.view(-1)
                for g in grad(surr_loss, policy.parameters())
            ])
            
            logger.info("Computing truncated natural gradient")
            avg_kl = lambda: kl(subsamp_dists, policy.dists(subsamp_obs)).mean()
            def F_0(v):
                grads = grad(avg_kl(), policy.parameters(), create_graph=True)
                flat_grads = torch.cat([grad.view(-1) for grad in grads])
                fvp = grad((flat_grads * v).sum(), policy.parameters())
                flat_fvp = torch.cat([g.contiguous().view(-1) for g in fvp])
                return flat_fvp.detach() + v * 1e-3

            descent_direction = conjugate_gradient(F_0, pol_grad)
            scale = torch.sqrt(
                2.0 * step_size *
                (1. / (descent_direction.dot(F_0(descent_direction))) + 1e-8)
            )
            descent_step = descent_direction * scale

            logger.info("Performing line search")
            # f(x0 - descent_step) \\approx f(x0) - grad_f.dot(descent_step)
            expected_improvement = pol_grad.dot(descent_step)

            flat_params = parameters_to_vector(policy.parameters())
            vector_to_parameters(flat_params - descent_step, policy.parameters())

            logger.info("Updating baseline")
            baseline.update(trajs)

            logger.info("Logging information")
            logger.logkv("SurrLoss", surr_loss.item())
            log_reward_statistics(env)
            log_baseline_statistics(trajs)
            log_action_distribution_statistics(all_dists)
            logger.dumpkvs()

            if snapshot_saver is not None:
                logger.info("Saving snapshot")
                snapshot_saver.save_state(
                    iter,
                    dict(
                        alg=tnpg,
                        alg_state=dict(
                            env_maker=env_maker,
                            policy=policy,
                            baseline=baseline,
                            n_iter=n_iter,
                            n_batch=n_batch,
                            n_envs=n_envs,
                            step_size=step_size,
                            kl_subsamp_ratio=kl_subsamp_ratio,
                            last_iter=last_iter,
                            gamma=gamma,
                            gae_lambda=gae_lambda
                        )
                    )
                )
