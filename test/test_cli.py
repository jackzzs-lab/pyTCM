import pytest
from contextlib import contextmanager

from click.testing import CliRunner

from protactm import cli

def run(*args, func=cli.cli, **kw):
    try:
        func(*args, **kw)
    except SystemExit as e:
        return e.code

def test_cli():
    assert run([]) == 0
    assert run(['--help']) == 0
    assert run(['wrong']) != 0

def test_sub(caplog):
    assert run(['sub']) == 0
    assert run(['sub', 'wrong']) != 0