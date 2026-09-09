"""Runs the browser-side test suite (tests/test_dashboard_ui.mjs) under node.

The dashboard's UI is a single dependency-free HTML file, so there is no JS test runner
in the project. Shelling out to node keeps `pytest` the one command that runs everything.
"""
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = os.path.join(HERE, "test_dashboard_ui.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_dashboard_action_dispatch():
    p = subprocess.run(["node", SUITE], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"\n--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}"
    assert "ok - dashboard action dispatch" in p.stdout
