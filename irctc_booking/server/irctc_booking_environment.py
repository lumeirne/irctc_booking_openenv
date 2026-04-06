# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""IRCTC booking environment implementation backed by deterministic simulation."""

from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

from irctc_booking.models import (
    IrctcBookingAction,
    IrctcBookingObservation,
    IrctcBookingState,
)
from irctc_booking.sim.engine import SimEngine
from irctc_booking.sim.grader import EpisodeGrader
from irctc_booking.sim.tasks import GROUND_TRUTHS


class IrctcBookingEnvironment(Environment):
    """OpenEnv-compatible IRCTC task simulation environment."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self) -> None:
        self._engine = SimEngine()
        self._grader = EpisodeGrader(GROUND_TRUTHS)
        self._state: IrctcBookingState | None = None
        self._trajectory: List[Dict[str, Any]] = []

    def reset(
        self,
        seed: int | None = None,
        episode_id: str | None = None,
        **kwargs: Any,
    ) -> IrctcBookingObservation:
        task_id = int(kwargs.get("task_id", 0))
        if task_id not in (0, 1, 2):
            raise ValueError(f"Invalid task_id {task_id}. Allowed values: 0, 1, 2")

        final_seed = int(seed if seed is not None else kwargs.get("seed", 42))
        final_episode_id = episode_id or str(uuid4())

        self._state, observation = self._engine.reset(
            task_id=task_id,
            seed=final_seed,
            episode_id=final_episode_id,
        )
        self._trajectory = []
        observation.metadata["task_id"] = task_id
        observation.metadata["seed"] = final_seed
        return observation

    def step(
        self,
        action: IrctcBookingAction,
        timeout_s: float | None = None,
        **kwargs: Any,
    ) -> IrctcBookingObservation:
        del timeout_s, kwargs

        if self._state is None:
            raise RuntimeError("Environment is not initialized. Call reset() first.")

        observation, reward, done, info = self._engine.step(state=self._state, action=action)

        self._trajectory.append(
            {
                "step": self._state.step_count,
                "action": {
                    "action_type": action.action_type.value,
                    "params": action.params,
                },
                "reward": reward,
                "done": done,
                "info": info,
            }
        )

        if done:
            score, breakdown = self._grader.score(
                trajectory=self._trajectory,
                final_state=self._state,
            )
            observation.metadata["episode_score"] = score
            observation.metadata["score_breakdown"] = breakdown
            observation.metadata["success"] = score >= 0.6

        return observation

    @property
    def state(self) -> State:
        if self._state is None:
            return State(episode_id=None, step_count=0)

        self._state.state_access_count += 1
        payload = self._state.model_dump()
        return State(**payload)
