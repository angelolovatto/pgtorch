import sys, os, os.path as osp, subprocess, gym
from textwrap import dedent
import proj.algorithms
from proj.utils.exp_grid import ExperimentGrid
from proj.common.models import *


# Command line args that will go to ExperimentGrid.run, and must possess unique
# values (therefore must be treated separately).
RUN_KEYS = ['log_dir', 'datestamp']


def friendly_err(err_msg):
    # add whitespace to error message to make it more readable
    return '\n\n' + err_msg + '\n\n'


def parse_and_execute_grid_search(cmd, args):

    algo = eval('proj.algorithms.'+cmd)

    # Before all else, check to see if any of the flags is 'help'.
    valid_help = ['--help', '-h', 'help']
    if any([arg in valid_help for arg in args]):
        print('\n\nShowing docstring for spinup.'+cmd+':\n')
        print(algo.__doc__)
        sys.exit()

    def process(arg):
        # Process an arg by eval-ing it, so users can specify more
        # than just strings at the command line (eg allows for
        # users to give functions as args).
        try:
            return eval(arg)
        except:
            return arg

    # Make first pass through args to build base arg_dict. Anything
    # with a '--' in front of it is an argument flag and everything after,
    # until the next flag, is a possible value.
    arg_dict = dict()
    for i, arg in enumerate(args):
        assert i > 0 or '--' in arg, \
            friendly_err("You didn't specify a first flag.")
        if '--' in arg:
            arg_key = arg.lstrip('-')
            arg_dict[arg_key] = []
        else:
            arg_dict[arg_key].append(process(arg))

    # Make second pass through, to catch flags that have no vals.
    # Assume such flags indicate that a boolean parameter should have
    # value True.
    for k,v in arg_dict.items():
        if len(v)==0:
            v.append(True)

    # Final pass: check for the special args that go to the 'run' command
    # for an experiment grid, separate them from the arg dict, and make sure
    # that they have unique values. The special args are given by RUN_KEYS.
    run_kwargs = dict()
    for k in RUN_KEYS:
        if k in arg_dict:
            val = arg_dict[k]
            assert len(val)==1, \
                friendly_err("You can only provide one value for %s."%k)
            run_kwargs[k] = val[0]
            del arg_dict[k]

    # Determine experiment name. If not given by user, will be determined
    # by the algorithm name.
    if 'exp_name' in arg_dict:
        assert len(arg_dict['exp_name'])==1, \
            friendly_err("You can only provide one value for exp_name.")
        exp_name = arg_dict['exp_name'][0]
        del arg_dict['exp_name']
    else:
        exp_name = 'cmd_' + cmd

    # Special handling for environment: make sure that env_name is a real,
    # registered gym environment.
    valid_envs = [e.id for e in list(gym.envs.registry.all())]
    assert 'env' in arg_dict, \
        friendly_err("You did not give a value for --env! Add one and try again.")
    for env_name in arg_dict['env']:
        err_msg = dedent("""

            %s is not registered with Gym.

            Recommendations:

                * Check for a typo (did you include the version tag?)

                * View the complete list of valid Gym environments at

                    https://gym.openai.com/envs/

            """%env_name)
        assert env_name in valid_envs, err_msg


    # Construct and execute the experiment grid.
    eg = ExperimentGrid(name=exp_name)
    for k,v in arg_dict.items():
        eg.add(k, v)
    eg.run(algo, **run_kwargs)


if __name__ == '__main__':
    cmd = sys.argv[1]
    valid_algos = ['vanilla', 'trpo', 'a2c', 'ppo', 'acktr']
    valid_utils = ['plot', 'sim_policy']
    valid_cmds = valid_algos + valid_utils
    assert cmd in valid_cmds, \
        "Select an algorithm or utility which is implemented in proj."

    if cmd in valid_algos:
        args = sys.argv[2:]
        parse_and_execute_grid_search(cmd, args)

    elif cmd in valid_utils:
        # Execute the correct utility file.
        if cmd == 'plot': cmd = osp.join('viskit', 'frontend')
        runfile = osp.join(
            osp.abspath(osp.dirname(__file__)), 'utils', cmd + '.py'
        )
        args = [sys.executable if sys.executable else 'python', runfile] + \
               sys.argv[2:]
        subprocess.check_call(args, env=os.environ)