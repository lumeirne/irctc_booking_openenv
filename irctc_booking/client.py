"""Client for the IRCTC booking OpenEnv environment."""

from __future__ import annotations

from typing import Any, Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult

from irctc_booking.models import (
    IrctcBookingAction,
    IrctcBookingObservation,
    IrctcBookingState,
)


class IrctcBookingEnv(
    EnvClient[IrctcBookingAction, IrctcBookingObservation, IrctcBookingState]
):
    """Typed client wrapper for reset/step/state interactions."""

    def _step_payload(self, action: IrctcBookingAction) -> Dict[str, Any]:
        return {
            "action_type": action.action_type.value,
            "params": action.params,
            "metadata": action.metadata,
        }

    def _parse_result(self, payload: Dict[str, Any]) -> StepResult[IrctcBookingObservation]:
        obs_data = payload.get("observation", {})
        observation = IrctcBookingObservation(**obs_data)

        reward = payload.get("reward", observation.reward)
        done = payload.get("done", observation.done)
        return StepResult(observation=observation, reward=reward, done=done)

    def _parse_state(self, payload: Dict[str, Any]) -> IrctcBookingState:
        return IrctcBookingState(**payload)
