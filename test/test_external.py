import re
import sys
import pytest
import logging
import subprocess

from protactm import app, external

app.logger.setLevel(logging.NOTSET)


def test_results():
    cmd = 'print("TEST1"); print("TEST2")'
    p = external.External([sys.executable, "-c", cmd])
    assert p.wait() == 0, "external unexpectedly failed."
    assert p.results() == ["TEST1", "TEST2"]


def test_read():
    cmd = 'import time; print("TEST"); time.sleep(10)'
    p = external.External([sys.executable, "-c", cmd])
    try:
        p.wait(timeout=1)
    except subprocess.TimeoutExpired:
        assert "TEST" == next(p.read())
        p.terminate()


def test_output_level(caplog):
    cmd = 'import sys; print("TypeError: TEST", file=sys.stderr)'
    p = external.External([sys.executable, "-c", cmd], raw=True)
    assert p.wait() == 0, "external unexpectedly failed."
    assert "TypeError: TEST" in [
        r.msg for r in caplog.records if r.levelno == logging.WARNING
    ], '"WARNING TEST" is not outputted.'


def test_output_traceback(caplog):
    p = external.External([sys.executable, "-c", "wrong"], raw=True)
    assert p.wait() == 1, "external unexpectedly succeeded."
    assert any(
        [r.msg.startswith("Traceback") for r in caplog.records if r.levelno == logging.DEBUG]
    ), '"DEBUG Traceback..." is not outputted.'
    assert any(
        [re.match(r"\s", r.msg) for r in caplog.records if r.levelno == logging.DEBUG]
    ), '"DEBUG ..." is not outputted.'
    assert any(
        [r.msg.startswith("NameError") for r in caplog.records if r.levelno == logging.WARNING]
    ), '"WARNING NameError..." is not outputted.'


def test_spack():
    try:
        spack = external.Spack()
    except RuntimeError as e:
        if "env_sh is not provided" in str(e):
            pytest.skip("spack is not configured properly, skipping.")
        raise
    with pytest.raises(RuntimeError):
        spack.load(["wrong"])


def test_module():
    try:
        module = external.Module()
    except RuntimeError as e:
        if "env_sh is not provided" in str(e):
            pytest.skip("module is not configured properly, skipping.")
        raise
    with pytest.raises(RuntimeError):
        module.load(["wrong"])


def test_pool():
    cmds = [f'print("{i}")' for i in range(6)]
    with external.ExternalPool(max_workers=2) as e:
        assert list(e.map([sys.executable, "-c", cmds])) == list(range(6))
