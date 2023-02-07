import shlex
from functools import cached_property
from pathlib import Path
from importlib import resources
from subprocess import Popen

from .app import config, logger
from .external import External, Venv
from .utils import Singleton


class SubVenvAdapter(metaclass=Singleton):
    """A class to store schrodinger sub-package venv status."""

    def __init__(self):
        self._venv_path = config.get("contrib.schrodinger.venv", Path().home() / ".virtualenvs" / "schrodinger.ve")
        self._venv_path = Path(self._venv_path).expanduser()
        self._sub_path = config.get("contrib.schrodinger.package")
        if not self._sub_path:
            with resources.path("protactm.contrib", "__init__.py") as r:
                self._sub_path = r.parent / "schrodinger"

    @cached_property
    def venv(self):
        """Initialize and return venv."""
        if not self._venv_path.is_dir():
            logger.warning("Creating schrodinger venv.")
            if not self._create_venv():
                raise RuntimeError("failed to create a schrodinger venv.")
            logger.warning("Installing requirements for the schrodinger venv, may be slow at first time.")
            if not self.requirements():
                raise RuntimeError("failed to install requirements for the schrodinger venv.")
        else:
            logger.debug("Initializing schrodinger venv")
        return Venv(self._venv_path / "bin" / "activate")

    def run(self, args=[], runner=[], venv=True, **kw):
        """Run command, with runner auto-detected based on venv.

        Args:
            args (list): arguments to be passed to the execuable.
            runner (list, optional): Defaults to "python" when using venv, and "$SCHRODINGER/run"
                                     when not.
            venv (bool, optional): Whether to use venv. Defaults to True.
            kw (dict, optional): Extra keyword arguments to be passed to Executor.
        """
        if not runner:
            if venv:
                runner = ["python"]
            else:
                runner = [Path(config["path.schrodinger"]) / "run"]
        if venv:
            return self.venv.popen([*runner, *args], **kw)
        else:
            return External([*runner, *args], **kw)

    def _create_venv(self, **kw):
        return not self.run(["schrodinger_virtualenv.py", self._venv_path], venv=False, **kw).wait()

    def requirements(self, **kw):
        """Update pip and install pre-defined requirements."""
        pip_pre = self.venv.pip(args=["pip", "setuptools", "wheel"], **kw)
        pip_specs = self.venv.pip(args=["-r", "requirements.txt"], cwd=self._sub_path, **kw)
        return pip_pre and pip_specs


def sub_package(args, path=None, debugpy=False, debugpy_address=None, filters=[], env={}, **kw):
    """Run command with schrodinger sub-package. Some pre-defined environment variables are passed
       to allow multiprocessing to be run.

    Args:
        args (_type_): Arguments to be passed to sub-package.
        debugpy (bool, optional): Whether to hook debugpy. Defaults to False.
        debugpy_address (str): IP:PORT address for debugpy to listen on. Defaults to None.
        filters (list, optional): A list of regex patterns for messages to be filtered. Defaults to ['user specific host file'].
        env (dict, optional): Extra environment variables to be passed to Executor. Defaults to {}.
        kw (dict, optional): Extra keyword arguments to be passed to Executor.
    """
    if path:
        cmd = [path, *args]
    else:
        cmd = ["-m", "protactmsub.cli", *args]  
    adapter = SubVenvAdapter()
    env.update({"SCHRODINGER_ALLOW_UNSAFE_MULTIPROCESSING": "1"})
    filters.extend(["user specific host file"])
    if debugpy:
        runner_str = f"python -m debugpy --listen {debugpy_address} --wait-for-client"
        return adapter.run(cmd, runner=shlex.split(runner_str), env=env, filters=filters, **kw)
    else:
        return adapter.run(cmd, env=env, filters=filters, **kw)


def sub_shell(shell="bash", args=[], **kw):
    """Start shell in schrodinger sub-package venv.

    Args:
        shell (str, optional): Shell executable to be used. Defaults to "bash".
        args (list, optional): Extra arguments to be passed to shell.
        kw (dict, optional): Extra keyword arguments to be passed to Executor.

    Returns:
        bool: whether the operation succeeded.
    """
    return SubVenvAdapter().venv.popen([shell, *args], cls=Popen, **kw).wait()


def sub_jupyterlab(ip="localhost", port=52000, args=[], env={}, **kw):
    """Start jupyter lab in schrodinger sub-package venv.

    Args:
        ip (str, optional): Defaults to "localhost".
        port (int, optional): Defaults to 52000.
        args (list, optional): Extra arguments to be passed to jupyterlab.
        env (dict, optional): Extra environment variables to be passed to Executor.
        kw (dict, optional): Extra keyword arguments to be passed to Executor.
    """

    if not any(a.startswith("--ip=") for a in args):
        args.append(f"--ip={ip}")
    if not any(a.startswith("--port=") for a in args):
        args.append(f"--port={port}")
    env.update({"SCHRODINGER_ALLOW_UNSAFE_MULTIPROCESSING": "1"})
    pattern = {
        r".*(Jupyter Notebook .* is running at:)": "info",
        r".*(https?://\S+)": "info",
        r"\[.*\] ERROR \| (.*)": "error",
        r"\[.*\] WARNING \| (.*)": "warning",
        r"\[.*\] (.*)": "debug",
    }
    adapter = SubVenvAdapter()
    return adapter.venv.popen(["jupyter", "lab", "-y", "--no-browser"] + args, pattern=pattern, env=env, **kw)


def sub_update(specs=[], **kw):
    """install packages in schrodinger sub-package venv.

    Args:
        specs (list, optional): The list of packages to be installed. Defaults to install pre-defined requirements.
        kw (dict, optional): Extra keyword arguments to be passed to Executor.

    Returns:
        bool: whether the operation succeeded.
    """
    if len(specs):
        return SubVenvAdapter().pip(specs, **kw)
    else:
        return SubVenvAdapter().requirements(**kw)
