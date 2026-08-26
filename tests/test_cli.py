"""
Unified CLI tests.

`swarm` is the single entry point. `swarm web` (and a bare `swarm`) launch the
server; `swarm version` prints the version. We assert argument routing without
actually binding a socket by patching run_server.
"""

import unittest
from unittest.mock import patch

from swarm import cli
from swarm import __version__


class TestUnifiedCli(unittest.TestCase):
    def test_web_subcommand_starts_server_with_args(self):
        with patch("swarm.server.run_server") as rs:
            cli.main(["web", "--port", "1234", "--host", "127.0.0.1"])
            rs.assert_called_once_with(host="127.0.0.1", port=1234)

    def test_bare_invocation_defaults_to_web(self):
        with patch("swarm.server.run_server") as rs:
            cli.main([])
            self.assertEqual(rs.call_count, 1)

    def test_top_level_port_shortcut(self):
        with patch("swarm.server.run_server") as rs:
            cli.main(["--port", "8899"])
            rs.assert_called_once_with(host=cli.HOST, port=8899)

    def test_version_command(self):
        with patch("builtins.print") as pr:
            cli.main(["version"])
            pr.assert_called_once()
            self.assertIn(__version__, pr.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
