"""Reward shaping for the IRCTC booking environment."""

from __future__ import annotations

from typing import Any

from irctc_booking.models import ActionTypeEnum, BookingStatusEnum, IrctcBookingState


class RewardCalculator:
    """Computes dense per-step rewards with partial progress signals."""

    def compute(
        self,
        state: IrctcBookingState,
        previous_state: IrctcBookingState,
        action_result: Any,
    ) -> float:
        base_penalty = float(getattr(action_result, "penalty", 0.0) or 0.0)

        booking_progress = self._booking_progress(state)
        confirmation_probability = self._confirmation_probability(state)
        rule_compliance = self._rule_compliance(state, previous_state)
        cost_efficiency = self._cost_efficiency(state)
        step_efficiency = self._step_efficiency(state)

        reward = (
            0.30 * booking_progress
            + 0.25 * confirmation_probability
            + 0.20 * rule_compliance
            + 0.15 * cost_efficiency
            + 0.10 * step_efficiency
        )

        reward += base_penalty
        reward += self._bonus_or_penalty_adjustment(state, previous_state)
        # Scale dense reward so cumulative episode returns remain within (0, 1).
        # This keeps each step strictly in-range while avoiding task-score overflow
        # when validators aggregate step rewards across an episode.
        scaled_reward = reward / 20.0
        return max(0.01, min(0.045, scaled_reward))

    def _booking_progress(self, state: IrctcBookingState) -> float:
        if not state.passengers:
            return 0.0

        total = len(state.passengers)
        covered = 0
        for record in state.pnr_registry.values():
            if record.booking_status == BookingStatusEnum.CNF:
                covered += len(record.passengers)
            elif (
                record.booking_status == BookingStatusEnum.WL
                and record.waitlist_position is not None
                and record.waitlist_position <= 10
            ):
                covered += len(record.passengers)

        return max(0.0, min(1.0, covered / total))

    def _confirmation_probability(self, state: IrctcBookingState) -> float:
        if not state.pnr_registry:
            return 0.0

        best = 0.0
        for record in state.pnr_registry.values():
            if record.booking_status == BookingStatusEnum.CNF:
                score = 1.0
            elif (
                record.booking_status == BookingStatusEnum.WL
                and record.waitlist_position is not None
            ):
                if record.waitlist_position <= 5:
                    score = 0.7
                elif record.waitlist_position <= 10:
                    score = 0.4
                else:
                    score = 0.1
            else:
                score = 0.1
            best = max(best, score)

        return best

    def _rule_compliance(
        self,
        state: IrctcBookingState,
        previous_state: IrctcBookingState,
    ) -> float:
        added = len(state.rule_violations) - len(previous_state.rule_violations)
        return max(0.0, min(1.0, 1.0 - 0.1 * max(added, 0)))

    def _cost_efficiency(self, state: IrctcBookingState) -> float:
        if state.budget_total <= 0:
            return 1.0
        score = 1.0 - (state.total_fare_spent / state.budget_total)
        return max(0.0, min(1.0, score))

    def _step_efficiency(self, state: IrctcBookingState) -> float:
        score = 1.0 - (state.step_count / 20.0)
        return max(0.0, min(1.0, score))

    def _bonus_or_penalty_adjustment(
        self,
        state: IrctcBookingState,
        previous_state: IrctcBookingState,
    ) -> float:
        adjustment = 0.0

        if (
            state.last_action
            and state.last_action.action_type == ActionTypeEnum.wait_step
            and self._waitlist_promoted(previous_state, state)
        ):
            adjustment += 0.05

        if (
            previous_state.last_action
            and state.last_action
            and previous_state.last_action.action_type == state.last_action.action_type
            and previous_state.last_action.params == state.last_action.params
        ):
            adjustment -= 0.05

        return adjustment

    def _waitlist_promoted(
        self,
        previous_state: IrctcBookingState,
        state: IrctcBookingState,
    ) -> bool:
        for pnr, record in state.pnr_registry.items():
            prev = previous_state.pnr_registry.get(pnr)
            if not prev:
                continue
            if (
                prev.booking_status == BookingStatusEnum.WL
                and record.booking_status == BookingStatusEnum.CNF
            ):
                return True
        return False
