import logging
import re
import os
import sys
import uuid
import json
import time
import shlex
import itertools
from shutil import which
from pathlib import Path
from subprocess import Popen, PIPE
from threading import Thread
from typing import Callable
from concurrent.futures import ThreadPoolExecutor

from . import app, utils

class ExternelError(RuntimeError):
    pass


class External(Popen):
    """
    An enhanced version of Popen for calling external commands, which can pass
    the output of stdout to variables in real time, and message the output of
    stderr through a logger according to certain rules.
    """
    @staticmethod
    def _handler(func):
        def handler(line, *args, **kw):
            return func(line, *args, **kw)

        return handler

    @staticmethod
    def _proxy_lines(pipe, handler):
        last = None
        with pipe:
            if handler:
                for line in pipe:
                    last = handler(line.decode().rstrip(), last=last)

    def __init__(self, args, desc=None, logger=None, raw=False, level=None, filters=None, pattern=None, output_stdout=False, **kw):
        """An subprocess running in background and redirect messages to custom logger.

        Args:
            args (list): Command splited by shlex.split
            desc (str, optional): Description of the external. Defaults to the pid of the subprocess.
            logger (logging.Logger, optional): Logger of the messages. Defaults to Logger('protactm').
            raw (bool, optional): If True, prefixes are not added to the messages. Defaults to False.
            level (int, optional): Logging level in logging. Defaults to the effective logging level of app.logger.
            filters (list, optional): A list of regex patterns for messages to be filtered. Defaults to None.
            pattern (dict, optional): A dict of {output regex: level name} mappings. Defaults = self.output_pattern.
        """
        self.handle_stdout = 'stdout' not in kw and not output_stdout
        self.handle_stderr = 'stderr' not in kw
        kw.update({'stdout': PIPE, 'stderr': PIPE})
        super().__init__(args, **kw)
        self.uuid = uuid.uuid4().hex
        self.args = args
        self.desc = desc
        if not logger:
            logger = app.logger
        logger = logger.getChild(f'external.{self.pid}')
        if level:
            logger.setLevel(level)
        self.logger = logger
        self.raw = raw
        self.filters = filters
        self.pattern = pattern
        self._results = []
        if self.handle_stdout:
            Thread(target=self._proxy_lines, args=[self.stdout, self._handler(self._as_result)]).start()
        if self.handle_stderr:
            Thread(target=self._proxy_lines, args=[self.stderr, self._handler(self._output)]).start()
        if output_stdout:
            Thread(target=self._proxy_lines, args=[self.stdout, self._handler(self._output)]).start()
        logger.debug(f'Started external "{self.get_command(truncate=60)}"')

    def get_command(self, truncate=0):
        """Get a truncated command."""
        return utils.truncate_str(' '.join(shlex.quote(str(a)) for a in self.args), truncate)

    def _as_result(self, line, **kw):
        self._results.append(line)

    def read(self):
        """A generator that waits for next stdout line output as str."""
        for i in itertools.count():
            while len(self._results) < i + 1:
                if self.poll() is not None:
                    raise StopIteration
                time.sleep(0.01)
            yield self._results[i]

    def results(self):
        """Wait for process to finish and return results as dict/list (if detected), or as list of str."""
        if self.wait():
            raise ExternelError(f"exit code {self.returncode} when running {self.get_command(truncate=20)}")
        try:
            return json.loads("\n".join(self._results))
        except ValueError:
            return self._results

    @property
    def output_pattern(self):
        if self.pattern:
            return self.pattern
        return {
            r".*error.*": self.logger.error,
            r".*warning.*": self.logger.warning,
            r"^info:\s*(.*)": self.logger.info,
            r"^debug:\s*(.*)": self.logger.debug,
            r"^traceback.*": self.logger.debug,
            r".*": self.logger.info,
        }

    @property
    def prefix(self):
        if self.desc:
            desc = self.desc
        else:
            desc = os.path.basename(self.args[0])
        if self.logger.getEffectiveLevel() == logging.DEBUG:
            desc += f"-{self.pid}"
        return desc

    def add_prefix(self, line):
        if self.raw:
            return line
        else:
            return f"[{self.prefix}] {line}"

    def _output(self, line: str, last=None):
        if self.filters:
            if any(re.search(r, line) for r in self.filters):
                return None
        if isinstance(last, Callable) and re.match(r"\s", line):
            last(line)
            return last
        for p, func in self.output_pattern.items():
            if isinstance(func, str): 
                func = getattr(self.logger, func)
            regex = re.search(p, line, re.IGNORECASE)
            if not regex:
                continue
            if len(regex.groups()):
                func(self.add_prefix(regex.group(1)))
                return func
            else:
                func(self.add_prefix(regex.group(0)))
                return func

class EnvMgr:
    """A class for saving, updating and running commands with environment variables"""
    # TODO add a submit function to submit LazyExternal to ExternalPool
    def __init__(self, env=None, inherit=False):
        self.env = {}
        if inherit:
            self.env.update(os.environ)
        if env:
            self.env.update(env)

    def popen(self, *args, cls=External, env={}, **kw):
        """Start a process in the envvar manager.

        Args:
            cls (type, optional): Popen-like class to be used. Defaults to External.
            env (dict, optional): Extra environment variables to be passed. Defaults to {}.
        """
        env.update(self.env if self.env else os.environ)
        return cls(*args, env=env, **kw)

    def shell(self, cmd, shell="bash", clean=False, **kw):
        """Start a command in the envvar manager in "shell mode".

        Args:
            cmd (str): A command to be run.
            shell (str, optional): Shell executable to be used. Defaults to "bash".
            clean (bool, optional): Start from an empty environment variable list as "env -i". Defaults to False.
        """
        if not which(shell):
            raise RuntimeError(f'"{shell}" is not found in your PATH, please note this script is for linux only.')
        if clean:
            prefix = f"env -i {shell} --norc --noprofile -c"
        else:
            prefix = f"{shell} --norc --noprofile -c"
        cmd = shlex.split(f"{prefix} {shlex.quote(cmd)}")
        return self.popen(cmd, **kw)

    def update(self, cmd, **kw):
        """Update the environment variables after running a command from shell.

        Args:
            cmd (str): A command to be run. Usually "source ..." or "... load" or "... activate".
        """
        dump = f'{sys.executable} -c "import os, json; print(json.dumps(dict(os.environ)))"'
        proc = self.shell(f"{cmd} && {dump}", stdout=PIPE, **kw)
        if proc.wait():
            raise RuntimeError(f"failed to update env from script.")
        try:
            env = json.loads(proc.stdout.read())
        except json.JSONDecodeError:
            raise RuntimeError(f"failed to update env from script, invalid env.")
        self.env.update(env)


class Spack(EnvMgr):
    def __init__(self, env_sh=None, **kw):
        super().__init__(**kw)
        if not env_sh:
            try:
                env_sh = app.config['envmgr.spack.init']
            except KeyError:
                pass
        if not env_sh and "SPACK_ROOT" in os.environ:
            env_sh = os.path.join(os.environ.get("SPACK_ROOT"), "share/spack/setup-env.sh")
        if env_sh:
            try:
                self.update(f"source {shlex.quote(str(env_sh))} >/dev/null", clean=True)
            except RuntimeError:
                raise RuntimeError("failed to load spack init script.") from None
        else:
            raise RuntimeError("spack can not be found automatically, and env_sh is not provided.")

    def load(self, specs):
        spec_str = " ".join(shlex.quote(s) for s in specs)
        try:
            self.update(f"spack load {spec_str}")
        except RuntimeError:
            raise RuntimeError(f'failed to load spack specs "{spec_str}".') from None
        return self

class Module(EnvMgr):
    def __init__(self, env_sh=None, **kw):
        super().__init__(**kw)
        if not env_sh:
            try:
                env_sh = app.config['envmgr.module.init']
            except KeyError:
                pass
        if not env_sh and "MODULESHOME" in os.environ:
            env_sh = os.path.join(os.environ.get("MODULESHOME"), "init/profile")
        if env_sh:
            try:
                self.update(f"source {shlex.quote(str(env_sh))} >/dev/null", clean=True)
            except RuntimeError:
                raise RuntimeError("failed to load module init script.") from None
        else:
            raise RuntimeError("module can not be found automatically, and env_sh is not provided.")

    def load(self, specs):
        spec_str = " ".join(shlex.quote(s) for s in specs)
        try:
            self.update(f"module load {spec_str}")
        except RuntimeError:
            raise RuntimeError(f'failed to load module specs "{spec_str}".') from None


class Venv(EnvMgr):
    def __init__(self, env_sh, **kw):
        super().__init__(**kw)
        if not Path(env_sh).is_file():
            raise IOError(f'venv init shell script "{env_sh}" is not found.')
        try:
            self.update(f"source {shlex.quote(str(env_sh))} >/dev/null")
        except RuntimeError:
            raise RuntimeError("failed to load venv init script.") from None
    
    def pip(self, operation=["install", "-U"], args=[], **kw):
        return not self.popen(["pip", "--disable-pip-version-check", *operation, *args], **kw).wait()


class ExternalPool(ThreadPoolExecutor):
    """A process pool for external with a similar mode of operation to concurrent.futures."""
    def __init__(self, cls=External, **kw):
        super().__init__(**kw)
        self._cls = cls

    def submit(self, args, **kw):
        """Submits a external command to be executed with the given arguments.

        Args:
            args (list): a list or arguments to specify the external to run.

        Returns:
            Future: A Future representing the given call.
        """
        # FIXME: externals will start to run when submit.
        # FIXME: may be we can fix it with a "LazyExternal"?
        p = self._cls(args, **kw)
        f = super().submit(p.results)
        f.popen = p
        return f

    def map(self, args_combs, timeout=None, **kw):
        if timeout is not None:
            end_time = timeout + time.monotonic()
        fs = [self.submit(args, **kw) for args in utils.product_nested(args_combs)]

        def result_iterator():
            try:
                fs.reverse()
                while fs:
                    if timeout is None:
                        yield fs.pop().result()
                    else:
                        yield fs.pop().result(end_time - time.monotonic())
            finally:
                for future in fs:
                    future.cancel()

        return result_iterator()
