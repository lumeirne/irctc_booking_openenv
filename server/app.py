"""OpenEnv validator-compatible app shim.

This keeps the runtime implementation in irctc_booking.server.app while exposing
server.app:app at repository root as expected by some OpenEnv tooling.
"""

from irctc_booking.server.app import app


def main(host: str = "0.0.0.0", port: int = 7860):
    """Validator-compatible main entrypoint delegating to package app."""
    from irctc_booking.server.app import main as package_main

    package_main(host=host, port=port)


if __name__ == "__main__":
    main()
