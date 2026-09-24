"""The systemd units that supervise the harness across a reboot.

A directive in the wrong section is not an error: systemd logs "Unknown key name ...
ignoring" and carries on, so a unit can look correct in the file and do nothing.
"""
import configparser
import glob
import os
import shutil
import subprocess

import pytest

from conftest import REPO_ROOT

UNIT_DIR = os.path.join(REPO_ROOT, "harness", "systemd")
UNITS = sorted(glob.glob(os.path.join(UNIT_DIR, "*.service")) +
               glob.glob(os.path.join(UNIT_DIR, "*.target")) +
               glob.glob(os.path.join(UNIT_DIR, "*.timer")))


def timer_triggered(path):
    """A service started by a timer of the same name is not enabled itself."""
    return path.endswith(".service") and os.path.exists(path[:-len(".service")] + ".timer")


def parse(path):
    # interpolation=None: systemd's %h / %I specifiers are not configparser syntax.
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str                       # systemd keys are case-sensitive
    cp.read(path)
    return cp


def test_units_exist():
    assert UNITS, "no unit files found"


@pytest.mark.parametrize("path", UNITS, ids=os.path.basename)
def test_unit_parses_and_has_an_install_section(path):
    cp = parse(path)
    assert "Unit" in cp
    if timer_triggered(path):
        # Enabling a timer's service would ALSO start it at every boot -- for the
        # nightly batch, a research run each time WSL comes up.
        assert "Install" not in cp, "a timer-triggered service must not be enableable"
    else:
        assert "Install" in cp, "a unit with no [Install] cannot be enabled"


def test_nightly_batch_survives_its_own_script_exiting():
    """The agents it launches are detached but share the unit's cgroup; the default
    KillMode would kill a running research agent when the batch script stops."""
    cp = parse(os.path.join(UNIT_DIR, "autoquant-nightly.service"))
    assert cp["Service"]["Type"] == "oneshot"
    assert cp["Service"]["KillMode"] == "process"
    t = parse(os.path.join(UNIT_DIR, "autoquant-nightly.timer"))
    assert t["Timer"]["OnCalendar"].strip()
    assert t["Timer"]["Persistent"] == "true"


def test_start_limit_directives_are_in_the_unit_section():
    """systemd moved these out of [Service] in v229. Left there they are ignored, so a
    runner that crashes on startup restarts every RestartSec forever -- against a live
    venue -- while the file still reads as though it were rate limited."""
    path = os.path.join(UNIT_DIR, "autoquant-strategy@.service")
    cp = parse(path)
    for key in ("StartLimitIntervalSec", "StartLimitBurst"):
        assert key in cp["Unit"], f"{key} must be in [Unit] to take effect"
        service = cp["Service"] if cp.has_section("Service") else {}
        assert key not in service, f"{key} in [Service] is silently ignored"


def test_restarting_strategies_are_rate_limited():
    cp = parse(os.path.join(UNIT_DIR, "autoquant-strategy@.service"))
    assert cp["Service"]["Restart"] == "always"
    assert int(cp["Unit"]["StartLimitBurst"]) > 0
    assert int(cp["Unit"]["StartLimitIntervalSec"]) > 0


@pytest.mark.parametrize("path", [p for p in UNITS if p.endswith(".service")],
                         ids=os.path.basename)
def test_service_units_declare_a_working_directory_and_start_command(path):
    cp = parse(path)
    assert cp["Service"]["ExecStart"].strip()
    assert cp["Service"]["WorkingDirectory"].strip()


@pytest.mark.skipif(shutil.which("systemd-analyze") is None,
                    reason="systemd-analyze is not available")
@pytest.mark.parametrize("path", UNITS, ids=os.path.basename)
def test_systemd_itself_reports_no_unknown_keys(path):
    """Ask systemd, not a parser: only it knows which key belongs in which section."""
    p = subprocess.run(["systemd-analyze", "verify", path],
                       capture_output=True, text=True, timeout=60)
    ours = [l for l in (p.stdout + p.stderr).splitlines()
            if os.path.basename(path) in l and "Unknown key name" in l]
    assert not ours, "\n".join(ours)
