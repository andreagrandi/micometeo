"""Run the demo API server from the command line."""

import os

from micometeo_api.server import run


def main() -> None:
    """Start the server using the host and port from the environment."""
    run(
        host=os.environ.get("MICOMETEO_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("MICOMETEO_API_PORT", "8080")),
    )


if __name__ == "__main__":
    main()
