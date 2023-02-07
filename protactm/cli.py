import logging
import shlex
import sys
import textwrap

import box
import click
from rich import print
from rich.console import Console
from rich.logging import RichHandler
from rich.pretty import pprint

logging.basicConfig(
    level=logging.NOTSET,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=Console(stderr=True))]
)

from .app import config, logger


@click.group()
@click.option("--verbose", "-v", count=True, default=False, help="Set level of logging.")
@click.option("--quiet", "-q", is_flag=True, default=False, help="Mute all messages under warning level.")
@click.option("--config", "-c", help="Extra config file to be loaded.")
def cli(verbose, quiet, config):
    """Cli Controller of ProtacTM package, a toolbox for developing and evaluating PROTAC ternary complex modeling protocols."""
    if config:
        logger.conf_file = config
    if quiet:
        logger.setLevel(logging.WARNING)
        return None
    if verbose > 1:
        from rich import traceback
        traceback.install(suppress=[click, box])
    elif verbose == 1:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

@cli.command()
@click.argument("fields", type=str, nargs=-1)
def debug(fields):
    """Print debug informations."""
    if not fields or "logger" in fields:
        print(f"Logger level: {logger.getEffectiveLevel()}")
    if not fields or "conf" in fields:
        print("Configs:")
        print(textwrap.indent(config.to_yaml().rstrip(), ' '*2))
        
@cli.command(context_settings=dict(ignore_unknown_options=True), add_help_option=False)
@click.option("--expand/--no-expand", "-e", default=False, help="Expand all dict or list results.")
@click.option("--debugpy", is_flag=True, help="Start and wait for debugpy connection.")
@click.option("--debugpy-address", default="localhost:5678", help="Address for debugpy connection.")
@click.option("--venv/--no-venv", default=True, help="Force using $SCHRODINGER/run.")
@click.option("--path", help="Run subpackage from path.")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def sub(args, expand, debugpy, debugpy_address, venv, path):
    """Call cli of schrodinger contrib sub-package."""
    from .adaptor import sub_package
    p = sub_package(args, debugpy=debugpy, debugpy_address=debugpy_address, venv=venv, path=path)
    if debugpy:
        logger.warning(f"Debugpy enabled at {debugpy_address}, waiting for connection.")
    if not p.wait():
        if p.results():
            if all(isinstance(i, str) for i in p.results()):
                print('\n'.join(p.results()))
            else:
                pprint(p.results(), expand_all=expand)
    else:
        sys.exit(p.returncode)

@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.option("--ip", default="localhost", help="Address to listen.")
@click.option("--port", default="52000", help="Port to listen.")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def sub_lab(ip, port, args):
    """Start a jupyter lab instance in schrodinger contrib sub-package."""
    from .adaptor import sub_jupyterlab
    p = sub_jupyterlab(ip, port, list(args))
    sys.exit(p.wait())

@cli.command()
@click.argument("specs", nargs=-1)
def sub_update(specs):
    """
    Update packages in schrodinger contrib sub-package, leave spec blank for
    updating pre-defined requirements.
    """
    from .adaptor import sub_update
    if len(specs):
        specs_str = ", ".join(shlex.quote(specs))
        logger.info(f'Installing {specs_str} in sub-package.')
    else:
        logger.info('Updating packages in schrodinger sub-package venv.')
    if not sub_update(specs):
        logger.critical('Failed to install packages in schrodinger sub-package venv.')
    else:
        logger.info('Succeed installing packages.')

@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.option("--shell", default="bash", help="Shell executable to use.")
@click.argument("specs", nargs=-1, type=click.UNPROCESSED)
def sub_shell(shell, specs):
    """Run shell in schrodinger contrib sub-package."""
    from .adaptor import sub_shell
    sys.exit(sub_shell(shell, specs))

if __name__ == "__main__":
    cli()
