from proj.common.alg_utils import *

def vanilla(env_maker, policy, baseline, n_iter=100, n_envs=mp.cpu_count(),
            n_batch=2000, last_iter=-1, gamma=0.99, gaelam=0.97,
            optimizer={'class': torch.optim.Adam}, val_iters=80, val_lr=1e-3):

    logger.save_config(locals())

    env = env_maker.make()
    policy = policy.pop('class')(env, **policy)
    baseline = baseline.pop('class')(env, **baseline)
    pol_optim = optimizer.pop('class')(policy.parameters(), **optimizer)
    val_optim = torch.optim.Adam(baseline.parameters(), lr=val_lr)

    if last_iter > -1:
        state = logger.get_state(last_iter+1)
        policy.load_state_dict(state['policy'])
        baseline.load_state_dict(state['baseline'])
        pol_optim.load_state_dict(state['pol_optim'])
        val_optim.load_state_dict(state['val_optim'])

    # Algorithm main loop
    with EnvPool(env_maker, n_envs=n_envs) as env_pool:
        for updt in trange(last_iter + 1, n_iter, desc="Training", unit="updt"):
            logger.info("Starting iteration {}".format(updt))
            logger.logkv("Iteration", updt)

            logger.info("Start collecting samples")
            buffer = parallel_collect_samples(env_pool, policy, n_batch)

            logger.info("Computing policy gradient variables")
            all_obs, all_acts, all_advs, all_dists = compute_pg_vars(
                buffer, policy, baseline, gamma, gaelam
            )

            logger.info("Applying policy gradient")
            J0 = torch.mean(policy.dists(all_obs).log_prob(all_acts) * all_advs)
            pol_optim.zero_grad()
            (-J0).backward()
            pol_optim.step()

            logger.info("Updating baseline")
            loss_fn = torch.nn.MSELoss()
            for _ in range(val_iters):
                targets = 0.1 * buffer["baselines"] + 0.9 * buffer["returns"]
                val_optim.zero_grad()
                loss_fn(baseline(all_obs), targets).backward()
                val_optim.step()

            logger.info("Logging information")
            logger.logkv("Objective", J0.item())
            log_reward_statistics(env)
            log_baseline_statistics(buffer)
            log_action_distribution_statistics(buffer, policy)
            logger.dumpkvs()

            logger.info("Saving snapshot")
            logger.save_state(
                updt+1,
                dict(
                    alg=dict(last_iter=updt),
                    policy=policy.state_dict(),
                    baseline=baseline.state_dict(),
                    pol_optim=pol_optim.state_dict(),
                    val_optim=val_optim.state_dict(),
                )
            )
