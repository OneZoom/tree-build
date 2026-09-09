"""
Tests for parse_args_and_add_logging_switch.

These spawn a subprocess for each case so we exercise the real atexit hook
and observe the actual process exit code, which is the whole point of the
helper.
"""

import subprocess
import sys
import textwrap


def _run(body, *script_args):
    """Run ``body`` under ``parse_args_and_add_logging_switch`` in a subprocess."""
    script = textwrap.dedent(
        f"""
        import argparse, logging
        from oz_tree_build.utilities.debug_util import parse_args_and_add_logging_switch
        parse_args_and_add_logging_switch(argparse.ArgumentParser())
        {body}
        """
    )
    return subprocess.run(
        [sys.executable, "-c", script, *script_args],
        capture_output=True,
        text=True,
    )


def test_no_logging_exits_zero():
    result = _run("pass")
    assert result.returncode == 0
    assert "Exiting with status 1" not in result.stderr


def test_warning_only_exits_zero():
    result = _run("logging.warning('a warning')")
    assert result.returncode == 0
    assert "a warning" in result.stderr
    assert "Exiting with status 1" not in result.stderr


def test_logged_error_exits_one():
    result = _run("logging.error('boom')")
    assert result.returncode == 1
    assert "boom" in result.stderr
    assert "Exiting with status 1: 1 error(s) were logged" in result.stderr


def test_critical_counts_as_error():
    result = _run("logging.critical('fatal')")
    assert result.returncode == 1
    assert "Exiting with status 1: 1 error(s) were logged" in result.stderr


def test_multiple_errors_counted():
    result = _run("logging.error('first'); logging.error('second')")
    assert result.returncode == 1
    assert "Exiting with status 1: 2 error(s) were logged" in result.stderr


def test_verbose_flag_enables_info_output():
    result = _run("logging.info('hello info')", "-v")
    assert result.returncode == 0
    assert "hello info" in result.stderr


def test_default_verbosity_suppresses_info():
    result = _run("logging.info('hello info')")
    assert result.returncode == 0
    assert "hello info" not in result.stderr


def test_verbose_flag_suppresses_debug():
    result = _run("logging.debug('hello debug')", "-v")
    assert result.returncode == 0
    assert "hello debug" not in result.stderr


def test_v_still_emits_errors():
    result = _run("logging.error('boom')", "-v")
    assert result.returncode == 1
    assert "boom" in result.stderr
    assert "Exiting with status 1: 1 error(s) were logged" in result.stderr


def test_vv_enables_debug_output():
    result = _run("logging.debug('hello debug')", "-vv")
    assert result.returncode == 0
    assert "hello debug" in result.stderr


def test_vv_still_emits_errors():
    result = _run("logging.error('boom')", "-vv")
    assert result.returncode == 1
    assert "boom" in result.stderr
    assert "Exiting with status 1: 1 error(s) were logged" in result.stderr


def test_vvv_enables_debug_output():
    result = _run("logging.debug('hello debug')", "-vvv")
    assert result.returncode == 0
    assert "hello debug" in result.stderr


def test_vvv_still_emits_errors():
    result = _run("logging.error('boom')", "-vvv")
    assert result.returncode == 1
    assert "boom" in result.stderr
    assert "Exiting with status 1: 1 error(s) were logged" in result.stderr
