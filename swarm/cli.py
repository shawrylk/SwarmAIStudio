"""
Swarm AI Studio Command Line Interface
"""

import sys
import argparse
from swarm.server import run_server
from swarm.config import PORT, HOST

def main():
    parser = argparse.ArgumentParser(
        description="Swarm AI Studio: Task-Aware Dynamic Swarm & Full GitHub Desktop Web Suite"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=PORT,
        help=f"Server port (default: {PORT})"
    )
    parser.add_argument(
        "--host", "-H",
        type=str,
        default=HOST,
        help=f"Server host binding (default: {HOST})"
    )
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)

if __name__ == "__main__":
    main()
