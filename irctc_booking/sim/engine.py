"""Core simulation engine for the IRCTC booking environment."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from irctc_booking.models import (
    ActionTypeEnum,
    AvailabilityLabel,
    BookingStatusEnum,
    IrctcBookingAction,
    IrctcBookingObservation,
    IrctcBookingState,
    QuotaEnum,
    TatkalStatusEnum,
    TrainAvailabilitySummary,
)
from irctc_booking.sim.event_scheduler import EventScheduler, EventType
from irctc_booking.sim.handlers import ACTION_HANDLERS, ActionResult
from irctc_booking.sim.reward import RewardCalculator
from irctc_booking.sim.seat_matrix import SeatMatrixManager
from irctc_booking.sim.tasks import TRAIN_DATABASE, get_task_config


class SimEngine:
    """Runs deterministic reset/step transitions for booking episodes."""

    def __init__(self) -> None:
        self.reward_calculator = RewardCalculator()
        self.event_scheduler: EventScheduler | None = None

    def reset(
        self,
        *,
        task_id: int,
        seed: int,
        episode_id: str,
    ) -> Tuple[IrctcBookingState, IrctcBookingObservation]:
        cfg = get_task_config(task_id)

        seat_matrix: Dict[str, Any] = {}
        for train_no, class_cfg in cfg["seat_configs"].items():
            for class_code, quota_cfg in class_cfg.items():
                key = f"{train_no}:{class_code}"
                seat_matrix[key] = SeatMatrixManager.create_seat_matrix(
                    train_no=train_no,
                    class_code=class_code,
                    quota_configs=quota_cfg,
                )

        train_catalog = {k: TRAIN_DATABASE[k] for k in cfg["trains"]}

        state = IrctcBookingState(
            episode_id=episode_id,
            task_id=task_id,
            seed=seed,
            step_count=0,
            time_step=0,
            passengers=list(cfg["passengers"]),
            selected_train=None,
            selected_class=None,
            applied_quota=None,
            pnr=None,
            booking_status=None,
            waitlist_position=None,
            seat_matrix=seat_matrix,
            train_catalog=train_catalog,
            budget_total=cfg["budget_total"],
            budget_remaining=cfg["budget_total"],
            cancellation_events_log=[],
            last_action=None,
            done=False,
            rule_violations=[],
            total_fare_spent=0.0,
            pnr_registry={},
            route_source=cfg.get("source"),
            route_destination=cfg.get("destination"),
            payment_failure_step=cfg.get("payment_failure_step"),
            payment_failure_train_no=cfg.get("primary_train_no"),
        )

        self.event_scheduler = EventScheduler(task_id=task_id, seed=seed)
        self.event_scheduler.generate_task_events(cfg)

        # Add deterministic background pressure on high-demand windows.
        for matrix in state.seat_matrix.values():
            self.event_scheduler.jitter_extra_contention(
                train_no=matrix.train_no,
                class_code=matrix.class_code,
                quota=QuotaEnum.General,
                demand_steps=[1, 2, 3, 4, 10, 11, 12, 13],
            )

        obs = self._build_observation(state, "Episode initialized. Start by searching trains.", 0.01)
        return state, obs

    def step(
        self,
        *,
        state: IrctcBookingState,
        action: IrctcBookingAction,
    ) -> Tuple[IrctcBookingObservation, float, bool, Dict[str, Any]]:
        if state.done:
            obs = self._build_observation(state, "Episode is already complete.", 0.01)
            obs.done = True
            obs.reward = 0.01
            return obs, 0.01, True, {"error": "Episode already done"}

        previous = state.model_copy(deep=True)
        state.step_count += 1
        state.time_step += 1
        state.last_action = action

        self._apply_events(state)

        handler = ACTION_HANDLERS.get(action.action_type)
        if handler is None:
            action_result = ActionResult(
                success=False,
                message=f"Unsupported action: {action.action_type.value}",
                penalty=-0.05,
            )
            state.rule_violations.append("unsupported action")
        else:
            action_result = handler(state, action.params)

        reward = self.reward_calculator.compute(state, previous, action_result)

        done = False
        if state.step_count >= 20:
            done = True
        elif self._is_goal_achieved(state, action):
            done = True

        state.done = done
        message = action_result.message
        obs = self._build_observation(state, message, reward)

        obs.metadata["action_data"] = action_result.data
        if not action_result.success:
            obs.metadata["error"] = action_result.message

        obs.done = done
        obs.reward = reward

        info: Dict[str, Any] = {
            "step_count": state.step_count,
            "time_step": state.time_step,
            "tatkal_status": self._tatkal_status(state.time_step).value,
        }
        return obs, reward, done, info

    def _is_goal_achieved(self, state: IrctcBookingState, action: IrctcBookingAction) -> bool:
        required_ids = {f"P{i + 1}" for i in range(len(state.passengers))}
        if not required_ids:
            return False

        covered = set()
        for record in state.pnr_registry.values():
            is_confirmed = record.booking_status.value == "CNF"
            is_paid_or_easy = (record.fare_paid > 0.0) or state.task_id == 0
            if is_confirmed and is_paid_or_easy:
                covered.update(record.passengers)

        if covered == required_ids:
            return True

        # Keep easy task short: allow completion right after successful CNF booking.
        if state.task_id == 0 and action.action_type == ActionTypeEnum.book_ticket and state.booking_status and state.booking_status.value == "CNF":
            return True

        return False

    def _apply_events(self, state: IrctcBookingState) -> None:
        if not self.event_scheduler:
            return

        for event in self.event_scheduler.get_events_at(state.time_step):
            key = f"{event.train_no}:{event.class_code}"
            matrix = state.seat_matrix.get(key)
            if not matrix:
                continue

            if event.event_type == EventType.CANCELLATION:
                promoted = SeatMatrixManager.promote_waitlist(matrix, event.quota)
                if promoted:
                    for record in state.pnr_registry.values():
                        if promoted in record.passengers:
                            record.booking_status = BookingStatusEnum.CNF
                            record.waitlist_position = None
                    state.cancellation_events_log.append(
                        {
                            "time_step": state.time_step,
                            "event_type": EventType.CANCELLATION,
                            "train_no": event.train_no,
                            "class_code": event.class_code,
                            "quota": event.quota.value,
                            "promoted_passenger": promoted,
                        }
                    )

            elif event.event_type == EventType.SEAT_CONTENTION:
                reduced = SeatMatrixManager.reduce_seats(
                    matrix,
                    event.quota,
                    int(event.metadata.get("seats_to_reduce", 1)),
                )
                if reduced > 0:
                    state.cancellation_events_log.append(
                        {
                            "time_step": state.time_step,
                            "event_type": EventType.SEAT_CONTENTION,
                            "train_no": event.train_no,
                            "class_code": event.class_code,
                            "quota": event.quota.value,
                            "seats_reduced": reduced,
                        }
                    )

    def _tatkal_status(self, time_step: int) -> TatkalStatusEnum:
        if time_step < 10:
            return TatkalStatusEnum.not_yet_open
        if 10 <= time_step <= 16:
            return TatkalStatusEnum.open
        return TatkalStatusEnum.closed

    def _tatkal_countdown(self, time_step: int) -> int:
        if time_step < 10:
            return 10 - time_step
        if time_step <= 16:
            return 16 - time_step
        return 0

    def _availability_label(self, confirmed: int, waitlist: int) -> AvailabilityLabel:
        if confirmed > 10:
            return AvailabilityLabel.Available
        if confirmed > 0:
            return AvailabilityLabel.Few_Seats
        if waitlist > 0:
            return AvailabilityLabel.WL
        return AvailabilityLabel.Fully_Booked

    def _build_summaries(self, state: IrctcBookingState) -> List[TrainAvailabilitySummary]:
        summaries: List[TrainAvailabilitySummary] = []
        for key, matrix in state.seat_matrix.items():
            train_no, class_code = key.split(":")
            train = state.train_catalog.get(train_no)
            if not train:
                continue

            # Use general quota for coarse summaries when available.
            slot = matrix.quota_allocations.get(QuotaEnum.General)
            if slot is None:
                slot = next(iter(matrix.quota_allocations.values()))

            confirmed = slot.confirmed_seats
            waitlist_count = len(slot.waitlist)
            approx = int(round(confirmed / 5.0) * 5)
            if confirmed > 0 and approx == 0:
                approx = 5

            summaries.append(
                TrainAvailabilitySummary(
                    train_no=train_no,
                    train_name=train.train_name,
                    class_code=class_code,
                    availability_label=self._availability_label(confirmed, waitlist_count),
                    approximate_count=approx,
                )
            )

        summaries.sort(key=lambda s: (s.train_no, s.class_code))
        return summaries

    def _build_observation(
        self,
        state: IrctcBookingState,
        message: str,
        reward: float,
    ) -> IrctcBookingObservation:
        obs = IrctcBookingObservation(
            task_id=state.task_id,
            trains=self._build_summaries(state),
            pnr=state.pnr,
            message=message,
            step_reward=reward,
            steps_remaining=max(0, 20 - state.step_count),
            tatkal_countdown=self._tatkal_countdown(state.time_step),
            booking_status=state.booking_status,
            waitlist_position=state.waitlist_position,
            tatkal_status=self._tatkal_status(state.time_step),
            chart_prepared=state.time_step > 16,
            done=state.done,
            reward=reward,
            metadata={
                "budget_remaining": state.budget_remaining,
                "step_count": state.step_count,
            },
        )
        return obs
