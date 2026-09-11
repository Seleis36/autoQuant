"""Shared fixtures.

The harness modules are plain scripts on `harness/`, not an installed package, so the
path is set up once here rather than in every test file.
"""
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_DIR = os.path.join(REPO_ROOT, "harness")
sys.path.insert(0, HARNESS_DIR)


@pytest.fixture
def live_dir(tmp_path, monkeypatch):
    """An isolated `live/` tree, wired into both dashboard and metrics.

    Both modules resolve LIVE_DIR at import time from their own file location, so a test
    that wrote into the real tree would mutate a running deployment.
    """
    import dashboard
    import metrics

    d = tmp_path / "live"
    d.mkdir()
    monkeypatch.setattr(dashboard, "LIVE_DIR", str(d))
    monkeypatch.setattr(metrics, "LIVE_DIR", str(d))
    return d


@pytest.fixture
def logs_dir(tmp_path, monkeypatch):
    import dashboard

    d = tmp_path / "logs"
    d.mkdir()
    monkeypatch.setattr(dashboard, "LOGS_DIR", str(d))
    return d


def write_strategy(live_dir, name, journal_rows=(), runner_log=None):
    """Create `live/<name>/` with an optional journal and runner.log."""
    import json

    d = live_dir / name
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"symbol": "BTCUSDT", "schedule": "1h"}))
    if journal_rows:
        (d / "journal.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in journal_rows))
    if runner_log is not None:
        (d / "runner.log").write_text(runner_log)
    return d
