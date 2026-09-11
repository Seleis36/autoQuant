"""Process start-time and uptime reporting.

`proc_started` names an instant, not a duration. It used to return the duration --
`time.time() - (boot + starttime/hz)` -- and `build_strategies` then computed
`time.time() - started`, subtracting an age from a wall clock. The result was every
running daemon reported as up for the whole Unix epoch: the dashboard read "up 20705d 16h".
"""
import os
import subprocess
import sys
import time

import pytest

import dashboard


@pytest.fixture
def sleeper():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    yield p
    p.kill()
    p.wait()


def test_proc_started_returns_an_epoch_timestamp(sleeper):
    started = dashboard.proc_started(sleeper.pid)
    assert started is not None
    # An epoch timestamp for a process launched just now is within seconds of now;
    # the old return value (an age of ~0) would be ~1.8e9 seconds adrift.
    assert abs(started - time.time()) < 10, (
        f"proc_started returned {started}, which is not a plausible epoch timestamp")


def test_uptime_derived_from_proc_started_is_small(sleeper):
    time.sleep(1.2)
    uptime = time.time() - dashboard.proc_started(sleeper.pid)
    assert 0.5 < uptime < 30, f"uptime {uptime}s is not plausible for a 1s-old process"


def test_uptime_is_not_the_age_of_the_epoch(sleeper):
    """The exact regression, stated in the units the dashboard displayed."""
    uptime_days = (time.time() - dashboard.proc_started(sleeper.pid)) / 86400
    assert uptime_days < 1, f"reported {uptime_days:.0f}d for a process started now"


def test_proc_started_is_never_in_the_future(sleeper):
    assert dashboard.proc_started(sleeper.pid) <= time.time() + 1


def test_proc_started_returns_none_for_a_dead_pid():
    p = subprocess.Popen([sys.executable, "-c", ""])
    p.wait()
    # A reaped pid has no /proc entry; the caller relies on None to render "—".
    assert dashboard.proc_started(p.pid) is None


def test_proc_started_handles_a_comm_containing_parens_and_spaces(tmp_path, monkeypatch):
    """/proc/<pid>/stat quotes comm in parens but does not escape them, so the fields
    after it can only be found by splitting on the LAST ')'."""
    fake = tmp_path / "stat"
    # Everything after comm: index 0 is state (stat field 3), so starttime
    # (stat field 22) sits at index 19.
    post = ["0"] * 30
    post[0] = "S"
    post[19] = "1000"
    fake.write_text("1234 (weird ) name) " + " ".join(post))

    real_open = open

    def fake_open(path, *a, **kw):
        if str(path) == "/proc/1234/stat":
            return real_open(fake, *a, **kw)
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", fake_open)
    hz = os.sysconf("SC_CLK_TCK")
    started = dashboard.proc_started(1234)
    assert started is not None
    with real_open("/proc/uptime") as fh:
        up = float(fh.read().split()[0])
    assert abs(started - ((time.time() - up) + 1000 / hz)) < 2
