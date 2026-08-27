"""Test package bootstrap.

Pins the dev-role engine to the single-completion path. The default in normal
operation is "auto", which routes code drafting through the Pi coding agent —
that spawns a real subprocess against a live local model, which would make the
suite slow, network-dependent and non-deterministic. Tests covering the Pi path
mock swarm.loop_engine.run_pi_agent explicitly instead.

This must run before any swarm import, since swarm.config reads the environment
at import time.
"""

import os

os.environ.setdefault("SWARM_DEV_ENGINE", "raw")
