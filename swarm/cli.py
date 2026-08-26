"""
Swarm AI Studio — unified command line interface.

A single command, `swarm`, drives everything:

    swarm web [--port 8080] [--host 0.0.0.0]   # launch the web console + JSON API
    swarm version                              # print version and exit

Running `swarm` with no arguments is a friendly alias for `swarm web`, so the
server still starts with a bare invocation.
"""

import argparse

from swarm import __version__
from swarm.config import PORT, HOST


def _add_web_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--port", "-p", type=int, default=PORT,
        help=f"Server port (default: {PORT})",
    )
    parser.add_argument(
        "--host", "-H", type=str, default=HOST,
        help=f"Server host binding (default: {HOST})",
    )


def cmd_web(args: argparse.Namespace) -> None:
    # Imported lazily so `swarm version` / `--help` stay instant and dependency-light.
    from swarm.server import run_server
    run_server(host=args.host, port=args.port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swarm",
        description="Swarm AI Studio: Task-Aware Dynamic Swarm & Full GitHub Desktop Web Suite",
    )
    parser.add_argument("--version", "-V", action="version", version=f"Swarm AI Studio {__version__}")
    # Top-level --port/--host so the bare `swarm --port 9000` shortcut keeps working.
    _add_web_args(parser)

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    web = sub.add_parser("web", help="Launch the web console + API server (default)")
    _add_web_args(web)
    web.set_defaults(func=cmd_web)

    ver = sub.add_parser("version", help="Print version and exit")
    ver.set_defaults(func=lambda a: print(f"Swarm AI Studio {__version__}"))

    return parser


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    # No subcommand → default to launching the web server.
    func = getattr(args, "func", cmd_web)
    func(args)


if __name__ == "__main__":
    main()
