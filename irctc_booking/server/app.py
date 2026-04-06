# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""FastAPI app for the IRCTC booking OpenEnv environment."""

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:  # pragma: no cover
    raise ImportError(
        "openenv is required for the web interface. Install dependencies with '\n    uv sync\n'"
    ) from e

from irctc_booking.models import IrctcBookingAction, IrctcBookingObservation
from irctc_booking.server.irctc_booking_environment import IrctcBookingEnvironment


# Create the app with web interface and README integration
app = create_app(
    IrctcBookingEnvironment,
    IrctcBookingAction,
    IrctcBookingObservation,
    env_name="irctc_booking",
    max_concurrent_envs=4,
)


def main(host: str = "0.0.0.0", port: int = 7860):
    """
    Entry point for local execution and container startup.
    """
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    main(port=args.port)
