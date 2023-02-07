import logging
import re
import sys
import traceback
from pathlib import Path

import click
from box import Box

from . import utils


def excepthook(suppress=[]):
    """A function to generate a excepthook to make file paths in traceback relative and truncated."""
    paths = []
    for s in suppress:
        if isinstance(s, str):
            paths.append(Path(s))
        elif hasattr(s, "__file__"):
            paths.append(Path(s.__file__).parent)

    def _check_file(f):
        if not f:
            return False
        if Path(f) in paths:
            return False
        if any(p in Path(f).parents for p in paths):
            return False
        if any(Path(f).name == p.name for p in paths):
            return False
        return True

    def _shorten(m):
        return f'File "{utils.truncate_path(m.group(1), 60)}"'

    def _print(type, value, tb):
        show = (fs for fs in traceback.extract_tb(tb) if _check_file(fs.filename))
        lines = traceback.format_list(show)
        lines = [re.sub(r'File "([^"]+)"', _shorten, line, 1) for line in lines]
        fmt = lines + traceback.format_exception_only(type, value)
        print("".join(fmt), end="", file=sys.stderr)

    return _print


sys.excepthook = excepthook(suppress=["runpy.py", click])

config = Box()

logger = logging.getLogger("protactmsub")
logger.setLevel(logging.NOTSET)