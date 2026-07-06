"""Tests for scripts/promote_dvdread1.py — the D-04/D-05 cutover wrapper.

The wrapper lives at repo-root ``scripts/`` (a host-side operator script
that drives ``docker compose``, not an in-container ``app.*`` module), so
these tests import it directly by inserting the repo-root ``scripts/``
directory onto ``sys.path`` — mirroring the existing sys.path-bootstrap
convention used elsewhere in this suite's ``conftest.py``.

Every ``subprocess.run`` call and the operator confirmation prompt are
mocked — these tests never invoke a real ``docker``/``alembic`` process.
"""

import os
import subprocess
import sys

import pytest

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_scripts_dir = os.path.join(_repo_root, "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import promote_dvdread1  # noqa: E402


class _FakeCompletedProcess:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


class _RecordingRunner:
    """Records every subprocess.run invocation and simulates docker compose.

    - Any command containing "printenv" reports OVID_MODE=canonical
      (simulating an operator running the wrapper against a canonical,
      write-serving deployment — the audience D-05's runbook targets).
    - Any command containing "alembic" either succeeds or raises
      CalledProcessError, per ``migration_should_fail``.
    - Everything else (the two "up -d" restart invocations) succeeds.
    """

    def __init__(self, migration_should_fail=False):
        self.calls = []
        self.migration_should_fail = migration_should_fail

    def __call__(self, cmd, **kwargs):
        self.calls.append(
            {"cmd": cmd, "env": kwargs.get("env"), "check": kwargs.get("check")}
        )
        if "printenv" in cmd:
            return _FakeCompletedProcess(stdout="canonical\n", returncode=0)
        if "alembic" in cmd:
            if self.migration_should_fail:
                raise subprocess.CalledProcessError(1, cmd)
            return _FakeCompletedProcess(stdout="", returncode=0)
        return _FakeCompletedProcess(stdout="", returncode=0)


# --------------------------------------------------------------------- _current_ovid_mode


def test_current_ovid_mode_returns_captured_value(monkeypatch):
    def fake_run(cmd, **kwargs):
        assert cmd[-1] == "OVID_MODE"
        return _FakeCompletedProcess(stdout="canonical\n", returncode=0)

    monkeypatch.setattr(promote_dvdread1.subprocess, "run", fake_run)
    assert (
        promote_dvdread1._current_ovid_mode(["-f", "docker-compose.yml"])
        == "canonical"
    )


def test_current_ovid_mode_defaults_to_standalone_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(
        promote_dvdread1.subprocess,
        "run",
        lambda cmd, **kwargs: _FakeCompletedProcess(stdout="", returncode=1),
    )
    assert (
        promote_dvdread1._current_ovid_mode(["-f", "docker-compose.yml"])
        == "standalone"
    )


def test_current_ovid_mode_defaults_to_standalone_on_empty_output(monkeypatch):
    monkeypatch.setattr(
        promote_dvdread1.subprocess,
        "run",
        lambda cmd, **kwargs: _FakeCompletedProcess(stdout="   \n", returncode=0),
    )
    assert (
        promote_dvdread1._current_ovid_mode(["-f", "docker-compose.yml"])
        == "standalone"
    )


def test_current_ovid_mode_defaults_to_standalone_on_oserror(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise OSError("docker not found")

    monkeypatch.setattr(promote_dvdread1.subprocess, "run", fake_run)
    assert (
        promote_dvdread1._current_ovid_mode(["-f", "docker-compose.yml"])
        == "standalone"
    )


# --------------------------------------------------------------------- main()


def test_main_requires_compose_file_argument():
    with pytest.raises(SystemExit):
        promote_dvdread1.main([])


def test_main_aborts_without_mutation_when_operator_declines(monkeypatch):
    runner = _RecordingRunner()
    monkeypatch.setattr(promote_dvdread1.subprocess, "run", runner)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    rc = promote_dvdread1.main(["-f", "docker-compose.yml"])

    assert rc == 1
    # Only the read-only printenv capture call happened — nothing mutated.
    assert len(runner.calls) == 1


def test_main_happy_path_toggles_mirror_then_restores_original_mode(monkeypatch):
    runner = _RecordingRunner()
    monkeypatch.setattr(promote_dvdread1.subprocess, "run", runner)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    rc = promote_dvdread1.main(["-f", "docker-compose.yml"])

    assert rc == 0
    up_calls = [c for c in runner.calls if "up" in c["cmd"]]
    assert len(up_calls) == 2
    assert up_calls[0]["env"]["OVID_MODE"] == "mirror"
    # Restored to the CAPTURED original value, never a hardcoded default.
    assert up_calls[-1]["env"]["OVID_MODE"] == "canonical"


def test_main_restores_original_mode_even_when_migration_fails(monkeypatch):
    runner = _RecordingRunner(migration_should_fail=True)
    monkeypatch.setattr(promote_dvdread1.subprocess, "run", runner)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    rc = promote_dvdread1.main(["-f", "docker-compose.yml"])

    assert rc != 0
    up_calls = [c for c in runner.calls if "up" in c["cmd"]]
    # The finally-guaranteed restore call still happened despite the
    # migration failure — the deployment is never left stranded read-only.
    assert len(up_calls) == 2
    assert up_calls[-1]["env"]["OVID_MODE"] == "canonical"
