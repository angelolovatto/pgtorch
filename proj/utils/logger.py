"""
This project was developed by Rocky Duan, Peter Chen, Pieter Abbeel for the
Berkeley Deep RL Bootcamp, August 2017. Bootcamp website with slides and lecture
videos: https://sites.google.com/view/deep-rl-bootcamp/.

Code adapted from OpenAI Baselines: https://github.com/openai/baselines

Copyright 2017 Deep RL Bootcamp Organizers.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""


import os, os.path as osp, sys, json, shutil, datetime, dateutil.tz
from proj.utils.tqdm_util import tqdm_out
from proj.utils.saver import SnapshotSaver
from proj.utils.json_util import convert_json
from collections import OrderedDict


LOG_OUTPUT_FORMATS = ['log', 'json']

DEBUG = 10
INFO = 20
WARN = 30
ERROR = 40

DISABLED = 50


class OutputFormat(object):
    def writekvs(self, kvs):
        """
        Write key-value pairs
        """
        raise NotImplementedError

    def writeseq(self, args):
        """
        Write a sequence of other data (e.g. a logging message)
        """
        pass

    def close(self):
        return


class HumanOutputFormat(OutputFormat):
    def __init__(self, file):
        self.file = file

    def writekvs(self, kvs):
        # Create strings for printing
        key2str = OrderedDict()
        for (key, val) in kvs.items():
            valstr = '%-8.5g' % (val,) if hasattr(val, '__float__') else val
            key2str[self._truncate(key)] = self._truncate(valstr)

        # Find max widths
        keywidth = max(map(len, key2str.keys()))
        valwidth = max(map(len, key2str.values()))

        # Write out the data
        dashes = '-' * (keywidth + valwidth + 7)
        lines = [dashes]
        for (key, val) in key2str.items():
            lines.append('| %s%s | %s%s |' % (
                key,
                ' ' * (keywidth - len(key)),
                val,
                ' ' * (valwidth - len(val)),
            ))
        lines.append(dashes)
        self.file.write('\n'.join(lines) + '\n')

        # Flush the output to the file
        self.file.flush()

    def _truncate(self, s):
        return s[:20] + '...' if len(s) > 23 else s

    def writeseq(self, args):
        for arg in args:
            self.file.write(arg)
        self.file.write('\n')
        self.file.flush()


class JSONOutputFormat(OutputFormat):
    def __init__(self, file):
        self.file = file

    def writekvs(self, kvs):
        for k, v in kvs.items():
            if hasattr(v, 'dtype'):
                v = v.tolist()
                kvs[k] = float(v)
        self.file.write(json.dumps(kvs) + '\n')
        self.file.flush()


def make_output_format(format, ev_dir):
    os.makedirs(ev_dir, exist_ok=True)
    if format == 'stdout':
        return HumanOutputFormat(sys.stdout)
    elif format == 'log':
        log_file = open(osp.join(ev_dir, 'log.txt'), 'at')
        return HumanOutputFormat(log_file)
    elif format == 'json':
        json_file = open(osp.join(ev_dir, 'progress.json'), 'at')
        return JSONOutputFormat(json_file)
    else:
        raise ValueError('Unknown format specified: %s' % (format,))


# ================================================================
# API
# ================================================================


def logkv(key, val):
    """
    Log a value of some diagnostic
    Call this once for each diagnostic quantity, each iteration
    """
    Logger.CURRENT.logkv(key, val)


def dumpkvs():
    """
    Write all of the diagnostics from the current iteration

    level: int. (see old_logger.py docs) If the global logger level is higher
                than the level argument here, don't print to stdout.
    """
    Logger.CURRENT.dumpkvs()


def log(*args, level=INFO):
    """
    Write the sequence of args, with no separators, to the console and output
    files (if you've configured an output file).
    """
    Logger.CURRENT.log(*args, level=level)


def debug(*args):
    log(*args, level=DEBUG)


def info(*args):
    log(*args, level=INFO)


def warn(*args):
    log(*args, level=WARN)


def error(*args):
    log(*args, level=ERROR)


def set_level(level):
    """
    Set logging threshold on current logger.
    """
    Logger.CURRENT.set_level(level)


def get_level():
    """
    Set logging threshold on current logger.
    """
    return Logger.CURRENT.level


def get_dir():
    """
    Get directory that log files are being written to. Will be None if there is
    no output directory (i.e., if you didn't call start).
    """
    return Logger.CURRENT.get_dir()


# Snapshot saving API, forwarded
# ----------------------------------------
def save_config(config):
    Logger.CURRENT.save_config(config)


def get_config():
    return Logger.CURRENT.saver.get_config()


def save_state(index, state):
    Logger.CURRENT.saver.save_state(index, state)


def get_state():
    return Logger.CURRENT.saver.get_state()


# ================================================================
# Backend
# ================================================================


class Nop(object):
    def nop(*args, **kw): pass
    def __getattr__(self, _): return self.nop


class Logger(object):
    # A logger with no output files. (See right below class definition)
    # So one can still log to the terminal without setting up any output files
    DEFAULT = None
    # Current logger being used by the free functions above
    CURRENT = None

    def __init__(self, path, output_formats, exp_name=None, **saver_kwargs):
        self.name2val = OrderedDict()  # values this iteration
        self.level = INFO
        self.path = path
        self.output_formats = output_formats
        self.exp_name = exp_name
        if path is not None:
            self.saver = SnapshotSaver(path, **saver_kwargs)
        else:
            self.saver = Nop()

    # Logging API, forwarded
    # ----------------------------------------
    def logkv(self, key, val):
        self.name2val[key] = val

    def dumpkvs(self):
        for fmt in self.output_formats:
            fmt.writekvs(self.name2val)
        self.name2val.clear()

    def log(self, *args, level=INFO):
        now = datetime.datetime.now(dateutil.tz.tzlocal())
        timestamp = now.strftime('[%Y-%m-%d %H:%M:%S.%f %Z] ')
        if self.level <= level:
            self._do_log((timestamp,) + args)

    def save_config(self, config):
        self.saver.save_config(config)
        config_json = convert_json(config)
        if self.exp_name is not None:
            config_json["exp_name"] = self.exp_name
        with open(os.path.join(self.path, "variant.json"), "wt") as f:
            json.dump(config_json, f)

    # Configuration
    # ----------------------------------------
    def set_level(self, level):
        self.level = level

    def get_dir(self):
        return self.path

    def close(self):
        for fmt in self.output_formats:
            fmt.close()

    # Misc
    # ----------------------------------------
    def _do_log(self, args):
        for fmt in self.output_formats:
            fmt.writeseq(args)


# ================================================================

Logger.DEFAULT = Logger(
    output_formats=[HumanOutputFormat(sys.stdout)], path=None)
Logger.CURRENT = Logger.DEFAULT


class session(object):
    """
    Context manager that sets up the loggers for an experiment.
    """
    # Set to a LoggerContext object using enter/exit or context manager
    CURRENT = None

    def __init__(self, format_strs=None, tqdm=True, **logger_kwargs):
        self.tqdm = tqdm
        if format_strs is None:
            format_strs = LOG_OUTPUT_FORMATS
        self.path = path = logger_kwargs['path']
        self.output_formats = [make_output_format(f, path) for f in format_strs]
        self.logger_kwargs = logger_kwargs

    def __enter__(self):
        if self.tqdm:
            self.tqdm_out = tqdm_out()
            self.tqdm_out.__enter__()
        os.makedirs(self.evaluation_dir(), exist_ok=True)
        Logger.CURRENT = Logger(
            output_formats=self.output_formats,
            **self.logger_kwargs
        )

    def __exit__(self, *args):
        if self.tqdm:
            self.tqdm_out.__exit__(*args)
        Logger.CURRENT.close()
        Logger.CURRENT = Logger.DEFAULT

    def evaluation_dir(self):
        return self.path


# ================================================================


def _demo():
    info("hi")
    debug("shouldn't appear")
    set_level(DEBUG)
    debug("should appear")
    path = "/tmp/testlogging"
    if os.path.exists(path):
        shutil.rmtree(path)
    with session(path=path):
        logkv("a", 3)
        logkv("b", 2.5)
        dumpkvs()
        logkv("b", -2.5)
        logkv("a", 5.5)
        dumpkvs()
        info("^^^ should see a = 5.5")

    logkv("b", -2.5)
    dumpkvs()

    logkv("a", "longasslongasslongasslongasslongasslongassvalue")
    dumpkvs()


if __name__ == "__main__":
    _demo()