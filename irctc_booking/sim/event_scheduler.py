"""Deterministic event scheduling for cancellations and seat contention."""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Any, Dict, List

from irctc_booking.models import QuotaEnum


class EventType:
    CANCELLATION = "cancellation"
    SEAT_CONTENTION = "seat_contention"


@dataclass
class Event:
    time_step: int
    event_type: str
    train_no: str
    class_code: str
    quota: QuotaEnum
    metadata: Dict[str, Any] = field(default_factory=dict)


class EventScheduler:
    """Stores events indexed by time step for fast deterministic lookup."""

    def __init__(self, task_id: int, seed: int) -> None:
        self.task_id = task_id
        self.seed = seed
        self._rng = Random(seed)
        self._events_by_timestep: Dict[int, List[Event]] = {}

    def schedule_cancellation_event(
        self,
        *,
        time_step: int,
        train_no: str,
        class_code: str,
        quota: QuotaEnum,
        passenger_id: str | None = None,
    ) -> None:
        event = Event(
            time_step=time_step,
            event_type=EventType.CANCELLATION,
            train_no=train_no,
            class_code=class_code,
            quota=quota,
            metadata={"passenger_id": passenger_id},
        )
        self._events_by_timestep.setdefault(time_step, []).append(event)

    def schedule_seat_contention_event(
        self,
        *,
        time_step: int,
        train_no: str,
        class_code: str,
        quota: QuotaEnum,
        seats_to_reduce: int,
    ) -> None:
        event = Event(
            time_step=time_step,
            event_type=EventType.SEAT_CONTENTION,
            train_no=train_no,
            class_code=class_code,
            quota=quota,
            metadata={"seats_to_reduce": seats_to_reduce},
        )
        self._events_by_timestep.setdefault(time_step, []).append(event)

    def get_events_at(self, time_step: int) -> List[Event]:
        return self._events_by_timestep.get(time_step, [])

    def generate_task_events(self, task_config: Dict[str, Any]) -> None:
        for event in task_config.get("cancellation_events", []):
            self.schedule_cancellation_event(
                time_step=event["time_step"],
                train_no=event["train_no"],
                class_code=event["class_code"],
                quota=event["quota"],
                passenger_id=event.get("passenger_id"),
            )

        for event in task_config.get("contention_events", []):
            self.schedule_seat_contention_event(
                time_step=event["time_step"],
                train_no=event["train_no"],
                class_code=event["class_code"],
                quota=event["quota"],
                seats_to_reduce=event["seats_to_reduce"],
            )

    def jitter_extra_contention(
        self,
        train_no: str,
        class_code: str,
        quota: QuotaEnum,
        demand_steps: List[int],
    ) -> None:
        """Adds deterministic pseudo-random contention for realism."""
        for step in demand_steps:
            seats = self._rng.randint(0, 1)
            if seats > 0:
                self.schedule_seat_contention_event(
                    time_step=step,
                    train_no=train_no,
                    class_code=class_code,
                    quota=quota,
                    seats_to_reduce=seats,
                )
